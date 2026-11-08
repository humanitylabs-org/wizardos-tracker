'use strict';
// WizardOS Tracker 0.14: Try it is the change's real feature switch on this Wizard (builder line `Switch: <author>/<id>`,
// shell route /wizard-os-home/store-install/_feature-switches, same state as Settings › Try new features).
// WizardOS Tracker 0.13: two-step review. The line is Queued → Building → AI review → Human review → Done, with
// two return arrows to Building (AI review fail, Human review Doesn't work), optional second human review
// ('1 of 2 reviews' on cards), and Sign in with GitHub (device flow) when the box has a client id.
// WizardOS Tracker 0.10: stable chip order (sorted once by the unfiltered totals), goal owners as name chips on
// the title line, shared step targets editable from a thin row under the bins (no control inside a bin).
// 0.9: Goals | Bugs + a small Builder switch; the assembly line Queued → Building →
// Review → Done (big numbers, arrows, a return arrow with the kick-back rate; each bin carries a tiny
// typical range p25–p75 with the median and a target tick; ⓘ for who + target; tap a bin to filter by stage).
// Bugs only: Who and Repo chip rows and a tiny sort control. Rows with a 'Try it' switch (not on Done).
const el = id => document.getElementById(id);
const make = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
const link = (cls, href) => { const a = make('a', cls); a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a; };
const EMPTY = { goals: 'No open goals.', bugs: 'No open bugs. Nice.' };
const GROUPS = ['test', 'airev', 'building', 'queued'];
const stage = { goals: null, bugs: null };   // tap a bin: show only that stage (not remembered)
const doneCache = {};   // view -> { at, items } recently closed, loaded when the Done bin is tapped
let me = null, view = location.hash === '#bugs' ? 'bugs' : 'goals', gen = 0, held = null, lastLoad = 0, who = '';
const NO_DATA = 'starts once the builder runs';
const BINS = [
  { key: 'open', group: 'queued', word: 'Queued' },
  { key: 'build', group: 'building', word: 'Building' },
  { key: 'ai', group: 'airev', word: 'AI review' },
  { key: 'review', group: 'test', word: 'Human review' },
  { key: 'done', group: null, word: 'Done' },
];
const POP = {
  build: ['WizardOS Builder', 'Writes the code, then hands it to Review.'],
  ai: ['The opener’s agent', 'Checks the build matches the issue: on to Human review, or back to Building. A goal’s owner’s agent checks goals; anyone outside the team gets any team agent.'],
  review: ['The team, not whoever opened it', 'Someone else tries it: Works, or back to Building.'],
  done: ['Closed', 'The opener closes it once it works.'],
};
const store = { get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch (_) { return null; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) {} } };
// Chip filters live on Bugs only (0.9: Goals has none); picks are remembered on the device.
const picked = { bugs: new Set(store.get('board.repos.bugs') || []) };
const pickedWho = { bugs: new Set(store.get('board.who.bugs') || []) };
let repoMore = false;   // the Repo row's '+N more' is open (not remembered)
const SORTS = [['oldest', 'Oldest'], ['newest', 'Newest'], ['discussed', 'Most discussed'], ['active', 'Recently active']];
const savedSort = v => SORTS.some(([k]) => k === store.get('board.sort.' + v)) ? store.get('board.sort.' + v) : 'oldest';
const sortBy = { goals: savedSort('goals'), bugs: savedSort('bugs') };
const ts = iso => { const t = Date.parse(iso || ''); return isNaN(t) ? 0 : t; };
const SORT_FN = {
  oldest: (a, b) => ts(a.created_at) - ts(b.created_at),
  newest: (a, b) => ts(b.created_at) - ts(a.created_at),
  discussed: (a, b) => (b.comments || 0) - (a.comments || 0) || ts(a.created_at) - ts(b.created_at),
  active: (a, b) => ts(b.updated_at) - ts(a.updated_at),
};
const cache = {};
const details = new Map();   // issue id -> { at, data }: a short cache so reopening is instant
const DETAIL_SECONDS = 60;

function say(text, kind = '') {
  const s = el('status');
  s.classList.toggle('wz-sr', !kind);
  s.classList.toggle('note', kind === 'note');
  s.textContent = text;
}
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
  if (!r.ok) { const e = new Error(body.error || 'Something went wrong. Try again.'); e.status = r.status; e.reason = body.reason; if ((body.reason === 'agent' || body.reason === 'not_member') && path !== 'api/connect') { me = { connected: false }; refuse(body.reason, e.message); } throw e; }
  return body;
}
function hold(on) {
  if (on && !held && window.WizardApp && WizardApp.version === 1) held = WizardApp.update.hold('Unsaved tracker note');
  if (!on && held) { held.release(); held = null; }
}
const repoName = r => (r || '').split('/').pop();
// 0.10: GitHub login -> the name people know, from the policy roster (served as `names`).
const nameOf = login => { const n = ((cache[view] || {}).names || {})[(login || '').toLowerCase()]; return n || login || ''; };
const typing = () => !!document.querySelector('.bd-fail');
const sheetOpen = () => el('detail').open;

// ---------- one small anchored popover (bins, Builder, Try it); tap outside or Esc closes it ----------
let popFor = null;
function pop(anchor, title, text) {
  const p = el('pop');
  if (popFor === anchor && !p.hidden) return unpop();
  p.classList.remove('bd-te');
  // 0.12.2: inside an open sheet the popover must live in the dialog (the top layer), or it renders underneath
  const host = anchor.closest('dialog[open]') || document.body;
  if (p.parentNode !== host) host.append(p);
  p.replaceChildren(...(title ? [make('b', '', title)] : []), ...[].concat(text).filter(Boolean).map(t => typeof t === 'string' ? make('span', '', t) : t));
  p.hidden = false; popFor = anchor;
  const r = anchor.getBoundingClientRect(), w = Math.min(260, innerWidth - 24);
  p.style.width = w + 'px';
  // a sheet can be the containing block of a fixed element inside it: place, measure, correct
  p.style.left = Math.max(12, Math.min(innerWidth - w - 12, r.left + r.width / 2 - w / 2)) + 'px';
  const below = r.bottom + 8, h = p.offsetHeight;
  p.style.top = (below + h > innerHeight - 8 ? Math.max(8, r.top - h - 8) : below) + 'px';
  if (host !== document.body) {
    const want = { left: parseFloat(p.style.left), top: parseFloat(p.style.top) }, got = p.getBoundingClientRect();
    p.style.left = (want.left * 2 - got.left) + 'px'; p.style.top = (want.top * 2 - got.top) + 'px';
  }
  p.classList.toggle('up', below + h > innerHeight - 8);
}
// 0.11: Done and the line stats count items closed since the reset date (policy `since`).
const sinceText = iso => { const t = Date.parse(iso || ''); return isNaN(t) ? 'All time'
  : 'Counted since ' + new Date(t).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }); };
function unpop() { el('pop').hidden = true; popFor = null; }
document.addEventListener('pointerdown', e => { if (popFor && !el('pop').contains(e.target) && !popFor.contains(e.target)) unpop(); }, true);
document.addEventListener('keydown', e => { if (e.key === 'Escape') unpop(); });
// The target editor stays open while its field has focus (a phone keyboard scrolls and resizes the page).
const editing = () => el('pop').contains(document.activeElement) && document.activeElement.tagName === 'INPUT';
el('scroll').addEventListener('scroll', () => { if (!editing()) unpop(); }, { passive: true });
addEventListener('resize', () => { if (!editing()) unpop(); });
const when = iso => {
  if (!iso) return '';
  const d = new Date(iso), days = Math.floor((Date.now() - d) / 864e5);
  if (days < 1) return 'today';
  if (days < 2) return 'yesterday';
  if (days < 30) return days + ' days ago';
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: d.getFullYear() === new Date().getFullYear() ? undefined : 'numeric' });
};
// Rows open in-app only: no href, so no native shell or link handler can send them to GitHub.
const tapTarget = (cls, fn) => { const a = make('a', cls); a.setAttribute('role', 'button'); a.tabIndex = 0;
  a.onclick = e => { e.preventDefault(); fn(); };
  a.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fn(); } }; return a; };
