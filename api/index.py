import os
from flask import Flask, jsonify, redirect

app = Flask(__name__)


def _streamlit_url() -> str:
    return os.getenv("STREAMLIT_PUBLIC_URL", "").strip()


@app.get("/")
def home():
    target = _streamlit_url()
    if not target:
        return (
            "STREAMLIT_PUBLIC_URL no esta configurada. "
            "Configura esta variable en Vercel con la URL publica de Streamlit.",
            503,
        )
    return redirect(target, code=302)


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "vercel-flask-gateway"})
