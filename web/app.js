'use strict';
// Board: Goals and Bugs on GitHub. Every action goes through this app's own API (relative paths).
const el = id => document.getElementById(id);
const make = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
const filters = { type: 'all', state: 'open', accepted: 'any', repo: '' };
let me = null, board = null, repoList = [], openItem = null, loadGen = 0;

function say(text, kind = '') {
  const s = el('status');
  s.classList.toggle('wz-sr', !kind);
  s.classList.toggle('note', kind === 'note');
  s.textContent = text;
}
// Finishing actions confirm with the shell's toast (in-app note when there is no shell).
function toast(text) {
  let shown = false;
  try { shown = !!(window.WizardApp && WizardApp.shell && typeof WizardApp.shell.toast === 'function' && WizardApp.shell.toast('✓', text)); } catch (_) {}
  if (!shown) { say(text, 'note'); setTimeout(() => { if (el('status').textContent === text) say(''); }, 4000); }
}
async function api(path, data) {
  const init = data === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) };
  const r = await fetch(path, init);
  let body = {};
  try { body = await r.json(); } catch (_) {}
  if (!r.ok) { const e = new Error(body.error || 'Something went wrong. Try again.'); e.status = r.status; throw e; }
  return body;
}

// ---------- sign in ----------
function showSignedIn(on) {
  el('signin').hidden = on; el('board').hidden = !on; el('loading').hidden = true;
}
function renderAccount(s) {
  me = s;
  showSignedIn(s.connected);
  if (!s.connected) return;
  const a = s.account || {};
  el('acct-login').textContent = a.login || 'GitHub';
  el('acct-sub').textContent = [a.name, a.kind === 'fine-grained' ? 'Fine-grained token' : a.kind === 'classic' ? 'Classic token' : 'Token'].filter(Boolean).join(' · ');
  const img = el('avatar'); img.hidden = false; img.src = 'api/avatar?u=' + encodeURIComponent(a.login || ''); img.onerror = () => { img.hidden = true; };
  el('org').value = s.org;
  el('agent-note').textContent = s.agent_account ? `Agents use Board with ${s.agent_account}’s account; they may report bugs and comment, never open or close goals.` : '';
}
el('connect-form').onsubmit = async e => {
  e.preventDefault();
  const t = el('token'), b = el('connect');
  b.disabled = true; t.disabled = true; say('Checking with GitHub…', 'note');
  try { const s = await api('api/connect', { token: t.value }); t.value = ''; say(''); renderAccount(s); toast(`Connected as ${s.account.login}.`); await loadAll(); }
  catch (err) { say(err.message, 'error'); }
  finally { b.disabled = false; t.disabled = false; }
};
el('disconnect').onclick = () => {
  openSheet('Disconnect GitHub?', body => {
    body.append(make('p', 'bd-note', 'Board forgets your token on this box. Your issues on GitHub stay as they are.'));
    const row = make('div', 'wz-actions');
    const yes = make('button', 'wz-button destructive', 'Disconnect'); yes.type = 'button';
    const no = make('button', 'wz-button secondary', 'Cancel'); no.type = 'button';
    no.onclick = closeSheet;
    yes.onclick = () => run(yes, async () => { renderAccount(await api('api/disconnect', {})); closeSheet(); toast('GitHub disconnected.'); });
    row.append(yes, no); body.append(row);
  });
};
el('org-form').onsubmit = async e => {
  e.preventDefault();
  try { const r = await api('api/settings', { org: el('org').value }); me.org = r.org; filters.repo = ''; toast(`Showing ${r.org}.`); await loadAll(); }
  catch (err) { say(err.message, 'error'); }
};

// ---------- board ----------
function seg(id, key) {
  el(id).addEventListener('click', e => {
    const b = e.target.closest('[data-v]'); if (!b) return;
    filters[key] = b.dataset.v;
    for (const x of el(id).querySelectorAll('[data-v]')) x.setAttribute('aria-pressed', String(x === b));
    loadBoard();
  });
}
seg('f-type', 'type'); seg('f-state', 'state'); seg('f-acc', 'accepted');
el('f-repo').onchange = () => { filters.repo = el('f-repo').value; loadBoard(); };
el('refresh').onclick = () => loadBoard(true);

