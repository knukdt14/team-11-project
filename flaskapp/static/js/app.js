// 과실비율 대시보드 — 전부 실데이터/실API 연동. mock 데이터 없음.

const BACKEND_URL = window.BACKEND_URL || "http://localhost:8000";

// ── 라우팅 ──────────────────────────────────────────────────────
const routes = ['home', 'consult', 'video', 'kb', 'stats'];
function go(route) {
  if (!routes.includes(route)) route = 'home';
  routes.forEach(r => document.getElementById('screen-' + r).classList.toggle('active', r === route));
  document.querySelectorAll('.nav .tabs button').forEach(b => b.classList.toggle('active', b.dataset.route === route));
  localStorage.setItem('route', route);
  window.scrollTo(0, 0);
  if (route === 'kb' && !kbLoaded) loadKbSources().then(loadKbGrid);
  if (route === 'stats' && !statsLoaded) loadStats();
}
document.querySelectorAll('[data-route]').forEach(el => {
  el.addEventListener('click', () => {
    if (el.dataset.fill) { document.getElementById('chatInput').value = el.dataset.fill; }
    go(el.dataset.route);
    if (el.dataset.fill) sendMsg(el.dataset.fill);
  });
});
go(localStorage.getItem('route') || 'home');

// ── 테마 토글 ───────────────────────────────────────────────────
const themeBtn = document.getElementById('themeToggle');
function applyTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  themeBtn.textContent = t === 'dark' ? '☀️' : '🌙';
  localStorage.setItem('theme', t);
}
applyTheme(localStorage.getItem('theme') || 'light');
themeBtn.addEventListener('click', () => {
  const cur = document.documentElement.getAttribute('data-theme');
  applyTheme(cur === 'dark' ? 'light' : 'dark');
});

// ── 백엔드 상태 배지 ────────────────────────────────────────────
async function checkBackend() {
  const badge = document.getElementById('backendBadge');
  try {
    const r = await fetch(`${BACKEND_URL}/health`, { signal: AbortSignal.timeout(3000) });
    if (!r.ok) throw new Error('not ok');
    badge.classList.remove('off');
    badge.innerHTML = '<span class="dot"></span> 백엔드 연결됨';
  } catch (e) {
    badge.classList.add('off');
    badge.innerHTML = '<span class="dot"></span> 백엔드 연결 안 됨 (ryeol FastAPI를 8000번 포트로 켜주세요)';
  }
}
checkBackend();

// ── 홈 통계 (실데이터) ──────────────────────────────────────────
fetch('/api/stats').then(r => r.json()).then(s => {
  const grid = document.getElementById('homeStatGrid');
  grid.children[0].querySelector('.num').textContent = s.diagram_count + '건';
  grid.children[1].querySelector('.num').textContent = s.precedent_count + '건';
  grid.children[2].querySelector('.num').textContent = s.law_count + '개';
  document.getElementById('homePill').textContent = `✦ AI 기반 · 공식 인정기준 ${s.diagram_count}건 학습`;
}).catch(() => {});

// ═══════════════════════════════════════════════════════════════
// 상담
// ═══════════════════════════════════════════════════════════════
let sessionId = null;
let currentResult = null;
let appliedMods = new Set();

const chatLog = document.getElementById('chatLog');
function addMsg(text, cls) {
  const d = document.createElement('div');
  d.className = 'msg ' + cls;
  d.textContent = text;
  chatLog.appendChild(d);
  chatLog.scrollTop = chatLog.scrollHeight;
  return d;
}

