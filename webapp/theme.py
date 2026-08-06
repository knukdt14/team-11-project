"""공통 디자인 시스템 — 색상·타이포·사이드바 네비·히어로·마스코트·게이지.

`woo/components/widgets.py`(Streamlit 버전)와 같은 색/폰트/컴포넌트 모양을 그대로
가져오되, NiceGUI(진짜 Vue/Quasar DOM)라서 Streamlit에서처럼 CSS 우선순위 싸움을
할 필요가 없습니다 — 우리가 만든 HTML에 우리가 만든 클래스를 그대로 씁니다.

사용법: 각 페이지 함수 맨 위에서 `with theme.page_frame("consult"):` 로 감싸면
사이드바 네비 + 배경 + 폰트가 자동으로 적용됩니다.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from nicegui import ui

나_색 = "#0D9488"   # 딥 틸 (teal-600) — 파랑/보라 계열에서 완전히 벗어난 방향
나_색2 = "#134E4A"  # 짙은 틸/네이비 (teal-900) — 히어로 그라데이션 어두운 쪽
상대_색 = "#D97706"  # 앰버 (amber-600) — 틸과 보색에 가까워 "나 vs 상대"가 선명히 구분됨

_BADGE_STYLE = {
    "높음": ("#DCFCE7", "#166534"),
    "보통": ("#FEF9C3", "#854D0E"),
    "낮음": ("#FEE2E2", "#991B1B"),
}

_FONTS_DIR = Path(__file__).resolve().parent / "static" / "fonts"
_FONT_WEIGHTS = {"Regular": 400, "Medium": 500, "SemiBold": 600, "Bold": 700}

NAV_PAGES = [
    ("home", "🏠", "홈", "/"),
    ("consult", "💬", "상담", "/consult"),
    ("video", "🎥", "영상 분석", "/video"),
    ("kb", "📚", "지식베이스", "/kb"),
]


def _font_face_css() -> str:
    """폰트를 정적 파일 URL로 참조합니다 (base64 통째 임베드 아님).

    ⚠️ 예전엔 폰트 4개(약 4.15MB)를 base64로 인코딩해서 CSS 문자열에 그대로 박아넣고,
    그 CSS를 `inject_head()`가 "페이지 넘길 때마다 매번" `ui.add_head_html()`로
    다시 심었습니다 — 즉 상담→영상분석 한 번 이동할 때마다 4MB를 다시 내려받는
    꼴이라 "버퍼링(페이지 전환 지연)"의 원인이었습니다. `main.py`가 이미
    `/static`을 정적 파일로 서빙하고 있으니, base64 대신 그냥 그 URL을 가리키게
    하면 브라우저가 폰트 파일 자체를 한 번만 받고 캐싱합니다(HTTP 캐시 히트) —
    페이지를 몇 번을 옮겨다녀도 다시 안 받습니다.
    """
    faces = []
    for weight_name, weight_num in _FONT_WEIGHTS.items():
        path = _FONTS_DIR / f"Pretendard-{weight_name}.woff2"
        if not path.exists():
            continue
        faces.append(
            f"""@font-face {{
                font-family: 'Pretendard'; font-weight: {weight_num}; font-style: normal;
                src: url('/static/fonts/Pretendard-{weight_name}.woff2') format('woff2');
                font-display: swap;
            }}"""
        )
    return "\n".join(faces)


_GLOBAL_CSS = f"""
{_font_face_css()}

* {{ box-sizing: border-box; }}

html, body {{
    font-family: "Pretendard", -apple-system, "Segoe UI", "Malgun Gothic",
                 "Apple SD Gothic Neo", sans-serif !important;
    color: #0F172A;
}}
/* ⚠️ 배경색을 여러 번 바꿔도 브라우저에 실제로 안 먹혔던 진짜 원인 — NiceGUI(Quasar)는
   `@layer theme, base, quasar, nicegui, ..., quasar_importants;`로 CSS 캐스케이드
   레이어를 씁니다. Quasar가 `quasar_importants` 레이어 안에서 body 배경을 !important로
   깔아두면, 우리가 head에 추가한 스타일은 "레이어 없음(unlayered)"이라 일반 규칙끼리는
   항상 이기지만 **!important 규칙 앞에서는 오히려 가장 약합니다**(레이어+!important는
   우선순위가 뒤집히는 CSS 스펙 때문) — 그래서 html/body에 아무리 background를 줘도
   조용히 씹혔던 것입니다. 대신 Quasar가 전혀 모르는 우리 자체 클래스(.fr-shell)에
   배경을 주면애초에 경쟁할 규칙이 없어서 100% 먹습니다. */
