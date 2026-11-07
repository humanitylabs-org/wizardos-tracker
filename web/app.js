'use strict';
// Wizard OS Tracker 0.9: Goals | Bugs + a small Builder switch; the assembly line Queued → Building →
// Review → Done (big numbers, arrows, a return arrow with the kick-back rate; each bin carries a tiny
// typical range p25–p75 with the median and a target tick; ⓘ for who + target; tap a bin to filter by stage).
// Bugs only: Who and Repo chip rows and a tiny sort control. Rows with a 'Try it' switch (mock-up, not on Done).
const el = id => document.getElementById(id);
const make = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
const link = (cls, href) => { const a = make('a', cls); a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a; };
const EMPTY = { goals: 'No open goals.', bugs: 'No open bugs. Nice.' };
const GROUPS = ['test', 'building', 'queued'];
const stageOf = { queued: 'queued', building: 'building', test: 'test', done: 'done' };
const stage = { goals: null, bugs: null };   // tap a bin: show only that stage (not remembered)
const doneCache = {};   // view -> { at, items } recently closed, loaded when the Done bin is tapped
let me = null, view = location.hash === '#bugs' ? 'bugs' : 'goals', gen = 0, held = null, lastLoad = 0, who = '';
const NO_DATA = 'starts once the builder runs';
const BINS = [
  { key: 'open', group: 'queued', word: 'Queued' },
  { key: 'build', group: 'building', word: 'Building' },
  { key: 'review', group: 'test', word: 'Review' },
  { key: 'done', group: null, word: 'Done' },
];
const POP = {
  build: ['Wizard OS Builder', 'Writes the code, then hands it to Review.'],
  review: ['The team, not whoever opened it', 'Someone else tries it: Works, or back to Building.'],
  done: ['Closed', 'The opener closes it once it works. All time.'],
};
const store = { get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch (_) { return null; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) {} } };
// Chip filters live on Bugs only (0.9: Goals has none); picks are remembered on the device.
const picked = { bugs: new Set(store.get('board.repos.bugs') || []) };
const pickedWho = { bugs: new Set(store.get('board.who.bugs') || []) };
let repoMore = false;   // the Repo row's '+N more' is open (not remembered)
const SORTS = [['oldest', 'Oldest'], ['newest', 'Newest'], ['discussed', 'Most discussed'], ['active', 'Recently active']];
const sortBy = { goals: null, bugs: SORTS.some(([k]) => k === store.get('board.sort.bugs')) ? store.get('board.sort.bugs') : 'oldest' };
const ts = iso => { const t = Date.parse(iso || ''); return isNaN(t) ? 0 : t; };
const SORT_FN = {
  oldest: (a, b) => ts(a.created_at) - ts(b.created_at),
  newest: (a, b) => ts(b.created_at) - ts(a.created_at),
  discussed: (a, b) => (b.comments || 0) - (a.comments || 0) || ts(a.created_at) - ts(b.created_at),
  active: (a, b) => ts(b.updated_at) - ts(a.updated_at),
};
let tries = {};   // 'owner/repo#12' -> true: this person's Try it switches (mock-up)
const tryKey = i => `${(i.repo || '').toLowerCase()}#${i.number}`;
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
  if (!r.ok) { const e = new Error(body.error || 'Something went wrong. Try again.'); e.status = r.status; throw e; }
  return body;
}
function hold(on) {
  if (on && !held && window.WizardApp && WizardApp.version === 1) held = WizardApp.update.hold('Unsaved tracker note');
  if (!on && held) { held.release(); held = null; }
}
const repoName = r => (r || '').split('/').pop();
const typing = () => !!document.querySelector('.bd-fail');
const sheetOpen = () => el('detail').open;

