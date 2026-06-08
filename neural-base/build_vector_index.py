#!/usr/bin/env python3
"""
build_vector_index.py — constroi a base neural (indice vetorial local) do Project Core-Engine.

Fluxo:
  1. carrega facts.jsonl (fatos atomicos) + chunka 00_MASTER_KNOWLEDGE_BASE.md por secao
  2. gera embeddings localmente com sentence-transformers (all-MiniLM-L6-v2, ~80MB, ARM-friendly)
  3. persiste num store Chroma em ./vectorstore

Rodar (no seu box, NAO neste sandbox — precisa baixar o modelo na 1a vez):
  pip install -r requirements.txt
  python build_vector_index.py

Depois consulte com:  python query_kb.py "como evitar loop de automacao?"

100% offline apos o primeiro download do modelo. Sem chamadas a APIs pagas.
"""
import json
import re
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
MASTER = HERE / "00_MASTER_KNOWLEDGE_BASE.md"
FACTS = HERE / "facts.jsonl"
STORE = HERE / "vectorstore"
MODEL_NAME = "all-MiniLM-L6-v2"
COLLECTION = "core_engine"


def load_facts():
    """Cada fato JSONL vira um chunk com metadados ricos."""
    chunks = []
    if not FACTS.exists():
        return chunks
    for line in FACTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        f = json.loads(line)
        chunks.append({
            "id": f["id"],
            "text": f["text"],
            "meta": {
                "source": "facts.jsonl",
                "module": f.get("module", ""),
                "kind": f.get("type", ""),
                "tags": ",".join(f.get("tags", [])),
            },
        })
    return chunks


def chunk_markdown(min_len=120, max_len=1800):
    """Quebra o master por cabecalhos (##/###); junta trechos curtos, parte trechos longos."""
    if not MASTER.exists():
        return []
    text = MASTER.read_text(encoding="utf-8")
    # divide preservando o cabecalho como prefixo do bloco
    parts = re.split(r"(?m)^(#{1,3} .+)$", text)
    blocks, current_head = [], "PREAMBULO"
    # parts intercala [pre, head, body, head, body, ...]
    buf = parts[0]
    if buf.strip():
        blocks.append((current_head, buf.strip()))
    for i in range(1, len(parts), 2):
        head = parts[i].strip("# ").strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        body = body.strip()
        if body:
            blocks.append((head, body))

    chunks, n = [], 0
    for head, body in blocks:
        if len(body) < min_len:
            # trechos muito curtos ainda viram chunk (titulos com listas)
            pass
        # parte blocos longos em janelas por paragrafo
        if len(body) > max_len:
            paras, window = body.split("\n\n"), ""
            for p in paras:
                if len(window) + len(p) > max_len and window:
                    n += 1
                    chunks.append({"id": f"MD-{n:03d}", "text": f"[{head}]\n{window.strip()}",
                                   "meta": {"source": "master", "section": head}})
                    window = ""
                window += p + "\n\n"
            if window.strip():
                n += 1
                chunks.append({"id": f"MD-{n:03d}", "text": f"[{head}]\n{window.strip()}",
                               "meta": {"source": "master", "section": head}})
        else:
            n += 1
            chunks.append({"id": f"MD-{n:03d}", "text": f"[{head}]\n{body}",
                           "meta": {"source": "master", "section": head}})
    return chunks


def main():
    try:
        from sentence_transformers import SentenceTransformer
        import chromadb
    except ImportError:
        sys.exit("Dependencias faltando. Rode: pip install -r requirements.txt")

    chunks = load_facts() + chunk_markdown()
    if not chunks:
        sys.exit("Nenhum chunk gerado — confira facts.jsonl e 00_MASTER_KNOWLEDGE_BASE.md.")
    print(f"[1/3] {len(chunks)} chunks carregados (fatos + master).")

    print(f"[2/3] gerando embeddings com {MODEL_NAME} ...")
    model = SentenceTransformer(MODEL_NAME)
    embeddings = model.encode([c["text"] for c in chunks],
                              show_progress_bar=True, normalize_embeddings=True).tolist()

    print(f"[3/3] persistindo em {STORE} ...")
    client = chromadb.PersistentClient(path=str(STORE))
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    coll = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    coll.add(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        embeddings=embeddings,
        metadatas=[c["meta"] for c in chunks],
    )
    print(f"OK — base neural com {len(chunks)} vetores pronta em {STORE}.")
    print('Consulte:  python query_kb.py "sua pergunta aqui"')


if __name__ == "__main__":
    main()
