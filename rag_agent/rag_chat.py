import argparse
import os
from pathlib import Path
from typing import Dict, List, Tuple

import chromadb
from dotenv import load_dotenv
from huggingface_hub import InferenceClient
from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).resolve().parent
CHROMA_DIR = BASE_DIR / "chroma_db"
COLLECTION_NAME = "moto3_docs"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
GEN_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"

load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")


class RagAssistant:
    def __init__(self, collection_name: str, gen_model: str, hf_token: str | None):
        self.collection_name = collection_name
        self.gen_model = gen_model
        self.hf_token = hf_token

        self.embedder = SentenceTransformer(EMBED_MODEL)
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.collection = self.client.get_collection(collection_name)
        self.inference = InferenceClient(api_key=hf_token)

    def retrieve(self, query: str, k: int = 4) -> List[Tuple[str, Dict, float]]:
        q_emb = self.embedder.encode([query], normalize_embeddings=True).tolist()[0]
        result = self.collection.query(query_embeddings=[q_emb], n_results=k)

        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        return list(zip(docs, metas, distances))

    @staticmethod
    def build_prompt(question: str, contexts: List[Tuple[str, Dict, float]]) -> str:
        blocks = []
        for i, (doc, meta, dist) in enumerate(contexts, start=1):
            source = meta.get("source", "unknown")
            chunk = meta.get("chunk", "?")
            sheet = meta.get("sheet", "")
            sheet_txt = f" | sheet {sheet}" if sheet else ""
            blocks.append(
                f"[Fuente {i}: {source}{sheet_txt} | chunk {chunk} | distancia {dist:.4f}]\n{doc}"
            )

        joined_context = "\n\n".join(blocks)
        return (
            "Eres un asistente tecnico de ingenieria Moto3.\n"
            "Responde unicamente con base en el contexto recuperado.\n"
            "Si falta informacion, dilo claramente.\n"
            "Cita fuentes al final con formato [Fuente X].\n\n"
            f"Contexto:\n{joined_context}\n\n"
            f"Pregunta:\n{question}"
        )

    def answer(self, question: str, k: int, temperature: float, max_tokens: int) -> str:
        payload = self.answer_with_sources(
            question=question,
            k=k,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        lines = [
            payload["answer"],
            "",
            "Fuentes recuperadas:",
            *payload["source_lines"],
        ]
        return "\n".join(lines)

    def answer_with_sources(
        self,
        question: str,
        k: int,
        temperature: float,
        max_tokens: int,
    ) -> Dict:
        contexts = self.retrieve(question, k=k)
        prompt = self.build_prompt(question, contexts)

        response = self.inference.chat_completion(
            model=self.gen_model,
            messages=[
                {
                    "role": "system",
                    "content": "Responde de forma tecnica, breve y fiel al contexto.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        answer_text = response.choices[0].message.content

        source_lines = []
        source_items = []
        for i, (_, meta, dist) in enumerate(contexts, start=1):
            source = meta.get("source", "unknown")
            chunk = meta.get("chunk", "?")
            sheet = meta.get("sheet", "")
            suffix = f" (sheet: {sheet})" if sheet else ""
            source_lines.append(f"[Fuente {i}] {source}{suffix} | chunk {chunk}")
            source_items.append(
                {
                    "index": i,
                    "source": source,
                    "chunk": chunk,
                    "sheet": sheet,
                    "distance": dist,
                }
            )

        return {
            "answer": answer_text,
            "source_lines": source_lines,
            "sources": source_items,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chat RAG against local Moto3 Chroma index")
    parser.add_argument("--collection", default=COLLECTION_NAME, help="Chroma collection name")
    parser.add_argument("--model", default=GEN_MODEL, help="HF model id")
    parser.add_argument("--k", type=int, default=4, help="Top-k retrieved chunks")
    parser.add_argument("--temperature", type=float, default=0.2, help="Generation temperature")
    parser.add_argument("--max-tokens", type=int, default=500, help="Max generated tokens")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        raise RuntimeError("HF_TOKEN is missing. Set it in rag_agent/.env or environment.")

    assistant = RagAssistant(
        collection_name=args.collection,
        gen_model=args.model,
        hf_token=hf_token,
    )

    print("RAG chat ready. Type 'salir' to exit.")
    while True:
        q = input("\nPregunta> ").strip()
        if q.lower() in {"exit", "quit", "salir"}:
            break
        if not q:
            continue

        try:
            result = assistant.answer(
                q,
                k=args.k,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
            print("\nRespuesta:\n")
            print(result)
        except Exception as exc:
            print(f"\nError: {exc}")


if __name__ == "__main__":
    main()