async function loadRepos() {
  try {
    const r = await api('api/repos'); repoList = r.repos;
    const sel = el('f-repo'), keep = filters.repo;
    sel.replaceChildren(new Option('All repos', ''));
    for (const x of repoList) sel.append(new Option(x.name, x.full_name));
    sel.value = keep;
  } catch (_) { repoList = []; }
}
async function loadBoard(refresh = false) {
  const gen = ++loadGen;
  const q = new URLSearchParams({ type: filters.type, state: filters.state, accepted: filters.type === 'goal' ? 'any' : filters.accepted });
  if (filters.repo) q.set('repo', filters.repo);
  if (refresh) q.set('refresh', '1');
  el('board').setAttribute('aria-busy', 'true');
  try {
    const b = await api('api/board?' + q);
    if (gen !== loadGen) return;
    board = b; renderBoard(); say('');
  } catch (err) {
    if (gen !== loadGen) return;
    if (err.status === 401) { const s = await api('api/status').catch(() => null); if (s) renderAccount(s); }
    say(err.message, 'error');
  } finally { if (gen === loadGen) el('board').removeAttribute('aria-busy'); }
}
function short(repo) { return repo && me && repo.toLowerCase().startsWith(me.org.toLowerCase() + '/') ? repo.slice(me.org.length + 1) : repo; }
function ago(iso) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (!isFinite(s)) return '';
  if (s < 3600) return Math.max(1, Math.round(s / 60)) + 'm';
  if (s < 86400) return Math.round(s / 3600) + 'h';
  if (s < 86400 * 60) return Math.round(s / 86400) + 'd';
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
function goalCard(g) {
  const c = make('button', 'wz-card bd-goal'); c.type = 'button'; c.dataset.id = g.id;
  c.append(make('span', 'bd-meta', `${short(g.repo)} #${g.number} · ${ago(g.updated_at)}`), make('b', 'bd-title', g.title));
  const m = make('span', 'wz-meter');
  const pct = g.tasks_total ? Math.round(100 * g.tasks_done / g.tasks_total) : 0;
  m.append(make('span', '', g.tasks_total ? `${g.tasks_done} of ${g.tasks_total} done` : 'No done-list yet'));
  const bar = make('i'); const fill = make('b'); fill.style.setProperty('--v', pct + '%'); bar.append(fill); m.append(bar);
  c.append(m);
  const foot = make('span', 'bd-foot');
  foot.append(make('span', 'wz-chip bd-chip', g.open_prs === 1 ? '1 open PR' : `${g.open_prs} open PRs`));
  if (g.state === 'closed') foot.append(make('span', 'wz-pill off', 'Closed'));
  c.append(foot);
  c.onclick = () => openDetail(g);
  return c;
}
function bugRow(b) {
  const li = make('li'); li.dataset.id = b.id;
  const row = make('button', 'wz-row'); row.type = 'button';
  const main = make('span', 'wz-main');
  main.append(make('b', '', b.title), make('small', '', `${short(b.repo)} #${b.number} · ${b.author || ''} · ${ago(b.updated_at)}`));
  const pill = make('span', 'wz-pill ' + (b.state === 'closed' ? 'off' : b.accepted ? 'ok' : 'warn'), b.state === 'closed' ? 'Closed' : b.accepted ? 'Accepted' : 'To accept');
  row.append(main, pill, make('span', 'chev', '›'));
  row.querySelector('.chev').setAttribute('aria-hidden', 'true');
  row.onclick = () => openDetail(b);
  li.append(row);
  return li;
}
function renderBoard() {
  const goals = board.goals, bugs = board.bugs;
  const showGoals = filters.type !== 'bug', showBugs = filters.type !== 'goal';
  el('goals-sec').hidden = !showGoals; el('bugs-sec').hidden = !showBugs;
  el('goals').replaceChildren(...goals.map(goalCard));
  el('bugs').replaceChildren(...bugs.map(bugRow));
  el('goals-count').textContent = goals.length; el('bugs-count').textContent = bugs.length;
  el('goals-empty').hidden = goals.length > 0; el('bugs-empty').hidden = bugs.length > 0;
  el('goals-empty').textContent = `No ${filters.state} goals${filters.repo ? ' in ' + short(filters.repo) : ''}.`;
  el('bugs-empty').textContent = `No ${filters.state} bugs${filters.accepted === 'no' ? ' waiting to be accepted' : filters.accepted === 'yes' ? ' accepted' : ''}${filters.repo ? ' in ' + short(filters.repo) : ''}.`;
  el('truncated').hidden = !board.truncated;
  el('truncated').textContent = board.truncated ? `Showing the ${board.count} most recently updated of ${board.total}. Pick a repo to narrow it.` : '';
}
// Replace one item in place after a change (or drop it when it no longer matches the filters).
function applyItem(it) {
  if (!board) return;
  const fits = it.state === filters.state && (filters.type === 'all' || it.type === filters.type)
    && (!filters.repo || it.repo === filters.repo)
    && (it.type !== 'bug' || filters.accepted === 'any' || filters.type === 'goal' || it.accepted === (filters.accepted === 'yes'));
  const list = it.type === 'goal' ? board.goals : board.bugs;
  const i = list.findIndex(x => x.id === it.id);
  if (fits) { if (i >= 0) list[i] = it; else list.unshift(it); } else if (i >= 0) list.splice(i, 1);
  renderBoard();
}
async function loadBoxes() {
  try {
    const b = await api('api/boxes');
    el('box-main').textContent = b.main ? `${b.main.sha} · ${b.main.message}` : (b.main_error || 'Not available');
    if (b.main && b.main.url) el('box-main-link').href = b.main.url;
  } catch (err) { el('box-main').textContent = err.message; }
}
async function loadAll() { await Promise.all([loadBoard(), loadRepos(), loadBoxes()]); }