// ---------- one small anchored popover (bins, Builder, Try it); tap outside or Esc closes it ----------
let popFor = null;
function pop(anchor, title, text) {
  const p = el('pop');
  if (popFor === anchor && !p.hidden) return unpop();
  p.replaceChildren(...(title ? [make('b', '', title)] : []), ...[].concat(text).filter(Boolean).map(t => make('span', '', t)));
  p.hidden = false; popFor = anchor;
  const r = anchor.getBoundingClientRect(), w = Math.min(260, innerWidth - 24);
  p.style.width = w + 'px';
  p.style.left = Math.max(12, Math.min(innerWidth - w - 12, r.left + r.width / 2 - w / 2)) + 'px';
  const below = r.bottom + 8, h = p.offsetHeight;
  p.style.top = (below + h > innerHeight - 8 ? Math.max(8, r.top - h - 8) : below) + 'px';
  p.classList.toggle('up', below + h > innerHeight - 8);
}
function unpop() { el('pop').hidden = true; popFor = null; }
document.addEventListener('pointerdown', e => { if (popFor && !el('pop').contains(e.target) && !popFor.contains(e.target)) unpop(); }, true);
document.addEventListener('keydown', e => { if (e.key === 'Escape') unpop(); });
el('scroll').addEventListener('scroll', unpop, { passive: true });
addEventListener('resize', unpop);
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
function show(s) {
  me = s;
  const on = !!s.connected;
  el('signin').hidden = on; el('board').hidden = !on; el('loading').hidden = true;
}
el('connect-form').onsubmit = async e => {
  e.preventDefault();
  const t = el('token'), b = el('connect');
  b.disabled = true; t.disabled = true; say('Checking with GitHub…', 'note');
  try { const s = await api('api/connect', { token: t.value }); t.value = ''; say(''); show(s); load('goals'); loadSide(); }
  catch (err) { say(err.message, 'error'); }
  finally { b.disabled = false; t.disabled = false; }
};

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