const plainClick = e => !(e.metaKey || e.ctrlKey || e.shiftKey || e.button);

// ---------- sign in ----------
const REFUSED_TITLE = { not_member: 'For the WizardOS team', agent: 'Your own account, please' };
function refuse(reason, message) {
  el('refused-title').textContent = REFUSED_TITLE[reason] || REFUSED_TITLE.not_member;
  el('refused-text').textContent = message;
  el('signin').hidden = true; el('board').hidden = true; el('loading').hidden = true; el('refused').hidden = false;
  say('');
}
function show(s) {
  me = s;
  account(s);
  if (s.refused && !s.connected) return refuse(s.refused.reason, s.refused.message);
  const on = !!s.connected;
  el('refused').hidden = true;
  el('signin').hidden = on; el('board').hidden = !on; el('loading').hidden = true;
  if (!on && s.notice) say(s.notice, 'error');
  signinMode(s);
  if (!on && s.oauth && !devTimer) api('api/device').then(r => { if (r.state === 'pending') showCode(r); }).catch(() => {});
}
// 0.12.2: one tiny account control, top right. Signed in: "Signed in as <name>" and Sign out; signed out: Sign in.
function account(s) {
  const on = !!(s && s.connected), a = (s && s.account) || {};
  el('acct-name').textContent = on ? 'Signed in as ' + (a.name || a.login || 'you') : '';
  el('acct-name').hidden = !on;
  el('acct-act').textContent = on ? 'Sign out' : 'Sign in';
}
el('acct-act').onclick = async () => {
  unpop();
  if (!(me && me.connected)) {
    el('refused').hidden = true; el('board').hidden = true; el('loading').hidden = true; el('signin').hidden = false;
    return (me && me.oauth && !tokenWanted ? el('oauth-go') : el('token')).focus();
  }
  const b = el('acct-act'); b.disabled = true;
  try { show(await api('api/disconnect', {})); say(''); }
  catch (err) { pop(b, '', err.message); }
  finally { b.disabled = false; }
};
el('refused-back').onclick = () => { el('refused').hidden = true; el('signin').hidden = false; signinMode(me); (me && me.oauth && !tokenWanted ? el('oauth-go') : el('token')).focus(); };
el('connect-form').onsubmit = async e => {
  e.preventDefault();
  const t = el('token'), b = el('connect');
  b.disabled = true; t.disabled = true; say('Checking with GitHub…', 'note');
  try { const s = await api('api/connect', { token: t.value }); t.value = ''; say(''); show(s); load('goals'); loadSide(); }
  catch (err) { if (err.reason) { t.value = ''; refuse(err.reason, err.message); } else say(err.message, 'error'); }
  finally { b.disabled = false; t.disabled = false; }
};

// ---------- 0.13: Sign in with GitHub (device flow): one button, a code to type on GitHub, the box polls ----------
let devTimer = null, tokenWanted = false;
function signinMode(s) {
  const oauth = !!(s && s.oauth), tokenMode = !oauth || tokenWanted;
  el('oauth').hidden = !oauth;
  el('connect-form').hidden = !tokenMode; el('token-help').hidden = !tokenMode;
  el('oauth-go').hidden = tokenWanted || !el('oauth-code').hidden;
  if (tokenWanted) el('oauth-code').hidden = true;
  el('oauth-token').textContent = tokenWanted ? 'Sign in with GitHub instead' : 'Use a token instead';
}
function stopDevice() { clearTimeout(devTimer); devTimer = null; el('oauth-code').hidden = true; signinMode(me); }
function showCode(r) {
  el('oauth-user-code').textContent = r.user_code;
  el('oauth-open').href = /^https:\/\//.test(r.verification_uri || '') ? r.verification_uri : 'https://github.com/login/device';
  el('oauth-wait').textContent = 'Waiting for GitHub…';
  el('oauth-code').hidden = false; el('oauth-go').hidden = true;
  clearTimeout(devTimer); devTimer = setTimeout(pollDevice, 2500);
}
async function pollDevice() {
  devTimer = null;
  let r;
  try { r = await api('api/device'); } catch (err) { devTimer = setTimeout(pollDevice, 5000); return; }
  if (r.state === 'pending') { devTimer = setTimeout(pollDevice, 2500); return; }
  stopDevice();
  if (r.state === 'done' && r.status) { say(''); show(r.status); load(view); loadSide(); return; }
  if (r.state === 'refused') return refuse(r.reason, r.message);
  if (r.state !== 'none' && r.state !== 'cancelled') say(r.message || 'Sign-in did not finish. Try again.', 'error');
}
el('oauth-go').onclick = async () => {
  const b = el('oauth-go'); b.disabled = true; say('Asking GitHub for a code…', 'note');
  try { showCode(await api('api/device/start', {})); say(''); }
  catch (err) { say(err.message, 'error'); }
  finally { b.disabled = false; }
};
el('oauth-copy').onclick = async () => {
  const code = el('oauth-user-code').textContent;
  let ok = false;
  try { await navigator.clipboard.writeText(code); ok = true; } catch (_) {
    try { const r = document.createRange(); r.selectNodeContents(el('oauth-user-code')); const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r); ok = document.execCommand('copy'); } catch (_) {}
  }
  el('oauth-copy').textContent = ok ? 'Copied' : 'Select it';
  setTimeout(() => { el('oauth-copy').textContent = 'Copy'; }, 2000);
};
el('oauth-cancel').onclick = () => { api('api/device/cancel', {}).catch(() => {}); stopDevice(); say(''); };
el('oauth-token').onclick = () => { tokenWanted = !tokenWanted; if (tokenWanted) { api('api/device/cancel', {}).catch(() => {}); clearTimeout(devTimer); devTimer = null; } signinMode(me); (tokenWanted ? el('token') : el('oauth-go')).focus(); };

// ---------- Goals | Bugs ----------
const sw = document.querySelector('.bd-switch');
sw.addEventListener('click', e => {
  const b = e.target.closest('[data-view]');
  if (!b || b.dataset.view === view) return;
  view = b.dataset.view;
  for (const x of sw.querySelectorAll('[data-view]')) x.setAttribute('aria-selected', String(x === b));
  hold(false);
  if (cache[view]) render(cache[view]);
  else { for (const g of [...GROUPS, 'done']) el('sec-' + g).hidden = true; el('totals').textContent = ''; el('steps').replaceChildren(); el('kick').hidden = true; el('filters').hidden = true; el('sort').hidden = true; el('empty').hidden = false; el('empty').textContent = 'Loading…'; }
  unpop(); repoMore = false;
  el('scroll').scrollTop = 0;
  load(view);
});

// 0.13.5: a small refresh button top right; it spins while a reload is in flight, and 'updated 20s ago' says how fresh the list is.
let inflight = 0, freshAt = 0;
function freshness() {
  const f = el('fresh'), r = el('reload'); if (!f || !r) return;
  r.hidden = !(me && me.connected); r.classList.toggle('spin', inflight > 0);
  r.setAttribute('aria-busy', String(inflight > 0));
  if (inflight > 0) { f.textContent = 'updating…'; return; }
  if (!freshAt) { f.textContent = ''; return; }
  const s = Math.round((Date.now() - freshAt) / 1000);
  f.textContent = s < 10 ? 'up to date' : s < 60 ? `updated ${s}s ago` : `updated ${Math.round(s / 60)}m ago`;
  f.classList.toggle('stale', s >= 90);
}
setInterval(freshness, 5000);

async function load(which, refresh = false) {
  const g = ++gen; lastLoad = Date.now(); inflight++; freshness();
  try {
    const d = await api(`api/split?view=${which}${refresh ? '&refresh=1' : ''}`);
    if (d.stats && d.stats.pending && cache[which] && cache[which].stats && !cache[which].stats.pending) d.stats = cache[which].stats;
    cache[which] = d;
    if (which === view && g === gen && !typing()) render(d);
    say('');
    if (d.stats && d.stats.pending) loadStats(which);
    if (which === view) freshAt = Date.now();
  } catch (err) {
    if (err.status === 401) { const s = await api('api/status').catch(() => null); if (s) show(s); }
    say(err.message, 'error');
  } finally { inflight = Math.max(0, inflight - 1); freshness(); }
}

