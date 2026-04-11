import argparse
import json
import uuid
from pathlib import Path
from typing import Dict, Iterable, List

import numpy as np
import pandas as pd
from docx import Document
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

try:
    import chromadb
except ModuleNotFoundError:
    chromadb = None

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DEFAULT_DATA_DIRS = [PROJECT_ROOT / "data", PROJECT_ROOT]
CHROMA_DIR = BASE_DIR / "chroma_db"
LOCAL_INDEX_DIR = BASE_DIR / "local_index"
COLLECTION_NAME = "moto3_docs"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

SUPPORTED_EXTENSIONS = {".csv", ".docx", ".xlsx", ".xls", ".pdf", ".txt", ".md"}


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> List[str]:
    text = text.replace("\r", "\n").strip()
    if not text:
        return []
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def read_docx(path: Path) -> str:
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def read_xlsx(path: Path) -> Dict[str, str]:
    # Returns one text block per sheet to preserve some structure.
    sheets = pd.read_excel(path, sheet_name=None)
    out: Dict[str, str] = {}
    for sheet_name, df in sheets.items():
        csv_text = df.to_csv(index=False)
        out[sheet_name] = csv_text
    return out


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def iter_supported_files(data_dirs: Iterable[Path]) -> Iterable[Path]:
    seen = set()
    for root in data_dirs:
        if not root.exists() or not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            # Avoid indexing code or env files from repo root.
            if path.name.startswith("."):
                continue
            if path.parent.name == "chroma_db":
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            yield path


def load_documents(data_dirs: List[Path], chunk_size: int, overlap: int) -> List[dict]:
    docs = []
    for path in iter_supported_files(data_dirs):
        suffix = path.suffix.lower()
        rel_name = str(path.relative_to(PROJECT_ROOT)) if path.is_relative_to(PROJECT_ROOT) else path.name

        if suffix == ".docx":
            text = read_docx(path)
            for i, chunk in enumerate(chunk_text(text, chunk_size, overlap)):
                docs.append(
                    {
                        "id": str(uuid.uuid4()),
                        "text": chunk,
                        "source": rel_name,
                        "chunk": i,
                        "sheet": "",
                        "doc_type": "docx",
                    }
                )

        elif suffix in {".xlsx", ".xls"}:
            sheet_map = read_xlsx(path)
            for sheet_name, sheet_text in sheet_map.items():
                for i, chunk in enumerate(chunk_text(sheet_text, chunk_size, overlap)):
                    docs.append(
                        {
                            "id": str(uuid.uuid4()),
                            "text": chunk,
                            "source": rel_name,
                            "chunk": i,
                            "sheet": sheet_name,
                            "doc_type": "xlsx",
                        }
                    )

        elif suffix == ".pdf":
            text = read_pdf(path)
            for i, chunk in enumerate(chunk_text(text, chunk_size, overlap)):
                docs.append(
                    {
                        "id": str(uuid.uuid4()),
                        "text": chunk,
                        "source": rel_name,
                        "chunk": i,
                        "sheet": "",
                        "doc_type": "pdf",
                    }
                )

        else:
            if suffix == ".csv":
                text = pd.read_csv(path).to_csv(index=False)
                doc_type = "csv"
            else:
                text = read_text_file(path)
                doc_type = suffix.lstrip(".")
            for i, chunk in enumerate(chunk_text(text, chunk_size, overlap)):
                docs.append(
                    {
                        "id": str(uuid.uuid4()),
                        "text": chunk,
                        "source": rel_name,
                        "chunk": i,
                        "sheet": "",
                        "doc_type": doc_type,
                    }
                )

    return docs


def build_index(collection_name: str, chunk_size: int, overlap: int, rebuild: bool) -> None:
    data_dirs = [p for p in DEFAULT_DATA_DIRS if p.exists()]
    docs = load_documents(data_dirs, chunk_size, overlap)
    if not docs:
        raise RuntimeError("No supported documents found to index.")

    embedder = SentenceTransformer(EMBED_MODEL)
    texts = [d["text"] for d in docs]
    ids = [d["id"] for d in docs]
    metas = [
        {
            "source": d["source"],
            "chunk": d["chunk"],
            "sheet": d["sheet"],
            "doc_type": d["doc_type"],
        }
        for d in docs
    ]

    embeddings = embedder.encode(texts, normalize_embeddings=True, batch_size=64)

    # Always persist a local fallback index to avoid hard dependency on chromadb.
    LOCAL_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.save(LOCAL_INDEX_DIR / f"{collection_name}_embeddings.npy", embeddings)
    with (LOCAL_INDEX_DIR / f"{collection_name}_records.jsonl").open("w", encoding="utf-8") as f:
        for doc_id, text, meta in zip(ids, texts, metas):
            f.write(
                json.dumps(
                    {
                        "id": doc_id,
                        "text": text,
                        "meta": meta,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    used_backends = ["local_index"]

    if chromadb is not None:
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        if rebuild:
            try:
                client.delete_collection(collection_name)
            except Exception:
                pass

        collection = client.get_or_create_collection(name=collection_name)
        collection.add(ids=ids, documents=texts, metadatas=metas, embeddings=embeddings.tolist())
        used_backends.append("chroma")

    print(f"Indexed {len(docs)} chunks in '{collection_name}'.")
    print(f"Backends: {', '.join(used_backends)}")
    if chromadb is not None:
        print(f"Chroma path: {CHROMA_DIR}")
    print(f"Local index path: {LOCAL_INDEX_DIR}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build local Chroma index for Moto3 documents")
    parser.add_argument("--collection", default=COLLECTION_NAME, help="Chroma collection name")
    parser.add_argument("--chunk-size", type=int, default=900, help="Chunk size in characters")
    parser.add_argument("--overlap", type=int, default=150, help="Chunk overlap in characters")
    parser.add_argument("--no-rebuild", action="store_true", help="Do not delete existing collection")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_index(
        collection_name=args.collection,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
        rebuild=not args.no_rebuild,
    )


if __name__ == "__main__":
    main()
