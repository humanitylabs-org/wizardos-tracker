'use strict';
// WizardOS Tracker 0.21.0: Report or request is two steps (the builder's triage step files it; until then the card says
// Sorting…); a Human review card flips an app's own switch (wizard.app-switches/1) and Open <app> shows the app in a
// large sheet over the Tracker. 0.20.0: one primary 'Report or request' button on top opens the WizardOS Reporter form (web/report.js,
// /api/report); items someone else checks say 'James checks this one (he filed it)', yours 'Your turn: check it';
// one Sort for every tab (Your turn first by default), so your items lead Bugs (Shipped included) and App features.
// WizardOS Tracker 0.19.1: the Goals number is every open goal; Human review / Shipping / Done cards and the detail
// name the release that has it (wizardos-tracker#7); wizardos-tracker and wizardos-builder items are never shown.
// 0.19.0: bugs ship before review (Miguel, 10 Nov): the builder merges a fix switched on, so the Bugs
// strip is Queued → Building → Shipped (AI check, then the filer's check, after the fact) → Done. The filer's card says
// 'Fixed and shipping. Check it when you can'; Doesn't work (any time, even after it closed) reopens it to Building.
// Done = in a For everyone release and the filer said Works, or 7 days in the filer's check with no Doesn't work.
// Queued replaces Filed and says why it waits; the Goals count is only goals of yours needing a status update;
// goal cards are minimal; a small 'Tracker updated · Reload' bar appears when the server runs a newer version.
// WizardOS Tracker 0.18.2: the default sort is 'Your turn first': items the viewer can act on now (their Human review,
// approvals for James or Miguel, show-and-tell for James, goals they own needing a status update) on top under a small
// 'Your turn' divider, then everything else oldest first. Core features wait for approval by James OR Miguel
// (wizard-os#423). Stats count items 'Still not working' (Doesn't work said more than once); the detail shows a badge.
// WizardOS Tracker 0.18: Goals | Core features | App features | Bugs. Core vs app comes from the repo (policy
// core_repos). Bugs and app features: Filed → Building → AI review → Human review (by the filer) → Shipping → Done.
// Core features: Waiting for approval (0.18.2: James or Miguel) → Building → AI review → Human review → Show-and-tell (James) → Shipping → Done.
// Shipping = approved, not yet in a release for everyone; Done = 'Shipped in <version>'. Goals are human-led: a status
// light (On track / At risk / Blocked) with a short human status, owners, linked items by stage. Cards: title, one
// 'where it is and what's next' line, ONE action area (Update / Try / Works · Doesn't work / Approve), small meta.
// The Update manager and Try changes live in Settings only.
// WizardOS Tracker 0.17: a calmer list (stage strip with count and name only; Stats, Filter and Sort behind small
// buttons; Works / Doesn't work in the detail), switches you can find (a real toggle, or the exact place with a button,
// on the card, in the detail and in Settings › Try changes), goals steered with Keep going / Change direction, and a
// Update manager (WizardOS and every app: installed vs latest, Update, Update all). Everyone sees the same UI: anything a
// viewer can't do is greyed out with the reason in place.
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
const EMPTY = { goals: 'No open goals.', core: 'No open core features.', apps: 'No open app features.', features: 'No open features.', bugs: 'No open bugs. Nice.' };
const GROUPS = ['test', 'show', 'james', 'airev', 'building', 'queued', 'sorting', 'shipping'];
const VIEWS = ['goals', 'core', 'apps', 'bugs'];
const stage = { goals: null, core: null, apps: null, bugs: null, features: null };   // tap a bin: show only that stage (not remembered)
const doneCache = {};   // view -> { at, items } recently closed, loaded when the Done bin is tapped
// 0.18.1: the last view is remembered per device; first landing is Core features (Goals only if you last used Goals).
const lastView = () => { try { const v = JSON.parse(localStorage.getItem('board.view')); return VIEWS.includes(v) ? v : 'core'; } catch (_) { return 'core'; } };
let me = null, view = ({ '#goals': 'goals', '#bugs': 'bugs', '#core': 'core', '#apps': 'apps', '#features': 'apps' })[location.hash] || lastView(), umOpen = false, umBack = 'core', gen = 0, held = null, lastLoad = 0, who = '';
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
  done: ['Closed', 'The opener closes it once it works. Only James closes a goal, once its done-list is ticked.'],
};
const store = { get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch (_) { return null; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) {} } };
// Chip filters live on Bugs only (0.9: Goals has none); picks are remembered on the device.
const picked = Object.fromEntries([...VIEWS, 'features'].map(v => [v, new Set(store.get('board.repos.' + v) || [])]));
const pickedWho = Object.fromEntries([...VIEWS, 'features'].map(v => [v, new Set(store.get('board.who.' + v) || [])]));
let repoMore = false;   // the Repo row's '+N more' is open (not remembered)
const SORTS = [['turn', 'Your turn first'], ['oldest', 'Oldest'], ['newest', 'Newest'], ['discussed', 'Most discussed'], ['active', 'Recently active']];
// 0.20: ONE sort for every tab (key board.sort3, default 'Your turn first' for everyone again): a pick on one tab
// applies on all of them, so an old per-tab pick can never hide your own items on Bugs or App features.
const savedSort = () => { const k = store.get('board.sort3'); return SORTS.some(([x]) => x === k) ? k : 'turn'; };
const sortBy = new Proxy({}, { get: () => savedSort(), set: (_, __, k) => { store.set('board.sort3', k); return true; } });
const ts = iso => { const t = Date.parse(iso || ''); return isNaN(t) ? 0 : t; };
const SORT_FN = {
  turn: (a, b) => ts(a.created_at) - ts(b.created_at),   // within each group: the existing order (oldest first)
  oldest: (a, b) => ts(a.created_at) - ts(b.created_at),
  newest: (a, b) => ts(b.created_at) - ts(a.created_at),
  discussed: (a, b) => (b.comments || 0) - (a.comments || 0) || ts(a.created_at) - ts(b.created_at),
  active: (a, b) => ts(b.updated_at) - ts(a.updated_at),
};
// 0.18.2: can the viewer act on this now? Human review (theirs), approval (James or Miguel), show-and-tell (James),
// a goal they own that needs a status update (none yet or old; the server's `turn`).
function myTurn(i) {
  if (!i || i.closed_at || i.state === 'closed') return false;
  if (i.group === 'test') return !!i.can_review;
  if (i.group === 'james' || i.group === 'show') return !!i.can_james;
  if (i.group === 'goals' || i.category === 'goal') return !!i.turn;
  return false;
}
function turnDivider(n) {
  const d = make('div', 'bd-turn-div'); d.setAttribute('role', 'separator');
  d.append(make('span', 'bd-turn-w', 'Your turn'), make('span', 'bd-n', String(n)));
  return d;
}
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
const sheetOpen = () => ['detail', 'filter', 'settings', 'report', 'appmodal'].some(x => el(x).open);

// ---------- one small anchored popover (bins, Builder, Try it); tap outside or Esc closes it ----------
let popFor = null;
let refocus = null;   // 0.21: {key, x, y} after an app sheet closes (backTo)
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
  for (const x of [el('report-open'), el('goals-btn'), el('builder'), document.querySelector('.bd-switch')]) x.hidden = !on;   // 0.22: the header row's board controls
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
  try { const s = await api('api/connect', { token: t.value }); t.value = ''; say(''); show(s); load(view); loadSide(); }
  catch (err) { if (err.reason) { t.value = ''; refuse(err.reason, err.message); } else say(err.message, 'error'); }
  finally { b.disabled = false; t.disabled = false; }
};