// ---------- the one sheet ----------
const sheet = el('sheet');
let sheetHold = null;
function openSheet(title, build) {
  el('sheet-h').textContent = title; el('sheet-msg').textContent = '';
  const body = el('sheet-body'); body.replaceChildren(); build(body);
  WzSheet.open(sheet);
}
function closeSheet() { WzSheet.close(sheet); }
sheet.addEventListener('close', () => { openItem = null; releaseHold(); });
function holdDraft(on) {
  if (on && !sheetHold && window.WizardApp && WizardApp.version === 1) sheetHold = WizardApp.update.hold('Unsaved Board form');
  if (!on) releaseHold();
}
function releaseHold() { if (sheetHold) { sheetHold.release(); sheetHold = null; } }
function sheetSay(t) { el('sheet-msg').textContent = t; }
async function run(button, fn) {
  const all = [...el('sheet-body').querySelectorAll('button, input, textarea, select')];
  all.forEach(x => { x.dataset.was = x.disabled ? '1' : ''; x.disabled = true; });
  sheetSay('');
  try { await fn(); }
  catch (err) { sheetSay(err.message); }
  finally { all.forEach(x => { x.disabled = x.dataset.was === '1'; }); }
}
function repoPicker() {
  const sel = make('select', 'wz-input bd-select'); sel.required = true; sel.setAttribute('aria-label', 'Repo');
  sel.append(new Option('Pick a repo', ''));
  for (const r of repoList) sel.append(new Option(r.name + (r.private ? ' (private)' : ''), r.full_name));
  if (filters.repo) sel.value = filters.repo;
  return sel;
}
function field(label, input) { const w = make('label', 'bd-field'); w.append(make('span', 'bd-label', label), input); return w; }

