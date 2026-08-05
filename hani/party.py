"""
A / B 당사자 규칙 — **이 파일이 단일 진실입니다.**

════════════════════════════════════════════════════════════════
결정 사항 (2026-08, 1번 제안 → 팀 확인 필요)

  ① KB 는 원문 그대로 둡니다.
     base_ratio 의 A/B 는 **인정기준 PDF에 인쇄된 그대로**입니다.
     보1 이 {a:70, b:30} 이면 A는 보행자, B는 자동차입니다.
     KB 단계에서 뒤집지 않습니다 — 뒤집으면 원문 페이지와 대조가 불가능해집니다.

  ② 뒤집기는 **이 파일의 to_consultant_view() 한 곳에서만** 합니다.
     API·화면·계산 어디서도 따로 뒤집지 마세요.
     두 곳에서 뒤집으면 원위치로 돌아와 조용히 틀립니다.

  ③ "상담자가 A인가 B인가"는 **사용자에게 물어봅니다.**
     화면에서 role_a / role_b 를 보여주고 고르게 하세요.
     예) 보1 → "보행자 쪽이신가요, 자동차 쪽이신가요?"
════════════════════════════════════════════════════════════════

문서·챕터별 A/B 역할 (원문 확인 완료)

  MAIN2023 보N   A = 보행자   B = 자동차      ← 유일하게 A가 비자동차
  MAIN2023 차N   A = 자동차   B = 자동차
  MAIN2023 거N   A = 자전거   B = 자동차
  PM2021         A = PM       B = 자동차
  ROUND2025      A = 레드차량 B = 블루차량

심의사례(CASES)는 별개입니다. A가 청구인 사례도, 피청구인 사례도 있어서
`a_party` / `b_party` 필드에 사례마다 기록해 두었습니다. 그 값을 그대로 쓰세요.
"""

from __future__ import annotations

from typing import Literal

Side = Literal["A", "B"]

# (source_id, 도표번호 접두어) → (A 역할, B 역할)
ROLES: dict[tuple[str, str], tuple[str, str]] = {
    ("MAIN2023", "보"): ("보행자", "자동차"),
    ("MAIN2023", "차"): ("자동차", "자동차"),
    ("MAIN2023", "거"): ("자전거", "자동차"),
    ("PM2021", ""): ("PM(개인형 이동장치)", "자동차"),
    ("ROUND2025", ""): ("레드 차량", "블루 차량"),
}

DEFAULT_ROLES = ("A 당사자", "B 당사자")


def roles_of(source_id: str, diagram_no: str) -> tuple[str, str]:
    """도표의 A/B가 각각 무엇인지 돌려줍니다."""
    if source_id == "MAIN2023":
        return ROLES.get(("MAIN2023", diagram_no[:1]), DEFAULT_ROLES)
    return ROLES.get((source_id, ""), DEFAULT_ROLES)


def to_consultant_view(payload: dict, consultant_side: Side = "A") -> dict:
    """
    KB payload 를 **상담자 기준**으로 변환합니다.

        consultant_side="A"  원문 그대로 (나 = A)
        consultant_side="B"  좌우를 뒤집음 (나 = B)

    반환값의 `나`/`상대` 를 화면에 그대로 쓰세요.
    원본 `base_ratio` 는 그대로 남겨 두어 원문 대조가 가능합니다.

    ⚠️ 여기서만 뒤집습니다. 호출한 쪽에서 또 뒤집지 마세요.
    """
    role_a, role_b = roles_of(payload.get("source_id", ""), payload.get("diagram_no", ""))
    base = payload.get("base_ratio")

    if consultant_side == "A":
        나_역할, 상대_역할 = role_a, role_b
        기본 = dict(base) if base else None
        수정 = list(payload.get("modifiers", []))
    else:
        나_역할, 상대_역할 = role_b, role_a
        기본 = {"a": base["b"], "b": base["a"]} if base else None
        # 수정요소의 대상도 함께 뒤집어야 계산이 맞습니다.
        수정 = [
            {**m, "target": ("B" if m["target"] == "A" else "A")}
            for m in payload.get("modifiers", [])
        ]

    return {
        "상담자_기준": consultant_side,
        "나_역할": 나_역할,
        "상대_역할": 상대_역할,
        "기본과실": 기본,            # {"a": 나, "b": 상대}
        "수정요소": 수정,            # target A = 나, B = 상대
        "원본_기본과실": base,       # 원문 대조용. 화면에 쓰지 마세요.
        "원본_A역할": role_a,
        "원본_B역할": role_b,
    }


def describe(payload: dict) -> str:
    """화면에 '누가 A인지' 안내할 문구."""
    a, b = roles_of(payload.get("source_id", ""), payload.get("diagram_no", ""))
    if a == b:
        return f"이 기준은 {a} 두 대 사이의 사고입니다. 어느 쪽이 본인인지 선택하세요."
    return f"이 기준에서 A는 {a}, B는 {b}입니다. 본인이 어느 쪽인지 선택하세요."