async function load(which, refresh = false) {
  const g = ++gen; lastLoad = Date.now();
  try {
    const d = await api(`api/split?view=${which}${refresh ? '&refresh=1' : ''}`);
    if (d.stats && d.stats.pending && cache[which] && cache[which].stats && !cache[which].stats.pending) d.stats = cache[which].stats;
    cache[which] = d;
    if (which === view && g === gen && !typing()) render(d);
    say('');
    if (d.stats && d.stats.pending) loadStats(which);
  } catch (err) {
    if (err.status === 401) { const s = await api('api/status').catch(() => null); if (s) show(s); }
    say(err.message, 'error');
  }
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
  el('filters').hidden = !bugs; el('sort').hidden = !bugs || stage[d.view] === 'done';   // Done lists newest closed first
  if (bugs) {
    const people = authorsOf({ groups: Object.fromEntries(GROUPS.map(g => [g, d.groups[g].filter(byRepo)])) });
    const counts = new Map(reposOf(d, byWho).map(([r, n]) => [r.toLowerCase(), n]));
    const repos = [...known].map(([k, r]) => [k, repoName(r), counts.get(k) || 0]).sort((a, b) => b[2] - a[2] || a[1].localeCompare(b[1]));
    chipRow('who', whoSet, people.map(([p, n]) => [p.toLowerCase(), p === d.login ? `${p} (you)` : p, n]));
    chipRow('repo', chosen, repos);
    sortControl();
  }
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
const REPO_TOP = 10;
function chip(label, n, on, fn, extra = '') {
  const b = make('button', 'bd-chip' + (extra ? ' ' + extra : '')); b.type = 'button';
  b.setAttribute('aria-pressed', String(on));
  b.append(make('span', 'bd-chip-l', label));
  if (n != null) b.append(make('span', 'bd-chip-n', String(n)));
  b.onclick = fn; return b;
}
function chipRow(kind, set, options) {
  const box = el('c-' + kind), total = options.reduce((a, o) => a + o[2], 0);
  const toggle = k => () => { if (set.has(k)) set.delete(k); else set.add(k); saveFilter(kind); };
  const out = [chip(kind === 'who' ? 'Everyone' : 'All repos', total, !set.size, () => { set.clear(); saveFilter(kind); }, 'all')];
  let shown = options;
  if (kind === 'repo' && !repoMore) {  // the repos with bugs (top few) and any picked; the rest behind '+N more'
    const top = options.filter(o => o[2] > 0).slice(0, REPO_TOP);
    shown = options.filter(o => top.includes(o) || set.has(o[0]));
  }
  out.push(...shown.map(([k, label, n]) => chip(label, n, set.has(k), toggle(k), n ? '' : 'zero')));
  if (kind === 'repo' && options.length > shown.length) out.push(chip(`+${options.length - shown.length} more`, null, false, () => { repoMore = true; render(cache[view]); }, 'more'));
  else if (kind === 'repo' && repoMore && options.length > REPO_TOP) out.push(chip('Less', null, false, () => { repoMore = false; render(cache[view]); }, 'more'));
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
  build: 'Build time: first building → ready-to-test',
  review: 'Time in review: ready-to-test → closed or kicked back',
  done: 'Total time: opened → closed',
};
const STAT_KEY = { open: 'queued', build: 'building', review: 'review', done: 'done' };
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
  return { queued: spread(items.map(i => i.wait)), building: spread(items.map(i => i.build)),
    review: spread(items.flatMap(i => i.review_rounds || [])), done: spread(items.map(i => i.total)),
    kick: { reviewed: reviewed.length, kicked: kicked.length, rate: reviewed.length ? kicked.length / reviewed.length : null,
      per: kicked.length ? kicked.reduce((a, i) => a + i.kicks, 0) / kicked.length : null,
      toDone: toDone.length ? toDone.reduce((a, b) => a + b, 0) / toDone.length : null } };
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
  if (!s.n) { box.append(make('span', 'bd-rn none', '—')); if (target) box.append(make('span', 'bd-rl', 'target ' + dur(target)));
    box.title = `${STAT_HELP[x.key]}: ${NO_DATA}`; return box; }
  const cls = target ? (s.median <= target ? 'ok' : 'warn') : '';
  const nums = make('span', 'bd-rn' + (s.p25 == null ? ' one' : ''));
  if (s.p25 != null) nums.append(make('span', 'lo', dur(s.p25)), make('b', 'md ' + cls, dur(s.median)), make('span', 'hi', dur(s.p75)));
  else nums.append(make('b', 'md ' + cls, dur(s.median)));
  box.append(nums, rangeBar(s, target, cls), make('span', 'bd-rl', target ? 'target ' + dur(target) : 'typical'));
  box.title = `${STAT_HELP[x.key]} (${s.n} item${s.n === 1 ? '' : 's'}). ` + statLines(x, s, target).filter(Boolean).join(' ') + (s.avg != null ? ` Average ${dur(s.avg)}.` : '');
  return box;
}
const infoIcon = () => {
  const svg = document.createElementNS(NS, 'svg'); svg.setAttribute('viewBox', '0 0 16 16'); svg.setAttribute('aria-hidden', 'true');
  const c = document.createElementNS(NS, 'circle'); c.setAttribute('cx', '8'); c.setAttribute('cy', '8'); c.setAttribute('r', '6.25');
  const p = document.createElementNS(NS, 'path'); p.setAttribute('d', 'M8 7.2v4M8 4.9v.1'); svg.append(c, p); return svg;
};
function flow(d, groups, done, st, hist) {
  steps = d.steps && d.steps.length === 3 ? d.steps : [];
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
    if (x.key === 'done') b.title = st.error ? st.error : done == null ? 'Counting…' : 'Closed, all time · tap for the latest';
    const wrow = make('span', 'bd-bin-wr');
    const info = make('button', 'bd-i'); info.type = 'button'; info.setAttribute('aria-label', `Who does ${x.word}?`); info.append(infoIcon());
    info.onclick = e => { e.stopPropagation(); openStep(x, info, d.view, ls ? statLines(x, ls[STAT_KEY[x.key]], (d.targets || {})[STAT_KEY[x.key]]) : statLines(x, null, (d.targets || {})[STAT_KEY[x.key]])); };
    wrow.append(make('span', 'bd-bin-w', x.word), info);
    li.append(b, wrow, binStat(x, ls, st, d.targets));
    li.onclick = e => { if (!info.contains(e.target)) setStage(g); };
    out.push(li);
  });
  el('steps').replaceChildren(...out);
  kickLabel(ls, st);
}
const pct = r => Math.round(r * 100) + '%';
const times = x => (Math.round(x * 10) / 10) + '×';
function kickLabel(ls, st) {
  const k = el('kick');
  const kk = ls && ls.kick;
  k.hidden = !!st.pending;
  if (st.pending) return;
  const text = !kk || kk.rate == null ? '—' : kk.kicked ? `${pct(kk.rate)} · ${times(kk.per)}` : '0%';
  k.textContent = text;
  const why = !kk || kk.rate == null ? `Kicked back: ${NO_DATA}`
    : `${pct(kk.rate)} of ${kk.reviewed} reviewed item${kk.reviewed === 1 ? '' : 's'} came back at least once` + (kk.kicked ? `, ${times(kk.per)} on average` : '')
      + (kk.toDone != null ? `. ${dur(kk.toDone)} on average from first kick-back to done.` : '.');
  k.title = why; k.setAttribute('aria-label', 'Doesn’t work goes back to Building. ' + why);
  k.onclick = () => pop(k, 'Doesn’t work → back to Building', why);
}
function openStep(x, anchor, kind, extra = []) {
  if (x.key === 'open') {
    const s = (steps || []).find(y => y.key === 'open');
    const who = s ? s.role : kind === 'goals' ? 'James' : 'Anyone on the team';
    return pop(anchor, who, [kind === 'goals' ? 'Opens goals. They wait here until the builder picks them up.' : 'Opens bugs. They wait here until the builder picks them up.', ...extra]);
  }
  const [who, text] = POP[x.key];
  pop(anchor, x.key === 'build' && steps && steps[1] ? steps[1].role : who, [text, ...extra]);
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
const owners = i => {
  const a = (i.assignees && i.assignees.length) ? i.assignees : [];
  return a.length ? (a.length === 1 ? 'Owner: ' : 'Owners: ') + a.join(', ') : 'No owner yet';
};

// Try it (mock-up): a small switch on every row, live only in Review; never opens the row.
function trySwitch(i) {
  const live = i.group === 'test' || (i.labels || []).some(l => String(l).toLowerCase() === 'ready-to-test');
  const on = live && !!tries[tryKey(i)];
  const b = make('button', 'bd-try'); b.type = 'button'; b.setAttribute('role', 'switch');
  b.setAttribute('aria-checked', String(on)); b.setAttribute('aria-label', 'Try it');
  if (!live) b.setAttribute('aria-disabled', 'true');
  b.append(make('i'));
  const stop = e => e.stopPropagation();
  b.addEventListener('keydown', stop); b.addEventListener('pointerdown', stop);
  b.onclick = async e => {
    e.preventDefault(); e.stopPropagation();
    if (!live) return pop(b, '', 'Can be switched on once it’s in Review.');
    const next = b.getAttribute('aria-checked') !== 'true', k = tryKey(i);
    b.setAttribute('aria-checked', String(next)); b.disabled = true;
    try {
      const r = await api('api/try', { repo: i.repo, number: i.number, on: next });
      tries = Object.fromEntries(Object.keys(r.items || {}).map(x => [x, true]));
      if (next) pop(b, '', 'Mock-up: this will switch the change on in your Wizard once it runs a build with it.'); else unpop();
    } catch (err) { b.setAttribute('aria-checked', String(!next)); if (next) delete tries[k]; say(err.message, 'error'); }
    finally { b.disabled = false; }
  };
  return b;
}
function loadTries() {
  return api('api/try').then(r => { tries = Object.fromEntries(Object.keys(r.items || {}).map(x => [x, true]));
    if (cache[view] && !typing()) render(cache[view]); }).catch(() => {});
}

function row(i, kind) {
  const wrap = make('div', 'bd-rowx');
  const a = tapTarget('bd-item', () => openDetail(i));
  const top = make('span', 'bd-top'); top.append(make('b', 'bd-title', i.title));
  if (kind === 'goals') top.append(bubble(i.comments || 0));
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
    meta.append(make('span', 'bd-owner', owners(i)));
    const rest = [p.total ? `${p.done}/${p.total}` : '', repoName(i.repo)].filter(Boolean).join(' · ');
    if (rest) meta.append(make('span', 'bd-repo', ' · ' + rest));
  } else {  // bugs: title, one line, then repo · opener · comments
    meta.classList.add('bd-meta-b');
    const a2 = i.group !== 'done' && age(i.created_at);
    meta.append(document.createTextNode([repoName(i.repo), i.opener || i.author].filter(Boolean).join(' · ') + ' · '));
    if (a2) { const g = make('span', 'bd-age', a2); g.title = 'Opened ' + when(i.created_at); meta.append(g, document.createTextNode(' · ')); }
    meta.append(bubble(i.comments || 0));
  }
  if (i.group === 'done' && i.closed_at) meta.append(make('span', 'bd-repo', ' · closed ' + when(i.closed_at)));
  a.append(meta);
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
  catch (err) { say(err.message, 'error'); }
  finally { t.disabled = false; }
};
function loadSide() {
  api('api/builder').then(showBuilder).catch(() => {});
  loadTries();
}

