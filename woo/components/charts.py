"""과실비율 게이지 · 수정요소 워터폴."""

from __future__ import annotations

import plotly.graph_objects as go

나_색 = "#2E86FF"
상대_색 = "#FF6B6B"


def fault_gauge(나_퍼센트: int, 나_라벨: str = "나", 상대_라벨: str = "상대") -> go.Figure:
    """0~100 과실비율 게이지. 나(파랑) 기준, 나머지는 상대."""
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=나_퍼센트,
            number={"suffix": "%", "font": {"size": 40}},
            title={"text": f"{나_라벨} 과실비율 (상대 {상대_라벨} {100 - 나_퍼센트}%)"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": 나_색},
                "steps": [
                    {"range": [0, 50], "color": "#EAF2FF"},
                    {"range": [50, 100], "color": "#FFECEC"},
                ],
                "threshold": {
                    "line": {"color": 상대_색, "width": 3},
                    "thickness": 0.8,
                    "value": 나_퍼센트,
                },
            },
        )
    )
    fig.update_layout(height=280, margin=dict(l=30, r=30, t=60, b=10))
    return fig


def modifier_waterfall(계산_단계: list[dict]) -> go.Figure:
    """기본과실 → 수정요소 적용 순서를 워터폴로. 계산_단계=[{"라벨":..,"값":..}]"""
    if not 계산_단계:
        return go.Figure()

    라벨 = [s["라벨"] for s in 계산_단계]
    값 = [s["값"] for s in 계산_단계]
    측정 = ["absolute"] + ["total"] * (len(값) - 1)

    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=측정,
            x=라벨,
            y=값,
            connector={"line": {"color": "#CBD5E1"}},
            increasing={"marker": {"color": 상대_색}},
            decreasing={"marker": {"color": 나_색}},
            totals={"marker": {"color": "#64748B"}},
            text=[str(v) for v in 값],
            textposition="outside",
        )
    )
    fig.update_layout(
        title="수정요소 적용 과정 (나의 과실비율 기준)",
        height=320,
        margin=dict(l=20, r=20, t=50, b=20),
        showlegend=False,
    )
    return fig