async function sendMsg(text) {
  if (!text || !text.trim()) return;
  addMsg(text, 'user');
  document.getElementById('followupChips').innerHTML = '';
  const loadingMsg = addMsg('생각 중...', 'bot');

  // ⚠️ 상태에 따라 완전히 다른 백엔드 엔드포인트를 타야 합니다 — 셋을 하나로
  // 뭉치면(전부 /consult로 보내면) 되묻기 답변이 "새 질문"으로 취급되어 이전
  // 맥락(사고설명)을 잃어버립니다. ryeol/app/service.py 계약 기준:
  //   최초 질문                        → POST /consult
  //   되묻기(needs_information/not_found) 답변 → POST /consult/additional-info (맥락 이어붙임)
  //   complete 이후의 반박/추가질문      → POST /follow-up (숫자는 안 바뀌고 설명만 옴)
  const needsInfo = currentResult && (currentResult.status === 'needs_information' || currentResult.status === 'not_found');
  const isFollowUp = currentResult && currentResult.status === 'complete';

  try {
    let resp, data;
    if (isFollowUp) {
      resp = await fetch(`${BACKEND_URL}/follow-up`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, 질문: text }),
      });
      data = await resp.json();
      loadingMsg.remove();
      addMsg(data.답변, 'bot');
      return;  // 결과 패널(과실비율)은 그대로 — 후속질문은 숫자를 안 바꿈
    }

    if (needsInfo) {
      resp = await fetch(`${BACKEND_URL}/consult/additional-info`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, 추가정보: text, 적용할_수정요소: Array.from(appliedMods) }),
      });
    } else {
      resp = await fetch(`${BACKEND_URL}/consult`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 사고설명: text, 상담자측: 'A', session_id: sessionId }),
      });
    }
    data = await resp.json();
    loadingMsg.remove();
    sessionId = data.session_id;
    currentResult = data;
    appliedMods = new Set((data.적용_수정요소 || []).map(m => m.id));

    if (data.status === 'not_found') {
      addMsg(data.경고 || '해당 기준을 찾을 수 없습니다.', 'bot');
      renderFollowupChips(data.되묻기);
      renderEmptyResult('해당 기준을 찾을 수 없습니다. 다르게 설명해보시겠어요?');
      return;
    }
    if (data.status === 'needs_information') {
      addMsg('조금만 더 알려주시면 정확히 계산해드려요.', 'bot');
      renderFollowupChips(data.되묻기);
      renderEmptyResult('추가 정보를 알려주시면 계산해드려요.');
      return;
    }
    addMsg(data.답변 || `${data.도표번호} 기준으로 결과를 정리했어요. 우측을 확인해주세요.`, 'bot');
    renderConsultResult(data);
  } catch (e) {
    loadingMsg.remove();
    addMsg('⚠️ 백엔드 호출에 실패했습니다: ' + e.message, 'bot');
  }
}

function renderFollowupChips(questions) {
  const row = document.getElementById('followupChips');
  row.innerHTML = '';
  (questions || []).forEach(q => {
    const c = document.createElement('span');
    c.className = 'chip';
    c.textContent = q;
    c.addEventListener('click', () => sendMsg(q));
    row.appendChild(c);
  });
}

function renderEmptyResult(text) {
  document.getElementById('resultPanel').innerHTML = `<div class="empty-state">${text}</div>`;
}

function donutHtml(a, b) {
  // 가로로 긴 스택 막대바 — 도넛+좁은 워터폴 조합이 옆에 빈 공간을 많이 남겨서
  // 폭 전체를 쓰는 막대 하나로 바꿨습니다 (숫자는 막대 안/밖에 크게 표시).
  const aLabel = a >= 12 ? `<span class="rb-label">A(나) ${a}%</span>` : '';
  const bLabel = b >= 12 ? `<span class="rb-label">B(상대) ${b}%</span>` : '';
  return `
    <div class="ratio-bar">
      <div class="ratio-bar-fill a" style="width:${a}%">${aLabel}</div>
      <div class="ratio-bar-fill b" style="width:${b}%">${bLabel}</div>
    </div>
    <div class="ratio-bar-caption">
      <span><i class="dot-a"></i>A차량(나) ${a}%</span>
      <span><i class="dot-b"></i>B차량(상대) ${b}%</span>
    </div>
  `;
}

function waterfallHtml(steps) {
  if (!steps || !steps.length) return '<div class="empty-state">계산 단계 없음</div>';
  const rows = steps.map((s, i) => {
    let cls = '';
    if (i > 0) {
      const delta = s.값 - steps[i - 1].값;
      cls = delta > 0 ? 'plus' : (delta < 0 ? 'minus' : '');
    }
    const sign = i > 0 && (s.값 - steps[i - 1].값) > 0 ? '+' : '';
    return `<div class="wf-row"><span class="wf-label">${s.라벨}</span><span class="wf-val ${cls}">${i === 0 ? s.값 : sign + (s.값 - steps[i-1].값)}</span></div>`;
  });
  return rows.join('');
}