.fr-shell {{
    /* 참고 목업처럼 옅은 회색 단색 배경 — 이전의 틸/앰버 블롭 메시는 뺐습니다. */
    background: #F1F3F5 !important;
    background-attachment: fixed;
}}
/* ⚠️ 진짜 원인 발견 — "오른쪽이 계속 비어 보인다"던 게 배경/레이아웃 튜닝 문제가
   아니라 진짜 버그였습니다. NiceGUI 자체 CSS(`nicegui.css`)가
   `.nicegui-content` 가 display:flex, flex-direction:column, align-items:flex-start
   로 되어 있어서, 그 바로 밑의 자식인 우리 `.fr-shell`이 부모 너비를 꽉 채우지
   않고 "내용물만큼만"(fit-content) 좁게 줄어들고 왼쪽 정렬됩니다 — 그래서 콘텐츠가
   화면 폭 일부에서 뚝 끊기고 나머지가 그냥 흰 배경(부모의 배경)으로 남았던 것입니다.
   자식을 부모 너비만큼 강제로 늘립니다. */
.nicegui-content {{ padding: 0 !important; background: transparent !important; align-items: stretch !important; }}
.fr-shell {{ width: 100%; }}
::selection {{ background: {나_색}33; }}

/* 커스텀 스크롤바 — 기본 회색 굵은 바 대신 은은하게 */
::-webkit-scrollbar {{ width: 10px; height: 10px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: #D8DCE8; border-radius: 999px; border: 2px solid transparent; background-clip: content-box; }}
::-webkit-scrollbar-thumb:hover {{ background: #B9C0D4; background-clip: content-box; }}

/* ── 레이아웃(상단 가로 네비바 방식) ──────────────────── */
/* 콘텐츠가 짧은 페이지(상담/영상분석/지식베이스)에서 푸터가 화면 중간에 붕 뜨지
   않고 항상 뷰포트 맨 아래에 붙도록, 세로 flex 컨테이너로 만들고 fr-main이
   남는 공간을 전부 차지(flex:1)하게 합니다. */
.fr-shell {{ min-height:100vh; display:flex; flex-direction:column; }}
.fr-topbar {{
    position: sticky; top:0; z-index: 100; height: 62px;
    display:flex; align-items:center; gap: 28px; padding: 0 28px;
    /* 참고 목업과 같은 짙은 슬레이트/네이비(거의 검정에 가까운 남색) */
    background: linear-gradient(90deg, #1E293B 0%, #0F172A 100%);
    box-shadow: 0 2px 16px rgba(0,0,0,.25);
}}
.fr-topbar-brand {{
    font-weight: 800; font-size: 1.15rem; letter-spacing: -.01em; color:#FFFFFF;
    display:flex; align-items:center; gap:10px; white-space:nowrap;
}}
.fr-topbar-icon {{
    width:34px; height:34px; flex-shrink:0; border-radius:50%;
    background: linear-gradient(135deg, {나_색}, {나_색2});
    display:flex; align-items:center; justify-content:center;
    box-shadow: 0 2px 8px rgba(0,0,0,.3);
}}
.fr-topnav {{ display:flex; align-items:center; gap:4px; flex:1; }}
.fr-topnav-link {{
    display:flex; align-items:center; gap:6px; padding: 8px 16px; border-radius: 10px;
    font-weight: 600; font-size: 0.96rem; color: rgba(255,255,255,.72);
    text-decoration:none !important; transition:.15s; cursor:pointer; white-space:nowrap;
}}
.fr-topnav-link:hover {{ background: rgba(255,255,255,.08); color:#fff; }}
.fr-topnav-link.active {{ background: rgba(255,255,255,.14); color:#fff; }}
.fr-topbar-right {{ display:flex; align-items:center; gap:14px; color: rgba(255,255,255,.75); font-size:.86rem; }}

.fr-main {{
    flex: 1; width: 100%;
    padding: 32px 40px 24px 40px; max-width: 1680px; margin: 0 auto;
    animation: fr-fade-in .45s ease both;
}}
@keyframes fr-fade-in {{
    from {{ opacity: 0; transform: translateY(6px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}

/* ── 숫자 스텝 카드 헤더 (목업의 "1. 사고 상황 입력" 스타일) ─── */
.fr-step-header {{
    display:flex; align-items:center; gap:10px; font-weight:800; font-size:1.05rem;
    color:#fff; background: linear-gradient(90deg,{나_색},{나_색2});
    padding: 12px 18px; border-radius: 14px 14px 0 0; margin-bottom:0;
}}
.fr-step-num {{
    width:24px; height:24px; border-radius:50%; background:rgba(255,255,255,.22);
    display:flex; align-items:center; justify-content:center; font-size:.82rem; flex-shrink:0;
}}
.fr-step-body {{
    background:#fff; border:1px solid rgba(15,23,42,.06); border-top:none;
    border-radius: 0 0 14px 14px; padding: 20px 22px;
    box-shadow: 0 1px 2px rgba(15,23,42,.03), 0 6px 20px rgba(15,23,42,.045);
    margin-bottom: 20px;
}}

/* ── 페이지 푸터 ──────────────────────────────────────── */
.fr-footer {{
    margin-top: 40px; padding: 20px 40px 28px 40px; border-top:1px solid rgba(15,23,42,.08);
    display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px;
    color:#94A3B8; font-size:.82rem;
}}
.fr-footer a {{ color:#64748B; text-decoration:none; margin-right:18px; }}
.fr-footer a:hover {{ color:{나_색}; }}

/* ── 히어로 배너 ─────────────────────────────────────── */
.fr-hero {{
    position: relative; overflow: hidden;
    background: linear-gradient(135deg, {나_색} 0%, {나_색2} 100%);
    color: white; border-radius: 22px; padding: 38px 42px;
    margin-bottom: 26px; box-shadow: 0 16px 40px rgba(79,70,229,0.28);
}}
.fr-hero::after {{
    content:''; position:absolute; right:-60px; top:-60px; width:220px; height:220px;
    border-radius:50%; background: radial-gradient(circle, rgba(255,255,255,.16), transparent 70%);
}}
.fr-hero-badge {{ position:absolute; top:26px; right:32px; z-index:1; }}
.fr-hero h1 {{
    position:relative; margin:0 0 10px 0; font-size:2.05rem; font-weight:800; line-height:1.35;
    letter-spacing: -.01em; word-break:keep-all; overflow-wrap:normal;
    display:flex; align-items:center; gap:14px;
}}
.fr-hero-icon {{
    width:46px; height:46px; flex-shrink:0; border-radius:50%;
    background: rgba(255,255,255,.16); display:flex; align-items:center; justify-content:center;
}}
.fr-hero p {{
    position:relative; margin:0; opacity:0.94; font-size:1.12rem; line-height:1.55;
    word-break:keep-all; overflow-wrap:normal;
}}

/* ── 카드(공용 컨테이너) ─────────────────────────────── */
.fr-card {{
    background:#FFFFFF; border:1px solid rgba(15,23,42,.06); border-radius:18px;
    padding: 22px 24px; margin-bottom: 18px;
    box-shadow: 0 1px 2px rgba(15,23,42,.03), 0 6px 20px rgba(15,23,42,.045);
    transition: box-shadow .2s, transform .2s;
}}

/* ── 상태 배지 (pill) ────────────────────────────────── */
.fr-badge {{
    display:inline-block; padding:4px 13px; border-radius:999px;
    font-size:0.88rem; font-weight:700; margin-left:8px; vertical-align:middle;
}}
.fr-status-pill {{
    display:inline-flex; align-items:center; gap:7px; padding:7px 16px;
    border-radius:999px; font-size:0.92rem; font-weight:700;
    box-shadow: 0 1px 2px rgba(15,23,42,.04);
}}
.fr-status-on {{ background:#ECFDF3; color:#027A48; }}
.fr-status-off {{ background:#FFFAEB; color:#B54708; }}
.fr-dot {{ width:8px; height:8px; border-radius:50%; display:inline-block; }}
.fr-status-on .fr-dot {{ box-shadow: 0 0 0 rgba(2,122,72,.5); animation: fr-pulse 1.8s infinite; }}
@keyframes fr-pulse {{
    0%   {{ box-shadow: 0 0 0 0 rgba(2,122,72,.45); }}
    70%  {{ box-shadow: 0 0 0 7px rgba(2,122,72,0); }}
    100% {{ box-shadow: 0 0 0 0 rgba(2,122,72,0); }}
}}

/* ── 예시 카드 ────────────────────────────────────────── */
.fr-example-card {{
    border:1px solid rgba(15,23,42,.06); border-radius:18px; padding:22px 24px;
    background:#FFFFFF; height:100%; transition: all .2s cubic-bezier(.22,.98,.35,1); cursor:pointer;
    box-shadow: 0 1px 2px rgba(15,23,42,.03), 0 4px 14px rgba(15,23,42,.04);
}}
.fr-example-card:hover {{
    border-color:{나_색}55; transform: translateY(-3px);
    box-shadow:0 12px 28px rgba(79,70,229,0.16);
}}
.fr-example-q {{ font-size:1.06rem; color:#1E293B; line-height:1.55; min-height:4.8em; font-weight:500; }}

/* ── 되묻기 칩 ────────────────────────────────────────── */
.fr-chip {{
    display:inline-block; padding:7px 16px; border-radius:999px;
    border:1px solid #E2E4F5; background:#F8F8FE; font-size:0.95rem; font-weight:500;
    margin:2px 4px 2px 0; cursor:pointer; transition:.15s;
}}
.fr-chip:hover {{ border-color:{나_색}; color:{나_색}; background:{나_색}0D; }}

/* ── 과실비율 히어로 스탯 ────────────────────────────── */
.fr-ratio-hero {{ display:flex; gap:14px; align-items:stretch; margin:8px 0 4px 0; }}
.fr-ratio-side {{ flex:1; border-radius:18px; padding:22px 16px; text-align:center; }}
.fr-side-a {{ background:linear-gradient(160deg,#E6F5F3,#F5FBFA); border:1px solid #BFE6E1; }}
.fr-side-b {{ background:linear-gradient(160deg,#FDF1E0,#FFFAF2); border:1px solid #F6DAA6; }}
.fr-ratio-role {{ font-size:0.95rem; color:#64748B; font-weight:600; margin-bottom:6px; }}
.fr-ratio-num {{ font-size:2.8rem; font-weight:800; line-height:1; letter-spacing:-.02em; }}
.fr-side-a .fr-ratio-num {{ color:{나_색}; }}
.fr-side-b .fr-ratio-num {{ color:{상대_색}; }}
.fr-ratio-vs {{ align-self:center; font-weight:700; color:#C4C9DA; font-size:1.2rem; }}

/* ── 섹션 제목 ────────────────────────────────────────── */
.fr-section-title {{
    font-size:1.22rem; font-weight:800; margin: 6px 0 14px 0; color:#0F172A; letter-spacing:-.01em;
    display:flex; align-items:center; gap:8px;
}}

/* ── 면책 문구 ────────────────────────────────────────── */
.fr-disclaimer {{
    font-size:0.86rem; color:#94A3B8; border-top:1px solid rgba(15,23,42,.06);
    padding-top:10px; margin-top:18px;
}}

/* ── 마스코트 말풍선 ──────────────────────────────────── */
.fr-mascot-row {{ display:flex; align-items:flex-start; gap:14px; margin:14px 0 22px 0; }}
.fr-mascot-avatar {{
    font-size:2.1rem; line-height:1; flex-shrink:0;
    width:58px; height:58px; display:flex; align-items:center; justify-content:center;
    background: linear-gradient(135deg, {나_색}14, {나_색2}14);
    border-radius:50%; box-shadow: 0 2px 10px rgba(79,70,229,.12);
}}
.fr-mascot-bubble {{
    position:relative; background:#FFFFFF; border:1px solid rgba(15,23,42,.06);
    border-radius:18px; padding:14px 18px; font-size:1.0rem; color:#1E293B;
    line-height:1.65; word-break:keep-all; overflow-wrap:normal;
    box-shadow: 0 4px 16px rgba(15,23,42,.06); max-width:680px;
}}
.fr-mascot-bubble::before {{
    content:''; position:absolute; left:-8px; top:20px;
    border-width:8px 8px 8px 0; border-style:solid;
    border-color:transparent rgba(15,23,42,.06) transparent transparent;
}}
.fr-mascot-bubble::after {{
    content:''; position:absolute; left:-6px; top:21px;
    border-width:7px 7px 7px 0; border-style:solid;
    border-color:transparent #FFFFFF transparent transparent;
}}

/* ── 지식베이스 카드 ─────────────────────────────────── */
.fr-kb-card {{
    border:1px solid rgba(15,23,42,.06); border-radius:16px; padding:18px 22px;
    margin-bottom:12px; background:#FFFFFF; transition: box-shadow .2s, transform .2s;
    box-shadow: 0 1px 2px rgba(15,23,42,.03), 0 4px 14px rgba(15,23,42,.04);
}}
.fr-kb-card:hover {{ box-shadow: 0 8px 22px rgba(15,23,42,.08); transform: translateY(-1px); }}
.fr-kb-title {{ font-weight:700; font-size:1.1rem; color:#0F172A; }}
.fr-kb-meta {{ font-size:0.86rem; color:#94A3B8; }}

/* ── NiceGUI 기본 위젯 톤 맞추기 ──────────────────────── */
.q-field {{ border-radius: 14px !important; }}
.q-field__control {{ border-radius: 14px !important; }}
/* ── 채팅 말풍선 (카카오톡 스타일) ──────────────────────
   ui.chat_message(Quasar QChatMessage)의 내부 클래스가 난독화된 번들에서
   추정하기 어렵고 실제로 두 번이나 틀렸어서, 우리가 직접 만든 div로
   완전히 통제 가능하게 바꿨습니다 — 관련 컴포넌트는 theme.chat_bubble(). */
.fr-chat-bubble {{
    padding: 10px 14px; border-radius: 16px; font-size: 0.92rem; line-height: 1.5;
    word-break: break-word;
}}
.fr-chat-bubble.sent {{ background:{나_색}; color:#fff; border-bottom-right-radius:4px; }}
.fr-chat-bubble.received {{ background:#F1F5F9; color:#1E293B; border-bottom-left-radius:4px; }}
.fr-chat-name {{ font-size:0.76rem; color:#94A3B8; margin-bottom:3px; }}
.q-btn {{ border-radius: 12px !important; text-transform: none !important; font-weight: 600 !important; }}
.fr-btn-primary {{
    background: linear-gradient(135deg, {나_색}, {나_색2}) !important; color:white !important;
    font-weight:700 !important; box-shadow: 0 6px 18px rgba(79,70,229,.32) !important;
    transition: transform .15s, box-shadow .15s !important;
}}
.fr-btn-primary:hover {{ transform: translateY(-1px); box-shadow: 0 10px 24px rgba(79,70,229,.4) !important; }}

/* NiceGUI 기본 배경(회색 톤)을 우리 배경과 맞추기 */
.q-page, body.body--light {{ background: transparent !important; }}
"""


def brand_icon_svg(size: int = 20) -> str:
    """탐정 마스코트 일러스트 아이콘(SVG) — 내비바/히어로 등에서 공용으로 씁니다."""
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        'xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="12" cy="9" r="5.2" fill="#FFFFFF" fill-opacity="0.95"/>'
        '<path d="M9 8.4c.6-1.2 1.8-1.8 3-1.5" stroke="#0F172A" stroke-width="1" '
        'stroke-linecap="round"/>'
        '<circle cx="10.1" cy="9.2" r="0.9" fill="#0F172A"/>'
        '<circle cx="13.4" cy="9.2" r="0.9" fill="#0F172A"/>'
        '<path d="M9.6 11.6c.7.6 2.1.6 2.8 0" stroke="#0F172A" stroke-width="1" '
        'stroke-linecap="round"/>'
        '<path d="M4.5 20c.6-3.4 3.4-5.6 7.5-5.6s6.9 2.2 7.5 5.6" '
        'stroke="#FFFFFF" stroke-width="1.6" stroke-linecap="round" fill="none"/>'
        '<circle cx="18.3" cy="16.3" r="2.6" stroke="#FFFFFF" stroke-width="1.4" '
        'fill="#1E293B"/>'
        '<line x1="20.1" y1="18.1" x2="21.6" y2="19.6" stroke="#FFFFFF" '
        'stroke-width="1.4" stroke-linecap="round"/>'
        "</svg>"
    )


def inject_head() -> None:
    """앱 시작 시 딱 한 번 호출 — 폰트/전역 CSS를 head에 심습니다."""
    ui.add_head_html(f"<style>{_GLOBAL_CSS}</style>")
    ui.colors(primary=나_색)


def top_nav(active: str) -> None:
    with ui.element("div").classes("fr-topbar"):
        ui.html(
            '<div class="fr-topbar-brand">'
            f'<span class="fr-topbar-icon">{brand_icon_svg(20)}</span>'
            "사고 과실 비율 AI 가이드"
            "</div>"
        )
        with ui.element("div").classes("fr-topnav"):
            for page_id, emoji, label, target in NAV_PAGES:
                cls = "fr-topnav-link active" if page_id == active else "fr-topnav-link"
                ui.link(f"{emoji} {label}", target).classes(cls)
        with ui.element("div").classes("fr-topbar-right"):
            from nicegui import app as _app

            username = _app.storage.user.get("username", "")
            ui.html(f'<span>👤 {username}</span>')

            def _logout() -> None:
                from webapp.auth import logout

                logout()

            ui.html('<span style="cursor:pointer;">로그아웃</span>').on("click", _logout)


def footer() -> None:
    ui.html(
        '<div class="fr-footer">'
        '<div><a href="#">이용약관</a><a href="#">개인정보처리방침</a><a href="#">자주 묻는 질문</a></div>'
        '<div>© 2026 과실비율 상담 팀 프로젝트 · 참고용 서비스입니다</div>'
        "</div>"
    )


@contextmanager
def page_frame(active: str):
    """페이지 함수 맨 위에서 `with theme.page_frame('consult') as main:` 로 감싸면
    상단 네비바 + 본문 레이아웃(+하단 푸터)이 자동으로 구성됩니다. 본문 콘텐츠는
    이 with 블록 안에서 그대로 이어서 그리면 됩니다."""
    with ui.element("div").classes("fr-shell"):
        top_nav(active)
        with ui.element("div").classes("fr-main") as main:
            yield main
        footer()


def hero(title: str, subtitle: str, badge_html: str = "") -> None:
    badge = f'<div class="fr-hero-badge">{badge_html}</div>' if badge_html else ""
    ui.html(
        f'<div class="fr-hero">'
        f"{badge}"
        f'<h1><span class="fr-hero-icon">{brand_icon_svg(26)}</span>{title}</h1>'
        f"<p>{subtitle}</p>"
        f"</div>"
    )


def mascot_say(text: str, emoji: str = "🕵️") -> None:
    ui.html(
        f'<div class="fr-mascot-row">'
        f'<div class="fr-mascot-avatar">{emoji}</div>'
        f'<div class="fr-mascot-bubble">{text}</div>'
        f"</div>"
    )


def chat_bubble(name: str, sent: bool):
    """카카오톡처럼 sent(나)는 오른쪽, received(AI)는 왼쪽에 붙는 말풍선.

    ``with theme.chat_bubble("나", sent=True): ui.label(...)`` 형태로 씁니다.
    반환값은 말풍선 본문 div라서, 나중에 ``bubble.clear()`` 후 다시 채워
    "로딩 중 → 답변" 갱신도 그대로 가능합니다.
    """
    side = "flex-end" if sent else "flex-start"
    with ui.row().classes("w-full no-wrap").style(f"justify-content:{side}; margin-bottom:10px;"):
        with ui.column().classes("gap-0").style(f"max-width:74%; align-items:{side};"):
            ui.label(name).classes("fr-chat-name")
            bubble = ui.element("div").classes(
                f"fr-chat-bubble {'sent' if sent else 'received'}"
            )
    return bubble


def status_pill_html(ok: bool, on_label: str, off_label: str) -> str:
    cls = "fr-status-on" if ok else "fr-status-off"
    dot = "#22C55E" if ok else "#F59E0B"
    label = on_label if ok else off_label
    return (
        f'<span class="fr-status-pill {cls}">'
        f'<span class="fr-dot" style="background:{dot}"></span>{label}</span>'
    )


def confidence_badge_html(level: str) -> str:
    bg, fg = _BADGE_STYLE.get(level, ("#E2E8F0", "#334155"))
    return f'<span class="fr-badge" style="background:{bg};color:{fg}">신뢰도 {level}</span>'


def confidence_from_score(score: float) -> str:
    if score >= 0.45:
        return "높음"
    if score >= 0.25:
        return "보통"
    return "낮음"


def ratio_hero_html(a: int, b: int, role_a: str = "", role_b: str = "") -> str:
    label_a = f"나 · {role_a}" if role_a and role_a not in ("나", "본인") else "나"
    label_b = f"상대 · {role_b}" if role_b and role_b not in ("상대",) else "상대"
    return (
        '<div class="fr-ratio-hero">'
        f'<div class="fr-ratio-side fr-side-a">'
        f'<div class="fr-ratio-role">{label_a}</div>'
        f'<div class="fr-ratio-num">{a}%</div></div>'
        '<div class="fr-ratio-vs">VS</div>'
        f'<div class="fr-ratio-side fr-side-b">'
        f'<div class="fr-ratio-role">{label_b}</div>'
        f'<div class="fr-ratio-num">{b}%</div></div>'
        "</div>"
    )


def disclaimer() -> None:
    ui.html(
        '<div class="fr-disclaimer">⚠️ 이 서비스는 참고용 안내이며 법적 효력이 없습니다. '
        "최종 과실비율은 보험사·법원의 판단에 따라 달라질 수 있습니다.</div>"
    )


def consult_report_text(result: dict, final_ratio: dict, applied_names: list[str]) -> str:
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


_GAUGE_JS = """
() => {
  const svg = document.getElementById('%(id)s');
  if (!svg) return;
  const circle = svg.querySelector('.fr-gauge-fg');
  const r = 80, circumference = 2 * Math.PI * r;
  const pct = %(a)s;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      circle.style.strokeDashoffset = circumference * (1 - pct / 100);
    });
  });
}
"""


def fault_gauge(container, a: int, b: int, role_a: str, role_b: str, gauge_id: str) -> None:
    """원형 과실비율 게이지 (SVG + CSS transition으로 애니메이션 — React/iframe 불필요).

    Streamlit 버전은 iframe 안에서 React를 돌려야 했지만(components.v1.html), NiceGUI는
    진짜 DOM이라 SVG를 직접 그리고 stroke-dashoffset을 자바스크립트 한 줄로 갱신하는
    것만으로 똑같은 애니메이션이 됩니다.
    """
    container.clear()
    r, cx, cy = 80, 100, 100
    circumference = 2 * 3.14159265 * r
    with container:
        ui.html(f"""
        <div style="display:flex;flex-direction:column;align-items:center;">
          <svg id="{gauge_id}" width="220" height="220" viewBox="0 0 200 200">
            <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#FFE4E4" stroke-width="16"/>
            <circle class="fr-gauge-fg" cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{나_색}"
                    stroke-width="16" stroke-dasharray="{circumference}"
                    stroke-dashoffset="{circumference}" stroke-linecap="round"
                    transform="rotate(-90 100 100)"
                    style="transition: stroke-dashoffset 0.9s cubic-bezier(.22,.98,.35,1)"/>
            <text x="100" y="96" text-anchor="middle" font-size="34" font-weight="800"
                  fill="{나_색}">{a}%</text>
            <text x="100" y="120" text-anchor="middle" font-size="12" fill="#94A3B8">나의 과실비율</text>
          </svg>
          <div style="display:flex;gap:18px;margin-top:8px;font-size:13px;">
            <div style="color:{나_색};font-weight:700;">나({role_a}) {a}%</div>
            <div style="color:{상대_색};font-weight:700;">상대({role_b}) {b}%</div>
          </div>
        </div>
        """)
    ui.run_javascript(_GAUGE_JS % {"id": gauge_id, "a": a})
