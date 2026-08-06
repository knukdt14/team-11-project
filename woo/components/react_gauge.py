"""React로 만든 애니메이션 과실비율 게이지.

Node/npm 빌드 체인 없이 진짜 React를 쓰기 위해, React/ReactDOM UMD 번들을
`woo/static/vendor/`에 미리 받아 로컬로 vendoring 해두고(오프라인 Docker 시연 환경도
CDN 없이 동작), `React.createElement`(JSX 아님 — 트랜스파일러 불필요)로 컴포넌트를 작성해
`streamlit.components.v1.html()`의 iframe 안에서 실행합니다.

⚠️ 단방향입니다: Streamlit → iframe으로 현재 값만 매번 새로 넘겨서 다시 그립니다.
   (수정요소 토글 → Streamlit rerun → 이 함수가 새 a/b로 재호출 → React가 그 값으로
   0에서 애니메이션 재생) 진짜 양방향 커스텀 컴포넌트(`streamlit-component-lib`)는
   Node/npm 빌드가 필요해서, 표시 전용 위젯인 게이지에는 이 정도로 충분합니다.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit.components.v1 as components

_VENDOR = Path(__file__).resolve().parent.parent / "static" / "vendor"


def _read_vendor(name: str) -> str:
    return (_VENDOR / name).read_text(encoding="utf-8")


def react_fault_gauge(a: int, b: int, role_a: str, role_b: str, height: int = 300) -> None:
    """애니메이션 원형 과실비율 게이지를 React로 렌더링합니다."""
    react_js = _read_vendor("react.production.min.js")
    react_dom_js = _read_vendor("react-dom.production.min.js")

    # 문자열은 json.dumps로 이스케이프 — 사고 설명/역할명에 따옴표가 섞여도 안전하게.
    role_a_js = json.dumps(role_a)
    role_b_js = json.dumps(role_b)

    html = f"""
    <div id="root"></div>
    <style>
      html, body {{ margin:0; padding:0; font-family:-apple-system,"Segoe UI","Malgun Gothic",sans-serif; }}
    </style>
    <script>{react_js}</script>
    <script>{react_dom_js}</script>
    <script>
      const e = React.createElement;
      const A = {a};
      const B = {b};
      const ROLE_A = {role_a_js};
      const ROLE_B = {role_b_js};
      const COLOR_A = "#2E5BFF";
      const COLOR_B = "#FF6B6B";

      function Gauge() {{
        const [animated, setAnimated] = React.useState(0);
        React.useEffect(() => {{
          setAnimated(0);
          const raf1 = requestAnimationFrame(() => {{
            requestAnimationFrame(() => setAnimated(A));
          }});
          return () => cancelAnimationFrame(raf1);
        }}, [A]);

        const r = 80, cx = 100, cy = 100;
        const circumference = 2 * Math.PI * r;
        const offset = circumference * (1 - animated / 100);

        return e('div', {{style: {{display:'flex', flexDirection:'column', alignItems:'center'}}}},
          e('svg', {{width: 220, height: 220, viewBox: '0 0 200 200'}},
            e('circle', {{cx, cy, r, fill:'none', stroke:'#FFE4E4', strokeWidth:16}}),
            e('circle', {{
              cx, cy, r, fill:'none', stroke: COLOR_A, strokeWidth:16,
              strokeDasharray: circumference, strokeDashoffset: offset,
              strokeLinecap:'round', transform:'rotate(-90 100 100)',
              style: {{transition:'stroke-dashoffset 0.9s cubic-bezier(.22,.98,.35,1)'}}
            }}),
            e('text', {{x:100, y:96, textAnchor:'middle', fontSize:34, fontWeight:800, fill:COLOR_A}}, Math.round(animated) + '%'),
            e('text', {{x:100, y:120, textAnchor:'middle', fontSize:12, fill:'#94A3B8'}}, '나의 과실비율')
          ),
          e('div', {{style:{{display:'flex', gap:18, marginTop:8, fontSize:13}}}},
            e('div', {{style:{{color:COLOR_A, fontWeight:700}}}}, '나(' + ROLE_A + ') ' + A + '%'),
            e('div', {{style:{{color:COLOR_B, fontWeight:700}}}}, '상대(' + ROLE_B + ') ' + B + '%')
          )
        );
      }}

      const root = ReactDOM.createRoot(document.getElementById('root'));
      root.render(e(Gauge));
    </script>
    """
    components.html(html, height=height)