el('add-goal').onclick = () => openSheet('Add goal', body => {
  const f = make('form', 'bd-form'); f.autocomplete = 'off';
  const repo = repoPicker();
  const title = make('input', 'wz-input'); title.required = true; title.maxLength = 200; title.placeholder = 'The outcome, e.g. Board ships to every box';
  const done = make('textarea', 'wz-input bd-area'); done.rows = 5; done.required = true; done.placeholder = 'One line per item, e.g.\nApp installs from the index\nMiguel uses it daily';
  const go = make('button', 'wz-button', 'Add goal'); go.type = 'submit';
  f.append(field('Repo', repo), field('Goal', title), field('Done when (one per line)', done), make('div', 'wz-actions'));
  f.lastChild.append(go);
  f.oninput = () => holdDraft(!!(title.value.trim() || done.value.trim()));
  f.onsubmit = e => { e.preventDefault(); run(go, async () => {
    const it = await api('api/goals', { repo: repo.value, title: title.value, done: done.value.split('\n') });
    releaseHold(); closeSheet(); applyItem(it);
    toast(it.warning || `Goal added to ${short(it.repo)}.`);
  }); };
  body.append(f); setTimeout(() => (repo.value ? title : repo).focus(), 50);
});
el('add-bug').onclick = () => openSheet('Report bug', body => {
  const f = make('form', 'bd-form'); f.autocomplete = 'off';
  const repo = repoPicker();
  const title = make('input', 'wz-input'); title.required = true; title.maxLength = 200; title.placeholder = 'What is wrong, in one line';
  const text = make('textarea', 'wz-input bd-area'); text.rows = 5; text.placeholder = 'What happens, what should happen, how to see it';
  const go = make('button', 'wz-button', 'Report bug'); go.type = 'submit';
  f.append(field('Repo', repo), field('Bug', title), field('Details', text), make('div', 'wz-actions'));
  f.lastChild.append(go);
  f.oninput = () => holdDraft(!!(title.value.trim() || text.value.trim()));
  f.onsubmit = e => { e.preventDefault(); run(go, async () => {
    const it = await api('api/bugs', { repo: repo.value, title: title.value, body: text.value });
    releaseHold(); closeSheet(); applyItem(it);
    toast(it.warning || `Bug reported in ${short(it.repo)}.`);
  }); };
  body.append(f); setTimeout(() => (repo.value ? title : repo).focus(), 50);
});