function modifierRow(m) {
  const checked = appliedMods.has(m.id) ? 'checked' : '';
  const cls = appliedMods.has(m.id) ? 'checked' : '';
  const sign = m.값 >= 0 ? '+' : '';
  return `<label class="modifier ${cls}"><input type="checkbox" data-mod-id="${m.id}" ${checked}> ${m.조건} (${sign}${m.값})</label>`;
}

function lawCardsHtml(laws) {
  if (!laws || !laws.length) return '';
  const items = laws.map(l => `
    <div class="panel" style="padding:12px 14px;margin-bottom:8px;">
      <b style="font-size:13px;">${l.조 || '조문'} ${l.제목 || ''}</b>
      ${l.시행중 === false ? '<span class="badge ref" style="margin-left:6px;">현재 미시행</span>' : ''}
      <p style="font-size:12.5px;color:var(--text-2);margin-top:6px;">${l.내용 || ''}</p>
    </div>
  `).join('');
  return `<h3>📜 관련 법규</h3>${items}`;
}

function caseCardsHtml(cases) {
  if (!cases || !cases.length) return '';
  const items = cases.map(c => {
    const 기본 = c.기본비율, 결정 = c.결정비율;
    return `
    <div class="panel" style="padding:12px 14px;margin-bottom:8px;">
      <b style="font-size:13px;">${c.제목 || '심의사례'}</b> <span class="badge ref">참고용</span>
      <p style="font-size:12px;color:var(--text-3);margin-top:6px;">청구인측: ${c.A_당사자 || '-'} · 피청구인측: ${c.B_당사자 || '-'}</p>
      ${기본 ? `<p style="font-size:12.5px;color:var(--text-2);">기본비율: A ${기본.A}% : B ${기본.B}%</p>` : ''}
      ${결정 ? `<p style="font-size:12.5px;color:var(--text-2);">실제 결정비율: A ${결정.A}% : B ${결정.B}%</p>` : ''}
      ${c.비율_달라짐 ? '<p style="font-size:11.5px;color:var(--yellow-700);">⚠️ 기본비율과 결정비율이 다른 사례입니다 — 다른 사정이 반영됐을 수 있어요.</p>' : ''}
    </div>
  `;
  }).join('');
  return `<h3>⚖️ 유사사례 (심의사례)</h3>${items}`;
}

function renderConsultResult(data) {
  const 후보목록 = (data.후보 || []).slice(0, 5);
  const compareRows = 후보목록.map(c => `
    <tr><td>${c.도표번호 || ''}</td><td>${c.제목 || ''}</td><td class="num">${(c.검색점수 || 0).toFixed(2)}</td></tr>
  `).join('');

  const 전체수정요소 = [...(data.적용_수정요소 || []), ...(data.미적용_수정요소 || [])];
  const modifierHtml = 전체수정요소.length
    ? `<div class="modifier-grid">${전체수정요소.map(modifierRow).join('')}</div>`
    : '<p class="helper-note">이 기준에는 수정요소가 없습니다.</p>';

  document.getElementById('resultPanel').innerHTML = `
    <div class="panel">
      <div class="breadcrumb">${(data.사고유형 && data.사고유형.대) || ''} &rsaquo; ${data.출처 || ''} &rsaquo;
        <b>${data.제목 || ''}</b> · <span class="badge official">공식 기준 · 도표 ${data.도표번호 || ''}</span>
      </div>

      <div class="donut-waterfall">
        <div id="donutWrap">${donutHtml(data.최종과실.A, data.최종과실.B)}</div>
        <div class="waterfall" id="waterfallWrap">${waterfallHtml(data.계산_단계)}</div>
      </div>

      ${data.image_url ? `
      <h3>📄 근거 도표</h3>
      <div style="text-align:center;margin-bottom:22px;">
        <img src="${BACKEND_URL}${data.image_url}" style="max-width:100%;border-radius:10px;border:1px solid var(--border);">
        ${data.pdf_page ? `<p style="font-size:11.5px;color:var(--text-3);margin-top:6px;">출처 p.${data.pdf_page}</p>` : ''}
      </div>` : ''}

      ${후보목록.length ? `
      <h3>유사 도표 비교</h3>
      <table class="fault-table">
        <thead><tr><th>도표번호</th><th>제목</th><th>관련도</th></tr></thead>
        <tbody>${compareRows}</tbody>
      </table>` : ''}

      <h3>수정요소</h3>
      <div id="modifierWrap">${modifierHtml}</div>
      <p class="helper-note">체크박스 클릭 시 즉시 재계산 (LLM 재호출 없음)</p>

      ${data.답변 ? `<div class="ai-note">💡 <span>${data.답변}</span></div>` : ''}
      <span class="badge ref">참고용 · 최종 판단은 보험사·법원 소관</span>
      ${data.신뢰도 ? `<span class="badge" style="margin-left:6px;background:var(--surface-2);color:var(--text-2)">신뢰도 ${data.신뢰도}</span>` : ''}

      ${lawCardsHtml(data.법조항)}
      ${caseCardsHtml(data.유사사례)}
      ${data.판례 && data.판례.length ? `<p style="font-size:12px;color:var(--text-3);margin-top:14px;">참조 판례: ${data.판례.join(', ')}</p>` : ''}
    </div>
  `;

  document.querySelectorAll('#modifierWrap input[type=checkbox]').forEach(cb => {
    cb.addEventListener('change', async (e) => {
      const id = e.target.dataset.modId;
      if (e.target.checked) appliedMods.add(id); else appliedMods.delete(id);
      await recalc();
    });
  });
}

