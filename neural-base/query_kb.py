#!/usr/bin/env python3
"""
query_kb.py — consulta semantica a base neural do Project Core-Engine.

Uso:
  python query_kb.py "como evitar loop infinito de automacao?"
  python query_kb.py "qual repo usar no modulo de social media?" -k 3
"""
import argparse
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
STORE = HERE / "vectorstore"
MODEL_NAME = "all-MiniLM-L6-v2"
COLLECTION = "core_engine"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question", help="pergunta em linguagem natural")
    ap.add_argument("-k", type=int, default=5, help="numero de trechos (default 5)")
    args = ap.parse_args()

    if not STORE.exists():
        sys.exit("Base nao construida. Rode antes: python build_vector_index.py")
    try:
        from sentence_transformers import SentenceTransformer
        import chromadb
    except ImportError:
        sys.exit("Dependencias faltando. Rode: pip install -r requirements.txt")

    model = SentenceTransformer(MODEL_NAME)
    q = model.encode([args.question], normalize_embeddings=True).tolist()

    client = chromadb.PersistentClient(path=str(STORE))
    coll = client.get_collection(COLLECTION)
    res = coll.query(query_embeddings=q, n_results=args.k)

    docs = res["documents"][0]
    metas = res["metadatas"][0]
    dists = res.get("distances", [[None] * len(docs)])[0]

    print(f"\nPergunta: {args.question}\n" + "=" * 70)
    for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists), 1):
        src = meta.get("section") or meta.get("module") or meta.get("source", "")
        score = f"{1 - dist:.3f}" if dist is not None else "?"
        print(f"\n[{i}] (sim {score}) fonte: {src}")
        print("-" * 70)
        print(doc.strip()[:1000])
    print("\n" + "=" * 70)
    print("Dica: passe esses trechos como contexto para um LLM gerar a resposta final.")


if __name__ == "__main__":
    main()