function openDetail(item) {
  openItem = item;
  openSheet(item.title, body => { body.append(make('p', 'bd-note', 'Loading…')); });
  const want = item.id;
  api(`api/issue?repo=${encodeURIComponent(item.repo)}&number=${item.number}`).then(d => { if (openItem && openItem.id === want && sheet.open) renderDetail(d); })
    .catch(err => { if (openItem && openItem.id === want) { el('sheet-body').replaceChildren(); sheetSay(err.message); } });
}
function renderDetail(d) {
  openItem = d;
  el('sheet-h').textContent = d.title;
  const body = el('sheet-body'); body.replaceChildren();
  const meta = make('p', 'bd-meta');
  meta.textContent = `${d.type === 'goal' ? 'Goal' : 'Bug'} · ${short(d.repo)} #${d.number} · ${d.state === 'open' ? 'Open' : 'Closed'}${d.type === 'bug' ? (d.accepted ? ' · Accepted' : ' · Not accepted yet') : ''} · by ${d.author || 'unknown'}`;
  body.append(meta);
  if (d.tasks.length) {
    body.append(make('h3', 'bd-h', `Done when · ${d.tasks_done} of ${d.tasks_total}`));
    const ul = make('ul', 'wz-list');
    d.tasks.forEach(t => {
      const li = make('li'); const row = make('button', 'wz-row'); row.type = 'button';
      row.setAttribute('aria-pressed', String(t.done));
      const box = make('span', 'wz-check'); box.setAttribute('aria-hidden', 'true');
      box.innerHTML = '<i><svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></i>';
      const main = make('span', 'wz-main'); main.append(make('b', '', t.text));
      row.append(box, main);
      row.onclick = () => run(row, async () => {
        const next = await api('api/issue/task', { repo: d.repo, number: d.number, index: t.index, done: !t.done, text: t.text });
        renderDetail({ ...next, comment_list: d.comment_list }); applyItem(strip(next));
      });
      li.append(row); ul.append(li);
    });
    body.append(ul);
  } else if (d.body) {
    const p = make('p', 'bd-body wz-prose'); p.textContent = d.body.length > 1200 ? d.body.slice(0, 1200) + '…' : d.body; body.append(p);
  }
  if (d.prs && d.prs.length) {
    body.append(make('h3', 'bd-h', 'Pull requests'));
    const ul = make('ul', 'wz-list');
    for (const p of d.prs) {
      const a = make('a', 'wz-row'); a.href = p.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
      const main = make('span', 'wz-main'); main.append(make('b', '', p.title || `#${p.number}`), make('small', '', `${short(p.repo)} #${p.number}`));
      a.append(main, make('span', 'wz-pill ' + (p.state === 'open' ? 'ok' : 'off'), p.state === 'open' ? 'Open' : p.state === 'merged' ? 'Merged' : 'Closed'));
      const li = make('li'); li.append(a); ul.append(li);
    }
    body.append(ul);
  }
  // Actions: humans accept bugs and open/close goals.
  const acts = make('div', 'wz-actions');
  if (d.type === 'bug' && !d.accepted && d.state === 'open') {
    const b = make('button', 'wz-button', 'Accept bug'); b.type = 'button';
    b.onclick = () => run(b, async () => { const it = await api('api/issue/accept', { repo: d.repo, number: d.number }); closeSheet(); applyItem(strip(it)); toast('Bug accepted. Agents can start on it.'); });
    acts.append(b);
  }
  const st = make('button', 'wz-button secondary', d.state === 'open' ? (d.type === 'goal' ? 'Close goal' : 'Close bug') : 'Reopen'); st.type = 'button';
  st.onclick = () => run(st, async () => {
    const it = await api(d.state === 'open' ? 'api/issue/close' : 'api/issue/reopen', { repo: d.repo, number: d.number });
    closeSheet(); applyItem(strip(it)); toast(it.state === 'closed' ? `Closed ${short(it.repo)} #${it.number}.` : `Reopened ${short(it.repo)} #${it.number}.`);
  });
  const gh = make('a', 'bd-link', 'Open on GitHub ↗'); gh.href = d.url; gh.target = '_blank'; gh.rel = 'noopener noreferrer';
  acts.append(st, gh);
  body.append(acts);
  // Comments
  body.append(make('h3', 'bd-h', d.comments ? `Comments · ${d.comments}` : 'Comments'));
  const cl = make('div', 'bd-comments');
  for (const c of d.comment_list || []) {
    const box = make('div', 'bd-comment');
    box.append(make('span', 'bd-meta', `${c.author || 'unknown'} · ${ago(c.created_at)}`), make('p', 'bd-body', c.body));
    cl.append(box);
  }
  body.append(cl);
  const f = make('form', 'bd-inline bd-comment-form'); f.autocomplete = 'off';
  const ta = make('textarea', 'wz-input bd-area'); ta.rows = 2; ta.placeholder = 'Add a comment'; ta.maxLength = 8000; ta.setAttribute('aria-label', 'Comment');
  const go = make('button', 'wz-button secondary', 'Comment'); go.type = 'submit';
  f.append(ta, go);
  f.oninput = () => holdDraft(!!ta.value.trim());
  f.onsubmit = e => { e.preventDefault(); if (!ta.value.trim()) return; run(go, async () => {
    await api('api/issue/comment', { repo: d.repo, number: d.number, body: ta.value });
    releaseHold();
    const fresh = await api(`api/issue?repo=${encodeURIComponent(d.repo)}&number=${d.number}&fresh=1`);
    renderDetail(fresh); applyItem(strip(fresh)); toast('Comment added.');
  }); };
  body.append(f);
}
function strip(d) { const x = { ...d }; delete x.body; delete x.tasks; delete x.comment_list; delete x.prs; return x; }

// ---------- start ----------
if (!window.WizardApp || WizardApp.version !== 1) {
  say('Wizard system functions are unavailable. Open this preview through Wizard.', 'error');
} else {
  WizardApp.ready({ name: 'board', version: '0.1.0' });
  // One screen; the sheet registers its own Back step through WzSheet. At root Back is the shell's.
  WizardApp.back.register({ canGoBack: () => false, back: () => false });
}
api('api/status').then(async s => { renderAccount(s); if (s.connected) await loadAll(); })
  .catch(err => { el('loading').hidden = true; say(err.message, 'error'); });
// Others change the board on GitHub: refresh when the window comes back into focus (cached ~60 s on the box).
let lastFocus = Date.now();
window.addEventListener('focus', () => { if (me && me.connected && Date.now() - lastFocus > 30000 && !sheet.open) { lastFocus = Date.now(); loadBoard(); } });