async function recalc() {
  if (!sessionId) return;
  const resp = await fetch(`${BACKEND_URL}/recalculate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, 적용할_수정요소: Array.from(appliedMods) }),
  });
  const data = await resp.json();
  document.getElementById('donutWrap').innerHTML = donutHtml(data.최종과실.A, data.최종과실.B);
  document.getElementById('waterfallWrap').innerHTML = waterfallHtml(data.계산_단계);
  document.querySelectorAll('#modifierWrap .modifier').forEach(el => {
    const id = el.querySelector('input').dataset.modId;
    el.classList.toggle('checked', appliedMods.has(id));
  });
}

document.getElementById('chatSend').addEventListener('click', () => {
  const inp = document.getElementById('chatInput');
  sendMsg(inp.value); inp.value = '';
});
document.getElementById('chatInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { sendMsg(e.target.value); e.target.value = ''; }
});

// ═══════════════════════════════════════════════════════════════
// 지식베이스
// ═══════════════════════════════════════════════════════════════
let kbLoaded = false;
let kbKind = 'standard';
let kbSource = '';
let kbOffset = 0;
let kbSearchQuery = '';   // 비어있으면 일반 둘러보기, 있으면 검색 결과 모드
const KB_PAGE = 30;

async function loadKbSources() {
  const wrap = document.getElementById('kbSourceChips');
  wrap.innerHTML = '<span class="tree-chip active" data-source="">전체</span>';
  const sources = await (await fetch(`/api/kb/sources?kind=${encodeURIComponent(kbKind)}`)).json();
  sources.forEach(s => {
    const chip = document.createElement('span');
    chip.className = 'tree-chip';
    chip.textContent = s.label;
    chip.dataset.source = s.id;
    chip.addEventListener('click', () => {
      wrap.querySelectorAll('.tree-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      kbSource = s.id;
      kbOffset = 0;
      document.getElementById('kbGrid').innerHTML = '';
      loadKbGrid();
    });
    wrap.appendChild(chip);
  });
  wrap.querySelector('[data-source=""]').addEventListener('click', () => {
    wrap.querySelectorAll('.tree-chip').forEach(c => c.classList.remove('active'));
    wrap.querySelector('[data-source=""]').classList.add('active');
    kbSource = '';
    kbOffset = 0;
    document.getElementById('kbGrid').innerHTML = '';
    loadKbGrid();
  });
}

// 종류(기준도표/도로교통법/심의사례) 탭 — 이전엔 standards()가 kind=='standard'만
// 줘서 법령·심의사례가 지식베이스에 아예 안 보였던 것을 여기서 고쳤습니다.
document.querySelectorAll('#kbKindChips .tree-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    document.querySelectorAll('#kbKindChips .tree-chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    kbKind = chip.dataset.kind;
    kbSource = '';
    kbOffset = 0;
    kbSearchQuery = '';
    document.getElementById('kbSearchInput').value = '';
    document.getElementById('kbSearchStatus').style.display = 'none';
    document.getElementById('kbSearchClear').style.display = 'none';
    document.getElementById('kbGrid').innerHTML = '';
    loadKbSources().then(loadKbGrid);
  });
});

function kbCardHtml(item) {
  const r = item.base_ratio || {};
  let thumb;
  if (item.image_path) {
    thumb = `<img src="/media/${item.image_path}" style="width:100%;height:110px;object-fit:cover;border-radius:8px;">`;
  } else if (item.kind === 'standard') {
    thumb = `<svg viewBox="0 0 200 90" width="100%"><rect width="200" height="90" fill="var(--surface)"/><rect x="10" y="40" width="180" height="4" fill="var(--border)"/><circle cx="40" cy="42" r="5" fill="var(--blue-500)"/><circle cx="160" cy="42" r="5" fill="var(--yellow-500)"/></svg>`;
  } else {
    // 법령/심의사례는 도표 이미지가 없으니 미리보기 텍스트로 대체.
    thumb = `<div style="height:110px;overflow:hidden;font-size:11px;color:var(--text-3);line-height:1.5;">${item.preview || ''}</div>`;
  }
  const meta = item.kind === 'standard'
    ? `${item.source_label} · 기본과실 A${r.a ?? '?'}:B${r.b ?? '?'}`
    : `${item.source_label}${item.kind === 'law' ? ' · 조문' : ' · 심의사례(참고용)'}`;
  const scoreBadge = item.score !== undefined ? `<span class="badge ref" style="margin-left:6px;">관련도 ${item.score}</span>` : '';
  return `
    <div class="kb-thumb">${thumb}</div>
    <div class="kb-body"><div class="kt">${item.diagram_no || ''}${scoreBadge}</div><div class="kn">${item.title || ''}</div>
    <div class="kr">${meta}</div></div>
  `;
}

async function loadKbGrid() {
  kbLoaded = true;
  const url = `/api/kb/list?kind=${encodeURIComponent(kbKind)}&source=${encodeURIComponent(kbSource)}&limit=${KB_PAGE}&offset=${kbOffset}`;
  const data = await (await fetch(url)).json();
  const grid = document.getElementById('kbGrid');
  data.items.forEach(item => {
    const card = document.createElement('div');
    card.className = 'kb-card';
    card.innerHTML = kbCardHtml(item);
    card.addEventListener('click', () => openKbModal(item.id));
    grid.appendChild(card);
  });
  kbOffset += data.items.length;
  document.getElementById('kbMoreBtn').style.display = kbOffset < data.total ? 'inline-flex' : 'none';
}
document.getElementById('kbMoreBtn').addEventListener('click', loadKbGrid);

// ── 통합 검색 (도표+법령+심의사례) ──────────────────────────────
async function runKbSearch() {
  const q = document.getElementById('kbSearchInput').value.trim();
  if (!q) return;
  kbSearchQuery = q;
  const status = document.getElementById('kbSearchStatus');
  status.style.display = 'block';
  status.textContent = '검색 중...';
  document.getElementById('kbSearchClear').style.display = 'inline-flex';
  document.getElementById('kbMoreBtn').style.display = 'none';

  const data = await (await fetch(`/api/kb/search?q=${encodeURIComponent(q)}`)).json();
  const grid = document.getElementById('kbGrid');
  grid.innerHTML = '';
  data.items.forEach(item => {
    const card = document.createElement('div');
    card.className = 'kb-card';
    card.innerHTML = kbCardHtml(item);
    card.addEventListener('click', () => openKbModal(item.id));
    grid.appendChild(card);
  });
  status.textContent = data.items.length
    ? `"${q}" 검색 결과 ${data.items.length}건 (도표+법령+심의사례 통합, 관련도순)`
    : `"${q}"에 해당하는 결과가 없습니다.`;
}
document.getElementById('kbSearchBtn').addEventListener('click', runKbSearch);
document.getElementById('kbSearchInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') runKbSearch(); });
document.getElementById('kbSearchClear').addEventListener('click', () => {
  kbSearchQuery = '';
  document.getElementById('kbSearchInput').value = '';
  document.getElementById('kbSearchStatus').style.display = 'none';
  document.getElementById('kbSearchClear').style.display = 'none';
  kbOffset = 0;
  document.getElementById('kbGrid').innerHTML = '';
  loadKbGrid();
});

async function openKbModal(id) {
  const s = await (await fetch(`/api/kb/${encodeURIComponent(id)}`)).json();
  if (s.error) return;

  if (s.kind === 'law') {
    document.getElementById('modalTitle').textContent = `${s.article_no} · ${s.title}`;
    document.getElementById('modalBody').innerHTML = `
      <p style="font-size:12px;color:var(--text-3);margin-bottom:10px;">${s.chapter || ''}${s.in_force === false ? ' · <span class="badge ref">현재 미시행</span>' : ''}</p>
      <p style="font-size:13.5px;color:var(--text-2);line-height:1.7;">${s.text || ''}</p>
      <span class="badge official" style="margin-top:14px;">도로교통법</span>
    `;
  } else if (s.kind === 'case') {
    const 기본 = s.base_ratio, 결정 = s.decision_ratio;
    document.getElementById('modalTitle').textContent = `${s.review_no || ''} · ${s.title || '심의사례'}`;
    document.getElementById('modalBody').innerHTML = `
      <p style="font-size:12px;color:var(--text-3);margin-bottom:10px;">청구인측: ${s.a_party || '-'} · 피청구인측: ${s.b_party || '-'}</p>
      ${기본 ? `<p style="font-size:13px;color:var(--text-2);">기본비율: A ${기본.a}% : B ${기본.b}%</p>` : ''}
      ${결정 ? `<p style="font-size:13px;color:var(--text-2);">결정비율: A ${결정.a}% : B ${결정.b}%</p>` : ''}
      ${s.accident_description ? `<p style="font-size:13px;color:var(--text-2);line-height:1.6;margin-top:8px;">${s.accident_description}</p>` : ''}
      ${s.decision_reason ? `<p style="font-size:12.5px;color:var(--text-3);margin-top:8px;">결정이유: ${s.decision_reason}</p>` : ''}
      <span class="badge ref" style="margin-top:14px;">참고용 · 계산에 사용 안 함</span>
    `;
  } else {
    document.getElementById('modalTitle').textContent = `${s.diagram_no} · ${s.title}`;
    const r = s.base_ratio || {};
    const mods = (s.modifiers || []).map(m =>
      `<li>${m.name} (${m.adjustment >= 0 ? '+' : ''}${m.adjustment}, 대상 ${m.target})</li>`
    ).join('');
    document.getElementById('modalBody').innerHTML = `
      ${s.image_path ? `<div style="text-align:center;margin-bottom:14px;"><img src="/media/${s.image_path}" style="max-width:100%;border-radius:10px;"></div>` : ''}
      <p style="font-size:13px;color:var(--text-2);margin-bottom:10px;">기본 과실비율: <b style="color:var(--text)">A ${r.a ?? '?'}% : B ${r.b ?? '?'}%</b></p>
      ${s.accident_description ? `<p style="font-size:13px;color:var(--text-2);line-height:1.6;">${s.accident_description}</p>` : ''}
      ${mods ? `<p style="font-size:12.5px;font-weight:700;margin-top:12px;">수정요소</p><ul style="font-size:12.5px;color:var(--text-2);padding-left:18px;">${mods}</ul>` : ''}
      ${s.laws && s.laws.length ? `<p style="font-size:12px;color:var(--text-3);margin-top:10px;">관련 법령: ${s.laws.join(', ')}</p>` : ''}
      <span class="badge official" style="margin-top:14px;">공식 기준</span>
    `;
  }
  document.getElementById('kbModal').classList.add('show');
}
document.getElementById('modalClose').addEventListener('click', () => document.getElementById('kbModal').classList.remove('show'));
document.getElementById('kbModal').addEventListener('click', (e) => { if (e.target.id === 'kbModal') e.target.classList.remove('show'); });

// ═══════════════════════════════════════════════════════════════
// 통계
// ═══════════════════════════════════════════════════════════════
let statsLoaded = false;
async function loadStats() {
  statsLoaded = true;
  const s = await (await fetch('/api/stats')).json();
  const grid = document.getElementById('statsGrid');
  grid.children[0].querySelector('.num').textContent = s.diagram_count + '건';
  grid.children[1].querySelector('.num').textContent = s.precedent_count + '건';
  grid.children[2].querySelector('.num').textContent = s.law_count + '개';
  grid.children[3].querySelector('.num').textContent = s.case_count + '건';

  renderBars('statsBySource', s.by_source);
  renderBars('statsByRatio', s.ratio_buckets);
}
function renderBars(elId, obj) {
  const wrap = document.getElementById(elId);
  const max = Math.max(1, ...Object.values(obj));
  wrap.innerHTML = Object.entries(obj).map(([label, v]) => `
    <div class="bar-col"><span class="bv">${v}</span><div class="bar" style="height:${(v / max) * 100}%"></div><span class="bl">${label}</span></div>
  `).join('');
}

// ═══════════════════════════════════════════════════════════════
// 영상 분석
// ═══════════════════════════════════════════════════════════════
const dropzone = document.getElementById('dropzone');
const videoInput = document.getElementById('videoInput');
const videoReselectWrap = document.getElementById('videoReselectWrap');
let videoLoaded = false;

// ⚠️ "영상 위 아무 곳이나 클릭하면 파일선택창이 열림" 버그 — e.target.tagName==='VIDEO'
// 체크만으로 video 자체 클릭을 걸러내려 했는데, 미리보기 텍스트·여백 클릭까지는
// 못 걸렀습니다(사용자 실측 확인). 클릭 대상을 하나하나 구분하는 대신, 영상이 이미
// 로드된 뒤에는 dropzone 클릭 자체를 완전히 무시하고, 대신 전용 "다른 영상 선택"
// 버튼(아래)으로만 파일선택창을 열게 분리했습니다 — 훨씬 확실합니다.
dropzone.addEventListener('click', () => {
  if (videoLoaded) return;
  videoInput.click();
});
dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('drag'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag'));
dropzone.addEventListener('drop', (e) => {
  e.preventDefault(); dropzone.classList.remove('drag');
  if (e.dataTransfer.files.length) { videoInput.files = e.dataTransfer.files; analyzeVideo(e.dataTransfer.files[0]); }
});
videoInput.addEventListener('change', () => { if (videoInput.files.length) analyzeVideo(videoInput.files[0]); });
document.getElementById('videoReselectBtn').addEventListener('click', () => videoInput.click());

function setVideoStep(activeIdx) {
  // ⚠️ 이전엔 (n, activeIdx) 두 파라미터라서, 스피너를 다음 단계로 옮기면서
  // n(막대 길이)을 같이 안 올려 진행바가 점보다 뒤처지는 버그가 있었습니다.
  // activeIdx 하나로 둘 다(막대 길이 + 완료 표시 + 스피너 위치) 계산해서
  // 절대 어긋나지 않게 합니다. activeIdx=-1이면 전부 완료.
  const steps = document.querySelectorAll('#videoStepLog .step');
  const doneCount = activeIdx === -1 ? steps.length : activeIdx;
  steps.forEach((s, i) => {
    s.classList.toggle('done', i < doneCount);
    s.innerHTML = (i === activeIdx) ? `<span class="spin"></span> ${s.dataset.label}` : s.dataset.label;
  });
  const fillTo = activeIdx === -1 ? steps.length : activeIdx + 1;
  document.getElementById('videoProgressFill').style.width = (fillTo / steps.length * 100) + '%';
}

function showVideoPreview(file) {
  const container = document.getElementById('dropzoneContent');
  container.innerHTML = '';
  videoLoaded = true;
  dropzone.style.cursor = 'default';
  videoReselectWrap.style.display = 'block';

  // ⚠️ innerHTML 문자열로 <video src="blob:...">를 박아넣는 방식 대신 DOM으로
  // 직접 만듭니다 — createElement + play()를 명시적으로 호출해야 play() 실패
  // (자동재생 정책, 코덱 미지원 등)를 .catch()/error 이벤트로 잡아서 사용자에게
  // 보여줄 수 있습니다. innerHTML의 autoplay 속성만 믿으면 실패해도 조용히
  // 아무 일도 안 일어나서 "재생 안 됨"이라고만 보이고 원인을 알 수 없었습니다.
  const video = document.createElement('video');
  video.src = URL.createObjectURL(file);
  video.controls = true;
  video.muted = true;
  video.style.cssText = 'max-width:100%;border-radius:10px;max-height:280px;';
  container.appendChild(video);

  const errNote = document.createElement('p');
  errNote.style.cssText = 'font-size:12px;color:var(--text-3);margin-top:6px;display:none;';
  container.appendChild(errNote);

  video.addEventListener('error', () => {
    errNote.style.display = 'block';
    errNote.textContent = '⚠️ 이 브라우저에서 이 영상 형식(코덱)을 재생하지 못합니다. 분석 자체는 계속 진행됩니다 — mp4(H.264) 파일이면 미리보기가 보통 잘 됩니다.';
  });
  video.play().catch(() => {
    // 자동재생이 막혀도(브라우저 정책) 큰 문제 아님 — controls로 직접 재생 누르면 됨.
    // 다만 완전히 조용히 넘어가지 않고, 재생 버튼을 눌러보라고 짧게 안내합니다.
    errNote.style.display = 'block';
    errNote.textContent = '▶ 재생 버튼을 눌러 미리보기를 시작하세요.';
  });
}

async function analyzeVideo(file) {
  document.getElementById('videoProgress').style.display = 'block';
  document.getElementById('videoResult').innerHTML = '';
  showVideoPreview(file);

  setVideoStep(1);

  const form = new FormData();
  form.append('video', file);

  try {
    const respPromise = fetch('/api/video/analyze', { method: 'POST', body: form });
    // 실제 서버 진행 신호가 없어서 대략적인 시점에 "검출·추적 → 충돌감지"로
    // 활성 스피너만 옮겨줍니다 (완료 표시는 절대 미리 안 함 — 응답 오면 한 번에).
    const t1 = setTimeout(() => setVideoStep(2), 4000);
    const resp = await respPromise;
    clearTimeout(t1);
    const data = await resp.json();
    setVideoStep(-1);

    if (data.error) {
      document.getElementById('videoResult').innerHTML = `<div class="panel"><p>⚠️ ${data.error}</p></div>`;
      return;
    }
    if (!data.is_accident) {
      document.getElementById('videoResult').innerHTML = `<div class="panel"><p>이 영상에서는 사고 신호를 찾지 못했어요.</p></div>`;
      return;
    }

    const frames = (data.frames || []).map(f =>
      `<img src="${f.url}" class="${f.is_impact ? 'impact' : ''}">`
    ).join('');

    let faultHtml = '';
    if (data.fault_error) {
      faultHtml = `
        <div class="panel" style="margin-top:14px;">
          <h3>⚖️ AI 과실비율 판정</h3>
          <p style="color:var(--text-2);font-size:13px;">⚠️ AI 판정을 지금 받아오지 못했습니다.</p>
          <p style="color:var(--text-3);font-size:11.5px;font-family:ui-monospace,monospace;">${data.fault_error}</p>
        </div>`;
    } else if (data.fault) {
      const f = data.fault;
      faultHtml = `
        <div class="panel" style="margin-top:14px;">
          <h3>⚖️ AI 과실비율 판정</h3>
          ${donutHtml(f.과실?.본인 ?? 0, f.과실?.상대 ?? 0)}
          <p><b>상황</b>: ${f.상황 || ''}</p>
          <p><b>근거 도표</b>: ${f.근거도표 || ''}</p>
          <p><b>설명</b>: ${f.설명 || ''}</p>
          <span class="badge ref">${f.주의 || '참고용'}</span>
        </div>`;
    }

    document.getElementById('videoResult').innerHTML = `
      <div class="panel">
        <p>✅ 사고 감지됨 — 충돌 순간: ${data.impact_frame}프레임</p>
        <h3>사고 근거 프레임</h3>
        <div class="frame-grid">${frames}</div>
      </div>
      ${faultHtml}
    `;
  } catch (e) {
    document.getElementById('videoResult').innerHTML = `<div class="panel"><p>⚠️ 분석 실패: ${e.message}</p></div>`;
  }
}