function testCard(t, kind) {
  const c = make('article', 'bd-card');
  const top = make('div', 'bd-card-top');
  const h = tapTarget('bd-title', () => openDetail(t)); h.textContent = t.title;
  top.append(h, trySwitch(t)); c.append(top);
  if (t.check) c.append(make('p', 'bd-check' + (kind === 'bugs' ? ' one' : ''), t.check));
  c.append(make('p', 'bd-hint', [repoName(t.repo), t.opener ? (t.mine ? 'you' : t.opener) : '', kind === 'bugs' ? age(t.created_at) : '', `${t.comments || 0} comments`].filter(Boolean).join(' · ')));
  if (t.mine) {  // nobody reviews what they (or their own agent) opened
    c.classList.add('mine');
    c.append(make('p', 'bd-mine', 'Someone else reviews this'));
    return c;
  }
  const btns = make('div', 'bd-btns');
  const ok = make('button', 'wz-button', 'Works'); ok.type = 'button';
  const no = make('button', 'wz-button secondary', 'Doesn’t work'); no.type = 'button';
  btns.append(ok, no); c.append(btns);
  const status = make('p', 'wz-status'); c.append(status);
  const busy = on => c.querySelectorAll('button, textarea').forEach(x => { x.disabled = on; });
  const done = msg => {
    hold(false);
    const d = cache[view]; if (d) { d.groups.test = d.groups.test.filter(x => x.id !== t.id); render(d); }
    details.delete(t.id);
    toast(msg); setTimeout(() => load(view, true), 1500);
  };
  ok.onclick = async () => {
    busy(true); status.textContent = '';
    try { await api('api/test/works', { repo: t.repo, number: t.number }); done('Thanks — marked as working.'); }
    catch (err) { status.textContent = err.message; busy(false); }
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
  r.textContent = who ? `Opened by ${who} · reviewed by anyone else on the team` : '';
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
function fill(d) {
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
const CUR = { queued: 'open', building: 'build', review: 'review', done: 'done' };
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
    review: staged && (f.spent.review || f.tries) ? dur(f.spent.review) : '—',
    done: closedDate ? closedDate.toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) : '—',
  };
  const cur = CUR[f.stage] || 'open';
  BINS.forEach((x, n) => {
    if (n) ol.append(arrow());
    const reached = x.key === 'open' || (x.key === 'build' && val.build !== '—') || (x.key === 'review' && val.review !== '—') || (x.key === 'done' && !!closedDate);
    const li = make('li', 'bd-dbin' + (x.key === cur ? ' cur' : '') + (!reached && x.key !== cur ? ' dim' : ''));
    li.append(make('span', 'bd-dbin-v', val[x.key]), make('span', 'bd-dbin-w', x.word));
    li.title = { open: 'Time spent queued', build: 'Time spent building', review: 'Time spent in review', done: 'Closed on' }[x.key];
    li.setAttribute('aria-label', `${x.word}: ${val[x.key]}${x.key === cur ? ' (now)' : ''}`);
    ol.append(li);
  });
  const loop = make('p', 'bd-loop bd-dloop'); loop.setAttribute('role', 'img');
  const k = make('span', 'bd-kick', f.kicks ? f.kicks + '×' : '0×');
  loop.setAttribute('aria-label', `Kicked back ${f.kicks || 0} time${f.kicks === 1 ? '' : 's'}`);
  loop.title = `Kicked back ${f.kicks || 0}×` + (f.kick_to_done != null ? ` · ${dur(f.kick_to_done)} from first kick-back to done` : '');
  loop.classList.toggle('none', !f.kicks);
  loop.append(k);
  const wrap = make('div', 'bd-flow bd-dflowx'); wrap.append(ol, loop);
  box.replaceChildren(wrap);
  if (!staged && f.state === 'open') box.append(make('p', 'bd-meta bd-dflow-note', `Queued for ${dur(f.spent.queued)} · no build yet`));
}

// ---------- start: refresh quietly on focus and every minute ----------
if (!window.WizardApp || WizardApp.version !== 1) {
  say('Wizard system functions are unavailable. Open this preview through Wizard.', 'error');
} else {
  WizardApp.ready({ name: 'board', version: '0.9.0' });
  WizardApp.back.register({ canGoBack: () => false, back: () => false });
}
for (const x of sw.querySelectorAll('[data-view]')) x.setAttribute('aria-selected', String(x.dataset.view === view));
api('api/status').then(s => { show(s); if (s.connected) { load(view); loadSide(); const other = view === 'goals' ? 'bugs' : 'goals'; setTimeout(() => { if (!cache[other]) api('api/split?view=' + other).then(d => { cache[other] = d; }).catch(() => {}); }, 600); } })
  .catch(err => { el('loading').hidden = true; say(err.message, 'error'); });
const quiet = () => me && me.connected && !document.hidden && !typing() && !sheetOpen() && !popFor;
const tick = () => { if (quiet() && Date.now() - lastLoad > 20000) load(view, true); };
window.addEventListener('focus', tick);
document.addEventListener('visibilitychange', tick);
setInterval(() => { if (quiet()) load(view, true); }, 60000);
