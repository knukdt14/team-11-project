"""
벡터 인덱스 생성 (Chroma) — 1회성 오프라인 스크립트.

  python build_vector
  EMBEDDING_BACKEND=st python build_vector   # 모델 사용 시

⚠️ 인덱스에는 **어떤 백엔드로 만들었는지**를 함께 기록합니다.
   검색 시 백엔드가 다르면 경고합니다 (섞이면 결과가 무의미해집니다).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHUNKS = ROOT / "data" / "processed" / "chunks.jsonl"
VECTOR_DIR = ROOT / "data" / "processed" / "vector_index"
PAYLOAD = ROOT / "data" / "processed" / "payloads.json"
COLLECTION = "fault_ratio"


def main() -> None:
    if not CHUNKS.exists():
        raise SystemExit("chunks.jsonl 이 없습니다. 먼저 `python build_chunks`")

    import chromadb

    from embedder import build_embedder

    chunks = [json.loads(l) for l in CHUNKS.open(encoding="utf-8") if l.strip()]
    emb = build_embedder()
    print(f"임베딩 백엔드: {emb.name} (dim={emb.dim})")
    print(f"{len(chunks)}건 임베딩 중…")

    vectors = emb.encode([c["text"] for c in chunks])

    VECTOR_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(VECTOR_DIR))
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    col = client.create_collection(
        COLLECTION,
        metadata={"hnsw:space": "cosine", "embedder": emb.name, "dim": emb.dim},
    )

    col.add(
        ids=[c["chunk_id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        embeddings=vectors,
        metadatas=[c["meta"] for c in chunks],
    )

    # payloads.json 은 build_chunks.py 가 만듭니다(부모 단위). 여기선 건드리지 않습니다.
    print(f"완료: {VECTOR_DIR} | {col.count()}건")


if __name__ == "__main__":
    main()