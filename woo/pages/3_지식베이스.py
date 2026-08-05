"""지식베이스 탐색 — 상담 흐름과 별개로 전체 KB를 자유 검색/필터링합니다."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from woo.components.kb_data import SOURCE_LABELS, source_label  # noqa: E402
from woo.components.widgets import hero, inject_css, topnav  # noqa: E402

st.set_page_config(page_title="지식베이스 · 과실비율", page_icon="📚", layout="wide")
inject_css()
topnav("kb")
hero("📚 지식베이스 탐색", "상담 없이 도표·판례·법령을 직접 검색해볼 수 있습니다.")


@st.cache_resource(show_spinner="검색 엔진 로딩 중...")
def _searcher():
    from taek.search import Searcher

    return Searcher()


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
    st.caption("검색어를 입력하고 검색 버튼을 누르면 결과가 여기 표시됩니다.")

st.divider()
st.page_link("pages/2_상담.py", label="💬 특정 사고 상황으로 상담받기", icon="💬")
