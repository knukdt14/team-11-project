"""신뢰도 배지 · 되묻기 칩 · 과실비율 히어로 등 커스텀 CSS 위젯.

`.streamlit/config.toml` 을 건드리지 않고(다른 팀원 영역 보호) 순수 CSS 주입만으로
색상·타이포·카드 스타일을 통일합니다. `inject_css()` 를 각 페이지 맨 위에서 한 번만
호출하세요. `topnav()` 는 Streamlit 기본 사이드바 페이지 목록 대신 쓰는 커스텀 상단
네비게이션입니다 — 페이지 맨 위, `inject_css()` 바로 다음에 호출하세요.
"""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

나_색 = "#2E5BFF"
상대_색 = "#FF6B6B"

_BADGE_STYLE = {
    "높음": ("#DCFCE7", "#166534"),
    "보통": ("#FEF9C3", "#854D0E"),
    "낮음": ("#FEE2E2", "#991B1B"),
}

_FONTS_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"
_FONT_WEIGHTS = {"Regular": 400, "Medium": 500, "SemiBold": 600, "Bold": 700}

_NAV_PAGES = [
    ("home", "🏠", "홈", "app.py"),
    ("consult", "💬", "상담", "pages/2_상담.py"),
    ("kb", "📚", "지식베이스", "pages/3_지식베이스.py"),
]


@st.cache_resource(show_spinner=False)
def _font_face_css() -> str:
    """Pretendard 를 로컬 vendor 파일에서 base64로 읽어 @font-face 로 박습니다.
    CDN/네트워크 의존 없이(오프라인 Docker 시연 포함) 항상 같은 폰트로 보이게 하기 위함.
    캐시해서 매 rerun마다 파일을 다시 읽고 인코딩하지 않도록 합니다."""
    faces = []
    for weight_name, weight_num in _FONT_WEIGHTS.items():
        path = _FONTS_DIR / f"Pretendard-{weight_name}.woff2"
        if not path.exists():
            continue
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        faces.append(
            f"""@font-face {{
                font-family: 'Pretendard'; font-weight: {weight_num}; font-style: normal;
                src: url(data:font/woff2;base64,{b64}) format('woff2');
                font-display: swap;
            }}"""
        )
    return "\n".join(faces)


