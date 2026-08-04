"""
인덱스 신선도 확인 — chunks.jsonl 지문(fingerprint).

⚠️ 청킹이나 파싱을 고치면 `chunks.jsonl` 은 바뀌는데 `vector_index/` 는 그대로입니다.
   그러면 **문서 내용과 벡터가 어긋난 채로 검색이 조용히 돌아갑니다.**
   오류가 안 나서 알아채기 어렵고, 검색 품질만 이유 없이 떨어집니다.

   그래서 인덱스를 만들 때 chunks.jsonl 의 해시를 함께 저장하고,
   검색할 때 대조해 다르면 경고합니다.

   (임베딩 모델 불일치는 search.py 가 별도로 중단시킵니다. 이건 '내용' 쪽 검사입니다.)
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def chunks_fingerprint(path: Path) -> str:
    """chunks.jsonl 의 내용 해시. 파일이 없으면 빈 문자열."""
    if not path.exists():
        return ""
    h = hashlib.blake2b(digest_size=8)
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()