async function loadStats(which) {
  try {
    const st = await api('api/stats?view=' + which);
    if (cache[which]) { cache[which].stats = st; if (which === view && !typing()) render(cache[which]); }
  } catch (err) { if (cache[which]) { cache[which].stats = { error: err.message, items: [] }; if (which === view) render(cache[which]); } }
}

function authorsOf(d) {
  const n = new Map();
  for (const g of GROUPS) for (const i of d.groups[g]) if (i.author) n.set(i.author, (n.get(i.author) || 0) + 1);
  return [...n.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

const repoKey = i => (i.repo || '').toLowerCase();
function reposOf(d, keepWho) {
  const n = new Map();
  for (const g of GROUPS) for (const i of d.groups[g]) if (keepWho(i)) n.set(i.repo, (n.get(i.repo) || 0) + 1);
  return [...n.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}
function render(d) {
  // Bugs only: Who and Repo chips (multi-select, remembered); picks no longer present drop out. Goals: no filters.
  const bugs = d.view === 'bugs';
  const whoSet = bugs ? pickedWho.bugs : new Set(), chosen = bugs ? picked.bugs : new Set();
  const allPeople = new Set(authorsOf(d).map(([p]) => p.toLowerCase()));
  for (const p of [...whoSet]) if (!allPeople.has(p)) whoSet.delete(p);
  const known = new Map((d.repos || []).map(r => [r.toLowerCase(), r]));
  for (const [r] of reposOf(d, () => true)) known.set(r.toLowerCase(), r);
  for (const r of [...chosen]) if (!known.has(r)) chosen.delete(r);
  const byWho = i => !whoSet.size || whoSet.has((i.author || '').toLowerCase());
  const byRepo = i => !chosen.size || chosen.has(repoKey(i));
  el('filters').hidden = !bugs; el('sort').hidden = stage[d.view] === 'done';   // Done lists newest closed first
  if (bugs) {
    // 0.10: each row's ORDER comes from the unfiltered totals (then name) and never changes with the other
    // row's picks; only the numbers do (zero dims). The collapsed Repo row's top few use the same totals.
    const allWho = authorsOf(d), allRepo = new Map(reposOf(d, () => true).map(([r, n]) => [r.toLowerCase(), n]));
    const whoN = new Map(authorsOf({ groups: Object.fromEntries(GROUPS.map(g => [g, d.groups[g].filter(byRepo)])) }).map(([p, n]) => [p.toLowerCase(), n]));
    const repoN = new Map(reposOf(d, byWho).map(([r, n]) => [r.toLowerCase(), n]));
    const label = p => { const n = nameOf(p); return p === d.login ? `${n} (you)` : n; };
    const people = allWho.map(([p, t]) => [p.toLowerCase(), label(p), whoN.get(p.toLowerCase()) || 0, t])
      .sort((a, b) => b[3] - a[3] || a[1].localeCompare(b[1]));
    const repos = [...known].map(([k, r]) => [k, repoName(r), repoN.get(k) || 0, allRepo.get(k) || 0])
      .sort((a, b) => b[3] - a[3] || a[1].localeCompare(b[1]));
    chipRow('who', whoSet, people);
    chipRow('repo', chosen, repos);
  }
  sortControl();
  const keep = i => byWho(i) && byRepo(i);
  const order = SORT_FN[sortBy[d.view]];
  const groups = Object.fromEntries(GROUPS.map(g => { const l = d.groups[g].filter(keep); return [g, order ? l.sort(order) : l]; }));
  const st = d.stats || {}, hist = (st.items || []).filter(keep);
  flow(d, groups, st.pending || st.error ? null : hist.filter(i => i.state === 'closed').length, st, hist);
  const only = stage[d.view];
  const sp = el('f-stage'); sp.hidden = !only;
  if (only) { sp.querySelector('button').textContent = (BINS.find(b => (b.group || 'done') === only) || {}).word + ' ✕'; }
  el('totals').textContent = d.more && !only ? `showing ${d.shown} of ${d.total}` : '';
  for (const g of GROUPS) {
    const list = only && only !== g ? [] : groups[g];
    el('sec-' + g).hidden = !list.length;
    el('n-' + g).textContent = list.length || '';
    if (g === 'test') {  // others' work first (Works / Doesn't work); what you or your agent opened says someone else reviews it
      el('list-test').replaceChildren(...list.filter(i => !i.mine).map(i => testCard(i, d.view)), ...list.filter(i => i.mine).map(i => testCard(i, d.view)));
    } else el('list-' + g).replaceChildren(...list.map(i => row(i, d.view)));
  }
  let none = only ? only !== 'done' && !groups[only].length : !GROUPS.some(g => groups[g].length);
  el('sec-done').hidden = only !== 'done';
  if (only === 'done') {
    const dc = doneCache[d.view];
    const list = dc && dc.items ? dc.items.filter(keep) : null;
    el('n-done').textContent = list && list.length ? list.length : '';
    el('list-done').replaceChildren(...(list || []).map(i => row(i, d.view)));
    el('sec-done').hidden = !(list && list.length);
    none = !list || !list.length;
    if (!list) { el('empty').hidden = false; el('empty').textContent = dc && dc.error ? dc.error : 'Loading…'; return; }
  }
  el('empty').hidden = !none;
  el('empty').textContent = only ? `Nothing ${only === 'done' ? 'closed' : 'in ' + ((BINS.find(b => b.group === only) || {}).word || '')} here${whoSet.size || chosen.size ? ' with these filters' : ''}.`
    : whoSet.size || chosen.size ? 'Nothing here with these filters.' : EMPTY[d.view];
}

// Tap a bin: show only that stage; tap it again (or the pill) for everything. Done loads recently closed.
function setStage(g) {
  stage[view] = stage[view] === g ? null : g;
  unpop();
  if (stage[view] === 'done') loadDone(view);
  if (cache[view]) render(cache[view]);
}
async function loadDone(which, force) {
  const hit = doneCache[which];
  if (hit && hit.items && !force && Date.now() - hit.at < 120000) return;
  try {
    const r = await api('api/done?view=' + which);
    doneCache[which] = { at: Date.now(), items: r.items || [] };
  } catch (err) { doneCache[which] = { at: Date.now(), items: null, error: err.message }; }
  if (which === view && cache[which] && !typing()) render(cache[which]);
}
el('f-stage').querySelector('button').onclick = () => { stage[view] = null; if (cache[view]) render(cache[view]); };

// ---------- Bugs filters: chip rows (tap to add/remove, All resets) and a tiny sort control ----------
const repoTop = () => innerWidth < 640 ? 5 : 10;   // collapsed Repo row: the top few with bugs (fewer on phones)
// The number keeps a width for as many digits as its unfiltered total, so changing counts never reflow the row.
function chip(label, n, on, fn, extra = '', most = null) {
  const b = make('button', 'bd-chip' + (extra ? ' ' + extra : '')); b.type = 'button';
  b.setAttribute('aria-pressed', String(on));
  b.append(make('span', 'bd-chip-l', label));
  if (n != null) { const s = make('span', 'bd-chip-n', String(n)); s.style.minWidth = Math.max(String(n).length, String(most == null ? n : most).length) + 'ch'; b.append(s); }
  b.onclick = fn; return b;
}
function chipRow(kind, set, options) {
  // options: [key, label, count now, unfiltered total], already in their stable order
  const box = el('c-' + kind), total = options.reduce((a, o) => a + o[2], 0), most = options.reduce((a, o) => a + o[3], 0);
  const toggle = k => () => { if (set.has(k)) set.delete(k); else set.add(k); saveFilter(kind); };
  const out = [chip(kind === 'who' ? 'Everyone' : 'All repos', total, !set.size, () => { set.clear(); saveFilter(kind); }, 'all', most)];
  let shown = options;
  if (kind === 'repo' && !repoMore) {  // the top few repos by unfiltered bugs, plus any picked; the rest behind '+N more'
    const top = options.filter(o => o[3] > 0).slice(0, repoTop());
    shown = options.filter(o => top.includes(o) || set.has(o[0]));
  }
  out.push(...shown.map(([k, label, n, t]) => chip(label, n, set.has(k), toggle(k), n ? '' : 'zero', t)));
  if (kind === 'repo' && options.length > shown.length) out.push(chip(`+${options.length - shown.length} more`, null, false, () => { repoMore = true; render(cache[view]); }, 'more'));
  else if (kind === 'repo' && repoMore && options.length > repoTop()) out.push(chip('Less', null, false, () => { repoMore = false; render(cache[view]); }, 'more'));
  box.replaceChildren(...out);
  box.hidden = options.length < (kind === 'who' ? 2 : 1) && !set.size;
}
function saveFilter(kind) {
  store.set((kind === 'who' ? 'board.who.' : 'board.repos.') + view, [...(kind === 'who' ? pickedWho : picked)[view]]);
  if (cache[view]) render(cache[view]);
}
function sortControl() {
  const box = el('sort');
  box.replaceChildren(...SORTS.map(([k, label]) => {
    const b = make('button', 'bd-sort-b', label); b.type = 'button'; b.setAttribute('role', 'radio');
    b.setAttribute('aria-checked', String(sortBy[view] === k));
    b.onclick = () => { sortBy[view] = k; store.set('board.sort.' + view, k); if (cache[view]) render(cache[view]); };
    return b;
  }));
}

// The assembly line: four bins (big number, word + ⓘ, a tiny avg and box-and-whisker), arrows between,
// and the return arrow under Review → Building labelled with the kick-back rate.
let steps = null;
const arrow = () => {
  const li = make('li', 'bd-arrow'); li.setAttribute('aria-hidden', 'true');
  const svg = document.createElementNS(NS, 'svg'); svg.setAttribute('viewBox', '0 0 20 12');
  const pth = document.createElementNS(NS, 'path'); pth.setAttribute('d', 'M1 6h16M12 1.5L17.5 6 12 10.5'); svg.append(pth); li.append(svg);
  return li;
};
const STAT_HELP = {
  open: 'Time queued: opened → first building label',
  build: 'Build time: first building → hand-off to AI review',
  ai: 'Time in AI review: ai-review → passed on or sent back',
  review: 'Time in Human review: ready-to-test → closed or kicked back',
  done: 'Total time: opened → closed',
};
const STAT_KEY = { open: 'queued', build: 'building', ai: 'ai', review: 'review', done: 'done' };
// Same maths as the server's line_stats(), run after the view's own filters.
function spread(xs) {
  xs = xs.filter(x => x != null).sort((a, b) => a - b);
  if (!xs.length) return { n: 0, avg: null, median: null, p25: null, p75: null };
  const q = p => { const i = (xs.length - 1) * p, lo = Math.floor(i), hi = Math.min(lo + 1, xs.length - 1); return xs[lo] + (xs[hi] - xs[lo]) * (i - lo); };
  const three = xs.length >= 3;
  return { n: xs.length, avg: xs.reduce((a, b) => a + b, 0) / xs.length, median: q(.5), p25: three ? q(.25) : null, p75: three ? q(.75) : null };
}
function lineStats(items) {
  const reviewed = items.filter(i => i.tries), kicked = items.filter(i => i.kicks);
  const toDone = kicked.map(i => i.kick_to_done).filter(x => x != null);
  const aiSeen = items.filter(i => i.ai_tries), aiKicked = items.filter(i => i.ai_kicks);
  return { queued: spread(items.map(i => i.wait)), building: spread(items.map(i => i.build)),
    ai: spread(items.flatMap(i => i.ai_rounds || [])),
    review: spread(items.flatMap(i => i.review_rounds || [])), done: spread(items.map(i => i.total)),
    kick: { reviewed: reviewed.length, kicked: kicked.length, rate: reviewed.length ? kicked.length / reviewed.length : null,
      per: kicked.length ? kicked.reduce((a, i) => a + i.kicks, 0) / kicked.length : null,
      toDone: toDone.length ? toDone.reduce((a, b) => a + b, 0) / toDone.length : null },
    aiKick: { reviewed: aiSeen.length, kicked: aiKicked.length, rate: aiSeen.length ? aiKicked.length / aiSeen.length : null,
      per: aiKicked.length ? aiKicked.reduce((a, i) => a + i.ai_kicks, 0) / aiKicked.length : null } };
}
// A tiny range bar: the typical middle half p25 → p75, a dot at the median, a thin accent tick at the target.
// Log scale over whichever is wider, the range or the target, so the tick always sits on the bar.
function rangeBar(s, target, cls) {
  const W = 60, H = 10, svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('class', 'bd-range'); svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('preserveAspectRatio', 'none');
  const a = s.p25 != null ? s.p25 : s.median, b = s.p75 != null ? s.p75 : s.median;
  const lo = Math.log1p(Math.min(a, target || a) / 1.5), hi = Math.log1p(Math.max(b, target || b) * 1.5);
  const x = v => 3 + (hi > lo ? (Math.log1p(v) - lo) / (hi - lo) : .5) * (W - 6);
  const add = (tag, at) => { const n = document.createElementNS(NS, tag); for (const k in at) n.setAttribute(k, at[k]); svg.append(n); return n; };
  add('line', { x1: 1, x2: W - 1, y1: H / 2, y2: H / 2, class: 't' });
  if (s.p25 != null) add('line', { x1: x(a), x2: Math.max(x(b), x(a) + .5), y1: H / 2, y2: H / 2, class: 'r' });
  if (target) add('line', { x1: x(target), x2: x(target), y1: 0, y2: H, class: 'g' });
  add('circle', { cx: x(s.median), cy: H / 2, r: 2.6, class: 'm ' + cls });
  return svg;
}
const statLines = (x, s, target) => [
  s && s.n ? (s.p25 != null ? `Typical ${dur(s.p25)}–${dur(s.p75)} (middle half), median ${dur(s.median)}.` : `Median ${dur(s.median)} (${s.n} item${s.n === 1 ? '' : 's'}).`) : '',
  target ? `Target: under ${dur(target)}.` : ''];
function binStat(x, ls, st, targets) {
  const box = make('span', 'bd-bin-s');
  if (st.pending) { box.textContent = '…'; box.title = 'Counting…'; return box; }
  const target = (targets || {})[STAT_KEY[x.key]] || null;
  if (st.error || !ls) { box.textContent = '—'; box.title = st.error || NO_DATA; return box; }
  const s = ls[STAT_KEY[x.key]];
  if (!s.n) { box.append(make('span', 'bd-rn none', '—'));
    box.title = `${STAT_HELP[x.key]}: ${NO_DATA}`; return box; }
  const cls = target ? (s.median <= target ? 'ok' : 'warn') : '';
  const nums = make('span', 'bd-rn' + (s.p25 == null ? ' one' : ''));
  if (s.p25 != null) nums.append(make('span', 'lo', dur(s.p25)), make('b', 'md ' + cls, dur(s.median)), make('span', 'hi', dur(s.p75)));
  else nums.append(make('b', 'md ' + cls, dur(s.median)));
  box.append(nums, rangeBar(s, target, cls));
  box.title = `${STAT_HELP[x.key]} (${s.n} item${s.n === 1 ? '' : 's'}). ` + statLines(x, s, target).filter(Boolean).join(' ') + (s.avg != null ? ` Average ${dur(s.avg)}.` : '');
  return box;
}
const infoIcon = () => {
  const svg = document.createElementNS(NS, 'svg'); svg.setAttribute('viewBox', '0 0 16 16'); svg.setAttribute('aria-hidden', 'true');
  const c = document.createElementNS(NS, 'circle'); c.setAttribute('cx', '8'); c.setAttribute('cy', '8'); c.setAttribute('r', '6.25');
  const p = document.createElementNS(NS, 'path'); p.setAttribute('d', 'M8 7.2v4M8 4.9v.1'); svg.append(c, p); return svg;
};
function flow(d, groups, done, st, hist) {
  steps = d.steps && d.steps.length >= 3 ? d.steps : [];
  const ls = st.pending || st.error ? null : lineStats(hist || []);
  const only = stage[d.view], out = [];
  BINS.forEach((x, n) => {
    if (n) out.push(arrow());
    const g = x.group || 'done';
    const count = x.group ? groups[x.group].length : done;
    const li = make('li', 'bd-stepli bd-binx' + (count ? ' on' : '') + (only === g ? ' sel' : '') + (only && only !== g ? ' dim' : ''));
    li.dataset.step = x.key;
    const b = make('button', 'bd-bin' + (count ? ' on' : '')); b.type = 'button'; b.dataset.step = x.key;
    b.setAttribute('aria-pressed', String(only === g));
    b.setAttribute('aria-label', `${x.word}: ${count == null ? 'counting' : count}. ${only === g ? 'Show everything' : 'Show only ' + x.word}`);
    b.append(make('span', 'bd-bin-n', count == null ? '—' : String(count)));
    if (x.key === 'done') b.title = st.error ? st.error : done == null ? 'Counting…' : `Closed ${sinceText(d.since).toLowerCase()} · tap for the latest`;
    li.append(b, make('span', 'bd-bin-w', x.word), binStat(x, ls, st, d.targets));
    li.onclick = () => setStage(g);
    out.push(li);
  });
  el('steps').replaceChildren(...out);
  // 0.10: the controls live in a thin row under the bins, one cell per bin column, never inside a bin.
  const target = k => (d.targets || {})[STAT_KEY[k]] || null;
  el('ctl').replaceChildren(...BINS.map(x => {
    const c = make('div', 'bd-ctl'); c.dataset.step = x.key;
    const t = make('button', 'bd-tgt'); t.type = 'button';
    const tv = make('span', 'bd-tgt-v');
    if (target(x.key)) tv.append(make('span', 'bd-tgt-k', 'target '), document.createTextNode(dur(target(x.key)))); else tv.textContent = 'set target';
    t.append(tv, make('span', 'bd-tgt-e', '✎'));
    t.setAttribute('aria-label', `${x.word} target: ${target(x.key) ? 'under ' + dur(target(x.key)) : 'none'}. Change it`);
    t.onclick = () => editTarget(t, d.view, x);
    const info = make('button', 'bd-i'); info.type = 'button'; info.setAttribute('aria-label', `Who does ${x.word}?`); info.append(infoIcon());
    info.onclick = () => openStep(x, info, d.view, [...statLines(x, ls ? ls[STAT_KEY[x.key]] : null, target(x.key)),
      ...(x.key === 'done' && d.since ? [make('span', 'bd-since', sinceText(d.since))] : [])]);
    c.append(t, info);
    return c;
  }));
  kickLabel(ls, st);
}

// ---------- 0.10: edit a step's target (shared, the same for everyone; permissions later) ----------
const PRESETS = [['15m', 900], ['1h', 3600], ['4h', 14400], ['1d', 86400], ['3d', 259200], ['1w', 604800], ['2w', 1209600]];
const parseDur = v => { const m = String(v || '').trim().toLowerCase().match(/^(\d+(?:\.\d+)?)\s*(m|min|h|d|w)?$/);
  if (!m) return null; const u = { m: 60, min: 60, h: 3600, d: 86400, w: 604800 }[m[2] || 'h']; const s = Math.round(parseFloat(m[1]) * u);
  return s >= 60 && s <= 31536000 ? s : null; };
function editTarget(anchor, which, x) {
  const p = el('pop');
  if (popFor === anchor && !p.hidden) return unpop();
  const cur = ((cache[which] || {}).targets || {})[STAT_KEY[x.key]] || null;
  const note = make('span', 'bd-te-note', 'Same for everyone.');
  const save = async sec => {
    p.querySelectorAll('button, input').forEach(n => { n.disabled = true; }); note.textContent = 'Saving…';
    try {
      const r = await api('api/targets', { view: which, step: STAT_KEY[x.key], seconds: sec });
      if (cache[which]) cache[which].targets = r.targets;
      unpop(); if (which === view && cache[which]) render(cache[which]);
      toast(`${x.word} target: ${dur(r.seconds)}`);
    } catch (err) { p.querySelectorAll('button, input').forEach(n => { n.disabled = false; }); note.textContent = err.message; }
  };
  const grid = make('div', 'bd-te-p'); grid.setAttribute('role', 'group'); grid.setAttribute('aria-label', 'Presets');
  for (const [label, sec] of PRESETS) {
    const b = make('button', 'bd-te-b', label); b.type = 'button'; b.setAttribute('aria-pressed', String(cur === sec));
    b.onclick = () => save(sec); grid.append(b);
  }
  const f = make('form', 'bd-te-f'); f.autocomplete = 'off';
  const inp = make('input', 'wz-input bd-te-i'); inp.placeholder = 'e.g. 6h, 2d, 45m'; inp.setAttribute('aria-label', 'Custom target');
  if (cur && !PRESETS.some(([, s]) => s === cur)) inp.value = dur(cur);
  const ok = make('button', 'bd-te-b bd-te-ok', 'Set'); ok.type = 'submit';
  f.append(inp, ok);
  f.onsubmit = e => { e.preventDefault(); const sec = parseDur(inp.value); if (!sec) { note.textContent = 'Try 30m, 4h, 3d or 2w (1 minute to 1 year).'; inp.focus(); return; } save(sec); };
  p.replaceChildren(make('b', '', `${x.word} target`), grid, f, note);
  p.hidden = false; popFor = anchor; p.classList.add('bd-te');
  const r = anchor.getBoundingClientRect(), w = Math.min(264, innerWidth - 24);
  p.style.width = w + 'px';
  p.style.left = Math.max(12, Math.min(innerWidth - w - 12, r.left + r.width / 2 - w / 2)) + 'px';
  const below = r.bottom + 8, h = p.offsetHeight;
  p.style.top = (below + h > innerHeight - 8 ? Math.max(8, r.top - h - 8) : below) + 'px';
}
const pct = r => Math.round(r * 100) + '%';
const times = x => (Math.round(x * 10) / 10) + '×';
function kickLabel(ls, st) {
  // 0.13: two return arrows into Building: from AI review (fail) and from Human review (Doesn't work)
  for (const [id, kk, from, word] of [['kick-ai', ls && ls.aiKick, 'AI review', 'AI review fail'], ['kick', ls && ls.kick, 'Human review', 'Doesn’t work']]) {
    const k = el(id);
    k.hidden = !!st.pending;
    if (st.pending) continue;
    k.textContent = !kk || kk.rate == null ? '—' : kk.kicked ? `${pct(kk.rate)} · ${times(kk.per)}` : '0%';
    const why = !kk || kk.rate == null ? `Sent back from ${from}: ${NO_DATA}`
      : `${pct(kk.rate)} of ${kk.reviewed} item${kk.reviewed === 1 ? '' : 's'} in ${from} came back at least once` + (kk.kicked ? `, ${times(kk.per)} on average` : '')
        + (kk.toDone != null ? `. ${dur(kk.toDone)} on average from first kick-back to done.` : '.');
    k.title = why; k.setAttribute('aria-label', `${word} goes back to Building. ` + why);
    k.onclick = () => pop(k, `${word} → back to Building`, why);
  }
}
function openStep(x, anchor, kind, extra = []) {
  if (x.key === 'open') {
    const s = (steps || []).find(y => y.key === 'open');
    const who = s ? s.role : kind === 'goals' ? 'James' : 'Anyone on the team';
    return pop(anchor, who, [kind === 'goals' ? 'Opens goals. They wait here until the builder picks them up.' : 'Opens bugs. They wait here until the builder picks them up.', ...extra]);
  }
  const s = (steps || []).find(y => y.key === x.key);
  let [who, text] = POP[x.key];
  if (x.key === 'review') {
    const n = (cache[kind] || {}).human_reviews || 1;
    if (kind === 'goals') { who = s ? s.role : 'Goal owner or James'; text = 'The goal’s owner, or James, tries it: Works, or back to Building.'; }
    if (n > 1) text += ` ${n} different people say Works before it’s done.`;
  }
  pop(anchor, (x.key === 'build' || x.key === 'ai') && s ? s.role : who, [text, ...extra]);
}

const dur = sec => {
  if (sec == null) return null;
  if (sec < 3600) return Math.max(1, Math.round(sec / 60)) + 'm';
  if (sec < 86400) return Math.round(sec / 3600) + 'h';
  const days = sec / 86400;
  return (days < 10 ? Math.round(days * 10) / 10 : Math.round(days)) + 'd';
};

const NS = 'http://www.w3.org/2000/svg';
// How long a bug has existed, short: 40m, 5h, 12d.
const age = iso => { const t = ts(iso); if (!t) return ''; const s = Math.max(0, (Date.now() - t) / 1000);
  return s < 3600 ? Math.max(1, Math.round(s / 60)) + 'm' : s < 86400 ? Math.floor(s / 3600) + 'h' : Math.floor(s / 86400) + 'd'; };
function bubble(n) {
  const s = make('span', 'bd-cmt'); s.setAttribute('aria-label', `${n} comment${n === 1 ? '' : 's'}`);
  const svg = document.createElementNS(NS, 'svg'); svg.setAttribute('viewBox', '0 0 16 16'); svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS(NS, 'path');
  path.setAttribute('d', 'M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z'); svg.append(path);
  s.append(svg, document.createTextNode(String(n)));
  return s;
}
// 0.10: goal owners sit on the title line as small accent name chips (initial + name; avatar images are not
// allowed by the app's CSP img-src 'self'). Logins map to people's names from the policy roster.
function ownerChips(i) {
  const a = (i.assignees && i.assignees.length) ? i.assignees : [];
  const box = make('span', 'bd-owners');
  if (!a.length) { box.append(make('span', 'bd-own none', 'No owner')); box.setAttribute('aria-label', 'No owner yet'); return box; }
  box.setAttribute('aria-label', (a.length === 1 ? 'Owner: ' : 'Owners: ') + a.map(nameOf).join(', '));
  for (const l of a) {
    const n = nameOf(l), c = make('span', 'bd-own'); c.title = n === l ? l : `${n} (${l})`; c.setAttribute('aria-hidden', 'true');
    c.append(make('i', '', (n[0] || '?').toUpperCase()), make('span', '', n));
    box.append(c);
  }
  return box;
}

// Try it (0.14): the change's feature switch on THIS Wizard. The builder names it in its "What to check" comment
// (`Switch: <author>/<id>`, served as i.switch). The Tracker page runs inside the owner's Wizard, on the shell's origin,
// so it reads and sets switches through the shell's owner-only route (wizard-app-manager `_feature-switches`, the same
// state as Settings › Appearance › Try new features). Live only in Human review; never opens the row.
const SWITCH_API = '/wizard-os-home/store-install/_feature-switches';
let box = null;   // null: not asked yet; {ok, update, locked, switches: {id: {on, locked}}}
function takeSwitches(r) {
  box = { ok: true, locked: !!r.locked, switches: Object.fromEntries((r.switches || []).filter(x => x && x.id).map(x => [x.id, x])) };
}
async function switchApi(data) {
  const init = { credentials: 'same-origin', cache: 'no-store' };
  if (data) Object.assign(init, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Wizard-Store': '1' }, body: JSON.stringify(data) });
  const r = await fetch(SWITCH_API, init);
  let body = null;
  try { body = await r.json(); } catch (_) {}
  if (!r.ok || !body) { const e = new Error((body && body.error) || ''); e.status = r.status; e.json = !!body; throw e; }
  return body;
}
function loadSwitches() {
  return switchApi().then(takeSwitches).catch(e => {
    // 404 from the box: its App Manager predates feature switches. Anything else (no JSON, network): not inside a Wizard.
    box = { ok: false, update: e.status === 404 };
  }).then(() => { if (cache[view] && !typing()) render(cache[view]); });
}
const UPDATE_NOTE = 'Update to try this';
function tryWhy(i) {
  if (!i.switch) return 'This change has nothing to switch on.';
  if (!box) return 'Checking this Wizard…';
  if (!box.ok) return box.update ? UPDATE_NOTE : 'Open the Tracker inside your Wizard to try this.';
  if (box.locked) return 'Switch to For testers in Settings to try this';
  if (!box.switches[i.switch]) return UPDATE_NOTE;   // not in this box's catalog yet
  return '';
}
function trySwitch(i) {
  const live = i.group === 'test' || (i.group == null && (i.labels || []).some(l => String(l).toLowerCase() === 'ready-to-test'));  // Human review only
  const sw = live && box && box.ok && i.switch ? box.switches[i.switch] : null;
  const on = !!(sw && sw.on && !box.locked);
  const b = make('button', 'bd-try'); b.type = 'button'; b.setAttribute('role', 'switch');
  b.setAttribute('aria-checked', String(on)); b.setAttribute('aria-label', 'Try it');
  if (i.switch) b.dataset.switch = i.switch;
  if (!live || tryWhy(i)) b.setAttribute('aria-disabled', 'true');
  b.append(make('i'));
  const stop = e => e.stopPropagation();
  b.addEventListener('keydown', stop); b.addEventListener('pointerdown', stop);
  b.onclick = async e => {
    e.preventDefault(); e.stopPropagation();
    if (!live) return pop(b, '', 'Can be switched on once it’s in Human review.');
    const why = tryWhy(i);
    if (why) return pop(b, '', why);
    const next = b.getAttribute('aria-checked') !== 'true';
    b.setAttribute('aria-checked', String(next)); b.disabled = true;
    try {
      takeSwitches(await switchApi({ id: i.switch, on: next }));
      if (next) pop(b, '', 'On in this Wizard. It shows within a few seconds; switch it off here or in Settings.'); else unpop();
      if (cache[view] && !typing()) render(cache[view]);
    } catch (err) {
      b.setAttribute('aria-checked', String(!next));
      if (err.status === 409) { box.locked = true; return pop(b, '', 'Switch to For testers in Settings to try this'); }
      if (err.status === 404 && err.json) return pop(b, '', UPDATE_NOTE);
      pop(b, '', err.message || 'Couldn’t reach this Wizard. Try again.');
    } finally { b.disabled = false; }
  };
  return b;
}

function row(i, kind) {
  const wrap = make('div', 'bd-rowx');
  const a = tapTarget('bd-item', () => openDetail(i));
  const top = make('span', 'bd-top'); top.append(make('b', 'bd-title', i.title));
  if (kind === 'goals') { top.append(ownerChips(i), bubble(i.comments || 0)); if ((i.assignees || []).length > 1) top.classList.add('multi'); }
  a.append(top);
  if (i.desc) a.append(make('span', 'bd-desc' + (kind === 'bugs' ? ' one' : ''), i.desc));
  const meta = make('span', 'bd-meta');
  if (kind === 'goals') {
    const p = i.progress || { done: 0, total: 0 };
    const pct = p.total ? Math.round(100 * p.done / p.total) : 0;
    if (p.total) {
      const bar = make('span', 'bd-bar'); const fill = make('i'); fill.style.width = pct + '%'; bar.append(fill);
      bar.setAttribute('role', 'progressbar'); bar.setAttribute('aria-valuenow', String(pct)); bar.setAttribute('aria-valuemin', '0'); bar.setAttribute('aria-valuemax', '100');
      a.append(bar);
    }
    const rest = [p.total ? `${p.done}/${p.total}` : '', repoName(i.repo)].filter(Boolean).join(' · ');
    if (rest) meta.append(make('span', 'bd-repo', rest));
  } else {  // bugs: title, one line, then repo · opener · comments
    meta.classList.add('bd-meta-b');
    const a2 = i.group !== 'done' && age(i.created_at);
    meta.append(document.createTextNode([repoName(i.repo), nameOf(i.author) || i.opener].filter(Boolean).join(' · ') + ' · '));
    if (a2) { const g = make('span', 'bd-age', a2); g.title = 'Opened ' + when(i.created_at); meta.append(g, document.createTextNode(' · ')); }
    meta.append(bubble(i.comments || 0));
  }
  if (i.group === 'done' && i.closed_at) meta.append(make('span', 'bd-repo', ' · closed ' + when(i.closed_at)));
  a.append(meta);
  if (i.group === 'airev') a.append(make('span', 'bd-aiwho', 'AI check: ' + (i.ai_reviewer || 'the opener’s agent')));
  wrap.append(a);
  if (i.group !== 'done') wrap.append(trySwitch(i));   // 0.9: no Try it on Done rows
  return wrap;
}

// ---------- Builder switch (mock-up): Paused until the builder host is connected ----------
let builderOn = false;
function showBuilder(b) {
  builderOn = !!b.running;
  const t = el('builder');
  t.setAttribute('aria-checked', String(builderOn));
  el('builder-state').textContent = builderOn ? 'Running' : 'Paused';
  t.title = b.updated_by ? `Set by ${b.updated_by} ${when(new Date(b.updated_at * 1000).toISOString())}` : '';
}
el('builder').onclick = async () => {
  const t = el('builder');
  if (!builderOn) return pop(t, '', 'Not connected to the builder yet');  // stops it: stays Paused
  t.disabled = true;
  try { showBuilder(await api('api/builder', { running: false })); }
  catch (err) { pop(t, '', err.status === 403 ? (err.message || 'Only team members can pause the builder.') : err.message); }
  finally { t.disabled = false; }
};
function loadSide() {
  api('api/builder').then(showBuilder).catch(() => {});
  loadSwitches();
}

function testCard(t, kind) {
  const c = make('article', 'bd-card');
  const top = make('div', 'bd-card-top');
  const h = tapTarget('bd-title', () => openDetail(t)); h.textContent = t.title;
  top.append(h, ...(kind === 'goals' ? [ownerChips(t)] : []), trySwitch(t)); c.append(top);
  if (kind === 'goals' && (t.assignees || []).length > 1) top.classList.add('multi');
  if (t.check) c.append(make('p', 'bd-check' + (kind === 'bugs' ? ' one' : ''), t.check));
  c.append(make('p', 'bd-hint', [repoName(t.repo), t.mine ? 'you' : nameOf(t.author) || t.opener || '', kind === 'bugs' ? age(t.created_at) : '', `${t.comments || 0} comments`].filter(Boolean).join(' · ')));
  const rv = t.reviews || { done: 0, need: 1, by: [] };
  if (rv.need > 1) {  // 0.13: a second, different human reviews it too
    const pr = make('p', 'bd-revs'); pr.append(make('b', '', `${rv.done} of ${rv.need} reviews`));
    if (rv.by && rv.by.length) pr.append(document.createTextNode(' · Works from ' + rv.by.join(', ')));
    c.append(pr);
  }
  // 0.12.2: the same buttons for everyone; on your own item (or your agent's) they explain who reviews it.
  const btns = make('div', 'bd-btns');
  const ok = make('button', 'wz-button', 'Works'); ok.type = 'button';
  const no = make('button', 'wz-button secondary', 'Doesn’t work'); no.type = 'button';
  btns.append(ok, no); c.append(btns);
  const rule = t.can_review === false ? (t.review_rule || 'Someone else reviews this — you opened it.') : t.can_review == null && t.mine ? 'Someone else reviews this — you opened it.' : '';
  if (rule) {
    const why = e => { e.preventDefault(); pop(e.currentTarget, '', rule); };
    ok.onclick = why; no.onclick = why;
    return c;
  }
  const status = make('p', 'wz-status'); c.append(status);
  const busy = on => c.querySelectorAll('button, textarea').forEach(x => { x.disabled = on; });
  const done = msg => {
    hold(false);
    const d = cache[view]; if (d) { d.groups.test = d.groups.test.filter(x => x.id !== t.id); render(d); }
    details.delete(t.id);
    toast(msg); setTimeout(() => load(view, true), 1500);
  };
  ok.onclick = async () => {
    if (t.reviewed_by_me) return pop(ok, '', `You already said Works. A second, different person reviews it too (${rv.done} of ${rv.need}).`);
    busy(true); status.textContent = '';
    try {
      const r = await api('api/test/works', { repo: t.repo, number: t.number });
      if (r.final === false) { busy(false); hold(false); t.reviewed_by_me = true; toast(`Thanks — ${r.reviews.done} of ${r.reviews.need} reviews.`); setTimeout(() => load(view, true), 1500); return; }
      done('Thanks — marked as working.');
    }
    catch (err) { busy(false); if (err.status === 403 || err.status === 409) pop(ok, '', err.message); else status.textContent = err.message; }
  };
  no.onclick = () => {
    const f = make('form', 'bd-fail'); f.autocomplete = 'off';
    const ta = make('textarea', 'wz-input bd-area'); ta.rows = 2; ta.required = true; ta.minLength = 3; ta.maxLength = 4000;
    ta.placeholder = 'What went wrong?'; ta.setAttribute('aria-label', 'What went wrong');
    const r = make('div', 'bd-btns');
    const cancel = make('button', 'wz-button quiet', 'Cancel'); cancel.type = 'button';
    const send = make('button', 'wz-button', 'Send'); send.type = 'submit';
    r.append(cancel, send); f.append(ta, r);
    btns.hidden = true; btns.after(f); ta.focus();
    ta.oninput = () => hold(!!ta.value.trim());
    cancel.onclick = () => { f.remove(); btns.hidden = false; hold(false); };
    f.onsubmit = async e => {
      e.preventDefault(); busy(true); status.textContent = '';
      try { await api('api/test/fails', { repo: t.repo, number: t.number, note: ta.value }); f.remove(); done('Sent back to the builder.'); }
      catch (err) { status.textContent = err.message; busy(false); }
    };
  };
  return c;
}

// ---------- detail: the whole issue and its comments, fetched on tap only ----------
// The server returns GitHub-rendered HTML it has already cleaned (whitelist: no scripts, frames,
// styles, event handlers or javascript: links; images become links). The view parses it inertly
// and re-checks before showing it.
const ATTRS = ['href', 'target', 'rel', 'class', 'type', 'disabled', 'checked', 'align', 'start'];
function safeFragment(html) {
  const doc = new DOMParser().parseFromString('<body>' + (html || '') + '</body>', 'text/html');
  doc.querySelectorAll('script,style,iframe,object,embed,link,meta,base,form,img,video,audio,svg').forEach(n => n.remove());
  for (const n of doc.body.querySelectorAll('*')) {
    for (const a of [...n.attributes]) {
      if (!ATTRS.includes(a.name) || (a.name === 'href' && !/^(https?:|mailto:)/i.test(a.value.trim()))) n.removeAttribute(a.name);
    }
    if (n.tagName === 'A') { n.target = '_blank'; n.rel = 'noopener noreferrer'; }
  }
  const frag = document.createDocumentFragment();
  frag.append(...doc.body.childNodes);
  return frag;
}
function prose(html, empty) {
  const box = make('div', 'bd-prose');
  if (html && html.trim()) box.append(safeFragment(html)); else if (empty) box.append(make('p', 'bd-meta', empty));
  return box;
}

let openId = null;
function roles(i) {
  const r = el('d-roles'), who = i.opener || i.author;
  r.hidden = !who;
  const goal = i.kind === 'goal' || (i.labels || []).some(l => String(l).toLowerCase() === 'goal') || view === 'goals';
  r.textContent = who ? `Opened by ${who} · AI review by their agent · ` + (goal ? 'human review by the goal’s owner or James' : 'human review by anyone else on the team') : '';
}
function openDetail(i) {
  const dlg = el('detail');
  openId = i.id;
  el('d-title').textContent = i.title;
  el('d-meta').textContent = [`${i.repo}#${i.number}`, i.author].filter(Boolean).join(' · ');
  el('d-gh').href = i.url;
  el('d-labels').textContent = '';
  roles(i);
  el('d-body').replaceChildren(make('p', 'bd-empty', 'Loading…'));
  closeCtl(null);
  el('d-comments').replaceChildren(); el('d-comments-h').hidden = true;
  itemFlow(i);
  WzSheet.open(dlg);
  dlg.scrollTop = 0;
  const hit = details.get(i.id);
  if (hit && Date.now() - hit.at < DETAIL_SECONDS * 1000) return fill(hit.data);
  api(`api/detail?repo=${encodeURIComponent(i.repo)}&number=${i.number}`)
    .then(d => { details.set(i.id, { at: Date.now(), data: d }); if (openId === i.id) fill(d); })
    .catch(err => { if (openId === i.id) el('d-body').replaceChildren(make('p', 'wz-status error', err.message)); });
}
// 0.12.2: Mark done / Reopen shows for everyone; only the opener may use it (the server refuses anyone else).
let detailNow = null;
function closeCtl(d) {
  const b = el('d-close');
  detailNow = d;
  b.hidden = !d || !d.state;
  if (d && d.state) b.textContent = d.state === 'closed' ? 'Reopen' : 'Mark done';
}
el('d-close').onclick = async () => {
  const d = detailNow, b = el('d-close');
  if (!d) return;
  const closing = d.state !== 'closed';
  if (!d.can_close) return pop(b, '', closing ? d.close_rule : d.close_rule.replace(' close ', ' reopen '));
  b.disabled = true;
  try {
    await api(closing ? 'api/issue/close' : 'api/issue/reopen', { repo: d.repo, number: d.number });
    details.delete(d.id); toast(closing ? 'Marked done.' : 'Reopened.');
    WzSheet.close ? WzSheet.close(el('detail')) : el('detail').close();
    setTimeout(() => load(view, true), 800);
  } catch (err) { pop(b, '', err.message); }
  finally { b.disabled = false; }
};
function fill(d) {
  closeCtl(d);
  el('d-title').textContent = d.title;
  el('d-meta').textContent = [`${d.repo}#${d.number}`, d.author && `opened by ${d.author}`, when(d.created_at)].filter(Boolean).join(' · ');
  el('d-labels').textContent = (d.labels || []).join(', ');
  roles(d);
  el('d-gh').href = d.url;
  el('d-body').replaceChildren(prose(d.body_html, 'No description.'));
  const cs = d.comments || [];
  el('d-comments-h').hidden = !cs.length;
  el('d-n-comments').textContent = cs.length + (d.comments_total > cs.length ? ` of ${d.comments_total}` : '');
  el('d-comments').replaceChildren(...cs.map(c => {
    const li = make('li', 'bd-comment');
    const head = make('p', 'bd-meta');
    head.append(make('b', 'bd-author', c.author || 'someone'), document.createTextNode(' · ' + when(c.created_at)));
    li.append(head, prose(c.body_html, ''));
    return li;
  }));
}
el('detail').addEventListener('close', () => { openId = null; unpop(); });

// ---------- one item's own assembly line (its label timeline, fetched on tap, cached briefly) ----------
const flows = new Map();
const CUR = { queued: 'open', building: 'build', ai: 'ai', review: 'review', done: 'done' };
function itemFlow(i) {
  const box = el('d-flow');
  box.replaceChildren(make('p', 'bd-meta bd-dflow-wait', ' '));
  const hit = flows.get(i.id);
  if (hit && Date.now() - hit.at < DETAIL_SECONDS * 1000) return drawItemFlow(hit.data);
  api(`api/flow?repo=${encodeURIComponent(i.repo)}&number=${i.number}`)
    .then(f => { flows.set(i.id, { at: Date.now(), data: f }); if (openId === i.id) drawItemFlow(f); })
    .catch(err => { if (openId === i.id) box.replaceChildren(make('p', 'bd-meta', err.message)); });
}
function drawItemFlow(f) {
  const box = el('d-flow');
  const ol = make('ol', 'bd-dflow'); ol.setAttribute('aria-label', 'This item so far');
  const staged = !!f.staged, closedDate = f.closed_at ? new Date(f.closed_at * 1000) : null;
  const val = {
    open: staged ? dur(f.spent.queued) : 'for ' + dur(f.spent.queued),
    build: staged && (f.spent.building || f.build != null) ? dur(f.spent.building) : '—',
    ai: staged && (f.spent.ai || f.ai_tries) ? dur(f.spent.ai) : '—',
    review: staged && (f.spent.review || f.tries) ? dur(f.spent.review) : '—',
    done: closedDate ? closedDate.toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) : '—',
  };
  const cur = CUR[f.stage] || 'open';
  BINS.forEach((x, n) => {
    if (n) ol.append(arrow());
    const reached = x.key === 'open' || (['build', 'ai', 'review'].includes(x.key) && val[x.key] !== '—') || (x.key === 'done' && !!closedDate);
    const li = make('li', 'bd-dbin' + (x.key === cur ? ' cur' : '') + (!reached && x.key !== cur ? ' dim' : ''));
    li.append(make('span', 'bd-dbin-v', val[x.key]), make('span', 'bd-dbin-w', x.word));
    li.title = { open: 'Time spent queued', build: 'Time spent building', ai: 'Time spent in AI review', review: 'Time spent in Human review', done: 'Closed on' }[x.key];
    li.setAttribute('aria-label', `${x.word}: ${val[x.key]}${x.key === cur ? ' (now)' : ''}`);
    ol.append(li);
  });
  const loop = make('p', 'bd-loop bd-loops bd-dloop'); loop.setAttribute('role', 'img');
  const ka = make('span', 'bd-kick bd-kick-ai', (f.ai_kicks || 0) + '×'), k = make('span', 'bd-kick bd-kick-h', (f.kicks || 0) + '×');
  loop.setAttribute('aria-label', `Sent back by AI review ${f.ai_kicks || 0} time${f.ai_kicks === 1 ? '' : 's'}, by Human review ${f.kicks || 0} time${f.kicks === 1 ? '' : 's'}`);
  loop.title = `AI review sent it back ${f.ai_kicks || 0}× · Human review ${f.kicks || 0}×` + (f.kick_to_done != null ? ` · ${dur(f.kick_to_done)} from first kick-back to done` : '');
  loop.classList.toggle('none', !f.kicks && !f.ai_kicks);
  loop.append(make('i', 'bd-loop2'), ka, k);
  const wrap = make('div', 'bd-flow bd-dflowx'); wrap.append(ol, loop);
  box.replaceChildren(wrap);
  if (!staged && f.state === 'open') box.append(make('p', 'bd-meta bd-dflow-note', `Queued for ${dur(f.spent.queued)} · no build yet`));
}

// ---------- start: refresh quietly on focus and every minute ----------
if (!window.WizardApp || WizardApp.version !== 1) {
  say('Wizard system functions are unavailable. Open this preview through Wizard.', 'error');
} else {
  WizardApp.ready({ name: 'wizard-os-tracker', version: '0.13.0' });
  WizardApp.back.register({ canGoBack: () => false, back: () => false });
}
for (const x of sw.querySelectorAll('[data-view]')) x.setAttribute('aria-selected', String(x.dataset.view === view));
api('api/status').then(s => { show(s); if (s.connected) { load(view); loadSide(); const other = view === 'goals' ? 'bugs' : 'goals'; setTimeout(() => { if (!cache[other]) api('api/split?view=' + other).then(d => { cache[other] = d; }).catch(() => {}); }, 600); } })
  .catch(err => { el('loading').hidden = true; say(err.message, 'error'); });
const quiet = () => me && me.connected && !document.hidden && !typing() && !sheetOpen() && !popFor;
const tick = () => { if (quiet() && Date.now() - lastLoad > 20000) load(view, true); };
window.addEventListener('focus', tick);
document.addEventListener('visibilitychange', tick);
setInterval(() => { if (quiet()) load(view, true); }, 30000);
el('reload').onclick = () => { if (!inflight) { load(view, true); loadSide(); } };
