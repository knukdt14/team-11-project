"""신뢰도 배지 · 되묻기 칩 · 과실비율 히어로 등 커스텀 CSS 위젯.

`.streamlit/config.toml` 을 건드리지 않고(다른 팀원 영역 보호) 순수 CSS 주입만으로
색상·타이포·카드 스타일을 통일합니다. `inject_css()` 를 각 페이지 맨 위에서 한 번만
호출하세요. `sidebar_nav()` 는 Streamlit 기본 사이드바 페이지 목록 대신 쓰는 커스텀
사이드바 네비게이션입니다 — 페이지 맨 위, `inject_css()` 바로 다음에 호출하세요.
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
    ("video", "🎥", "영상 분석", "pages/4_영상분석.py"),
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
            font-size: 1.08rem;
        }}
        /* 기본 문단/캡션/마크다운 글자도 같이 키움 (여백만 넓고 글자는 작아 보인다는
           피드백 — Streamlit 기본 크기가 전체적으로 작아서 위 html 폰트 하나로는
           st.write/st.caption 등 내부 요소까지 안 커짐, 각각 지정 필요) */
        [data-testid="stMarkdownContainer"] p {{ font-size: 1.05rem; line-height: 1.65; }}
        [data-testid="stCaptionContainer"], .stCaption {{ font-size: 0.92rem !important; }}
        .block-container {{ padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1120px; }}

        /* ── 배경: 차분한 단색 계열 (화려한 다색 그라데이션 대신) ──── */
        .stApp {{
            background: linear-gradient(180deg, #F8F9FC 0%, #F1F3F8 100%);
        }}
        [data-testid="stSidebar"] {{
            background: #FFFFFF;
            border-right: 1px solid #EAECF1;
        }}
        [data-testid="stSidebar"] .block-container {{ padding-top: 1.4rem; }}

        /* ── Streamlit 기본 크롬 정리 ─────────────────────────── */
        /* ⚠️ 버전마다 testid가 바뀝니다(예전엔 stDeployButton, 지금(1.60)은
           stAppDeployButton) — 두 이름 다 대비. */
        #MainMenu {{ visibility: hidden; }}
        footer {{ visibility: hidden; }}
        .stDeployButton, [data-testid="stAppDeployButton"] {{ display: none !important; }}
        [data-testid="stToolbarActions"] {{ display: none !important; }}
        header[data-testid="stHeader"] {{ background: rgba(255,255,255,0); }}
        [data-testid="stSidebarNav"] {{ display: none; }}  /* 자동 페이지 목록 → sidebar_nav()로 대체 */

        /* ── 사이드바 내비게이션 (홈/상담/지식베이스) ─────────────── */
        .fr-navbar-brand {{
            font-weight: 800; font-size: 1.25rem; color: #0F172A;
            display:flex; align-items:center; gap:8px; white-space:nowrap;
        }}
        /* ⚠️ st.page_link는 내부에 툴팁 래퍼+마크다운 컴포넌트가 여러 겹 감싸고 있어서
           (BaseButtonTooltip > div > a > span > <p>) CSS로 글자색을 덮어씌우려 해도
           실제로 안 먹히는 걸 두 번이나 확인했습니다(상단바 때도, 사이드바로 옮긴
           직후에도 라벨 글자가 안 보였음) — 그래서 훨씬 단순한 st.button +
           st.switch_page 조합으로 바꿨습니다. 버튼은 중첩 구조가 없어서 CSS가
           바로 먹습니다. */
        [data-testid="stSidebar"] div[data-testid="stVerticalBlock"]:has(button[kind]) div.stButton {{
            margin-bottom: 2px;
        }}
        [data-testid="stSidebar"] .stButton>button {{
            width: 100%; justify-content: flex-start !important; text-align: left !important;
            border-radius: 10px !important; font-weight: 600 !important; font-size: 1.08rem !important;
            padding: 12px 14px !important; border: none !important; box-shadow: none !important;
            transition: .15s;
        }}
        [data-testid="stSidebar"] .stButton>button[kind="secondary"] {{
            background: transparent !important; color: #334155 !important;
        }}
        [data-testid="stSidebar"] .stButton>button[kind="secondary"]:hover {{
            background: #F1F5F9 !important; color: {나_색} !important;
        }}
        [data-testid="stSidebar"] .stButton>button[kind="primary"] {{
            background: {나_색}14 !important; color: {나_색} !important;
        }}
        [data-testid="stSidebar"] .stButton>button[kind="primary"]:hover {{
            background: {나_색}22 !important; color: {나_색} !important;
        }}

        /* ── 히어로 배너 ─────────────────────────────────────── */
        .fr-hero {{
            background: linear-gradient(135deg, {나_색} 0%, #6C4CFF 100%);
            color: white; border-radius: 18px; padding: 34px 38px;
            margin-bottom: 24px; box-shadow: 0 10px 28px rgba(46,91,255,0.22);
        }}
        /* ⚠️ 한글은 단어 사이에 띄어쓰기가 있어도 브라우저 기본 줄바꿈(overflow-wrap)이
           음절 단위로 끊어버려서 "대시보드"가 "대시보"+"드"처럼 단어 중간에서
           줄바꿈됐습니다 — word-break:keep-all 로 단어(띄어쓰기) 단위로만 줄바꿈되게
           고정합니다. */
        .fr-hero h1 {{
            margin:0 0 10px 0; font-size:2rem; font-weight:800; line-height:1.35;
            word-break:keep-all; overflow-wrap:normal;
        }}
        .fr-hero p {{
            margin:0; opacity:0.92; font-size:1.15rem; line-height:1.55;
            word-break:keep-all; overflow-wrap:normal;
        }}

        /* ── 상태 배지 (pill) ────────────────────────────────── */
        .fr-badge {{
            display:inline-block; padding:4px 13px; border-radius:999px;
            font-size:0.88rem; font-weight:700; margin-left:8px; vertical-align:middle;
        }}
        .fr-status-pill {{
            display:inline-flex; align-items:center; gap:6px; padding:7px 15px;
            border-radius:999px; font-size:0.92rem; font-weight:600;
        }}
        .fr-status-on {{ background:#DCFCE7; color:#166534; }}
        .fr-status-off {{ background:#FEF3C7; color:#92400E; }}
        .fr-dot {{ width:8px; height:8px; border-radius:50%; display:inline-block; }}

        /* ── 예시 카드 / 일반 카드 ───────────────────────────── */
        .fr-example-card {{
            border:1px solid #E2E8F0; border-radius:16px; padding:20px 22px;
            background:#FAFBFF; height:100%; transition:.15s;
        }}
        .fr-example-card:hover {{ border-color:{나_색}; box-shadow:0 4px 14px rgba(46,91,255,0.12); }}
        /* ⚠️ min-height는 텍스트 줄 수(2줄 vs 3줄)에 따라 카드 높이가 서로 달라지는
           문제 때문입니다 — st.columns는 세로로 자동 stretch가 안 돼서, 가장 긴
           예시(3줄)를 기준으로 넉넉하게 잡아야 3개 카드 높이가 맞습니다. */
        .fr-example-q {{ font-size:1.08rem; color:#1E293B; line-height:1.55; min-height:4.8em; }}

        /* ── 되묻기 칩 ────────────────────────────────────────── */
        .fr-chip {{
            display:inline-block; padding:7px 15px; border-radius:999px;
            border:1px solid #CBD5E1; background:#F8FAFC; font-size:0.95rem;
            margin:2px 4px 2px 0;
        }}

        /* ── 과실비율 히어로 스탯 ────────────────────────────── */
        .fr-ratio-hero {{ display:flex; gap:14px; align-items:stretch; margin:8px 0 4px 0; }}
        .fr-ratio-side {{
            flex:1; border-radius:16px; padding:20px 16px; text-align:center;
        }}
        .fr-side-a {{ background:linear-gradient(160deg,#EAF1FF,#F5F8FF); border:1px solid #DCE7FF; }}
        .fr-side-b {{ background:linear-gradient(160deg,#FFEDED,#FFF6F6); border:1px solid #FFD9D9; }}
        .fr-ratio-role {{ font-size:0.95rem; color:#64748B; font-weight:600; margin-bottom:6px; }}
        .fr-ratio-num {{ font-size:2.7rem; font-weight:800; line-height:1; }}
        .fr-side-a .fr-ratio-num {{ color:{나_색}; }}
        .fr-side-b .fr-ratio-num {{ color:{상대_색}; }}
        .fr-ratio-vs {{
            align-self:center; font-weight:700; color:#94A3B8; font-size:1.2rem;
        }}

        /* ── 섹션 제목 ────────────────────────────────────────── */
        .fr-section-title {{
            font-size:1.25rem; font-weight:700; margin: 4px 0 12px 0; color:#1E293B;
        }}

        /* ── 면책 문구 ────────────────────────────────────────── */
        .fr-disclaimer {{
            font-size:0.88rem; color:#64748B; border-top:1px solid #E2E8F0;
            padding-top:8px; margin-top:16px;
        }}

        /* ── 버튼을 조금 더 둥글게 ───────────────────────────── */
        .stButton>button, .stChatInputContainer, div[data-baseweb="select"] {{
            border-radius:12px !important;
        }}
        /* ⚠️ 좁은 컬럼(예: "↔ 반대쪽이에요" 버튼)에서 "이에"+"요"처럼 단어 중간에서
           줄바꿈되던 문제 — 원인이 히어로 제목 때와 달랐습니다. 버튼 라벨은 Streamlit이
           내부적으로 다시 마크다운 컴포넌트(<p>)로 렌더링하면서 그 <p> 자체에
           word-break:break-word를 직접 박아넣기 때문에, .stButton>button에 준
           word-break는 상속될 기회조차 없이 무시됩니다 — <p> 자신을 !important로
           직접 덮어써야 합니다. */
        .stButton>button p {{
            word-break: keep-all !important; overflow-wrap: normal !important;
        }}
        .stButton>button[kind="primary"] {{
            box-shadow: 0 4px 12px rgba(46,91,255,0.28);
        }}

        /* ── "안내문 박스 + 반대쪽 버튼" 같은 줄: 높이 맞추기 ────────── */
        /* ⚠️ align-items:stretch + height:100% 체인으로 맞춰봤지만 Streamlit의
           중첩 wrapper(stColumn>stVerticalBlock>stElementContainer>...) 어딘가에서
           또 auto로 끊겨서 여전히 안 맞았습니다 — 부모 체인에 기대는 대신, 두 박스
           자체에 똑같은 min-height를 직접 박아넣고 내용은 세로 중앙정렬하는 쪽이
           훨씬 확실합니다(조상 높이가 어떻게 되든 상관없이 항상 이 값으로 고정됨). */
        /* min-height는 "이 이상"이라 버튼 쪽 내용(2줄+패딩)이 78px을 실제로 넘어버려서
           결국 버튼이 더 컸습니다 — 아예 height를 고정값으로 못박아 두 박스가 항상
           똑같은 크기가 되도록 합니다. */
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stAlertContainer"]):has(.stButton)
            div[data-testid="stAlertContainer"] {{
            height: 84px !important; box-sizing: border-box !important;
            display: flex !important; align-items: center !important;
        }}
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stAlertContainer"]):has(.stButton)
            .stButton>button {{
            height: 84px !important; box-sizing: border-box !important;
            display: flex !important; align-items: center !important; justify-content: center !important;
        }}
        /* ⚠️ 높이는 맞았는데도 위/아래 선이 계속 안 맞았던 이유 — 두 컬럼 안의
           stElementContainer(각 요소를 감싸는 블록)가 기본적으로 위아래 margin을
           갖고 있어서, 그 margin 크기가 안내문 쪽과 버튼 쪽이 서로 달라(내용물 종류가
           다르니 Streamlit이 기본으로 주는 여백도 다름) 박스 자체는 높이가 같아도
           시작 위치가 어긋났습니다. 이 줄에서만 그 여백을 0으로 눌러서 둘 다 컬럼
           맨 위에서 시작하게 맞춥니다. */
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stAlertContainer"]):has(.stButton)
            div[data-testid="stElementContainer"] {{
            margin: 0 !important;
        }}
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stAlertContainer"]):has(.stButton) {{
            align-items: flex-start !important;
        }}

        /* ── 마스코트 말풍선 ──────────────────────────────────── */
        .fr-mascot-row {{
            display:flex; align-items:flex-start; gap:14px; margin:14px 0 22px 0;
        }}
        .fr-mascot-avatar {{
            font-size:2.2rem; line-height:1; flex-shrink:0;
            width:60px; height:60px; display:flex; align-items:center; justify-content:center;
            background:#FFFFFF; border:2px solid #E2E8F0; border-radius:50%;
            box-shadow:0 2px 8px rgba(0,0,0,0.06);
        }}
        .fr-mascot-bubble {{
            position:relative; background:#FFFFFF; border:1px solid #E2E8F0;
            border-radius:16px; padding:14px 18px; font-size:1.02rem; color:#1E293B;
            line-height:1.65; word-break:keep-all; overflow-wrap:normal;
            box-shadow:0 2px 10px rgba(0,0,0,0.05); max-width:680px;
        }}
        .fr-mascot-bubble::before {{
            content:''; position:absolute; left:-8px; top:20px;
            border-width:8px 8px 8px 0; border-style:solid;
            border-color:transparent #E2E8F0 transparent transparent;
        }}
        .fr-mascot-bubble::after {{
            content:''; position:absolute; left:-6px; top:21px;
            border-width:7px 7px 7px 0; border-style:solid;
            border-color:transparent #FFFFFF transparent transparent;
        }}

        /* ── 사이드바 브랜드 ─────────────────────────────────── */
        .fr-sidebar-brand {{
            display:flex; align-items:center; gap:8px; font-weight:800;
            font-size:1.2rem; margin-bottom:2px;
        }}
        .fr-sidebar-sub {{ font-size:0.88rem; color:#94A3B8; margin-bottom:14px; }}
        .fr-history-item {{
            font-size:0.92rem; color:#475569; padding:6px 0; border-bottom:1px solid #F1F5F9;
        }}

        /* ── 지식베이스 카드 ─────────────────────────────────── */
        .fr-kb-card {{
            border:1px solid #E2E8F0; border-radius:14px; padding:16px 20px;
            margin-bottom:10px; background:#FFFFFF;
        }}
        .fr-kb-title {{ font-weight:700; font-size:1.12rem; }}
        .fr-kb-meta {{ font-size:0.88rem; color:#94A3B8; }}

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
    """사이드바에 붙이는 보조 라벨(히스토리 위젯 등 위). 메인 내비는 sidebar_nav() 를 쓰세요."""
    with st.sidebar:
        st.markdown(
            f'<div class="fr-sidebar-brand">🚦 과실비율 상담</div>'
            f'<div class="fr-sidebar-sub">{subtitle}</div>',
            unsafe_allow_html=True,
        )


def sidebar_nav(active: str) -> None:
    """왼쪽 사이드바에 그리는 커스텀 네비게이션(홈/상담/지식베이스).

    `inject_css()` 가 `[data-testid="stSidebarNav"]`(자동 페이지 목록)를 숨기므로,
    페이지 이동은 여기서만 가능합니다. 모든 페이지 맨 위, `inject_css()` 바로 다음에
    호출하세요. `active` 는 `_NAV_PAGES` 의 첫 값(id)입니다.

    ⚠️ st.page_link 대신 st.button + st.switch_page를 씁니다 — page_link는 내부에
    툴팁 래퍼/마크다운 컴포넌트가 여러 겹 감싸고 있어 CSS로 글자색을 덮어씌워도
    실제로 안 먹히는 걸(라벨이 아예 안 보임) 두 번 확인했습니다. 버튼은 그런 중첩이
    없어서 CSS가 바로 먹습니다.
    """
    with st.sidebar:
        st.markdown('<div class="fr-navbar-brand">🚦 과실비율 상담</div>', unsafe_allow_html=True)
        st.markdown('<div style="height:14px"></div>', unsafe_allow_html=True)
        for page_id, emoji, label, target in _NAV_PAGES:
            is_active = page_id == active
            clicked = st.button(
                f"{emoji}  {label}",
                key=f"nav_{page_id}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            )
            if clicked and not is_active:
                st.switch_page(target)


def hero(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="fr-hero"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


def mascot_say(text: str, emoji: str = "🕵️") -> None:
    """캐릭터가 말풍선으로 얘기하는 것처럼 텍스트를 보여줍니다.

    영상 분석처럼 "결과가 뭔지 한눈에 안 들어오는" 화면에서, 분석 상태/결과를
    캐릭터가 직접 설명해주는 느낌을 주기 위한 것 — 텍스트만 바꿔서 여러 상황
    (안내/성공/실패)에 재사용하세요.
    """
    st.markdown(
        f'<div class="fr-mascot-row">'
        f'<div class="fr-mascot-avatar">{emoji}</div>'
        f'<div class="fr-mascot-bubble">{text}</div>'
        f"</div>",
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