def inject_css() -> None:
    st.markdown(f"<style>{_font_face_css()}</style>", unsafe_allow_html=True)
    st.markdown(
        f"""
        <style>
        /* ── 전역 타이포 ─────────────────────────────────────── */
        html, body, [class*="css"] {{
            font-family: "Pretendard", -apple-system, "Segoe UI", "Malgun Gothic",
                         "Apple SD Gothic Neo", sans-serif;
        }}
        .block-container {{ padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1120px; }}

        /* ── 배경: 흰 배경 대신 은은한 그라데이션 메시 ───────────── */
        .stApp {{
            background:
                radial-gradient(1100px circle at 10% -8%, rgba(46,91,255,0.14) 0%, transparent 46%),
                radial-gradient(900px circle at 92% 8%, rgba(108,76,255,0.12) 0%, transparent 42%),
                radial-gradient(1000px circle at 50% 115%, rgba(255,107,107,0.08) 0%, transparent 48%),
                linear-gradient(180deg, #F6F8FD 0%, #EEF1F9 55%, #EAEFFB 100%);
            background-attachment: fixed;
        }}
        [data-testid="stSidebar"] {{
            background: rgba(255,255,255,0.7); backdrop-filter: blur(8px);
            border-right: 1px solid rgba(226,232,240,0.7);
        }}

        /* ── Streamlit 기본 크롬 정리 ─────────────────────────── */
        #MainMenu {{ visibility: hidden; }}
        footer {{ visibility: hidden; }}
        .stDeployButton {{ display: none; }}
        header[data-testid="stHeader"] {{ background: rgba(255,255,255,0); }}
        [data-testid="stSidebarNav"] {{ display: none; }}  /* 자동 페이지 목록 → topnav로 대체 */

        /* ── 상단 네비게이션 바 ───────────────────────────────── */
        .fr-navbar-wrap {{
            position: sticky; top: 0; z-index: 999;
            background: rgba(255,255,255,0.86); backdrop-filter: blur(10px);
            border-bottom: 1px solid #EDF0F5; margin: -1.2rem -1rem 1.6rem -1rem;
            padding: 0 1rem;
        }}
        .fr-navbar-brand {{
            font-weight: 800; font-size: 1.05rem; color: #1E293B;
            display:flex; align-items:center; gap:6px; white-space:nowrap;
        }}
        div[data-testid="stPageLink"] {{ width: auto !important; }}
        div[data-testid="stPageLink"] a {{
            border-radius: 999px !important; padding: 7px 16px !important;
            font-weight: 600 !important; font-size: 0.88rem !important;
            color: #64748B !important; background: transparent !important;
            border: 1px solid transparent !important; transition: .15s;
        }}
        div[data-testid="stPageLink"] a:hover {{
            background: #F1F5F9 !important; color: #1E293B !important;
        }}
        .fr-nav-active div[data-testid="stPageLink"] a {{
            background: {나_색}1A !important; color: {나_색} !important;
            border-color: {나_색}33 !important;
        }}

        /* ── 히어로 배너 ─────────────────────────────────────── */
        .fr-hero {{
            background: linear-gradient(135deg, {나_색} 0%, #6C4CFF 100%);
            color: white; border-radius: 20px; padding: 36px 40px;
            margin-bottom: 28px; box-shadow: 0 8px 24px rgba(46,91,255,0.25);
        }}
        .fr-hero h1 {{ margin:0 0 8px 0; font-size:1.9rem; font-weight:800; }}
        .fr-hero p {{ margin:0; opacity:0.92; font-size:1.02rem; }}

        /* ── 상태 배지 (pill) ────────────────────────────────── */
        .fr-badge {{
            display:inline-block; padding:3px 12px; border-radius:999px;
            font-size:0.78rem; font-weight:700; margin-left:8px; vertical-align:middle;
        }}
        .fr-status-pill {{
            display:inline-flex; align-items:center; gap:6px; padding:6px 14px;
            border-radius:999px; font-size:0.82rem; font-weight:600;
        }}
        .fr-status-on {{ background:#DCFCE7; color:#166534; }}
        .fr-status-off {{ background:#FEF3C7; color:#92400E; }}
        .fr-dot {{ width:8px; height:8px; border-radius:50%; display:inline-block; }}

        /* ── 예시 카드 / 일반 카드 ───────────────────────────── */
        .fr-example-card {{
            border:1px solid #E2E8F0; border-radius:16px; padding:18px 20px;
            background:#FAFBFF; height:100%; transition:.15s;
        }}
        .fr-example-card:hover {{ border-color:{나_색}; box-shadow:0 4px 14px rgba(46,91,255,0.12); }}
        .fr-example-q {{ font-size:0.95rem; color:#1E293B; line-height:1.5; min-height:3.2em; }}

        /* ── 되묻기 칩 ────────────────────────────────────────── */
        .fr-chip {{
            display:inline-block; padding:6px 14px; border-radius:999px;
            border:1px solid #CBD5E1; background:#F8FAFC; font-size:0.85rem;
            margin:2px 4px 2px 0;
        }}

        /* ── 과실비율 히어로 스탯 ────────────────────────────── */
        .fr-ratio-hero {{ display:flex; gap:14px; align-items:stretch; margin:8px 0 4px 0; }}
        .fr-ratio-side {{
            flex:1; border-radius:16px; padding:20px 16px; text-align:center;
        }}
        .fr-side-a {{ background:linear-gradient(160deg,#EAF1FF,#F5F8FF); border:1px solid #DCE7FF; }}
        .fr-side-b {{ background:linear-gradient(160deg,#FFEDED,#FFF6F6); border:1px solid #FFD9D9; }}
        .fr-ratio-role {{ font-size:0.85rem; color:#64748B; font-weight:600; margin-bottom:6px; }}
        .fr-ratio-num {{ font-size:2.4rem; font-weight:800; line-height:1; }}
        .fr-side-a .fr-ratio-num {{ color:{나_색}; }}
        .fr-side-b .fr-ratio-num {{ color:{상대_색}; }}
        .fr-ratio-vs {{
            align-self:center; font-weight:700; color:#94A3B8; font-size:1.1rem;
        }}

        /* ── 섹션 제목 ────────────────────────────────────────── */
        .fr-section-title {{
            font-size:1.05rem; font-weight:700; margin: 4px 0 10px 0; color:#1E293B;
        }}

        /* ── 면책 문구 ────────────────────────────────────────── */
        .fr-disclaimer {{
            font-size:0.78rem; color:#64748B; border-top:1px solid #E2E8F0;
            padding-top:8px; margin-top:16px;
        }}

        /* ── 버튼을 조금 더 둥글게 ───────────────────────────── */
        .stButton>button, .stChatInputContainer, div[data-baseweb="select"] {{
            border-radius:12px !important;
        }}
        .stButton>button[kind="primary"] {{
            box-shadow: 0 4px 12px rgba(46,91,255,0.28);
        }}

        /* ── 사이드바 브랜드 ─────────────────────────────────── */
        .fr-sidebar-brand {{
            display:flex; align-items:center; gap:8px; font-weight:800;
            font-size:1.05rem; margin-bottom:2px;
        }}
        .fr-sidebar-sub {{ font-size:0.78rem; color:#94A3B8; margin-bottom:14px; }}
        .fr-history-item {{
            font-size:0.82rem; color:#475569; padding:6px 0; border-bottom:1px solid #F1F5F9;
        }}

        /* ── 지식베이스 카드 ─────────────────────────────────── */
        .fr-kb-card {{
            border:1px solid #E2E8F0; border-radius:14px; padding:14px 18px;
            margin-bottom:10px; background:#FFFFFF;
        }}
        .fr-kb-title {{ font-weight:700; font-size:0.98rem; }}
        .fr-kb-meta {{ font-size:0.78rem; color:#94A3B8; }}

        /* ── 통계 지표 카드 ───────────────────────────────────── */
        div[data-testid="stMetric"] {{
            background:#FAFBFF; border:1px solid #E2E8F0; border-radius:14px;
            padding:12px 16px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def sidebar_brand(subtitle: str = "AI 과실비율 상담 서비스") -> None:
    """사이드바에 붙이는 보조 라벨(히스토리 위젯 등 위). 메인 내비는 topnav() 를 쓰세요."""
    with st.sidebar:
        st.markdown(
            f'<div class="fr-sidebar-brand">🚦 과실비율 상담</div>'
            f'<div class="fr-sidebar-sub">{subtitle}</div>',
            unsafe_allow_html=True,
        )


def topnav(active: str) -> None:
    """Streamlit 기본 사이드바 페이지 목록을 대신하는 상단 네비게이션 바.

    `inject_css()` 가 `[data-testid="stSidebarNav"]`(자동 페이지 목록)를 숨기므로,
    페이지 이동은 이 네비바의 `st.page_link` 로만 가능합니다. 모든 페이지 맨 위,
    `inject_css()` 바로 다음에 호출하세요. `active` 는 `_NAV_PAGES` 의 첫 값(id)입니다.
    """
    st.markdown('<div class="fr-navbar-wrap">', unsafe_allow_html=True)
    cols = st.columns([2, 1, 1, 1])
    with cols[0]:
        st.markdown(
            '<div class="fr-navbar-brand" style="padding:10px 0;">🚦 과실비율 상담</div>',
            unsafe_allow_html=True,
        )
    for col, (page_id, emoji, label, target) in zip(cols[1:], _NAV_PAGES, strict=False):
        with col:
            wrap_cls = "fr-nav-active" if page_id == active else ""
            st.markdown(f'<div class="{wrap_cls}" style="padding:6px 0;">', unsafe_allow_html=True)
            st.page_link(target, label=label, icon=emoji)
            st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def hero(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="fr-hero"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


def status_pill(ok: bool, on_label: str, off_label: str) -> str:
    cls = "fr-status-on" if ok else "fr-status-off"
    dot = "#22C55E" if ok else "#F59E0B"
    label = on_label if ok else off_label
    return (
        f'<span class="fr-status-pill {cls}">'
        f'<span class="fr-dot" style="background:{dot}"></span>{label}</span>'
    )


def confidence_badge(level: str) -> str:
    """신뢰도 배지 HTML 조각. level: 높음/보통/낮음."""
    bg, fg = _BADGE_STYLE.get(level, ("#E2E8F0", "#334155"))
    return f'<span class="fr-badge" style="background:{bg};color:{fg}">신뢰도 {level}</span>'


def confidence_from_score(score: float) -> str:
    """검색 점수 → 신뢰도 라벨.

    ⚠️ mode="hybrid"(RRF 융합) 점수 기준으로 보정된 임계값입니다. 코사인(0~1)이 아니라
    "1/(순위+k)" 합산이라 스케일이 다릅니다 — 실측 상위 매칭이 보통 0.5~0.6대였습니다.
    """
    if score >= 0.45:
        return "높음"
    if score >= 0.25:
        return "보통"
    return "낮음"


def ratio_hero(a: int, b: int, role_a: str, role_b: str) -> str:
    """A:B 과실비율을 색으로 구분된 큰 숫자 두 블록으로 보여주는 HTML."""
    return (
        '<div class="fr-ratio-hero">'
        f'<div class="fr-ratio-side fr-side-a">'
        f'<div class="fr-ratio-role">나 · {role_a}</div>'
        f'<div class="fr-ratio-num">{a}%</div></div>'
        '<div class="fr-ratio-vs">VS</div>'
        f'<div class="fr-ratio-side fr-side-b">'
        f'<div class="fr-ratio-role">상대 · {role_b}</div>'
        f'<div class="fr-ratio-num">{b}%</div></div>'
        "</div>"
    )


def follow_up_chips(questions: list[str], key_prefix: str = "chip") -> str | None:
    """되묻기 칩들을 버튼으로 렌더링. 클릭된 질문 텍스트를 반환(없으면 None)."""
    if not questions:
        return None
    st.caption("확인이 필요해요 — 아래 중 해당하는 것을 눌러 알려주세요")
    cols = st.columns(len(questions)) if len(questions) <= 4 else st.columns(4)
    clicked: str | None = None
    for i, q in enumerate(questions):
        col = cols[i % len(cols)]
        if col.button(q, key=f"{key_prefix}_{i}"):
            clicked = q
    return clicked


def consult_report_text(result: dict, final_ratio: dict, applied_names: list[str]) -> str:
    """상담 결과를 다운로드용 평문 리포트로 정리합니다. (README §11 계약 키 기준: A/B 대문자)"""
    lines = [
        "==================================",
        " 과실비율 상담 결과 리포트",
        "==================================",
        "",
        f"질문: {result.get('질문', '')}",
        f"기준 도표: {result.get('도표번호', '')} — {result.get('제목', '')}",
        f"{result.get('나_역할', 'A')}(나) vs {result.get('상대_역할', 'B')}(상대)",
        "",
        f"최종 과실비율: 나 {final_ratio['A']}% : 상대 {final_ratio['B']}%",
        "",
        "적용된 수정요소:",
    ]
    lines += [f"  - {n}" for n in applied_names] if applied_names else ["  (없음)"]
    if result.get("법조항"):
        lines += ["", "관련 법령:"]
        lines += [f"  - {law.get('조')} {law.get('제목', '')}" for law in result["법조항"]]
    if result.get("유사사례"):
        lines += ["", "참고 판례/심의사례:"]
        lines += [f"  - {c.get('제목')}" for c in result["유사사례"]]
    if result.get("판례"):
        lines += ["", "참조 판례:"]
        lines += [f"  - {p}" for p in result["판례"]]
    lines += [
        "",
        "----------------------------------",
        "⚠️ 이 리포트는 참고용 안내이며 법적 효력이 없습니다.",
        "최종 과실비율은 보험사·법원의 판단에 따라 달라질 수 있습니다.",
    ]
    return "\n".join(lines)


def disclaimer() -> None:
    st.markdown(
        '<div class="fr-disclaimer">⚠️ 이 서비스는 참고용 안내이며 법적 효력이 없습니다. '
        "최종 과실비율은 보험사·법원의 판단에 따라 달라질 수 있습니다.</div>",
        unsafe_allow_html=True,
    )
