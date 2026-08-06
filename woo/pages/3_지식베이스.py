"""지식베이스 탐색 — 상담 흐름과 별개로 전체 KB를 자유 검색/필터링합니다."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from woo.components.kb_data import SOURCE_LABELS, source_label, standards  # noqa: E402
from woo.components.widgets import hero, inject_css, top_nav  # noqa: E402

st.set_page_config(page_title="지식베이스 · 과실비율", page_icon="📚", layout="wide")
inject_css()
top_nav("kb")
hero("📚 지식베이스 탐색", "상담 없이 도표·판례·법령을 직접 검색해볼 수 있습니다.")


@st.cache_resource(show_spinner="검색 엔진 로딩 중...")
def _searcher():
    from taek.search import Searcher

    return Searcher()


@st.dialog("도표 상세", width="large")
def _kb_show_detail(s: dict) -> None:
    """카드 클릭 시 뜨는 상세 모달 (목업의 KB 카드 클릭→모달과 동일한 동작)."""
    r = s.get("base_ratio") or {}
    st.markdown(f"### {s.get('diagram_no', '')} · {s.get('title', '')}")
    st.caption(f"{source_label(s.get('source_id', ''))} · p.{s.get('source_page', '?')}")

    img_path = Path(__file__).resolve().parent.parent.parent / "hani" / "data" / (s.get("image_path") or "")
    if s.get("image_path") and img_path.exists():
        st.image(str(img_path))

    st.markdown(f"**기본과실**: A {r.get('a', '?')}% : B {r.get('b', '?')}%")
    if s.get("accident_description"):
        st.markdown(f"**사고 상황**\n\n{s['accident_description']}")
    if s.get("modifiers"):
        st.markdown("**수정요소**")
        for m in s["modifiers"]:
            st.caption(f"- {m['name']} ({'+' if m['adjustment'] >= 0 else ''}{m['adjustment']}, 대상 {m['target']})")
    if s.get("laws"):
        st.caption("관련 법령: " + ", ".join(s["laws"]))
    if s.get("precedents"):
        st.caption("참조 판례: " + ", ".join(s["precedents"]))
    st.markdown('<span class="fr-badge fr-badge-official">공식 기준</span>', unsafe_allow_html=True)


with st.container(border=True):
    c1, c2 = st.columns([3, 1])
    with c1:
        query = st.text_input("검색어", placeholder="예) 후방추돌, 회전교차로, 전동킥보드 …")
    with c2:
        source_id = st.selectbox(
            "문서", ["전체", *SOURCE_LABELS.keys()], format_func=lambda s: s if s == "전체" else source_label(s)
        )
    kind = st.radio("종류", ["기준 도표", "심의사례", "법령"], horizontal=True)
    go = st.button("🔎 검색", type="primary")

_KIND_MAP = {"기준 도표": "standard", "심의사례": "case", "법령": "law"}

if go and query.strip():
    searcher = _searcher()
    with st.spinner("검색 중..."):
        hits = searcher.search(
            query.strip(),
            top_k=15,
            kind=_KIND_MAP[kind],
            source_id=None if source_id == "전체" else source_id,
            mode="hybrid",
            expand=True,
        )

    st.write(f"**{len(hits)}건** 검색됨")
    if not hits:
        st.info("검색 결과가 없습니다. 다른 표현으로 다시 시도해보세요.")

    for h in hits:
        p = h.payload
        with st.container(border=True):
            # Hit.label 은 kind='case' 를 안 가려서 "None 제목"처럼 나올 수 있어 직접 조립.
            label = h.label if h.kind != "case" else p.get("title", h.text[:40])
            top1, top2 = st.columns([5, 1])
            with top1:
                st.markdown(f"**{label}**")
                st.caption(f"{source_label(p.get('source_id', ''))} · p.{p.get('source_page', '?')}")
            with top2:
                st.caption(f"관련도 {h.score:.2f}")
            snippet = h.text.strip().replace("\n", " ")
            st.write(snippet[:200] + ("…" if len(snippet) > 200 else ""))
            with st.expander("자세히 보기"):
                if p.get("base_ratio"):
                    st.markdown(f"기본과실: A {p['base_ratio']['a']}% : B {p['base_ratio']['b']}%")
                if p.get("modifiers"):
                    st.markdown("**수정요소**")
                    for m in p["modifiers"]:
                        st.caption(f"- {m['name']} ({'+' if m['adjustment'] >= 0 else ''}{m['adjustment']}, {m['target']})")
                if p.get("laws"):
                    st.caption("관련 법령: " + ", ".join(p["laws"]))
elif go:
    st.warning("검색어를 입력해주세요.")
else:
    # ── 둘러보기: 검색 안 해도 실데이터(hani/data/processed/payloads.json)를
    #    바로 카드로 훑어볼 수 있게. 목업의 트리필터·카드그리드·모달을 여기서 구현.
    st.write("")
    st.markdown('<div class="fr-section-title">🗂️ 도표 둘러보기</div>', unsafe_allow_html=True)

    all_standards = standards()
    browse_sources = sorted({s.get("source_id") for s in all_standards if s.get("source_id")})
    chip_labels = ["전체"] + [source_label(s) for s in browse_sources]
    chip_values = ["전체"] + browse_sources

    st.session_state.setdefault("kb_browse_source", "전체")
    st.session_state.setdefault("kb_browse_n", 30)

    chip_cols = st.columns(len(chip_values))
    for col, label, value in zip(chip_cols, chip_labels, chip_values, strict=False):
        with col:
            is_active = st.session_state["kb_browse_source"] == value
            if st.button(label, key=f"kbchip_{value}", use_container_width=True,
                         type="primary" if is_active else "secondary"):
                st.session_state["kb_browse_source"] = value
                st.session_state["kb_browse_n"] = 30
                st.rerun()

    filtered = [
        s for s in all_standards
        if st.session_state["kb_browse_source"] == "전체" or s.get("source_id") == st.session_state["kb_browse_source"]
    ]
    st.caption(f"총 {len(filtered)}건")

    shown = filtered[: st.session_state["kb_browse_n"]]
    grid_cols = st.columns(3)
    for i, s in enumerate(shown):
        with grid_cols[i % 3]:
            with st.container(border=True):
                r = s.get("base_ratio") or {}
                st.markdown(
                    f'<div class="fr-kb-title">{s.get("diagram_no", "")} · {s.get("title", "")}</div>'
                    f'<div class="fr-kb-meta">{source_label(s.get("source_id", ""))} '
                    f'· 기본과실 A{r.get("a", "?")}:B{r.get("b", "?")}</div>',
                    unsafe_allow_html=True,
                )
                if st.button("자세히 보기", key=f"kbcard_{s.get('source_id')}_{s.get('diagram_no')}_{i}",
                             use_container_width=True):
                    _kb_show_detail(s)

    if len(filtered) > len(shown):
        if st.button(f"더 보기 (+{min(30, len(filtered) - len(shown))})", use_container_width=True):
            st.session_state["kb_browse_n"] += 30
            st.rerun()

st.divider()
st.page_link("pages/2_상담.py", label="💬 특정 사고 상황으로 상담받기", icon="💬")