// ---------- 0.13: Sign in with GitHub (device flow): one button, a code to type on GitHub, the box polls ----------
let devTimer = null, tokenWanted = false, otherWays = false;   // 0.24.0: other ways show only after GitHub sign-in fails
function signinMode(s) {
  const oauth = !!(s && s.oauth), tokenMode = !oauth || tokenWanted;
  el('oauth').hidden = !oauth;
  el('connect-form').hidden = !tokenMode; el('token-help').hidden = !tokenMode;
  el('oauth-go').hidden = tokenWanted || !el('oauth-code').hidden;
  if (tokenWanted) el('oauth-code').hidden = true;
  el('oauth-token').hidden = !(tokenWanted || otherWays);
  el('oauth-token').textContent = tokenWanted ? 'Sign in with GitHub instead' : 'Other ways to sign in';
}
function stopDevice() { clearTimeout(devTimer); devTimer = null; el('oauth-code').hidden = true; signinMode(me); }
function showCode(r) {
  el('oauth-user-code').textContent = r.user_code;
  el('oauth-open').href = /^https:\/\//.test(r.verification_uri || '') ? r.verification_uri : 'https://github.com/login/device';
  el('oauth-wait').textContent = 'Waiting for GitHub… this page signs you in by itself.';
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
  if (r.state !== 'none' && r.state !== 'cancelled') { otherWays = true; signinMode(me); say(r.message || 'Sign-in did not finish. Try again.', 'error'); }
}
el('oauth-go').onclick = async () => {
  const b = el('oauth-go'); b.disabled = true; say('Asking GitHub for a code…', 'note');
  try { showCode(await api('api/device/start', {})); say(''); }
  catch (err) { otherWays = true; signinMode(me); say(err.message, 'error'); }
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

// ---------- 0.18.1: Goals button (left) | Core features | App features | Bugs ----------
const sw = document.querySelector('.bd-switch');
function markView() {
  for (const x of sw.querySelectorAll('[data-view]')) x.setAttribute('aria-selected', String(x.dataset.view === view));
  el('goals-btn').setAttribute('aria-pressed', String(view === 'goals'));
}
// 0.19.1: the number is every open goal (all goals count the same, whoever looks)
const GOALS_TIP = 'Open goals';
function goalsOpen(d) { const g = d && d.groups && d.groups.goals; return g ? Math.max(g.length, d.total || 0) : 0; }
function goalsBadge() {
  const n = el('goals-n');
  const k = goalsOpen(cache.goals);
  n.hidden = !k; n.textContent = k ? String(k) : '';
  n.title = GOALS_TIP;
  n.setAttribute('aria-label', k ? `${k}: ${GOALS_TIP.toLowerCase()}` : '');
  el('goals-btn').title = k ? `${GOALS_TIP}: ${k}` : 'Goals';
}
function pickView(v) {
  if (!v || v === view) return;
  view = v; store.set('board.view', v);
  for (const k of Object.keys(stage)) stage[k] = null;   // 0.15: a new tab always starts unfiltered (all stages)
  markView();
  hold(false);
  try { history.replaceState(null, '', '#' + view); } catch (_) {}
  unpop(); repoMore = false;
  el('scroll').scrollTop = 0;
  if (cache[view]) render(cache[view]);
  else { el('secs').replaceChildren(); el('totals').textContent = ''; el('strip').replaceChildren(); el('filtered').hidden = true; el('empty').hidden = false; el('empty').textContent = 'Loading…'; }
  load(view);
}
sw.addEventListener('click', e => { const b = e.target.closest('[data-view]'); if (b) pickView(b.dataset.view); });
el('goals-btn').onclick = () => pickView('goals');

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
    if (which === 'goals') goalsBadge();
    if (which === view && g === gen && !typing()) render(d);
    if (el('settings').open) tryList();
    say('');
    if (d.stats && d.stats.pending && which !== 'goals') loadStats(which);
    if (which !== 'goals') loadDone(which, refresh);
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
  for (const i of Object.values(d.groups || {}).flat()) if (i.author) n.set(i.author, (n.get(i.author) || 0) + 1);
  return [...n.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

const repoKey = i => (i.repo || '').toLowerCase();
function reposOf(d, keepWho) {
  const n = new Map();
  for (const i of Object.values(d.groups || {}).flat()) if (keepWho(i)) n.set(i.repo, (n.get(i.repo) || 0) + 1);
  return [...n.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}
function render(d) {
  if (d.view !== view) return;
  for (const g of Object.values(d.groups || {})) for (const i of g || []) adoptSwitch(i);
  for (const i of (d.items || [])) adoptSwitch(i);
  // 0.17: person and repo filters live in the Filter sheet (every list view); one small 'Filtered: …' line says what is set
  const whoSet = pickedWho[d.view], chosen = picked[d.view];
  const allPeople = new Set(authorsOf(d).map(([p]) => p.toLowerCase()));
  for (const p of [...whoSet]) if (!allPeople.has(p)) whoSet.delete(p);
  const known = new Map((d.repos || []).map(r => [r.toLowerCase(), r]));
  for (const [r] of reposOf(d, () => true)) known.set(r.toLowerCase(), r);
  for (const r of [...chosen]) if (!known.has(r)) chosen.delete(r);
  const byWho = i => !whoSet.size || whoSet.has((i.author || '').toLowerCase());
  const byRepo = i => !chosen.size || chosen.has(repoKey(i));
  const allWho = authorsOf(d), allRepo = new Map(reposOf(d, () => true).map(([r, n]) => [r.toLowerCase(), n]));
  const whoN = new Map(authorsOf({ groups: Object.fromEntries(Object.entries(d.groups).map(([g, l]) => [g, l.filter(byRepo)])) }).map(([p, n]) => [p.toLowerCase(), n]));
  const repoN = new Map(reposOf(d, byWho).map(([r, n]) => [r.toLowerCase(), n]));
  const label = p => { const n = nameOf(p); return p === d.login ? `${n} (you)` : n; };
  const people = allWho.map(([p, t]) => [p.toLowerCase(), label(p), whoN.get(p.toLowerCase()) || 0, t]).sort((a, b) => b[3] - a[3] || a[1].localeCompare(b[1]));
  const repos = [...known].map(([k, r]) => [k, repoName(r), repoN.get(k) || 0, allRepo.get(k) || 0]).sort((a, b) => b[3] - a[3] || a[1].localeCompare(b[1]));
  chipRow('who', whoSet, people);
  chipRow('repo', chosen, repos);
  filteredLine(whoSet, chosen, people, repos);
  const goals = d.view === 'goals';
  el('lists').classList.toggle('bd-goalsview', goals);
  el('sort-btn').replaceChildren(make('span', 'bd-sort-k', 'Sort: '), (SORTS.find(([k]) => k === sortBy[d.view]) || SORTS[0])[1]);   // 0.22: phones drop 'Sort: '
  el('sort-btn').hidden = stage[d.view] === 'done';   // Done lists newest closed first
  const keep = i => byWho(i) && byRepo(i);
  const order = SORT_FN[sortBy[d.view]];
  if (goals) return renderGoals(d, keep, order);
  const groups = Object.fromEntries(GROUPS.map(g => { const l = (d.groups[g] || []).filter(keep); return [g, order ? l.sort(order) : l]; }));
  // 0.18: Shipping = open approved items + closed items not yet in a release for everyone; Done = shipped (from api/done)
  const dc = doneCache[d.view] || {};
  for (const i of groups.shipping) if (dc.open_ship && dc.open_ship[i.id]) i.ship = dc.open_ship[i.id];
  const closed = dc.items ? dc.items.filter(keep) : null;
  groups.shipping = [...groups.shipping, ...(closed || []).filter(i => i.group === 'shipping')];
  groups.done = closed ? closed.filter(i => i.group === 'done') : null;
  const st = d.stats || {}, hist = (st.items || []).filter(keep);
  const doneN = st.pending || st.error ? null : hist.filter(i => i.state === 'closed').length;
  const bins = binsOf(d.view);
  strip(d, bins, groups);
  flow(d, groups, doneN, st, hist);
  waitLine(d.view, groups);
  const only = stage[d.view];
  const bin = bins.find(b => b.key === only);
  const showing = g => !only ? g !== 'done' : (bin ? bin.groups.includes(g) : false);
  el('totals').textContent = d.more && !only ? `showing ${d.shown} of ${d.total}` : '';
  const secs = [];
  let any = false;
  // 0.18.2: 'Your turn first' lifts what the viewer can act on now above every section, under a small divider
  const turnFirst = sortBy[d.view] === 'turn';
  const mine = turnFirst ? sectionsOf(d.view).filter(([g]) => showing(g) && groups[g]).flatMap(([g]) => groups[g].filter(myTurn)) : [];
  if (mine.length) {
    any = true;
    const s = make('section', 'bd-sec bd-turn'); s.id = 'sec-turn';
    const l = make('div', 'bd-list'); l.replaceChildren(...mine.map(itemCard));
    s.append(turnDivider(mine.length), l); secs.push(s, make('hr', 'bd-turn-end'));
  }
  const mineSet = new Set(mine);
  for (const [g, title] of sectionsOf(d.view)) {
    const list = groups[g] && groups[g].filter(i => !mineSet.has(i));
    if (!showing(g) || !list || !list.length) continue;
    any = true;
    const s = make('section', 'bd-sec'); s.id = 'sec-' + g;
    const h = make('h2', 'bd-sec-h', title + ' '); h.append(make('span', 'bd-n', String(list.length)));
    const wo = whoWaits(list);   // 0.25: whose move it is, right on the stage heading
    if (wo) h.append(make('span', 'bd-sec-who', '· waiting on ' + wo));
    const l = make('div', 'bd-list'); l.replaceChildren(...list.map(itemCard));
    s.append(h, l); secs.push(s);
  }
  if (secs.length && secs[secs.length - 1].tagName === 'HR') secs.pop();   // nothing below the 'Your turn' group
  el('secs').replaceChildren(...secs);
  // 0.16: in the background, cached. 0.20: shipped bugs in their AI check too (their line names the release)
  const askOn = [...(d.groups.test || []), ...(d.view === 'bugs' ? d.groups.airev || [] : [])];
  if (askOn.length) setTimeout(() => checkOnBox(askOn), 0);
  if (refocus) backTo();   // 0.21: just closed an app sheet: stay on the same card and button through repaints
  el('empty').hidden = any;
  if (only === 'done' && !groups.done) { el('empty').hidden = false; el('empty').textContent = dc.error || 'Loading…'; return; }
  el('empty').textContent = only ? `Nothing in ${(bin || {}).word || ''} here${whoSet.size || chosen.size ? ' with this filter' : ''}.`
    : whoSet.size || chosen.size ? 'Nothing here with this filter.' : EMPTY[d.view];
}
// 0.25 (Miguel, 10 Nov): every tab answers "who has it for action?" and "where is it stuck?" in one line under the strip.
const WAIT_VERB = { test: 'to check', james: 'to approve', show: 'show-and-tell', airev: 'AI check', building: 'building', queued: 'queued', sorting: 'sorting' };
function whoWaits(list) {
  const by = new Map();
  for (const i of list) { const w = ((i.waiting_on || {}).who || []).join(' or '); if (w) by.set(w, (by.get(w) || 0) + 1); }
  const names = [...by.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  if (!names.length) return '';
  return names.length === 1 ? names[0][0] : names.map(([w, n]) => `${w} ${n}`).join(', ');
}
function waitLine(v, groups) {
  const p = el('waitline'); if (!p) return;
  const people = new Map();   // who -> [[stage, n, stuck]]
  for (const g of Object.keys(WAIT_VERB)) for (const i of groups[g] || []) {
    const wo = i.waiting_on || {};
    for (const w of [(wo.who || []).join(' or ')].filter(Boolean)) {   // 'James or Miguel' is one entry, not two
      const key = wo.stuck ? 'stuck' : (v === 'bugs' && g === 'airev' ? 'airev' : g);
      const m = people.get(w) || new Map(); m.set(key, (m.get(key) || 0) + 1); people.set(w, m);
    }
  }
  const verb = k => k === 'stuck' ? 'stuck (builder gave up)' : WAIT_VERB[k];
  const rows = [...people.entries()].map(([w, m]) => [w, [...m.values()].reduce((a, b) => a + b, 0), m]).sort((a, b) => b[1] - a[1]);
  p.hidden = !rows.length;
  p.replaceChildren(make('span', 'bd-wait-k', 'Waiting on '), ...rows.flatMap(([w, , m], n) => {
    const bit = make('span', 'bd-wait-p' + (m.has('stuck') ? ' warn' : ''));
    bit.append(make('b', '', w), document.createTextNode(' ' + [...m.entries()].map(([k, c]) => `${c} ${verb(k)}`).join(', ')));
    return n ? [document.createTextNode(' · '), bit] : [bit];
  }));
}
// 0.17: 'Filtered: Jan · wizard-ux ×' only when a filter is set; × clears it.
function filteredLine(whoSet, chosen, people, repos) {
  const p = el('filtered');
  const names = [...people.filter(([k]) => whoSet.has(k)).map(x => x[1].replace(' (you)', '')), ...repos.filter(([k]) => chosen.has(k)).map(x => x[1])];
  p.hidden = !names.length;
  el('filter-btn').classList.toggle('on', !!names.length);
  if (!names.length) return p.replaceChildren();
  const x = make('button', 'bd-x', '×'); x.type = 'button'; x.setAttribute('aria-label', 'Clear the filter');
  x.onclick = () => { whoSet.clear(); chosen.clear(); saveFilter('who'); saveFilter('repo'); };
  p.replaceChildren(document.createTextNode('Filtered: ' + names.join(' · ') + ' '), x);
}
el('filter-btn').onclick = () => { unpop(); if (cache[view]) render(cache[view]); WzSheet.open(el('filter')); };
el('filter-done').onclick = () => WzSheet.close(el('filter'));
el('filter-clear').onclick = () => { pickedWho[view].clear(); picked[view].clear(); saveFilter('who'); saveFilter('repo'); };
// 0.17.1: Show stats / Hide stats expands the stats inline under the strip; collapsed by default, remembered on this device.
function statsShown(on, animate) {
  const s = el('stats'), b = el('stats-btn');
  if (!animate) { s.classList.add('still'); requestAnimationFrame(() => requestAnimationFrame(() => s.classList.remove('still'))); }
  s.classList.toggle('open', on); s.inert = !on;
  b.setAttribute('aria-expanded', String(on)); b.textContent = on ? 'Hide stats' : 'Show stats';
}
statsShown(store.get('board.stats') === true, false);
el('stats-btn').onclick = () => { const on = el('stats-btn').getAttribute('aria-expanded') !== 'true'; store.set('board.stats', on); statsShown(on, true); };
el('sort-btn').onclick = () => {
  const b = el('sort-btn'), list = make('div', 'bd-menu'); list.setAttribute('role', 'menu');
  for (const [k, label] of SORTS) {
    const it = make('button', 'bd-menu-i', label); it.type = 'button'; it.setAttribute('role', 'menuitemradio');
    it.setAttribute('aria-checked', String(sortBy[view] === k));
    it.onclick = () => { sortBy[view] = k; unpop(); if (cache[view]) render(cache[view]); };
    list.append(it);
  }
  pop(b, '', [list]);
  const first = list.querySelector('[aria-checked="true"]'); if (first) first.focus();
};

// Tap a bin: show only that stage; tap it again (or the pill) for everything. Done loads recently closed.
function setStage(g) {
  stage[view] = stage[view] === g ? null : g;
  unpop();
  if (cache[view]) render(cache[view]);
}
async function loadDone(which, force) {
  const hit = doneCache[which];
  if (hit && hit.items && Date.now() - hit.at < (force ? 60000 : 120000)) return;
  try {
    const r = await api('api/done?view=' + which + (force ? '&refresh=1' : ''));
    doneCache[which] = { at: Date.now(), items: r.items || [], open_ship: r.open_ship || {} };
  } catch (err) { doneCache[which] = { at: Date.now(), items: null, error: err.message }; }
  if (which === view && cache[which] && !typing()) render(cache[which]);
}

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
  // 0.17: the Filter sheet lists every person and repo (no '+N more')
  out.push(...options.map(([k, label, n, t]) => chip(label, n, set.has(k), toggle(k), n ? '' : 'zero', t)));
  box.replaceChildren(...out);
}
function saveFilter(kind) {
  store.set((kind === 'who' ? 'board.who.' : 'board.repos.') + view, [...(kind === 'who' ? pickedWho : picked)[view]]);
  if (cache[view]) render(cache[view]);
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
  const reviewed = items.filter(i => (i.review_rounds || []).length || i.kicks), kicked = items.filter(i => i.kicks);
  const toDone = kicked.map(i => i.kick_to_done).filter(x => x != null);
  const aiSeen = items.filter(i => (i.ai_rounds || []).length || i.ai_kicks), aiKicked = items.filter(i => i.ai_kicks);
  return { queued: spread(items.map(i => i.wait)), building: spread(items.map(i => i.build)),
    ai: spread(items.flatMap(i => i.ai_rounds || [])),
    review: spread(items.flatMap(i => i.review_rounds || [])), done: spread(items.map(i => i.total)),
    kick: { reviewed: reviewed.length, kicked: kicked.length, rate: reviewed.length ? kicked.length / reviewed.length : null,
      per: kicked.length ? kicked.reduce((a, i) => a + i.kicks, 0) / kicked.length : null,
      toDone: toDone.length ? toDone.reduce((a, b) => a + b, 0) / toDone.length : null },
    still: items.filter(i => (i.kicks || 0) >= 2).length,   // 0.18.2: Doesn't work said more than once
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
  el('stats-note').textContent = sinceText(d.since) + ' · typical time per step, the target (✎ same for everyone), and how often work comes back.';
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
  const sn = el('still-n');   // 0.18.2
  sn.hidden = !ls;
  if (ls) {
    sn.replaceChildren(make('b', '', 'Still not working: ' + ls.still), document.createTextNode(' · items where someone said Doesn’t work more than once'));
    sn.classList.toggle('warn', ls.still > 0);
  }
}

// 0.18: each list tab has its own stage strip; every stage has a small ⓘ saying what happens there and who does it.
const HUMAN_CHECK_TIP = 'A quick sanity check by whoever filed it. It never holds up shipping.';
const STAGE_INFO = {
  queued: 'Queued. Each card says why it waits: Next for the builder (it picks it up on its next run), or Oscar builds this one (the builder skips the Tracker and Builder repos).',
  shipped: 'Fixed and merged switched on: in For testers within minutes, then For everyone with the next release. Shipping never waits on a human. The filer’s agent runs a quick AI check meanwhile. Doesn’t work, at any point, sends it back to Building.',
  humancheck: 'A quick sanity check by whoever filed it. It never holds up shipping. They can do it any time after Shipped, even while it is still in For testers: Works, or Doesn’t work (back to Building).',
  checked: 'Whoever filed it said Works, or 7 days passed with no Doesn’t work: Checked (no problems in 7 days). Each card also says which release has it.',
  james: 'James or Miguel approves before the builder starts. Core features change WizardOS for everyone. James or Miguel: Approve or Decline on the card.',
  building: 'The WizardOS Builder writes the change (a feature arrives behind a switch, off by default).',
  corebuild: 'Approved by James or Miguel. The WizardOS Builder writes the change behind a switch, off by default.',
  airev: 'The filer’s agent checks that the build matches the issue: on to Human review, or back to Building (counted as a kick-back).',
  test: 'The person who filed it tries it on their Wizard (Update first if needed, then the switch if there is one) and says Works or Doesn’t work. Doesn’t work goes back to Building.',
  show: 'James sees it working. When he approves, the switch is removed (on for everyone) and it ships.',
  shipping: 'Approved, but not yet in a release everyone gets. It shows which wait it is in: Waiting for release, In For testers <version>, Waiting for Mac app build, or Waiting for <app> release.',
  done: 'In a release that reaches everyone: For everyone (stable) for WizardOS and the Mac app, the app’s latest Store release for apps. The card says Shipped in <version>.',
};
function binsOf(v) {
  const tail = [{ key: 'airev', word: 'AI review', groups: ['airev'] }, { key: 'test', word: 'Human review', groups: ['test'] }];
  const end = [{ key: 'shipping', word: 'Shipping', groups: ['shipping'] }, { key: 'done', word: 'Done', groups: ['done'] }];
  if (v === 'core') return [{ key: 'james', word: 'Waiting for approval', groups: ['sorting', 'james'], tip: 'James or Miguel approves before the builder starts' },
    { key: 'building', word: 'Build queue', groups: ['queued', 'building'], info: 'corebuild' }, ...tail,
    { key: 'show', word: 'Show-and-tell', groups: ['show'] }, ...end];
  // 0.20 (Miguel): shipping never waits on humans. Shipped = merged, on its way (AI check running); Human check = the filer's
  // sanity check, any time after Shipped; Checked = they said Works, or 7 days with no Doesn't work. Release is shown apart.
  if (v === 'bugs') return [{ key: 'queued', word: 'Queued', groups: ['sorting', 'queued'] }, { key: 'building', word: 'Building', groups: ['building'] },
    { key: 'shipped', word: 'Shipped', groups: ['airev'], tip: 'Merged and on its way to everyone. Never waits on a human.' },
    { key: 'test', word: 'Human check', groups: ['test'], info: 'humancheck', tip: HUMAN_CHECK_TIP },
    { key: 'done', word: 'Checked', groups: ['shipping', 'done'], info: 'checked', tip: 'Whoever filed it said Works, or 7 days passed with no Doesn’t work' }];
  return [{ key: 'queued', word: 'Queued', groups: ['sorting', 'queued'] }, { key: 'building', word: 'Building', groups: ['building'] }, ...tail, ...end];
}
function sectionsOf(v) {
  if (v === 'bugs') return [['test', 'Human check'], ['airev', 'Shipped · AI check'], ['building', 'Building'], ['queued', 'Queued'], ['sorting', 'Sorting…'],
    ['shipping', 'Checked'], ['done', 'Checked · in a release for everyone']];
  return [['test', 'Human review'], ['show', 'Show-and-tell'], ['james', 'Waiting for approval'], ['airev', 'AI review'],
    ['building', 'Building'], ['queued', v === 'core' ? 'Approved · waiting for the builder' : 'Queued'], ['sorting', 'Sorting…'], ['shipping', 'Shipping'], ['done', 'Done']]
    .filter(([g]) => v === 'core' || !['show', 'james'].includes(g));
}
function strip(d, bins, groups) {
  const only = stage[d.view], out = [];
  bins.forEach((x, n) => {
    if (n) out.push(arrow());
    const lists = x.groups.map(g => groups[g]);
    const count = lists.some(l => l == null) ? null : lists.reduce((a, l) => a + l.length, 0);
    const li = make('li', 'bd-stepli bd-binx' + (count ? ' on' : '') + (only === x.key ? ' sel' : '') + (only && only !== x.key ? ' dim' : ''));
    li.dataset.step = x.key;
    const b = make('button', 'bd-bin' + (count ? ' on' : '')); b.type = 'button'; b.dataset.step = x.key;
    b.setAttribute('aria-pressed', String(only === x.key));
    b.setAttribute('aria-label', `${x.word}: ${count == null ? 'counting' : count}. ${only === x.key ? 'Show everything' : 'Show only ' + x.word}`);
    b.append(make('span', 'bd-bin-n', count == null ? '—' : String(count)));
    const w = make('span', 'bd-bin-w', x.word + ' ');
    const info = make('button', 'bd-i bd-i-s'); info.type = 'button'; info.setAttribute('aria-label', 'What happens in ' + x.word); info.append(infoIcon());
    info.onclick = e => { e.stopPropagation(); pop(info, x.word, STAGE_INFO[x.info || x.key]); };
    w.append(info);
    if (x.tip) { li.title = x.tip; b.title = x.tip; }
    li.append(b, w);
    li.onclick = () => setStage(x.key);
    out.push(li);
  });
  el('strip').replaceChildren(...out);
  el('strip').parentNode.style.gridTemplateColumns = bins.map(() => 'minmax(0, 1fr)').join(' var(--ga) ');
  // 0.22: on a phone the strip scrolls sideways (one line, never wraps); keep the chosen stage in view
  const sel = only && el('strip').querySelector('.bd-binx.sel'), sc = el('strip').parentNode;
  if (sel && sc.scrollWidth > sc.clientWidth) {
    const r = sel.getBoundingClientRect(), o = sc.getBoundingClientRect();
    sc.scrollLeft = Math.max(0, sc.scrollLeft + r.left - o.left - (o.width - r.width) / 2);
  }
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
    return pop(anchor, who, [kind === 'goals' ? 'Opens goals. They wait here until the builder picks them up.' : kind === 'features' ? 'Opens features to try. They wait here until the builder picks them up.' : 'Opens bugs. They wait here until the builder picks them up.', ...extra]);
  }
  const s = (steps || []).find(y => y.key === x.key);
  let [who, text] = POP[x.key];
  if (x.key === 'review') {
    const n = (cache[kind] || {}).human_reviews || 1;
    if (kind === 'goals') { who = s ? s.role : 'Goal owners or James'; text = 'The goal’s owners, or James, look at each slice: Keep going or Change direction, and tick the done-list items that are now done. No Works / Doesn’t work on goals.'; }
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
// 0.23: ONE catalog for core and apps. The box's App Manager merges every installed app's own switches
// (wizard.app-switches/1, ids '<app>:<switch>', kind 'app') with the core ones, and flips an app's switch server-side
// with the owner's authority, so a card works the same in every browser. A Human review item whose issue a catalog
// switch names gets a real Try it toggle, core or app.
function takeSwitches(r) {
  const rows = (r.switches || []).filter(x => x && x.id);
  const byIssue = {};
  for (const x of rows) for (const ref of (x.issues || [])) { const k = String(ref).toLowerCase(); if (!byIssue[k]) byIssue[k] = x.id; }
  box = { ok: true, locked: !!r.locked, switches: Object.fromEntries(rows.map(x => [x.id, x])), byIssue };
  for (const v of Object.keys(cache)) for (const g of Object.values((cache[v] || {}).groups || {})) for (const i of g || []) adoptSwitch(i);
  for (const v of Object.keys(cache)) for (const i of ((cache[v] || {}).items || [])) adoptSwitch(i);
}
// An item without a 'Switch:' line takes the catalog switch that names its issue (an app's own switch, usually).
function adoptSwitch(i) {
  if (!i || !box || !box.ok || (i.switch && !i.switch_adopted)) return i;
  // 0.24.2: a 'Switch: <app>:<id>' line names the catalog row itself
  const named = appSwitchId(i);
  const id = box.byIssue[String(i.id || '').toLowerCase()] || (named && box.switches[named.id] ? named.id : null);
  if (id) { i.switch = id; i.switch_adopted = true; }
  return i;
}
// 0.24.2: an app switch written in the builder's line as '<app>:<switch>' (the catalog's own id form)
function appSwitchId(i) {
  const m = /^([a-z0-9][a-z0-9-]{0,63}):([a-z0-9][a-z0-9-]{0,63})$/i.exec(String(i.switch_how || '').trim());
  return m ? { id: m[0].toLowerCase(), app: m[1].toLowerCase(), sw: m[2].toLowerCase() } : null;
}
// A core switch is locked on For everyone; an app's own switch follows the app (never locked by the channel).
const swLocked = sw => !!(sw && (sw.kind === 'app' ? sw.locked : (box.locked || sw.locked)));
async function switchApi(data) {
  const init = { credentials: 'same-origin', cache: 'no-store' };
  if (data) Object.assign(init, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Wizard-Store': '1' }, body: JSON.stringify(data) });
  const r = await fetch(SWITCH_API, init);
  let body = null;
  try { body = await r.json(); } catch (_) {}
  if (!r.ok || !body) { const e = new Error((body && body.error) || ''); e.status = r.status; e.json = !!body; throw e; }
  return body;
}
let switchTry = 0;
function loadSwitches() {
  switchTry++;
  return switchApi().then(takeSwitches).catch(e => {
    // 404 from the box: its App Manager predates feature switches. Anything else (no JSON, network): not inside a Wizard.
    box = { ok: false, update: e.status === 404, status: e.status || 0 };
  }).then(() => { if (cache[view] && !typing()) render(cache[view]); if (el('settings').open) tryList(); });
}
const UPDATE_NOTE = 'Update to try this';
function tryWhy(i) {
  if (!i.switch) return LIVE_NOTE;
  if (!box) return 'Checking this Wizard…';
  if (!box.ok && switchTry < 3) setTimeout(loadSwitches, 4000 * switchTry);   // 0.17: a slow first answer no longer greys it for good
  if (!box.ok) return box.update ? UPDATE_NOTE : 'Open the Tracker inside your Wizard to try this.';
  if (!box.switches[i.switch]) return 'Your Wizard doesn’t have this switch yet: update WizardOS';   // not in this box's catalog yet
  if (swLocked(box.switches[i.switch])) return 'Switch to For testers in Settings to try this';
  return '';
}
// 0.17: the switch, said in words on the status line (and why it's greyed out, in place, not only on tap)
function switchWords(i) {
  if (!i.switch) return null;
  const why = tryWhy(i);
  if (why) return make('span', 'bd-sw-why', why);
  const sw = box.switches[i.switch];
  return make('span', 'bd-sw-name', `${sw.name || i.switch}: ${sw.on && !swLocked(sw) ? 'on' : 'off'}`);
}
// 0.17: a switch the Tracker can't flip: the exact place, with a button that opens it when there is one.
function placeBits(i) {
  const pl = i.switch_place;
  if (!pl) return [];
  const out = [];
  if (pl.kind === 'mac') {
    out.push(make('span', 'bd-sw-why', 'Mac app switch: ' + ((pl.cmd || '').split(' ')[3] || i.switch_how)));
    if (pl.cmd) out.push(smallBtn('Copy command', async b => {
      let ok = false; try { await navigator.clipboard.writeText(pl.cmd); ok = true; } catch (_) {}
      pop(b, ok ? 'Copied' : 'Run this in Terminal', [pl.cmd, 'Then quit and reopen Wizard on your Mac.']);
    }));
  } else if (pl.kind === 'app') {
    const app = appForRepo(pl.repo);
    const hit = app && appSwitchFor(i, app);
    if (hit) out.push(appToggle(i, app, hit), make('span', 'bd-sw-name', `${hit.name || hit.id}: ${hit.on ? 'on' : 'off'}`));
    else out.push(make('span', 'bd-sw-why', `${app ? app.name : repoName(pl.repo)}: ${pl.text}`));
    out.push(openKey(smallBtn(app ? `Open ${app.name}` : 'Open', b => app ? openApp(app.id, app.name, b, i) : pop(b, '', `Open ${repoName(pl.repo)} on your Wizard, then ${pl.text}.`)), i));
  } else out.push(make('span', 'bd-sw-why', 'Turn on: ' + pl.text));
  return out;
}
// 0.17: ask first, in place (a small popover with Cancel focused), never window.confirm
function askPop(anchor, text, yesText, fn) {
  const row = make('div', 'bd-askrow');
  const no = make('button', 'bd-mini', 'Cancel'); no.type = 'button'; no.onclick = () => unpop();
  const yes = make('button', 'bd-mini bd-mini-go', yesText); yes.type = 'button'; yes.onclick = () => { unpop(); fn(); };
  row.append(no, yes);
  pop(anchor, '', [text, row]);
  no.focus();
}
function smallBtn(text, fn) {
  const b = make('button', 'bd-mini', text); b.type = 'button';
  b.addEventListener('pointerdown', e => e.stopPropagation());
  b.onclick = e => { e.preventDefault(); e.stopPropagation(); fn(b); };
  return b;
}
// ---------- 0.21 app switches (wizard.app-switches/1, docs/app-switches.md) ----------
// An app declares its own feature switches and serves them at its same-origin path: GET /<app>/api/switches ->
// {contract: 'wizard.app-switches/1', switches: [{id, name, description, on, default, issues: ['owner/repo#N']}]};
// POST the same path {id, on} (JSON, X-Wizard-Switch: 1, the Wizard's own origin) -> the same listing. The owner's
// state lives in the app (per owner, not per device), so the card, the app's own Settings and its agent agree.
// A card finds its switch by the issue it delivers (issues) or by the name in the hand-over's Switch: line.
const APP_SWITCHES = 'wizard.app-switches/1';
const appSw = {};   // app id -> {at, ok, status, switches, busy}
// Path: /<app>/api/switches, or /<app>/api/view/switches for an app whose owner pages live under api/view (Messenger).
const SW_PATHS = ['/api/switches', '/api/view/switches'];
const appSwWhere = {};   // app id -> the path that answered
async function appSwitchApi(id, data) {
  // 0.24.2: the read carries X-Wizard-Switch: 1 too. Calendar (and any app checking the owner the contract's way) answers
  // its switch list only with it (403 owner_only without), which hid every Calendar Try it once the box catalog lacked
  // app rows (an App Manager older than the one-catalog release).
  const init = { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json', 'X-Wizard-Switch': '1' } };
  if (data) Object.assign(init, { method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-Wizard-Switch': '1' }, body: JSON.stringify(data) });
  let r = null;
  for (const p of appSwWhere[id] ? [appSwWhere[id]] : SW_PATHS) {
    r = await fetch('/' + encodeURIComponent(id) + p, init);
    if (r.status !== 404 || data) { if (r.ok) appSwWhere[id] = p; break; }
  }
  const json = /json/.test(r.headers.get('content-type') || '') ? await r.json().catch(() => null) : null;
  if (!r.ok || !json || !Array.isArray(json.switches)) {
    const er = json && json.error, e = new Error(typeof er === 'string' ? er : (er && er.message) || ''); e.status = r.status; throw e;
  }
  return json;
}
function loadAppSwitches(id, force) {
  const cur = appSw[id];
  if (cur && (cur.busy || (!force && Date.now() - cur.at < 60000))) return;
  appSw[id] = { ...(cur || { switches: [] }), busy: true };
  appSwitchApi(id).then(j => { appSw[id] = { at: Date.now(), ok: true, status: 200, switches: j.switches.filter(x => x && x.id) }; })
    .catch(e => { appSw[id] = { at: Date.now(), ok: false, status: e.status || 0, switches: [] }; })
    .then(() => { if (cache[view] && !typing() && !el('appmodal').open) render(cache[view]); if (el('settings').open) tryList(); });
}
function appSwitchFor(i, app, byIssueOnly) {
  const st = appSw[app.id];
  if (!st) { loadAppSwitches(app.id); return null; }
  if (!st.ok) return null;
  const id = String(i.id || '').toLowerCase(), how = String(i.switch_how || '').toLowerCase();
  return st.switches.find(x => (x.issues || []).some(r => String(r).toLowerCase() === id))
    || (!byIssueOnly && st.switches.find(x => x.name && how.includes(String(x.name).toLowerCase()))) || null;
}
// 0.24.2: why an app's Try it can't be flipped right now (greyed, never hidden)
function appWhy(i, app, pl) {
  if (!app) return `Install ${repoName((pl && pl.repo) || i.repo)} first`;
  const st = appSw[app.id];
  if (!st || (st.busy && !st.at)) return `Checking ${app.name}…`;
  if (!st.ok) return st.status === 404 ? (app.update ? `Update ${app.name} first` : `${app.name} has no switches to flip yet`) : st.status === 403 || st.status === 401 ? `Open ${app.name} once, then try again` : `Can’t reach ${app.name} right now`;
  // it answers, but doesn't list this item's switch: newer in the Store, or not in this build at all
  return app.update ? `Update ${app.name} first` : `${app.name} ${app.version || ''} doesn’t list this switch yet`.replace('  ', ' ');
}
// 0.24.2: a Try it that can't be flipped right now: greyed, the reason in its label and on tap (Miguel: never hidden)
function greyTry(name, why, on) {
  const b = make('button', 'bd-try'); b.type = 'button'; b.setAttribute('role', 'switch');
  b.setAttribute('aria-disabled', 'true'); b.setAttribute('aria-label', `Try it: ${name || ''} (${why})`); b.title = why;
  b.dataset.tryWhy = why;
  b.append(make('i')); tryFace(b, !!on);
  const stop = e => e.stopPropagation();
  b.addEventListener('keydown', stop); b.addEventListener('pointerdown', stop);
  b.onclick = e => { e.preventDefault(); e.stopPropagation(); pop(b, '', why); };
  return b;
}
function appToggle(i, app, sw) {
  const b = make('button', 'bd-try bd-try-app'); b.type = 'button'; b.setAttribute('role', 'switch');
  b.setAttribute('aria-label', `Try it: ${sw.name || sw.id} in ${app.name}`); b.title = `${sw.name || sw.id} (${app.name})`;
  b.dataset.appSwitch = app.id + ':' + sw.id;
  b.append(make('i')); tryFace(b, !!sw.on);
  const stop = e => e.stopPropagation();
  b.addEventListener('keydown', stop); b.addEventListener('pointerdown', stop);
  b.onclick = async e => {
    e.preventDefault(); e.stopPropagation();
    const next = b.getAttribute('aria-checked') !== 'true';
    tryFace(b, next); b.disabled = true;
    try {
      const j = await appSwitchApi(app.id, { id: sw.id, on: next });
      appSw[app.id] = { at: Date.now(), ok: true, status: 200, switches: j.switches.filter(x => x && x.id) };
      if (b.closest('#appmodal')) unpop();
      else if (next) pop(b, '', `On in ${app.name}. Now open ${app.name} and try it; switch it off here.`); else unpop();
      flipped();
    } catch (err) {
      tryFace(b, !next);
      pop(b, '', err.status === 403 ? `Only this Wizard’s owner can switch ${app.name}.` : err.status === 401 ? `Open ${app.name} once, then try again.` : `${app.name} didn’t switch (${err.message || 'HTTP ' + (err.status || 'error')}).`);
    } finally { b.disabled = false; if (cache[view] && !typing()) setTimeout(() => render(cache[view]), 0); }
  };
  return b;
}

// ---------- 0.21 Open <app>: the app in a large sheet over the Tracker; Close returns exactly where you were ----------
// Same-origin path /<app id>/ in an iframe. An app that refuses framing (X-Frame-Options DENY, CSP frame-ancestors
// without this origin) opens in a new tab instead, and says so.
let appBack = null;
// Each Open button carries its item, so focus can return to the same button after a re-render replaced it.
function openKey(b, i) { b.dataset.openKey = i.id; return b; }
// 0.22: the list scrolls in #scroll (not the window): keep both, so Close lands exactly where you were
const place = () => ({ x: scrollX, y: scrollY, top: el('scroll').scrollTop });
function goPlace(p) { if (!p) return; scrollTo(p.x, p.y); el('scroll').scrollTop = p.top; }
function backTo() {
  if (!refocus) return;
  const { key } = refocus;
  const b = [...document.querySelectorAll('[data-open-key]')].find(n => n.dataset.openKey === key && n.offsetParent);
  goPlace(refocus.at);
  if (b) b.focus({ preventScroll: true });
}
async function frameRefusal(path) {
  try {
    const ctl = new AbortController();
    const r = await fetch(path, { credentials: 'same-origin', cache: 'no-store', signal: ctl.signal });
    const xfo = (r.headers.get('x-frame-options') || '').trim().toLowerCase();
    const csp = r.headers.get('content-security-policy') || '';
    ctl.abort();
    if (xfo === 'deny') return 'X-Frame-Options: DENY';
    if (xfo && xfo !== 'sameorigin') return 'X-Frame-Options: ' + xfo;
    const fa = (csp.match(/frame-ancestors([^;]*)/i) || [])[1];
    if (fa != null) {
      const src = fa.trim().split(/\s+/).filter(Boolean);
      const ok = src.some(x => x === "'self'" || x === '*' || x.replace(/\/$/, '') === location.origin);
      if (!ok) return 'CSP frame-ancestors ' + (fa.trim() || "'none'");
    }
  } catch (_) {}
  return '';
}
function newTab(path, name, btn, why) {
  window.open(path, '_blank', 'noopener');
  if (btn) pop(btn, '', `${name} doesn’t open inside the Tracker${why ? ' (' + why + ')' : ''}, so it opened in a new tab.`);
}
async function openApp(id, name, btn, item) {
  name = name || id;
  const path = '/' + encodeURIComponent(id) + '/';
  const why = await frameRefusal(path);
  if (why) return newTab(path, name, btn, why);
  unpop();
  appBack = { focus: btn || document.activeElement, at: place(), id, key: btn && btn.dataset.openKey, item: item || null, name };
  const d = el('appmodal'), f = el('appmodal-f');
  el('appmodal-tab').href = path; f.title = name;
  modalBar();
  f.onload = () => {
    let ok = false;
    try { const doc = f.contentDocument; ok = !!(doc && doc.location.href !== 'about:blank'); } catch (_) {}
    if (!ok && d.open && f.getAttribute('src') !== 'about:blank') { d.close(); newTab(path, name, appBack && appBack.focus, 'it refused to be framed'); }
  };
  f.src = path;
  if (typeof d.showModal === 'function') d.showModal(); else d.setAttribute('open', '');   // older phone webviews
  document.documentElement.classList.add('bd-modal-on');   // the list underneath stays put (no scroll-through)
  // 0.22: the phone's Back closes it, like the sheets (WizardApp.back; the shell asks the app first)
  const B = window.WizardApp && window.WizardApp.back;
  if (!d.__back && B && typeof B.push === 'function') { try { d.__back = B.push(() => { closeApp(); return true; }); } catch (_) {} }
  el('appmodal-x').focus({ preventScroll: true });
}
function closeApp() { const d = el('appmodal'); if (typeof d.close === 'function' && d.open) d.close(); else if (d.hasAttribute('open')) { d.removeAttribute('open'); d.dispatchEvent(new Event('close')); } }
el('appmodal-x').onclick = closeApp;
// 0.23.1: the pop-up's slim bar: the item's title, the same Try it toggle as its card (one state, rebuilt from it on
// every flip), Works / Doesn't work with the card's confirm and required note, and Close. Without an item: the app's name.
function modalBar() {
  const it = appBack && appBack.item, d = el('appmodal');
  el('appmodal-h').textContent = it ? it.title : (appBack ? appBack.name : '');
  el('appmodal-h').title = it ? `${it.title} · ${appBack.name}` : '';
  const tw = el('appmodal-try'), acts = el('appmodal-acts');
  tw.replaceChildren(); acts.replaceChildren();
  d.classList.toggle('bd-has-item', !!it);
  if (!it) return;
  const tg = tryToggle(it);
  if (tg) { tw.append(tg); const ts = tryState(it); if (ts.why) { const bits = ts.run ? [make('span', 'bd-why-s', ts.why)] : blockerBits(it, ts, ts.why); bits.forEach(x => (x.classList.contains('bd-why-s') ? x : x.querySelector('.bd-why-s') || x).classList.add('bd-try-why')); tw.append(...bits); } }
  if (it.group === 'test') acts.append(verdictBtns(it, el('appmodal-bar'), tryState(it).wait));
}
// The live item behind the pop-up (a refresh may have replaced the object the button carried)
function liveItem(it) {
  for (const v of Object.keys(cache)) for (const g of Object.values((cache[v] || {}).groups || {})) for (const x of g || []) if (x.id === it.id) return x;
  return it;
}
// After any flip: the card and the pop-up show the new state, and the framed app reloads so the change shows now
function flipped() {
  const d = el('appmodal');
  if (!d.open || !appBack) return;
  if (appBack.item) { appBack.item = liveItem(appBack.item); adoptSwitch(appBack.item); }
  modalBar();
  reloadFrame();
}
function reloadFrame() {
  const f = el('appmodal-f');
  try { f.contentWindow.location.reload(); } catch (_) { const s = f.getAttribute('src'); f.setAttribute('src', 'about:blank'); f.setAttribute('src', s); }
}
el('appmodal').addEventListener('close', () => {
  const d = el('appmodal'), f = el('appmodal-f'); f.onload = null; f.setAttribute('src', 'about:blank');
  document.documentElement.classList.remove('bd-modal-on');
  if (d.__back) { try { d.__back.release(); } catch (_) {} d.__back = null; }
  const back = appBack; appBack = null;
  if (!back) return;
  goPlace(back.at);
  if (back.focus && back.focus.isConnected) back.focus.focus({ preventScroll: true });
  refocus = back.key ? { key: back.key, at: back.at } : null;
  setTimeout(() => { refocus = null; }, 8000);
  loadAppSwitches(back.id, true);   // the owner may have flipped it inside the app (backTo() keeps the place after the repaint)
});
// 0.15: bug fixes ship live, not behind a switch; a Switch line that isn't a shell tweak (a device setting, an env knob)
// can't be flipped from here, so both get a plain line saying how to try it instead of a dead switch.
const LIVE_NOTE = 'Live once your Wizard has the update';
// 0.22: every Try toggle says what it is and where it stands: 'Try it' and On or Off, next to its switch
function tryFace(b, on) {
  b.classList.add('bd-try-pill');
  if (!b.querySelector('.bd-try-l')) b.append(make('span', 'bd-try-l', 'Try it'), make('span', 'bd-try-s'));
  b.querySelector('.bd-try-s').textContent = on ? 'On' : 'Off';
  b.setAttribute('aria-checked', String(!!on));
}
function trySwitch(i) {
  const live = i.group === 'test' || i.group === 'show' || (i.group == null && (i.labels || []).some(l => String(l).toLowerCase() === 'ready-to-test'));  // Human review only
  const sw = live && box && box.ok && i.switch ? box.switches[i.switch] : null;
  const on = !!(sw && sw.on && !swLocked(sw));
  const b = make('button', 'bd-try'); b.type = 'button'; b.setAttribute('role', 'switch');
  b.setAttribute('aria-label', 'Try it: ' + ((sw && sw.name) || i.switch || '') + (live && tryWhy(i) ? ' (' + tryWhy(i) + ')' : ''));
  if (i.switch) { b.dataset.switch = i.switch; b.title = (sw && sw.name) || i.switch; }
  if (!live || tryWhy(i)) b.setAttribute('aria-disabled', 'true');
  b.append(make('i')); tryFace(b, on);
  const stop = e => e.stopPropagation();
  b.addEventListener('keydown', stop); b.addEventListener('pointerdown', stop);
  b.onclick = async e => {
    e.preventDefault(); e.stopPropagation();
    if (!live) return pop(b, '', 'Can be switched on once it’s in Human review.');
    const why = tryWhy(i);
    if (why) return pop(b, '', why);
    const next = b.getAttribute('aria-checked') !== 'true';
    tryFace(b, next); b.disabled = true;
    try {
      takeSwitches(await switchApi({ id: i.switch, on: next }));
      if (b.closest('#appmodal')) unpop();   // 0.23.1: in the pop-up the app reloads with it instead
      else if (next) pop(b, '', 'On in this Wizard. It shows within a few seconds; switch it off here or in Settings.'); else unpop();
      flipped();
      if (cache[view] && !typing()) render(cache[view]);
      if (el('settings').open) tryList();
      if (openId === i.id) detailSwitch(i);
    } catch (err) {
      tryFace(b, !next);
      if (err.status === 409) { box.locked = true; return pop(b, '', 'Switch to For testers in Settings to try this'); }
      if (err.status === 404 && err.json) return pop(b, '', UPDATE_NOTE);
      pop(b, '', err.message || 'Couldn’t reach this Wizard. Try again.');
    } finally { b.disabled = false; }
  };
  return b;
}

// 0.18 shared bits: a greyed button that says why on tap, with the reason in place next to it
function greyBtn(text, why, cls = 'bd-mini') {
  const b = make('button', cls, text); b.type = 'button'; b.setAttribute('aria-disabled', 'true'); b.title = why;
  b.addEventListener('pointerdown', e => e.stopPropagation());
  b.onclick = e => { e.preventDefault(); e.stopPropagation(); pop(b, '', why); };
  return b;
}
const ago = iso => {
  const t = ts(iso); if (!t) return '';
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 90) return 'just now';
  if (s < 3600) return Math.round(s / 60) + ' minutes ago';
  if (s < 86400) { const h = Math.round(s / 3600); return h === 1 ? 'an hour ago' : h + ' hours ago'; }
  const d = Math.floor(s / 86400); return d === 1 ? 'yesterday' : d + ' days ago';
};
const firstName = x => String(x || '').split(' ')[0];

// ---------- Builder switch (0.13.8): real. The builder checks it before every run; pausing asks first ----------
let builderOn = false;
function showBuilder(b) {
  builderOn = !!b.running;
  const t = el('builder');
  t.setAttribute('aria-checked', String(builderOn));
  el('builder-state').textContent = builderOn ? 'Running' : 'Paused';
  t.title = b.updated_by ? `Set by ${b.updated_by} ${when(new Date(b.updated_at * 1000).toISOString())}` : '';
}
async function setBuilder(on) {
  const t = el('builder'); unpop(); t.disabled = true;
  try { showBuilder(await api('api/builder', { running: on })); }
  catch (err) { pop(t, '', err.status === 403 ? (err.message || 'Only team members can start or pause the builder.') : err.message); }
  finally { t.disabled = false; }
}
el('builder').onclick = () => {
  const t = el('builder');
  if (!builderOn) return setBuilder(true);
  const yes = make('button', 'bd-btn bd-danger', 'Pause builder'), no = make('button', 'bd-btn', 'Keep running');
  yes.type = no.type = 'button';
  yes.onclick = () => setBuilder(false); no.onclick = unpop;
  const row = make('div', 'bd-pop-actions'); row.append(no, yes);
  pop(t, 'Pause the WizardOS Builder?', ['It finishes what it is doing now, then picks up nothing new until someone turns it back on.', row]);
  no.focus();
};
function loadSide() {
  api('api/builder').then(showBuilder).catch(() => {});
  loadSwitches();
}

// ---------- 0.16 Is it on my Wizard? The page reads what this box runs (WizardOS release + channel from the shell's
// owner-only _updates route, each app's version from its own /<id>/healthz); the server maps that to commits and asks
// GitHub whether the build contains the merged PR(s). Painted from a local cache first, checked in the background. ----
const UPDATES_API = '/wizard-os-home/store-install/_updates';
const ONBOX_SECONDS = 300;
const facts = { release: null, channel: null, apps: {}, mac: null };
const appsTried = new Set();
let factsReady = null;
const onbox = new Map(Object.entries(store.get('board.onbox') || {}));   // id -> { at, key, v }
const factsKey = () => JSON.stringify([facts.release, facts.channel, facts.apps, facts.mac]);
// 0.17: inside the Mac app, its version (the shell's native bridge app.info), so a Mac change is only 'On your Wizard'
// when this Mac app contains it. Anywhere else facts.mac stays null: a Mac change then needs the Mac app update.
function macVersion() {
  try {
    const top = parent !== window ? parent : window;
    if (top.document.documentElement.dataset.nativeChrome !== 'mac') return Promise.resolve(null);
    const call = top.WizCore && top.WizCore.bridge && top.WizCore.bridge.call;
    if (typeof call !== 'function') return Promise.resolve(null);
    return Promise.race([call('app.info', {}), new Promise(r => setTimeout(() => r(null), 3000))])
      .then(x => x && typeof x.version === 'string' && /^[0-9][0-9A-Za-z.+_-]{0,40}$/.test(x.version) ? x.version : null).catch(() => null);
  } catch (_) { return Promise.resolve(null); }
}
function loadFacts() {
  if (!factsReady) factsReady = Promise.all([
    fetch(UPDATES_API, { credentials: 'same-origin', cache: 'no-store' })
      .then(r => r.ok ? r.json() : null).then(b => { if (b && b.installed) { facts.release = String(b.installed); facts.channel = b.channel || null; } updates = b || updates; })
      .catch(() => {}),
    macVersion().then(v => { facts.mac = v; })]);
  return factsReady;
}
async function appVersion(id) {
  appsTried.add(id);
  try {
    const r = await fetch('/' + encodeURIComponent(id) + '/healthz', { credentials: 'same-origin', cache: 'no-store' });
    const b = r.ok ? await r.json() : null;
    if (b && typeof b.version === 'string') facts.apps[id] = b.version;
  } catch (_) {}
}
const deliversOf = t => ({ id: t.id, delivers: t.delivers || [], open_prs: t.open_prs || 0 });
const onboxOf = t => {
  if (!(t.delivers || []).length && !t.open_prs) return { state: 'unknown' };
  const hit = onbox.get(t.id);
  return hit ? hit.v : null;
};
let onboxBusy = false;
async function checkOnBox(items) {
  if (onboxBusy) return;
  const want = items.filter(t => (t.delivers || []).length || t.open_prs);
  if (!want.length) return;
  onboxBusy = true;
  let changed = false;
  try {
    await loadFacts();
    for (let round = 0; round < 2; round++) {
      const key = factsKey();
      const ask = want.filter(t => { const h = onbox.get(t.id); return !h || h.key !== key || Date.now() - h.at > ONBOX_SECONDS * 1000; });
      if (!ask.length) break;
      const r = await api('api/onbox', { box: facts, items: ask.map(deliversOf) });
      const need = new Set();
      for (const [id, v] of Object.entries(r.items || {})) {
        const was = onbox.get(id);
        if (!was || JSON.stringify(was.v) !== JSON.stringify(v)) changed = true;
        onbox.set(id, { at: Date.now(), key, v });
        for (const a of v.apps || []) if (!(a in facts.apps) && !appsTried.has(a)) need.add(a);
      }
      if (!need.size) break;
      await Promise.all([...need].map(appVersion));     // then ask again with those versions
    }
    store.set('board.onbox', Object.fromEntries([...onbox.entries()].filter(([, h]) => Date.now() - h.at < 864e5).slice(-80)));
    if (!changed) return;   // nothing new: no repaint (a repaint would ask again)
    if (cache[view] && !typing() && !document.querySelector('.bd-confirm')) render(cache[view]);
    if (openId) { const d = (cache[view] && cache[view].groups.test || []).find(x => x.id === openId); if (d) onboxLine(el('d-onbox'), d); }
  } catch (_) {
  } finally { onboxBusy = false; }
}
const ONBOX_TEXT = { yes: 'On your Wizard ✓', no: 'Not on your Wizard yet', unknown: 'Can’t tell if this is on your Wizard' };
const cap = x => x ? x[0].toUpperCase() + x.slice(1) : x;

// 0.19.1 (wizardos-tracker#7): which release has it, from the same release lookup as Shipping. Human review: from
// api/onbox (`release`); Shipping and Done: from api/done (`ship`, when it names a version).
function releaseOf(i) {
  if (i.group === 'test') { const v = onboxOf(i); return v && v.release && v.release.text || ''; }
  if (i.group === 'shipping' || i.group === 'done') return i.ship && i.ship.version ? i.ship.text : '';
  return '';
}
// ---------- 0.18 cards: title; one plain line 'where it is and what's next'; ONE action area; small meta ----------
// 0.20 (Miguel): a bug's two facts, side by side and independent: where it shipped, and its Human check.
// 'Shipped in For testers 0.3.150 · Human check pending', later 'Shipped in For everyone 0.3.152 · Checked by Miguel'.
function shippedText(t) {
  if (!t) return 'Shipped';
  if (/^In /.test(t)) return 'Shipped in ' + t.slice(3);
  if (/^Waiting\b/.test(t)) return 'Merged · ' + t.charAt(0).toLowerCase() + t.slice(1);   // not in any release yet
  return /^Shipped\b/.test(t) ? t : 'Shipped · ' + t.charAt(0).toLowerCase() + t.slice(1);
}
function bugLine(i) {
  const g = i.group;
  const rel = g === 'shipping' || g === 'done' ? (i.ship ? i.ship.text : '') : ((onboxOf(i) || {}).release || {}).text;
  const ship = shippedText(rel);
  const by = ((i.waiting_on || {}).who || []).join(' or ');
  if (g === 'test') return i.can_review ? [ship + ' · Your turn: check it', 'turn'] : [ship + ' · Waiting for ' + (by || i.opener || 'the filer') + ' to check it', ''];
  if (g === 'airev') return [ship + ' · ' + (by && by !== 'Any team agent' ? by + '’s AI check' : 'AI check') + ', then ' + (i.opener || 'the filer') + ' checks it', ''];
  const ck = i.checked ? i.checked.text : 'Checked';
  return [ship + ' · ' + ck, g === 'done' ? 'done' : ''];
}
function whereLine(i) {
  const g = i.group;
  if (i.kind === 'bug' && (i.shipped || ((g === 'shipping' || g === 'done') && i.state_reason !== 'not_planned'))) return bugLine(i);
  if (g === 'test') {
    if (!i.can_review) return [i.review_rule || `${i.opener || 'the filer'} checks this one`, ''];
    const ob = onboxOf(i);
    if (ob && ob.state === 'no') return ['Your turn: update, then check it', 'turn'];
    return ['Your turn: check it', 'turn'];
  }
  if (g === 'show') return i.can_james ? ['Your turn: show-and-tell', 'turn'] : ['Waiting for James’ show-and-tell', ''];
  if (g === 'james') return i.can_james ? ['Your turn: approve or decline', 'turn'] : ['Waiting for James or Miguel to approve', ''];
  if (g === 'airev') return [i.ai_reviewer && i.ai_reviewer !== 'any team agent' ? `Waiting for ${i.ai_reviewer}’s AI check` : 'Waiting for an AI check', ''];
  if (i.blocked && (g === 'building' || g === 'queued')) return ['Stuck: the builder gave up · waiting for Oscar', 'warn'];
  if (g === 'building') return ['The builder is on it', ''];
  if (g === 'queued') return [(i.category === 'core' ? 'Approved · ' : 'Queued · ') + (i.wait_reason || 'Next for the builder'), i.wait_reason === 'Oscar builds this one' ? 'oscar' : ''];
  if (g === 'sorting') return ['Sorting… the builder files it in the right place in a minute or two', ''];
  if (g === 'shipping') return [(i.kind === 'bug' && i.closed_at ? 'Fixed · ' : '') + (i.ship ? i.ship.text : 'Approved · checking releases…'), ''];
  if (g === 'done') return [i.ship ? i.ship.text : 'Done', 'done'];
  return ['', ''];
}
function itemCard(i) {
  const c = make('article', 'bd-card bd-card-calm bd-icard');
  const top = make('div', 'bd-card-top');
  const h = tapTarget('bd-title', () => openDetail(i)); h.textContent = i.title;
  top.append(h); c.append(top);
  const [text, cls] = whereLine(i);
  if (text) c.append(make('p', 'bd-where' + (cls ? ' ' + cls : ''), text));
  const rel = i.kind === 'bug' && /^Shipped/.test(text) ? '' : releaseOf(i);   // 0.20: a bug's line already names it
  if (rel && rel !== (i.ship && i.ship.text)) c.append(make('p', 'bd-hint bd-rel', rel));   // Shipping/Done say it above
  const act = actionArea(i);
  if (act) c.append(act);
  const when_ = i.group === 'done' || i.group === 'shipping' && i.closed_at ? (i.closed_at ? 'closed ' + when(i.closed_at) : '') : age(i.created_at);
  c.append(make('p', 'bd-hint', [`${repoName(i.repo)} #${i.number}`, nameOf(i.author) || i.opener || '', when_].filter(Boolean).join(' · ')));
  return c;
}
// 0.23.1: what a Human review item needs before it can be tried: shared by the card, the detail and the app pop-up's bar
function tryState(i) {
  const ob = onboxOf(i);
  // 0.21.3: an app that already serves this item's switch has the change, whatever the release records say
  const pl = i.switch_place || null;
  let swApp = pl && pl.kind === 'app' ? appForRepo(pl.repo) : null;
  let hit = (i.switch_adopted && box && box.ok && box.switches[i.switch]) || (swApp ? appSwitchFor(i, swApp) : null);
  // 0.24.2: no Switch line, but the item's own app serves a switch naming its issue: that is its switch
  if (!hit && !i.switch && !swApp && i.group === 'test') { const a = appForRepo(i.repo); const h = a && appSwitchFor(i, a, true); if (h) { hit = h; swApp = a; } }
  // 0.24.2: 'Switch: <app>:<id>' (not in the box catalog): that app's own switch
  const named = !i.switch ? appSwitchId(i) : null;
  if (named && !hit) {
    swApp = ((catalog && catalog.apps) || []).find(a => a.id === named.app) || appForRepo(i.repo);
    const st = swApp && (appSw[swApp.id] || (loadAppSwitches(swApp.id), null));
    hit = (st && st.ok && st.switches.find(x => String(x.id).toLowerCase() === named.sw)) || null;
  }
  const run = updRunFor(i, ob);
  let wait = '';
  if (run) { if (run.state !== 'done') wait = run.state === 'failed' ? 'Update first: this change isn’t on your Wizard yet.' : 'Updating your Wizard…'; }
  else if (ob && ob.state === 'no' && !hit) wait = 'Update first: this change isn’t on your Wizard yet.';
  // 0.24.2 (Miguel): an item with a switch, core or app, ALWAYS shows Try it; when it can't be flipped now, `why` says
  // why next to the greyed toggle ('Update Calendar first'), on the card and in the pop-up bar.
  const has = !!(i.switch || hit || named || (pl && pl.kind === 'app'));
  let why = '';
  if (has) {
    if (wait) {
      const fix = (ob && ob.fix) || '';
      why = run && run.state !== 'failed' ? `Updating ${run.name || 'your Wizard'}…`
        : run ? `Update ${run.name || 'your Wizard'} first` : /^Update /.test(fix) ? fix + ' first' : fix || 'Update first';
    } else if (i.switch) why = tryWhy(i);
    else if (!hit) why = appWhy(i, swApp, pl);
  }
  return { ob, pl, swApp, hit, run, wait, has, why, app: swApp || appForRepo(i.repo) };
}
// 0.24.5 (Miguel): whenever an update is what blocks an item, the Update button sits right next to that blocker text on
// EVERY card (reviewer or not, card, detail, the app pop-up's bar and Settings), and becomes the in-place progress panel
// once it runs. Which update: the item's own 'Update X' (onbox fix), 'Update <app> first' (the app's switch is newer in
// the Store) or a core switch this WizardOS doesn't have yet.
const reEsc = x => String(x).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
function blockUpd(i, t) {
  const why = (t && t.why) || '', ob = t && t.ob;
  if (ob && ob.state === 'no' && /^Update /.test(ob.fix || '') && (!t.hit || /^Updat/.test(why))) {
    const k = runKeyOf(ob);
    if (k) return { key: k, go: b => k === 'os' ? updateWizardOS(b, i) : updateApp(k, b, i) };
  }
  if (/update WizardOS|^Update WizardOS|^Update to try this$/i.test(why)) return { key: 'os', go: b => updateWizardOS(b, i) };
  const app = t && (t.swApp || t.app);
  if (app && app.update && new RegExp('^Updat(e|ing) ' + reEsc(app.name) + '\\b').test(why)) return { key: app.id, go: b => updateApp(app.id, b, i) };
  return null;
}
// The blocker line: its words, then the Update button beside them, or the running update's progress instead.
function blockerBits(i, t, text) {
  if (!text) return [];
  const u = blockUpd(i, t);
  if (!u) return [make('span', 'bd-why-s', text)];
  const r = runs.get(u.key);
  if (r) return [updPanel(r, i)];
  const line = make('span', 'bd-blocker');
  line.dataset.blocker = u.key;
  line.append(make('span', 'bd-why-s', text), smallBtn('Update', b => u.go(b)));
  return [line];
}
// 0.23.1: the item's Try it toggle on its own (the same state as the card's). 0.24.2: never null for an item with a
// switch: greyed (with tryState().why) when it can't be flipped right now. Null only when there is no switch at all.
function tryToggle(i) {
  const t = tryState(i);
  if (!t.has) return null;
  const name = (t.hit && (t.hit.name || t.hit.id)) || (box && box.ok && i.switch && box.switches[i.switch] && box.switches[i.switch].name) || i.switch || i.switch_how || '';
  if (t.wait) return greyTry(name, t.why, t.hit && t.hit.on);
  if (i.switch) return trySwitch(i);   // greys itself (tryWhy) when the box can't flip it
  if (t.hit && t.swApp) return appToggle(i, t.swApp, t.hit);
  return greyTry(name, t.why || 'Not ready to try yet', false);
}
// Doesn't work always asks what's wrong (Miguel, 0.23.1): the note is required and goes into the issue comment
const WRONG = { label: 'What’s wrong?', placeholder: 'e.g. Swiping feels choppy, it should glide one day at a time', send: 'Send' };
// 0.24.2: Doesn't work takes screenshots too (pick or paste, several, thumbnails); a failed send keeps the note open
function doesntWork(area, i, b) { noteAsk(area, WRONG.placeholder, WRONG.send, (note, shots) => tested(i, false, note, b, shots), { required: true, label: WRONG.label, shots: true }); }
// Works (one tap, then the existing confirm) and Doesn't work: on the card, in the detail and in the app pop-up's bar
function verdictBtns(i, area, wait) {
  const btns = make('span', 'bd-act-btns');
  if (!i.can_review) { btns.append(greyBtn('Works', i.review_rule), greyBtn('Doesn’t work', i.review_rule)); return btns; }
  const yes = wait ? greyBtn('Works', wait, 'bd-mini bd-mini-go') : smallBtn('Works', b => askPop(b, i.category === 'core' ? 'Mark as works? It goes to James’ show-and-tell.' : i.shipped ? 'Mark as works? It closes as fixed.' : 'Mark as works? It ships with the next release.', 'Works', () => tested(i, true, '', b)));
  if (!wait) yes.classList.add('bd-mini-go');
  const no = wait ? greyBtn('Doesn’t work', wait) : smallBtn('Doesn’t work', b => doesntWork(area, i, b));
  btns.append(yes, no);
  return btns;
}
// The one action area: exactly what is needed now, greyed with the reason for anyone else.
function actionArea(i, inDetail) {
  const g = i.group, row = make('div', 'bd-act');
  // 0.19: a shipped bug (AI check running, or closed and on its way to everyone): the filer can still say Doesn't work
  if (i.kind === 'bug' && i.can_fail && (g === 'airev' || (g === 'shipping' && i.closed_at))) {
    const no = smallBtn('Doesn’t work', b => doesntWork(row, i, b));
    row.append(make('span', 'bd-act-l', 'Still broken?'), no);
    return row;
  }
  if (g === 'test') {
    if (!i.can_review) {
      // 0.24.5: someone else gives the verdict, but anyone may try it on their own Wizard: Try it and the update
      // blocker (with its Update button) show here too
      const t0 = tryState(i), tg0 = tryToggle(i), r0 = t0.run;
      if (r0) row.append(updPanel(r0, i));
      if (tg0) { const grp = make('div', 'bd-trygrp'); grp.append(tg0); row.append(grp); }
      if (!r0) row.append(...blockerBits(i, t0, t0.why || (t0.ob && t0.ob.state === 'no' && !t0.hit ? t0.ob.fix || ONBOX_TEXT.no : '')));
      row.append(greyBtn('Works', i.review_rule), greyBtn('Doesn’t work', i.review_rule));
      row.append(make('span', 'bd-why-s', i.review_rule));   // 0.20: 'James checks this one (he filed it)'
      return row;
    }
    const t = tryState(i);
    const { ob, pl, swApp, hit, run } = t;
    let wait = t.wait;
    if (run) {
      row.append(updPanel(run, i));   // 0.22: Update shows its progress in place, then 'On your Wizard ✓'
    } else if (ob && ob.state === 'no' && !hit && !(t.has && blockUpd(i, t))) {
      const u = updateFor(ob, i);
      const need = make('div', 'bd-need');
      need.append(make('span', 'bd-act-l', ob.fix || 'Not on your Wizard yet'));
      if (u) need.append(u);
      row.append(need);
    }
    // 0.22: the try flow, in order: Try it (switch it on) -> Open <app> -> Works / Doesn't work
    // 0.24.2: Try it is always there when the item has a switch (greyed with the reason when it can't flip now)
    const grp = make('div', 'bd-trygrp');
    let why = '';
    const tg = tryToggle(i);
    if (tg) { grp.append(tg); why = t.why; }
    else if (!wait && pl && pl.kind !== 'app') grp.append(...placeBits(i));
    const app = t.app;
    if (app && app.id !== 'wizardos-tracker') grp.append(openKey(smallBtn(`Open ${app.name}`, b => openApp(app.id, app.name, b, i)), i));
    else if (pl && pl.kind === 'app' && !swApp) grp.append(openKey(smallBtn('Open', b => pop(b, '', `Open ${repoName(pl.repo)} on your Wizard, then ${pl.text}.`)), i));
    if (grp.childNodes.length) row.append(grp);
    if (why && !run) row.append(...blockerBits(i, t, why));
    row.append(verdictBtns(i, row, wait));
    if (wait && inDetail) row.append(make('span', 'bd-why-s', wait));
    return row;
  }
  if (g === 'james') {
    if (!i.can_james) { row.append(greyBtn('Approve', i.james_rule), greyBtn('Decline', i.james_rule), make('span', 'bd-why-s', i.james_rule)); return row; }
    const yes = smallBtn('Approve', b => askPop(b, 'Approve this core feature? The builder may start on it.', 'Approve', () => james(i, 'approve', '', b)));
    yes.classList.add('bd-mini-go');
    const no = smallBtn('Decline', b => noteAsk(row, 'Why not? (optional)', 'Decline', note => james(i, 'decline', note, b)));
    row.append(yes, no); return row;
  }
  if (g === 'show') {
    if (!i.can_james) { row.append(greyBtn('Approve', i.james_rule), make('span', 'bd-why-s', i.james_rule)); return row; }
    if (i.switch) { const grp = make('div', 'bd-trygrp'); grp.append(trySwitch(i)); row.append(grp); }
    const yes = smallBtn('Approve', b => askPop(b, 'Approve after the show-and-tell? The switch goes away (on for everyone) and it ships.', 'Approve', () => showOk(i, b)));
    yes.classList.add('bd-mini-go');
    row.append(yes); return row;
  }
  return null;
}
// An inline 'why' note under the action area (Doesn't work, Decline), Cancel focused first
function noteAsk(area, placeholder, yesText, fn, opt = {}) {
  if (area.nextSibling && area.nextSibling.classList && area.nextSibling.classList.contains('bd-fail')) return area.nextSibling.querySelector('textarea').focus();
  const f = make('form', 'bd-fail bd-confirm'); f.autocomplete = 'off';
  const ta = make('textarea', 'wz-input bd-area'); ta.rows = 2; ta.maxLength = 4000; ta.placeholder = placeholder; ta.setAttribute('aria-label', opt.label || placeholder);
  if (opt.label) { const id = 'bd-note-' + Math.random().toString(36).slice(2, 8); ta.id = id; const l = make('label', 'bd-fail-l', opt.label); l.htmlFor = id; f.append(l); }
  if (opt.required) ta.required = true;
  const r = make('div', 'bd-btns');
  const cancel = make('button', 'wz-button secondary', 'Cancel'); cancel.type = 'button';
  const go = make('button', 'wz-button', yesText); go.type = 'submit';
  // 0.23.1: a required note (Doesn't work): Send stays off until there is text
  const gate = () => { if (opt.required) go.disabled = !ta.value.trim(); };
  ta.oninput = () => { hold(!!ta.value.trim()); gate(); };
  gate();
  r.append(cancel, go); f.append(ta);
  let shots = null;
  const say = make('p', 'wz-status'); say.setAttribute('role', 'status');
  if (opt.shots && window.WizardReporter && WizardReporter.attacher) {
    const row = make('div', 'rr-shot'); f.append(row);
    shots = WizardReporter.attacher(row, t => { say.textContent = t; });
    if (!WizardReporter.options()) WizardReporter.load().catch(() => {});
    for (const ev of ['paste', 'drop']) ta.addEventListener(ev, e => {
      const fs = shots.imagesOf(e.clipboardData || e.dataTransfer);
      if (fs.length) { e.preventDefault(); shots.add(fs); }
    });
  }
  f.append(say, r);
  area.after(f); ta.focus();
  const close = () => { f.remove(); hold(false); };
  cancel.onclick = close;
  f.onkeydown = e => { if (e.key === 'Escape') { e.stopPropagation(); e.preventDefault(); close(); } };
  f.onsubmit = async e => {
    e.preventDefault();
    const note = ta.value.trim();
    if (opt.required && !note) { gate(); return ta.focus(); }
    go.disabled = cancel.disabled = true;
    const ok = await fn(note, shots && shots.list().length ? shots.payload() : undefined);
    if (ok === false) { go.disabled = cancel.disabled = false; gate(); return; }   // keep the words (and screenshots)
    close();
  };
}
function afterAct(i, msg) {
  hold(false);
  for (const v of Object.keys(cache)) { const d = cache[v]; if (d && d.groups) for (const g of Object.keys(d.groups)) d.groups[g] = d.groups[g].filter(x => x.id !== i.id); }
  details.delete(i.id); onbox.delete(i.id); delete doneCache[view];
  if (el('detail').open) WzSheet.close(el('detail'));
  if (el('appmodal').open) closeApp();   // 0.23.1: the check was made from the pop-up's bar
  if (cache[view]) render(cache[view]);
  toast(msg); setTimeout(() => load(view, true), 1500);
}
async function tested(i, works, note, b, screenshots) {
  try {
    const r = await api(works ? 'api/test/works' : 'api/test/fails', { repo: i.repo, number: i.number, note, screenshots });
    afterAct(i, (works ? (r.stage === 'show' ? 'Thanks — on to James’ show-and-tell.' : 'Thanks — it’s shipping.') : r.reopened ? 'Reopened: back to the builder.' : 'Sent back to the builder.') + (r.warning ? ' ' + r.warning : ''));
    return true;
  } catch (err) { pop(b, '', err.message); return false; }
}
async function james(i, decision, note, b) {
  try { await api('api/james', { repo: i.repo, number: i.number, decision, note }); afterAct(i, decision === 'approve' ? 'Approved: the builder may start.' : 'Declined.'); }
  catch (err) { pop(b, '', err.message); }
}
async function showOk(i, b) {
  try { const r = await api('api/show', { repo: i.repo, number: i.number }); afterAct(i, r.switch_default ? 'Approved: the builder turns it on for everyone.' : 'Approved: it’s shipping.'); }
  catch (err) { pop(b, '', err.message); }
}
// Kept for scripts that call it: the status line in the detail ('On your Wizard ✓' or what to update, and the switch)
function statusLine(p, t) {
  const v = onboxOf(t);
  p.className = (p.id ? 'bd-d-onbox ' : 'bd-onbox ') + (v ? v.state : 'wait');
  p.replaceChildren(document.createTextNode(v ? ONBOX_TEXT[v.state] || ONBOX_TEXT.unknown : 'Checking your Wizard…'));
  if (v && v.state === 'no' && v.fix) p.append(document.createTextNode(' · '), make('b', '', v.fix));
  p.hidden = false;
  return p;
}
function onboxLine(p, t) { const r = statusLine(p, t); if (p.id === 'd-onbox') releaseLine(t); return r; }
function releaseLine(i) {
  const p = el('d-release'), t = ['test', 'shipping', 'done'].includes(i.group) ? releaseOf(i) : '';
  p.hidden = !t; p.textContent = t ? 'Release: ' + t : '';
}
// 0.18: Update performs the update in place (the box's own App Manager routes), no separate panel.
function updateFor(v, i) {
  const fix = v.fix || '';
  if (/^Update WizardOS/.test(fix)) return smallBtn('Update', b => updateWizardOS(b, i));
  const m = /^Update (.+)$/.exec(fix);
  if (m) {
    const id = (v.apps || [])[0] || (appsByName().get(m[1].toLowerCase()) || {}).id;
    return smallBtn('Update', b => id ? updateApp(id, b, i) : pop(b, '', 'Update it in Settings › Updates.'));
  }
  if (fix === 'Needs the Mac app update') return smallBtn('How', b => pop(b, '', 'In the Mac app: Wizard menu › Check for Updates…'));
  if (/For testers/.test(fix)) return smallBtn('How', b => pop(b, '', 'Settings › Updates › For testers.'));
  return null;
}

// ---------- 0.18 Goals: the home tab. One larger card per goal: status light, the latest human status, owners,
// linked bugs and features by stage, and Update status (the goal's owners or James; greyed for others) ----------
const LIGHT = { green: 'On track', yellow: 'At risk', red: 'Blocked' };
const STAGE_WORD = { sorting: 'sorting', test: 'human review', show: 'show-and-tell', james: 'waiting for approval', airev: 'AI review', building: 'building', queued: 'queued', shipping: 'shipping', done: 'done' };
function renderGoals(d, keep, order) {
  const list = (d.groups.goals || []).filter(keep);
  if (order) list.sort(order);
  el('strip').replaceChildren(); el('totals').textContent = '';
  const mine = sortBy[d.view] === 'turn' ? list.filter(myTurn) : [], rest = list.filter(g => !mine.includes(g));
  const block = (xs, cls) => { const l = make('div', 'bd-list bd-goals' + (cls ? ' ' + cls : '')); l.append(...xs.map(goalCard)); return l; };
  const out = [];
  if (mine.length) { const s = make('section', 'bd-sec bd-turn'); s.id = 'sec-turn'; s.append(turnDivider(mine.length), block(mine)); out.push(s); if (rest.length) out.push(make('hr', 'bd-turn-end')); }
  if (rest.length) out.push(block(rest));
  el('secs').replaceChildren(...out);
  el('empty').hidden = !!list.length;
  el('empty').textContent = EMPTY.goals;
}
function statusBits(s, big) {
  const p = make('div', 'bd-gstatus' + (big ? ' big' : ''));
  if (!s) { const h = make('p', 'bd-ghead'); h.append(make('span', 'bd-light none'), make('span', 'bd-gword none', 'No status yet')); p.append(h); return p; }
  const head = make('p', 'bd-ghead');
  head.append(make('span', 'bd-light ' + s.color), make('b', 'bd-gword', LIGHT[s.color] || s.word));
  p.append(head);
  if (s.text) p.append(make('p', 'bd-gtext', s.text));
  const by = make('p', 'bd-hint', `Updated ${ago(s.at)} by ${firstName(s.by_person || s.by_name || s.by)}`);
  p.append(by);
  if (s.stale) p.append(make('p', 'bd-hint bd-stale', 'Status is old'));
  return p;
}
function linkedLine(g) {
  const c = g.linked_counts || {}, keys = ['test', 'show', 'james', 'airev', 'building', 'queued', 'shipping', 'done'].filter(k => c[k]);
  if (!keys.length) return make('p', 'bd-hint', 'No linked bugs or features yet');
  return make('p', 'bd-glinked', `${(g.linked || []).length} linked: ` + keys.map(k => `${c[k]} ${STAGE_WORD[k]}`).join(' · '));
}
// 0.19: a minimal goal card: title, status light + one line, owner, done list, updated ago (the rest is in the detail)
function goalCard(g) {
  const c = make('article', 'bd-card bd-goal bd-goal-min');
  const top = make('div', 'bd-card-top');
  const h = tapTarget('bd-title', () => openDetail(g)); h.textContent = g.title;
  top.append(h, ownerChips(g));
  if ((g.assignees || []).length > 1) top.classList.add('multi');
  c.append(top);
  const s = g.status, line = make('p', 'bd-gline');
  line.append(make('span', 'bd-light ' + (s ? s.color : 'none')));
  const word = make('b', 'bd-gword' + (s ? '' : ' none'), s ? (LIGHT[s.color] || s.word) : 'No status yet');
  line.append(word);
  if (s && s.text) { const t = make('span', 'bd-gone', ' · ' + s.text.replace(/\s+/g, ' ')); t.title = s.text; line.append(t); }
  c.append(line);
  const p = g.progress || {};
  const meta = [p.total ? `Done list ${p.done}/${p.total}` : 'No done list', s ? `updated ${ago(s.at)}` : '', s && s.stale ? 'status is old' : ''].filter(Boolean);
  const m = make('p', 'bd-hint bd-gmeta', meta.join(' · '));
  if (p.total) m.title = 'Ticked items on the goal’s done list (its checkboxes)';
  c.append(m);
  if (g.turn && g.can_status) { const act = make('div', 'bd-act'); act.append(smallBtn('Update status', b => statusForm(g, act, b))); c.append(act); }
  return c;
}
// Pick a colour, write one or two sentences, confirm. Saved as a comment 'Status: <colour>' then the text.
function statusForm(g, area, btn) {
  if (area.nextSibling && area.nextSibling.classList && area.nextSibling.classList.contains('bd-fail')) return;
  const f = make('form', 'bd-fail bd-confirm bd-sform'); f.autocomplete = 'off';
  const pick = make('div', 'bd-lights'); pick.setAttribute('role', 'radiogroup'); pick.setAttribute('aria-label', 'Status');
  let color = (g.status && g.status.color) || 'green';
  const paint = () => pick.querySelectorAll('button').forEach(x => x.setAttribute('aria-checked', String(x.dataset.c === color)));
  for (const [k, w] of Object.entries(LIGHT)) {
    const b = make('button', 'bd-lightpick'); b.type = 'button'; b.dataset.c = k; b.setAttribute('role', 'radio');
    b.append(make('span', 'bd-light ' + k), document.createTextNode(w));
    b.onclick = () => { color = k; paint(); };
    pick.append(b);
  }
  paint();
  const ta = make('textarea', 'wz-input bd-area'); ta.rows = 2; ta.maxLength = 600; ta.required = true;
  ta.placeholder = 'One or two sentences: where it stands'; ta.setAttribute('aria-label', 'Status');
  ta.oninput = () => hold(!!ta.value.trim());
  const status = make('p', 'wz-status');
  const r = make('div', 'bd-btns');
  const cancel = make('button', 'wz-button secondary', 'Cancel'); cancel.type = 'button';
  const go = make('button', 'wz-button', 'Post status'); go.type = 'submit';
  r.append(cancel, go); f.append(pick, ta, status, r);
  area.after(f); ta.focus();
  const close = () => { f.remove(); hold(false); };
  cancel.onclick = close;
  f.onkeydown = e => { if (e.key === 'Escape') { e.stopPropagation(); close(); } };
  f.onsubmit = async e => {
    e.preventDefault();
    const text = ta.value.trim();
    if (text.length < 3) { status.textContent = 'Write a sentence or two.'; return; }
    go.disabled = cancel.disabled = true;
    try {
      const res = await api('api/goal/status', { repo: g.repo, number: g.number, color, text });
      g.status = { ...res.status, by_person: (cache.goals && cache.goals.me_person) || res.status.by_person };
      details.delete(g.id); close(); goalsBadge();
      toast('Status posted.');
      if (cache[view]) render(cache[view]);
      if (openId === g.id) openDetail(g);
    } catch (err) { go.disabled = cancel.disabled = false; status.textContent = err.message; }
  };
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

let openId = null, openItem = null;
function roles(i) {
  const r = el('d-roles'), who = i.opener || i.author;
  const goal = i.kind === 'goal' || i.category === 'goal' || view === 'goals';
  r.hidden = !who;
  if (!who) return;
  if (goal) { r.textContent = 'Human-led goal, never built by the builder · its owners or James post status · only James closes it'; return; }
  if (i.category === 'bug' || i.kind === 'bug') { r.textContent = `Reported by ${who} · merged and shipping as soon as it’s built · then an AI check by their agent and ${who}’s own check · Doesn’t work reopens it`; return; }
  r.textContent = `Filed by ${who} · AI review by their agent · ${who} tries it` + (i.category === 'core' ? ' · James or Miguel approves before building, James after a show-and-tell' : '') + ' · then Shipping until it’s in a release for everyone';
}
function openDetail(i, toAct) {
  const dlg = el('detail');
  openId = i.id; openItem = i;
  el('d-title').textContent = i.title;
  el('d-meta').textContent = [`${i.repo}#${i.number}`, i.author].filter(Boolean).join(' · ');
  el('d-gh').href = i.url;
  el('d-labels').textContent = '';
  roles(i);
  el('d-still').hidden = true;   // 0.18.2: set from the item's own flow (Doesn't work said more than once)
  const inReview = i.group === 'test';   // 0.16
  el('d-onbox').hidden = !inReview;
  if (inReview) onboxLine(el('d-onbox'), i);
  releaseLine(i);
  el('d-steps').hidden = !(inReview && (i.steps || i.check));
  if (inReview) el('d-steps').textContent = i.steps ? 'To test: ' + cap(i.steps) : i.check || '';
  detailSwitch(i);
  detailGoal(i, null);
  detailAct(i);
  el('d-body').replaceChildren(make('p', 'bd-empty', 'Loading…'));
  closeCtl(null);
  el('d-comments').replaceChildren(); el('d-comments-h').hidden = true;
  itemFlow(i);
  WzSheet.open(dlg);
  dlg.scrollTop = 0;
  if (toAct) setTimeout(() => { const a = el('d-act'); if (!a.hidden) { a.scrollIntoView({ block: 'center' }); const f = a.querySelector('button:not([aria-disabled="true"])'); if (f) f.focus(); } }, 60);
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
  if (d && d.state) b.textContent = d.state === 'closed' ? 'Reopen' : d.kind === 'goal' ? 'Close goal' : 'Mark done';
  // 0.17: everyone sees it; it is greyed out (with the reason on tap) for anyone who may not use it
  if (d) b.setAttribute('aria-disabled', String(!d.can_close));
  if (d) b.title = d.can_close ? '' : d.close_rule;
}
el('d-close').onclick = async () => {
  const d = detailNow, b = el('d-close');
  if (!d) return;
  const closing = d.state !== 'closed';
  if (!d.can_close) return pop(b, '', closing ? d.close_rule : d.close_rule.replace(' close', ' reopen').replace(' closes', ' reopens'));
  let anyway = false;
  if (closing && d.kind === 'goal' && !d.all_done && !b.dataset.anyway) {
    const left = (d.tasks || []).filter(t => !t.done).length;
    return askPop(b, (d.tasks || []).length ? `${left} done-list item${left === 1 ? '' : 's'} not ticked yet. Close the goal anyway?` : 'This goal has no done-list. Close it anyway?',
      'Close anyway', () => { b.dataset.anyway = '1'; b.click(); });
  }
  anyway = !!b.dataset.anyway; delete b.dataset.anyway;
  b.disabled = true;
  try {
    await api(closing ? 'api/issue/close' : 'api/issue/reopen', { repo: d.repo, number: d.number, ...(anyway ? { anyway: true } : {}) });
    details.delete(d.id); toast(closing ? 'Marked done.' : 'Reopened.');
    WzSheet.close ? WzSheet.close(el('detail')) : el('detail').close();
    setTimeout(() => load(view, true), 800);
  } catch (err) { pop(b, '', err.message); }
  finally { b.disabled = false; }
};
function fill(d) {
  closeCtl(d);
  if (d.kind === 'goal') detailGoal(openItem || d, d);
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
el('detail').addEventListener('close', () => { openId = null; openItem = null; unpop(); hold(false); });

// 0.17: the switch in the detail: a real toggle with its name and state, or the exact place to flip it.
function detailSwitch(i) {
  const box_ = el('d-switch');   // 0.18: the switch sits in the one action area (card and detail); this only explains it
  if (i.group !== 'test' || (!i.switch && !i.switch_place)) { box_.hidden = true; return box_.replaceChildren(); }
  box_.hidden = false;
  const txt = make('div', 'bd-d-swtxt');
  if (i.switch) {
    const sw = box && box.ok && box.switches[i.switch];
    txt.append(make('b', '', 'Switch: ' + ((sw && sw.name) || i.switch)), make('span', 'bd-meta', sw && sw.description ? sw.description : 'Feature switch ' + i.switch));
  } else {
    const pl = i.switch_place;
    txt.append(make('b', '', 'Switch: ' + i.switch_how), make('span', 'bd-meta', pl.kind === 'mac' ? 'A Mac app setting. Run this in Terminal, then quit and reopen Wizard.' : pl.kind === 'app' ? 'A setting inside the app: ' + pl.text : pl.kind === 'box' ? pl.text : 'Turn on: ' + pl.text));
    if (pl.cmd) txt.append(make('code', 'bd-cmd', pl.cmd));
  }
  box_.replaceChildren(txt);
}

// 0.18 goals: status history (newest first), done-list, owners, and linked bugs and features by stage.
function detailGoal(i, d) {
  const g = el('d-goal');
  const goal = i.kind === 'goal' || i.category === 'goal' || view === 'goals' || (d && d.kind === 'goal');
  if (!goal) { g.hidden = true; return g.replaceChildren(); }
  g.hidden = false;
  const out = [statusBits(i.status, true)];
  const act = make('div', 'bd-act');
  const can = d ? d.can_status : i.can_status, rule = (d && d.status_rule) || i.status_rule;
  act.append(can ? smallBtn('Update status', b => statusForm(i, act, b)) : greyBtn('Update status', rule));
  if (!can) act.append(make('span', 'bd-why-s', rule));
  out.push(act);
  const hist = d ? d.status_history || [] : null;
  out.push(make('h3', 'bd-sec-h bd-d-h', 'Status history'));
  if (!hist) out.push(make('p', 'bd-meta', 'Loading…'));
  else if (!hist.length) out.push(make('p', 'bd-meta', 'No status posted yet.'));
  else {
    const ol = make('ol', 'bd-timeline');
    for (const s of hist) {
      const li = make('li', 'bd-tl');
      const h = make('p', 'bd-ghead'); h.append(make('span', 'bd-light ' + s.color), make('b', 'bd-gword', LIGHT[s.color]), make('span', 'bd-hint', ` · ${firstName(s.by_person || s.by)} · ${ago(s.at)}`));
      li.append(h);
      if (s.text) li.append(make('p', 'bd-gtext', s.text));
      ol.append(li);
    }
    out.push(ol);
  }
  const tasks = (d && d.tasks) || i.tasks || [];
  const done = tasks.filter(t => t.done).length;
  out.push(make('h3', 'bd-sec-h bd-d-h', `Done-list ${tasks.length ? done + ' of ' + tasks.length : ''}`));
  if (tasks.length) {
    const ul = make('ul', 'bd-tasks');
    for (const t of tasks) { const li = make('li', t.done ? 'done' : ''); li.append(make('span', 'bd-tick', t.done ? '✓' : '○'), document.createTextNode(' ' + t.text)); ul.append(li); }
    out.push(ul);
  } else out.push(make('p', 'bd-meta', 'No done-list in this goal yet (- [ ] items in the description).'));
  const owners = (i.assignees || []).map(nameOf).join(', ');
  out.push(make('p', 'bd-meta', `Owners: ${owners || 'none yet'} · only James closes goals`));
  const linked = i.linked || [];
  out.push(make('h3', 'bd-sec-h bd-d-h', `Linked bugs and features ${linked.length || ''}`));
  if (!linked.length) out.push(make('p', 'bd-meta', 'None yet. The builder links an item to a goal only on a clear match (a “Goal: owner/repo#N” line).'));
  for (const k of ['test', 'show', 'james', 'airev', 'building', 'queued', 'shipping', 'done']) {
    const xs = linked.filter(x => x.stage === k);
    if (!xs.length) continue;
    out.push(make('p', 'bd-hint bd-lk-h', cap(STAGE_WORD[k]) + ` (${xs.length})`));
    const ul = make('ul', 'bd-linked');
    for (const x of xs) { const li = make('li'); const a = link('bd-link', x.url); a.textContent = x.title; li.append(a, make('span', 'bd-hint', ` · ${x.category === 'bug' ? 'bug' : x.category + ' feature'} · ${repoName(x.repo)} #${x.number}`)); ul.append(li); }
    out.push(ul);
  }
  g.replaceChildren(...out);
}

// 0.18: the detail shows the same one action area as the card.
function detailAct(i) {
  const a = el('d-act');
  const area = i && i.kind !== 'goal' && view !== 'goals' ? actionArea(i, true) : null;
  if (!area) { a.hidden = true; return a.replaceChildren(); }
  a.hidden = false;
  const [text] = whereLine(i);
  a.replaceChildren(make('h3', 'bd-sec-h bd-d-h', text || 'Next'), area);
}

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
  const still = el('d-still'), k2 = f.kicks || 0;
  still.hidden = !(f.still_not_working || k2 >= 2);
  if (!still.hidden) { still.textContent = `Still not working · Doesn’t work ${k2}×`; still.title = `Someone said Doesn’t work ${k2} times on this item`; }
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

// ---------- 0.17 Update manager: this box's WizardOS and every app, installed vs latest, Update and Update all ----------
// Sources (all the box's own App Manager routes the page already reaches on the shell's origin, owner-only):
// store-install/_updates (WizardOS release, channel, last failure), store-data/wizard/v1/installed-apps (what runs),
// store-data/wizard/v1/index/search (the Store's latest release per repo) and POST store-install/<id> with
// {source, repo, commit, operation: 'update'} (the Store's own exact-release update). No other team box is known to the
// Tracker yet (no list of team Wizards exists), so it shows this Wizard only.
const STORE_DATA = '/wizard-os-home/store-data/', STORE_INSTALL = '/wizard-os-home/store-install/';
let updates = null, catalog = null, catalogAt = 0, wizBusy = new Map(), wizFail = store.get('board.wizfail') || {};
const getJSON = (u, init) => fetch(u, { credentials: 'same-origin', cache: 'no-store', ...(init || {}) }).then(async r => { const b = await r.json().catch(() => null); if (!r.ok) { const e = new Error((b && b.error) || `HTTP ${r.status}`); e.status = r.status; throw e; } return b; });
async function loadCatalog(force) {
  if (catalog && !force && Date.now() - catalogAt < 120000) return catalog;
  const [inst, idx, up] = await Promise.allSettled([getJSON(STORE_DATA + 'wizard/v1/installed-apps'), getJSON(STORE_DATA + 'wizard/v1/index/search?limit=100' + (force ? '&refresh=1' : '')), getJSON(UPDATES_API)]);
  if (up.status === 'fulfilled') updates = up.value;
  if (inst.status !== 'fulfilled') { catalog = { error: inst.reason && inst.reason.status === 404 ? 'This Wizard’s App Manager can’t list its apps yet: update WizardOS.' : 'Open the Tracker inside your Wizard to see its apps.', apps: [] }; return catalog; }
  const rel = new Map();   // repo (lower) -> newest Store release for that exact repository
  for (const a of (idx.status === 'fulfilled' && idx.value.apps) || []) for (const r of [a, ...(a.releases || [])]) {
    if (!r || !r.repo || !/^[a-f0-9]{40}$/i.test(r.commit || '')) continue;
    const k = r.source + ':' + r.repo.toLowerCase() + ':' + r.id;
    if (!rel.has(k)) rel.set(k, r);
  }
  const apps = (inst.value.wam || []).map(w => {
    const r = rel.get(w.source + ':' + String(w.repo || '').toLowerCase() + ':' + w.id) || (w.source === 'owner-private' ? null : rel.get('standard:' + String(w.repo || '').toLowerCase() + ':' + w.id));
    const latest = r ? r.version : null;
    const pinned = WITH_OS.has(w.id);   // shipped and pinned by the WizardOS release, not updated one by one
    const cmp = latest ? vcmp(latest, w.version || '') : 0;
    return { id: w.id, name: w.name || w.id, version: w.version || '', commit: w.commit || '', repo: w.repo, source: w.source, status: w.status, system: !!w.system,
             latest, latestCommit: r ? r.commit : null, release: r, pinned, ahead: cmp < 0,
             update: !pinned && !!(r && r.commit && r.commit !== w.commit) && cmp > 0 };
  }).sort((a, b) => (b.update - a.update) || a.name.localeCompare(b.name));
  catalog = { apps, architecture: inst.value.architecture, complete: inst.value.complete, indexError: idx.status !== 'fulfilled' };
  catalogAt = Date.now();
  return catalog;
}
const WITH_OS = new Set(['wizard-ux', 'wizard-agent-service', 'wizard-app-manager']);
// Compare two release versions (numbers numerically, a pre-release below its release): >0 when a is newer.
function vcmp(a, b) {
  const sp = v => String(v).split(/[-+]/)[0].split('.').map(x => parseInt(x, 10) || 0), pre = v => String(v).includes('-');
  const x = sp(a), y = sp(b);
  for (let n = 0; n < Math.max(x.length, y.length); n++) if ((x[n] || 0) !== (y[n] || 0)) return (x[n] || 0) - (y[n] || 0);
  if (pre(a) !== pre(b)) return pre(a) ? -1 : 1;
  return String(a).localeCompare(String(b), undefined, { numeric: true });
}
const appsByName = () => new Map(((catalog && catalog.apps) || []).map(a => [a.name.toLowerCase(), a]));
function appForRepo(repo) {
  const r = String(repo || '').toLowerCase();
  return ((catalog && catalog.apps) || []).find(a => String(a.repo || '').toLowerCase() === r) || null;
}
// ---------- 0.22 Update progress, in place (on the card, in the detail and in Settings) ----------
// API gap: the App Manager's install job reports only state (installing / installed / failed), started, finished and
// error, and WizardOS's _updates only installing / failed / failure_reason / quick. Neither names a step or an ETA, so
// the Tracker shows its own steps: Starting (asked) -> Installing (the job runs) -> Restarting (polled on the app's
// /healthz version, or WizardOS's installed release) -> Done. A step the job does name (step, phase, message) is shown.
const UPD_STEPS = ['Starting', 'Installing', 'Restarting', 'Done'];
const runs = new Map();   // 'os' | app id -> { key, name, to, at, end, step, detail, state, reason, quick, items, retry }
const took = store.get('board.updtook') || {};   // key -> the last few update durations (seconds) on this device
function usually(r) {
  const xs = (took[r.key] || []).slice(-5).sort((a, b) => a - b);
  const sec = xs.length ? xs[Math.floor(xs.length / 2)] : r.key === 'os' ? (r.quick ? 150 : 480) : 90;
  const m = Math.max(1, Math.round(sec / 60));
  return `usually about ${m} minute${m === 1 ? '' : 's'}`;
}
const clock = sec => `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, '0')}`;
function runKeyOf(v) {
  const fix = (v && v.fix) || '';
  if (/^Update WizardOS/.test(fix)) return 'os';
  const m = /^Update (.+)$/.exec(fix);
  return m ? (v.apps || [])[0] || (appsByName().get(m[1].toLowerCase()) || {}).id || null : null;
}
function updRunFor(i, ob) {
  for (const r of runs.values()) if (r.items.has(i.id)) return r;
  const r = ob && ob.state === 'no' ? runs.get(runKeyOf(ob)) : null;
  return r && r.state === 'running' ? r : null;
}
function newRun(key, name, to, item, retry, quick) {
  const was = runs.get(key);
  const r = { key, name, to, at: Date.now(), end: 0, step: 'Starting', detail: '', state: 'running', reason: '', quick: !!quick,
              items: new Set(was ? was.items : []), retry };
  if (item) r.items.add(item.id);
  runs.set(key, r); repaintRuns();
  return r;
}
function runStep(r, step, detail) {
  if (r.step === step && r.detail === (detail || '')) return;
  r.step = step; r.detail = detail || '';
  if (r.key !== 'os') wizBusy.set(r.key, step + '…');
  repaintRuns();
}
function runEnd(r, ok, reason) {
  r.state = ok ? 'done' : 'failed'; r.end = Date.now(); r.reason = reason || '';
  if (ok) { r.step = 'Done'; (took[r.key] = (took[r.key] || []).concat(Math.round((r.end - r.at) / 1000)).slice(-5)); store.set('board.updtook', took); }
  setTimeout(() => { if (runs.get(r.key) === r && r.state !== 'running') { runs.delete(r.key); repaintRuns(); } }, ok ? 180000 : 600000);
  repaintRuns();
}
// The job's own words for its step, when it gives any (a newer App Manager may)
const jobDetail = j => { const x = j && (j.step || j.phase || j.message); return typeof x === 'string' ? x.slice(0, 80) : ''; };
function updPanel(r, i) {
  const box = make('div', 'bd-upd ' + r.state); box.dataset.upd = r.key;
  box.setAttribute('role', 'status'); box.setAttribute('aria-live', 'polite');
  const head = make('p', 'bd-upd-h'), t = make('span', 'bd-upd-t');
  const to = r.to ? ' to ' + r.to : '';
  head.append(make('i', 'bd-upd-dot', r.state === 'done' ? '✓' : r.state === 'failed' ? '!' : ''),
    make('b', '', r.state === 'running' ? `Updating ${r.name}${to}` : r.state === 'failed' ? `${r.name} didn’t update` : `${r.name} updated${to}`), t);
  box.append(head);
  const ol = make('ol', 'bd-upd-steps'), n = UPD_STEPS.indexOf(r.step);
  UPD_STEPS.forEach((w, k) => {
    const li = make('li', r.state === 'done' || k < n ? 'ok' : k === n ? (r.state === 'failed' ? 'bad' : 'now') : '', w);
    if (k === n && r.state === 'running') li.setAttribute('aria-current', 'step');
    ol.append(li);
  });
  box.append(ol);
  if (r.state === 'running') box.append(make('p', 'bd-upd-note', [r.detail, cap(usually(r))].filter(Boolean).join(' · ')));
  if (r.state === 'failed') {
    const why = make('p', 'bd-upd-why', r.reason || 'No reason given.');
    if (r.retry) why.append(document.createTextNode(' '), smallBtn('Try again', b => r.retry(b)));
    box.append(why);
  }
  if (r.state === 'done') {
    const v = i ? onboxOf(i) : null;
    box.append(make('p', 'bd-upd-ok' + (v && v.state === 'yes' ? ' yes' : ''), !i ? 'Done.' : !v ? 'Checking your Wizard…' : v.state === 'yes' ? ONBOX_TEXT.yes
      : v.state === 'no' ? `Updated, but this change isn’t in it yet${v.fix ? ' · ' + v.fix : ''}` : ONBOX_TEXT.unknown));
  }
  tickText(t, r);
  return box;
}
function tickText(t, r) { const sec = Math.max(0, ((r.state === 'running' ? Date.now() : r.end) - r.at) / 1000); t.textContent = r.state === 'running' ? clock(sec) : 'took ' + clock(sec); }
setInterval(() => { for (const b of document.querySelectorAll('.bd-upd.running')) { const r = runs.get(b.dataset.upd), t = b.querySelector('.bd-upd-t'); if (r && t) tickText(t, r); } }, 1000);
function repaintRuns() {
  if (cache[view] && !typing() && !document.querySelector('.bd-confirm')) render(cache[view]);
  if (openItem && el('detail').open) detailAct(openItem);
  paintWizards();
  if (typeof selfUpdate === 'function') selfUpdate();
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
// Restarting: wait until the app answers its health check with a version other than the one it had (the new one)
async function backUp(url, want, had, name, seconds) {
  let last = null;
  for (const end = Date.now() + seconds * 1000; Date.now() < end; await sleep(2000)) {
    try { const h = await getJSON(url); last = h && h.version; if (last && (last === want || (had && last !== had))) return last; } catch (_) {}
  }
  throw new Error(last ? `${name} restarted but still runs ${last}.` : `${name} didn’t come back within ${Math.round(seconds / 60)} minutes.`);
}
async function updateApp(id, btn, item) {
  await loadCatalog();
  const a = ((catalog && catalog.apps) || []).find(x => x.id === id);
  if (!a || !a.release) return btn && pop(btn, '', 'The Store has no newer release of this app for this Wizard. Update in Settings › Apps.');
  if (!a.update) return btn && pop(btn, '', a.pinned ? `${a.name} updates with WizardOS.` : `${a.name} is already the latest (${a.version}).`);
  if (runs.get(id) && runs.get(id).state === 'running') return;
  const sel = { source: a.release.source, repo: a.release.repo, commit: a.release.commit, operation: 'update' };
  const self = id === 'wizardos-tracker';
  wizBusy.set(id, 'Starting…');
  const r = newRun(id, a.name, a.latest, item, b => updateApp(id, b, item));
  try {
    const url = STORE_INSTALL + encodeURIComponent(id);
    let j = await getJSON(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Wizard-Store': '1' }, body: JSON.stringify(sel) });
    for (let n = 0; j && j.state === 'installing' && n < 360; n++) {
      runStep(r, 'Installing', jobDetail(j));
      await sleep(2500); j = await getJSON(url).catch(() => ({ state: 'installing' }));
    }
    if (!j || j.state !== 'installed') throw new Error((j && j.error) || 'The App Manager didn’t finish. Refresh to check.');
    runStep(r, 'Restarting', jobDetail(j));
    const v = await backUp(self ? 'healthz' : '/' + encodeURIComponent(id) + '/healthz', a.latest, self ? me && me.version : a.version, a.name, 150);
    facts.apps[id] = v;
    delete wizFail[id]; runEnd(r, true);
  } catch (e) {
    const reason = e.status === 404 ? 'This Wizard’s App Manager can’t update apps from here yet. Update in Settings › Apps.' : e.message;
    wizFail[id] = { at: Date.now(), name: a.name, to: a.latest, reason };
    runEnd(r, false, reason);
  } finally {
    store.set('board.wizfail', wizFail);
    wizBusy.delete(id); catalog = null; onbox.clear();
    if (self && !wizFail[id]) { toast('The Tracker updated: reloading…'); setTimeout(() => location.reload(), 1500); return; }
    await loadCatalog(true); paintWizards();
    if (cache[view]) { render(cache[view]); checkOnBox([...((cache[view].groups || {}).test || [])]); }
  }
}
async function updateAll(btn) {
  const list = ((catalog && catalog.apps) || []).filter(a => a.update && !wizBusy.has(a.id));
  if (!list.length) return pop(btn, '', 'Every app is up to date.');
  askPop(btn, `Update ${list.length} app${list.length === 1 ? '' : 's'}? Each one restarts for a moment.`, 'Update all', async () => { for (const a of list) await updateApp(a.id); });
}
async function updateWizardOS(btn, item) {
  try {
    const u = updates || await getJSON(UPDATES_API);
    const target = u && (u.latest_for_channel || (u.channel === 'latest' ? u.latest : u.stable));
    if (!u || !u.update_available) return btn && pop(btn, '', `WizardOS ${u && u.installed ? u.installed : ''} is the latest on ${u && u.channel === 'latest' ? 'For testers' : 'Stable'}.`);
    if (runs.get('os') && runs.get('os').state === 'running') return;
    if (btn && !btn.dataset.sure) return askPop(btn, `Update WizardOS ${u.installed} → ${target}? Wizard restarts for a moment.`, 'Update', () => { btn.dataset.sure = '1'; updateWizardOS(btn, item).finally(() => { delete btn.dataset.sure; }); });
    const r = newRun('os', 'WizardOS', target, item, b => updateWizardOS(b, item), u.quick);
    try {
      const a = await getJSON(UPDATES_API, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Wizard-Store': '1' }, body: JSON.stringify({ action: 'apply' }) });
      if (a && a.error) throw new Error(a.error);
      store.set('board.osrun', { to: target, from: u.installed, at: r.at, item: item ? item.id : null });
      await followOS(r, u.installed);
    } catch (e) { runEnd(r, false, e.status === 404 ? 'Update in Settings › Updates.' : e.message); store.set('board.osrun', null); }
  } catch (e) { if (btn) pop(btn, '', e.status === 404 ? 'Update in Settings › Updates.' : e.message); }
}
// Installing while _updates says installing; Restarting while Wizard is away (or back but not yet on the release);
// Done once _updates reports the target installed; failed with its failure_reason.
async function followOS(r, from) {
  let away = false;
  for (const end = r.at + 25 * 60000; Date.now() < end; await sleep(3000)) {
    let u = null;
    try { u = await getJSON(UPDATES_API); } catch (_) { away = true; runStep(r, 'Restarting', 'Wizard is restarting'); continue; }
    updates = u; r.quick = !!u.quick;
    if (u.installed && (u.installed === r.to || (from && u.installed !== from && !u.installing))) {
      store.set('board.osrun', null); facts.release = u.installed; factsReady = null; onbox.clear(); runEnd(r, true);
      if (cache[view]) checkOnBox([...((cache[view].groups || {}).test || [])]);
      return;
    }
    if (u.failed || u.interrupted) throw new Error(u.failure_reason || 'The WizardOS update stopped.');
    runStep(r, u.installing ? 'Installing' : away ? 'Restarting' : 'Installing', u.installing ? (u.quick ? 'Swapping the Wizard image' : '') : '');
  }
  throw new Error('Still not done after 25 minutes. Check Settings › Updates.');
}
// A WizardOS update restarts Wizard, which may reload this page: pick the progress back up
(() => {
  const o = store.get('board.osrun');
  if (!o || !o.to || Date.now() - o.at > 30 * 60000) return;
  const r = { key: 'os', name: 'WizardOS', to: o.to, at: o.at, end: 0, step: 'Restarting', detail: '', state: 'running', reason: '', quick: false,
              items: new Set(o.item ? [o.item] : []), retry: b => updateWizardOS(b) };
  runs.set('os', r);
  followOS(r, o.from).catch(e => { runEnd(r, false, e.message); store.set('board.osrun', null); });
})();
// 0.18: the Update manager lives in Settings only (no separate view or header button). openUM opens Settings at an app.
let umFocus = null;
function openUM(focusId) {
  unpop();
  umFocus = focusId || null;
  if (!el('settings').open) { tryList(); WzSheet.open(el('settings')); }
  showWizards(true);
}
// The Tracker's own row shows the version that is actually running (the server answering this page), so it is right
// straight after a self-update even if the App Manager's list is a moment behind.
function runningSelf(a) {
  const v = me.version, cmp = a.latest ? vcmp(a.latest, v) : 0;
  return { ...a, version: v, update: a.update && cmp > 0, ahead: a.latest ? cmp < 0 : a.ahead };
}
async function showWizards(force) {
  if (!catalog) el('um-body').replaceChildren(make('p', 'bd-empty', 'Loading…'));
  await loadCatalog(force);
  paintWizards();
}
function paintWizards() {
  if (!el('settings').open || !catalog) return;
  const w = el('um-body'), u = updates || {};
  const host = /^[0-9.]+$|^localhost$/.test(location.hostname) ? 'This Wizard' : location.hostname.split('.')[0];
  const card = make('article', 'bd-card bd-wiz');
  const head = make('div', 'bd-card-top'); head.append(make('b', 'bd-title', host), make('span', 'bd-meta', 'this Wizard'));
  card.append(head);
  const os = make('p', 'bd-onbox ' + (u.update_available ? 'no' : 'yes'));
  const ch = u.channel === 'latest' ? 'For testers' : u.channel === 'stable' ? 'Stable' : '—';
  os.append(make('b', '', 'WizardOS ' + (u.installed || '?')), document.createTextNode(` · ${ch}` + (u.update_available ? ` · ${u.latest_for_channel || (u.channel === 'latest' ? u.latest : u.stable)} available ` : ' · latest ✓')));
  const osRun = runs.get('os');
  if (u.update_available && !osRun) os.append(smallBtn(u.installing ? 'Updating…' : 'Update', b => updateWizardOS(b)));
  card.append(os);
  if (osRun) card.append(updPanel(osRun, null));
  if (u.failed || u.interrupted) card.append(make('p', 'bd-why', `Last WizardOS update failed${u.retry_target ? ' (' + u.retry_target + ')' : ''}: ${u.failure_reason || 'no reason given'}.`));
  const apps = (catalog.apps || []).map(a => a.id === 'wizardos-tracker' && me && me.version ? runningSelf(a) : a);
  const n = apps.filter(a => a.update).length;
  const bar = make('div', 'bd-wiz-bar');
  bar.append(make('span', 'bd-meta', catalog.error || `${apps.length} apps · ${n ? n + ' to update' : 'all up to date'}`));
  const all = smallBtn('Update all', b => updateAll(b)); if (!n) all.setAttribute('aria-disabled', 'true'); bar.append(all);
  card.append(bar);
  const fails = Object.entries(wizFail).sort((a, b) => b[1].at - a[1].at);
  if (fails.length) { const [id, f] = fails[0]; card.append(make('p', 'bd-why', `Last failed update: ${f.name || id} → ${f.to || '?'} (${when(new Date(f.at).toISOString())}): ${f.reason}`)); }
  const list = make('div', 'bd-list rows bd-wiz-apps');
  for (const a of apps) {
    const r = make('div', 'bd-rowx bd-wiz-app' + (a.id === umFocus ? ' focus' : ''));
    r.dataset.app = a.id;
    const t = make('div', 'bd-item'); t.append(make('b', 'bd-title', a.name));
    const busy = wizBusy.get(a.id);
    const where = a.pinned ? 'updates with WizardOS' : a.update ? `latest ${a.latest}` : a.ahead ? `newer than the Store (${a.latest})` : a.latest ? 'latest ✓' : a.source === 'owner-private' ? 'private build' : 'not in the Store';
    t.append(make('span', 'bd-meta', [a.version || '?', where, a.status && a.status !== 'running' ? a.status : ''].filter(Boolean).join(' · ')));
    r.append(t);
    const b = smallBtn(busy || 'Update', x => a.update ? updateApp(a.id, x) : pop(x, '', b.title));
    if (!a.update || busy) { b.setAttribute('aria-disabled', 'true'); b.title = busy || (a.pinned ? 'Updates with WizardOS (above).' : a.ahead ? 'This Wizard runs a newer build than the Store lists.' : a.latest ? 'Already the latest.' : 'Nothing in the Store to update to.'); }
    r.append(b);
    list.append(r);
  }
  card.append(list);
  card.append(make('p', 'bd-meta', 'Only this Wizard for now: the Tracker doesn’t know the team’s other Wizards yet.'));
  w.replaceChildren(card);
  const f = umFocus && w.querySelector(`[data-app="${CSS.escape(umFocus)}"]`);
  if (f) f.scrollIntoView({ block: 'center' });
}

// ---------- 0.17 Settings › Try changes: every switch in Human review, on/off, the same toggles as on the cards ----------
function tryList() {
  const rows = [], seen = new Set();
  for (const v of VIEWS) for (const i of ((cache[v] || {}).groups || {}).test || []) {
    if ((!i.switch && !i.switch_place) || seen.has(i.id)) continue;
    seen.add(i.id);
    const r = make('div', 'bd-rowx bd-try-row');
    const t = tapTarget('bd-item', () => { WzSheet.close(el('settings')); openDetail(i); });
    t.append(make('b', 'bd-title', i.title));
    const s = make('span', 'bd-meta');
    if (i.switch) { const sw = box && box.ok && box.switches[i.switch]; s.textContent = `${(sw && sw.name) || i.switch} · ${repoName(i.repo)}`; const why = tryWhy(i); if (why) t.append(s, ...blockerBits(i, { why }, why)); else t.append(s); }
    else { s.textContent = `${repoName(i.repo)} · `; t.append(s); for (const x of placeBits(i)) s.append(x, document.createTextNode(' ')); }
    r.append(t);
    if (i.switch) r.append(trySwitch(i));
    rows.push(r);
  }
  el('try-n').textContent = rows.length || '';
  el('try-list').replaceChildren(...(rows.length ? rows : [make('p', 'bd-empty', 'No change in Human review has a switch right now.')]));
  el('settings-ver').textContent = `WizardOS Tracker ${(me && me.version) || ''}`;
}
el('settings-btn').onclick = () => { unpop(); umFocus = null; tryList(); WzSheet.open(el('settings')); showWizards(false); if (!box || !box.ok) loadSwitches(); };

// ---------- 0.19: 'Tracker updated · Reload' when the server runs another version than this page (healthz every 2 min) ----------
const PAGE_VERSION = '0.25.0';
function newerBar(v) {
  let b = el('newer');
  if (!b) {
    b = make('div', 'bd-newer'); b.id = 'newer'; b.setAttribute('role', 'status');
    const t = make('span', 'bd-newer-t'), go = make('button', 'bd-newer-go', 'Reload'); go.type = 'button';
    go.onclick = () => location.reload();
    b.append(t, document.createTextNode(' · '), go); document.body.append(b);
  }
  b.querySelector('.bd-newer-t').textContent = 'Tracker updated';
  b.title = `This page is ${PAGE_VERSION}; the Tracker now runs ${v}.`;
  b.hidden = false;
}
async function checkVersion() {
  try { const h = await getJSON('healthz'); if (h && h.version && h.version !== PAGE_VERSION) newerBar(h.version); } catch (_) {}
}
setInterval(checkVersion, 120000);
setTimeout(checkVersion, 5000);

// ---------- 0.24.0: a newer Tracker in the Store -> one clear 'Update' on the main screen (signed in or not) ----------
// The same path as Settings › Update (the box's own App Manager, owner-only same-origin route); one tap, no confirm:
// the Tracker restarts for a moment and the page reloads itself. Agents send the owner here instead of running wam.
function selfUpdate() {
  const box = el('selfupd'); if (!box) return;
  const a0 = ((catalog && catalog.apps) || []).find(a => a.id === 'wizardos-tracker');
  const a = a0 && me && me.version ? runningSelf(a0) : a0;
  const r = runs.get('wizardos-tracker');
  if (r) { box.hidden = false; box.className = 'bd-selfupd'; box.replaceChildren(updPanel(r, null)); return; }
  if (!a || !a.update) { box.hidden = true; return box.replaceChildren(); }
  const t = make('span', 'bd-selfupd-t', `A new version of the Tracker is ready (${a.latest}).`);
  const go = make('button', 'wz-button bd-selfupd-go', 'Update'); go.type = 'button'; go.id = 'selfupd-go';
  go.onclick = () => { go.disabled = true; updateApp('wizardos-tracker', go).finally(() => { go.disabled = false; selfUpdate(); }); };
  box.className = 'bd-selfupd'; box.hidden = false; box.replaceChildren(t, go);
}
async function checkSelfUpdate(force) {
  try { await loadCatalog(force); } catch (_) {}
  selfUpdate();
}
setTimeout(() => checkSelfUpdate(false), 1500);
setInterval(() => { if (!document.hidden) checkSelfUpdate(true); }, 30 * 60000);

// ---------- start: refresh quietly on focus and every minute ----------
if (!window.WizardApp || WizardApp.version !== 1) {
  say('Wizard system functions are unavailable. Open this preview through Wizard.', 'error');
} else {
  WizardApp.ready({ name: 'wizardos-tracker', version: '0.25.0' });
  if (/^#(updates|wizards)$/.test(location.hash)) setTimeout(() => openUM(), 300);
}
markView();
loadCatalog().catch(() => {});
api('api/status').then(s => { show(s); if (s.connected) { load(view); loadSide(); setTimeout(() => { for (const other of VIEWS) if (other !== view && !cache[other]) api('api/split?view=' + other).then(d => { cache[other] = d; if (other === 'goals') goalsBadge(); }).catch(() => {}); }, 600); } })
  .catch(err => { el('loading').hidden = true; say(err.message, 'error'); });
const quiet = () => me && me.connected && !document.hidden && !typing() && !sheetOpen() && !popFor;
const tick = () => { if (quiet() && Date.now() - lastLoad > 20000) load(view, true); };
window.addEventListener('focus', tick);
document.addEventListener('visibilitychange', tick);
setInterval(() => { if (quiet()) load(view, true); }, 30000);
el('reload').onclick = () => { if (!inflight) { load(view, true); loadSide(); } };

// ---------- 0.20 Report or request: the WizardOS Reporter (web/report.js) lives in its own module; the Tracker only
// reloads the tab the item landed on and offers its WizardOS Update button for the 'update first' warning ----------
if (window.WizardReporter) {
  WizardReporter.onFiled = r => { setTimeout(() => load(r.view || view, true), 800); };
  WizardReporter.onUpdate = b => updateWizardOS(b);
}
