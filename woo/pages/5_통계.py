"""통계 — 지식베이스(payloads.json) 현황을 실데이터 기준으로 요약.

⚠️ 이 프로젝트 전체의 원칙("숫자는 지어내지 않는다")과 동일하게, 여기 나오는
모든 수치는 hani/data/processed/payloads.json을 그 자리에서 직접 집계한
실제 값입니다. 목업 디자인 참고용으로 있던 고정 숫자(342건 등)는 쓰지 않습니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from woo.components.kb_data import load_payloads, source_label, standards  # noqa: E402
from woo.components.widgets import hero, inject_css, top_nav  # noqa: E402

st.set_page_config(page_title="통계 · 과실비율", page_icon="📊", layout="wide")
inject_css()
top_nav("stats")
hero("📊 통계", "인정기준 지식베이스 현황을 한눈에 확인합니다 (실데이터 집계).")

payloads = load_payloads()
전체 = list(payloads.values())
기준도표 = standards()

# ── 요약 카드 ────────────────────────────────────────────────
전체법령 = set()
전체판례 = set()
for s in 기준도표:
    전체법령.update(s.get("laws") or [])
    전체판례.update(s.get("precedents") or [])
심의사례_수 = sum(1 for v in 전체 if v.get("kind") == "case")

c1, c2, c3, c4 = st.columns(4)
c1.metric("기준 도표 수", f"{len(기준도표)}건")
c2.metric("참조 판례 수", f"{len(전체판례)}건")
c3.metric("관련 법조항 수", f"{len(전체법령)}개")
c4.metric("심의사례 수", f"{심의사례_수}건")

st.write("")

# ── 차트 2개 ─────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.markdown('<div class="fr-section-title">출처 문서별 도표 수</div>', unsafe_allow_html=True)
    by_source: dict[str, int] = {}
    for s in 기준도표:
        label = source_label(s.get("source_id", ""))
        by_source[label] = by_source.get(label, 0) + 1
    if by_source:
        items = sorted(by_source.items(), key=lambda kv: -kv[1])
        fig = go.Figure(go.Bar(
            x=[k for k, _ in items], y=[v for _, v in items],
            marker_color="#3366FF", text=[v for _, v in items], textposition="outside",
        ))
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("데이터 없음")

with col2:
    st.markdown('<div class="fr-section-title">기본과실 분포 (A 기준)</div>', unsafe_allow_html=True)
    buckets = {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0}
    for s in 기준도표:
        a = (s.get("base_ratio") or {}).get("a")
        if a is None:
            continue
        idx = min(int(a) // 20, 4)
        key = list(buckets.keys())[idx]
        buckets[key] += 1
    fig2 = go.Figure(go.Bar(
        x=list(buckets.keys()), y=list(buckets.values()),
        marker_color="#F5A524", text=list(buckets.values()), textposition="outside",
    ))
    fig2.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
    st.plotly_chart(fig2, use_container_width=True)

st.caption(
    f"⚠️ '기본과실 없음'(base_ratio_variants만 있는 조건부 기준 등)인 도표 "
    f"{len(기준도표) - sum(buckets.values())}건은 분포 차트에서 제외됐습니다."
)

st.divider()
st.page_link("pages/3_지식베이스.py", label="📚 지식베이스에서 직접 둘러보기", icon="📚")
