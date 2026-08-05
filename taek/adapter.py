"""
검색 결과 → API 계약 변환 (2번 → 3번 인도 지점).

`Searcher` 가 내는 `Hit` 은 검색 내부 구조(`chunk_id`·`score`·`payload`)입니다.
README §11 의 `/consult` 응답은 한글 필드(`도표번호`·`기본과실`·`수정요소`)입니다.
그 사이를 여기서 한 번만 변환합니다.

⚠️ **A/B 를 여기서 뒤집지 마세요.**
   뒤집기는 `hani.party.to_consultant_view()` 한 곳에서만 합니다.
   두 곳에서 뒤집으면 원위치로 돌아와 조용히 틀립니다.
   이 모듈은 `consultant_side` 를 받아 `to_consultant_view()` 에 **넘기기만** 합니다.

⚠️ **심의사례의 A/B 는 도표의 A/B 와 다릅니다.**
   도표: A = 앞 당사자(보행자·자전거·PM 등), B = 자동차
   사례: A = 청구인, B = 피청구인  ← 사건마다 뒤바뀝니다
   그래서 사례는 `to_consultant_view()` 에 절대 넣지 않고, 원문 표기를 그대로 보여줍니다.

사용
    from taek.search import Searcher
    from taek.adapter import to_consult_payload, to_case_cards

    s = Searcher()
    hits = s.search(질문, mode="hybrid", reject=True, expand=True)
    payload = to_consult_payload(hits, consultant_side="A")
    if payload["경고"]:
        ...  # 해당 기준 없음
"""

from __future__ import annotations

from typing import Any

try:
    from .search import Hit
except ImportError:
    from search import Hit


def _diagram(h: Hit, consultant_side: str) -> dict[str, Any]:
    """도표 Hit 하나를 상담자 관점으로 변환합니다."""
    from hani.party import to_consultant_view      # 뒤집기는 여기 한 곳에서만

    p = h.payload
    view = to_consultant_view(p, consultant_side=consultant_side)
    기본 = view.get("기본과실") or {}
    return {
        "도표번호": p.get("diagram_no"),
        "제목": p.get("title", ""),
        "출처": p.get("source_id"),
        "나_역할": view.get("나_역할"),
        "상대_역할": view.get("상대_역할"),
        "기본과실": {"A": 기본.get("a"), "B": 기본.get("b")} if 기본 else None,
        "수정요소": [
            {"id": f"{p.get('source_id')}-{p.get('diagram_no')}-M{i:02d}",
             "조건": m.get("name"), "대상": m.get("target"), "값": m.get("adjustment"),
             "적용됨": False, "근거": f"인정기준 p.{p.get('source_page')}"}
            for i, m in enumerate((view.get("수정요소") or []), 1)
        ],
        "해설": p.get("base_ratio_explanation", ""),
        "사고상황": p.get("accident_description", ""),
        "사고유형": {
            "대": "보행자 대 자동차" if p.get("diagram_no", "").startswith("보") else
                  "자전거 대 자동차" if p.get("diagram_no", "").startswith("거") else
                  "PM 대 자동차" if p.get("source_id") == "PM2021" else "차 대 차",
            "중": p.get("section", "") or "",
            "소": p.get("title", "") or "",
        },
        "판례": p.get("precedents", []),
        "법조항": p.get("laws", []),
        "image_url": f"/images/{p.get('source_id')}-{p.get('diagram_no')}.png" if p.get("image_path") else None,
        "pdf_page": p.get("source_page"),
        "검색점수": h.score,
        "매칭면": h.facet,
        # 파싱 검수가 필요한 도표는 화면에서 낮은 신뢰도로 표시하세요.
        "검수필요": bool(p.get("parse_flags")),
    }


def to_consult_payload(
    hits: list[Hit],
    consultant_side: str = "A",
    top_k: int = 3,
) -> dict[str, Any]:
    """
    검색 결과를 `/consult` 응답의 **검색 부분**으로 변환합니다.

    ⚠️ 과실비율 **계산은 하지 않습니다.** 숫자는 3번의 `apply_modifiers()` 만 만듭니다.
       여기서는 기본과실과 수정요소 목록까지만 넘깁니다.

    `hits` 가 비어 있으면 (= `search(reject=True)` 가 거절) 경고를 담아 반환합니다.
    """
    if not hits:
        return {
            "사고유형": None, "도표번호": None, "기본과실": None,
            "수정요소": [], "후보": [], "유사사례": [],
            "최종과실": None,
            "경고": "해당 기준을 찾을 수 없습니다",
            "되묻기": [
                "사고 장소가 교차로였나요, 아니면 직선도로였나요?",
                "신호등이 있는 곳이었나요?",
                "본인 차량은 직진 중이었나요, 회전 중이었나요?",
            ],
        }

    도표들 = [h for h in hits if h.kind == "standard"]
    if not 도표들:
        return to_consult_payload([], consultant_side)

    최상위 = _diagram(도표들[0], consultant_side)
    return {
        **최상위,
        "후보": [_diagram(h, consultant_side) for h in 도표들[1:top_k]],
        "최종과실": None,        # ← 3번의 apply_modifiers() 가 채웁니다
        "경고": None,
        "되묻기": [],
    }


def to_case_cards(hits: list[Hit], top_k: int = 3) -> list[dict[str, Any]]:
    """
    심의사례를 화면 표시용으로 변환합니다.

    ⚠️ **참고용입니다. 계산에 쓰지 마세요.**
       · 기본비율 ≠ 결정비율인 사례가 226건 중 90건입니다.
       · A 가 청구인지 피청구인지 사례마다 뒤바뀝니다 → 원문 표기를 그대로 노출합니다.
       · 현행 도표와의 매핑이 아직 전부 `review_required` 입니다.

    4번(프론트)은 반드시 `참고용` 배지와 `주의` 문구를 함께 띄워 주세요.
    """
    out = []
    for h in hits[:top_k]:
        if h.kind != "case":
            continue
        p = h.payload
        기본, 결정 = p.get("base_ratio"), p.get("decision_ratio")
        out.append({
            "심의번호": p.get("review_no"),
            "제목": p.get("title", ""),
            # 도표의 A/B 와 다릅니다. 뒤집지 말고 원문 그대로 보여주세요.
            "A_당사자": p.get("a_party"),
            "B_당사자": p.get("b_party"),
            "기본비율": {"A": 기본["a"], "B": 기본["b"]} if 기본 else None,
            "결정비율": {"A": 결정["a"], "B": 결정["b"]} if 결정 else None,
            "비율_달라짐": bool(기본 and 결정 and 기본 != 결정),
            "사고상황": p.get("accident_description", ""),
            "결정이유": p.get("decision_reason", ""),
            "pdf_page": p.get("source_page"),
            "참고용": True,
            "주의": "심의사례는 참고용입니다. 과실비율 계산에 사용하지 마세요. "
                    "A/B 는 청구인·피청구인이며 도표의 A/B 와 다릅니다.",
        })
    return out


def to_law_cards(hits: list[Hit]) -> list[dict[str, Any]]:
    """`Searcher.laws_for()` 결과를 화면 표시용으로."""
    return [
        {"조": h.payload.get("article_no"), "제목": h.payload.get("title", ""),
         "내용": h.payload.get("text", ""), "시행중": h.payload.get("in_force", True)}
        for h in hits if h.kind == "law"
    ]
