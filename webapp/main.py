"""NiceGUI 대시보드 진입점.

실행 (프로젝트 루트에서):
    python -m webapp.main

Streamlit 버전(`woo/`)과 기능은 동일하고(홈/상담/영상분석/지식베이스), UI 레이어만
NiceGUI(진짜 Vue/Quasar 기반 웹앱)로 새로 짰습니다. 백엔드 호출·검색·CV 로직은
`webapp/services/*`에서 기존 `services/cv`, `taek`, `ryeol` 코드를 그대로 재사용합니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nicegui import app, ui  # noqa: E402

from webapp.pages import consult, home, kb, login, video  # noqa: E402,F401 — @ui.page 데코레이터 등록용

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.add_static_files("/static", str(STATIC_DIR))

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="사고 과실 비율 AI 가이드",
        favicon="🚦",
        port=8700,
        reload=False,
        storage_secret="fault-ratio-dashboard-dev-secret",
    )
