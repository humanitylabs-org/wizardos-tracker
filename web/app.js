'use strict';
// Wizard OS Tracker 0.7: Goals | Bugs + a small Builder switch; the assembly line Queued → Building →
// Review → Done (big numbers, arrows, a return arrow; tap a bin for who); small stats; Everyone ▾ and
// All repos ▾ inline checklists; grouped rows with a 'Try it' switch (mock-up). Issue in a sheet on tap.
const el = id => document.getElementById(id);
const make = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
const link = (cls, href) => { const a = make('a', cls); a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a; };
const EMPTY = { goals: 'No open goals.', bugs: 'No open bugs. Nice.' };
const GROUPS = ['test', 'building', 'queued'];
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
const picked = { goals: new Set(store.get('board.repos.goals') || []), bugs: new Set(store.get('board.repos.bugs') || []) };
const pickedWho = { goals: new Set(store.get('board.who.goals') || []), bugs: new Set(store.get('board.who.bugs') || []) };
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
  p.replaceChildren(...(title ? [make('b', '', title)] : []), make('span', '', text));
  p.hidden = false; popFor = anchor;
  const r = anchor.getBoundingClientRect(), w = Math.min(260, innerWidth - 24);
  p.style.width = w + 'px';
  p.style.left = Math.max(12, Math.min(innerWidth - w - 12, r.left + r.width / 2 - w / 2)) + 'px';
  const below = r.bottom + 8, h = p.offsetHeight;
  p.style.top = (below + h > innerHeight - 8 ? Math.max(8, r.top - h - 8) : below) + 'px';
  p.classList.toggle('up', below + h > innerHeight - 8);
}
function unpop() { el('pop').hidden = true; popFor = null; }
document.addEventListener('pointerdown', e => { if (popFor && !el('pop').contains(e.target) && !popFor.contains(e.target)) unpop();
  for (const f of document.querySelectorAll('.bd-f.open')) if (!f.contains(e.target)) closeFilter(f); }, true);
document.addEventListener('keydown', e => { if (e.key === 'Escape') { unpop(); for (const f of document.querySelectorAll('.bd-f.open')) closeFilter(f, true); } });
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
  else { for (const g of GROUPS) el('sec-' + g).hidden = true; el('totals').textContent = ''; el('steps').replaceChildren(); el('stats').replaceChildren(); el('empty').hidden = false; el('empty').textContent = 'Loading…'; }
  unpop(); for (const f of document.querySelectorAll('.bd-f.open')) closeFilter(f);
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
  // Everyone ▾ and All repos ▾: multi-select, remembered per view; picks no longer present drop out.
  const whoSet = pickedWho[d.view], chosen = picked[d.view];
  const allPeople = new Set(authorsOf(d).map(([p]) => p.toLowerCase()));
  for (const p of [...whoSet]) if (!allPeople.has(p)) whoSet.delete(p);
  const present = new Set(reposOf(d, () => true).map(([r]) => r.toLowerCase()));
  for (const r of [...chosen]) if (!present.has(r)) chosen.delete(r);
  const byWho = i => !whoSet.size || whoSet.has((i.author || '').toLowerCase());
  const byRepo = i => !chosen.size || chosen.has(repoKey(i));
  const people = authorsOf({ groups: Object.fromEntries(GROUPS.map(g => [g, d.groups[g].filter(byRepo)])) });
  const repos = reposOf(d, byWho);
  filterButton('who', whoSet, people.map(([p, n]) => [p.toLowerCase(), p === d.login ? `${p} (you)` : p, n]), 'Everyone', x => x, 'people');
  filterButton('repo', chosen, repos.map(([r, n]) => [r.toLowerCase(), repoName(r), n]), 'All repos', repoName, 'repos');
  const keep = i => byWho(i) && byRepo(i);
  const groups = Object.fromEntries(GROUPS.map(g => [g, d.groups[g].filter(keep)]));
  const st = d.stats || {}, hist = (st.items || []).filter(keep);
  flow(d, groups, st.pending || st.error ? null : hist.filter(i => i.state === 'closed').length, st);
  stats(hist, st);
  el('totals').textContent = d.more ? `showing ${d.shown} of ${d.total}` : '';
  for (const g of GROUPS) {
    const list = groups[g];
    el('sec-' + g).hidden = !list.length;
    el('n-' + g).textContent = list.length || '';
    if (g === 'test') {  // others' work first (Works / Doesn't work); what you or your agent opened says someone else reviews it
      el('list-test').replaceChildren(...list.filter(i => !i.mine).map(i => testCard(i, d.view)), ...list.filter(i => i.mine).map(i => testCard(i, d.view)));
    } else el('list-' + g).replaceChildren(...list.map(i => row(i, d.view)));
  }
  const none = !GROUPS.some(g => groups[g].length);
  el('empty').hidden = !none;
  el('empty').textContent = whoSet.size || chosen.size ? 'Nothing here with these filters.' : EMPTY[d.view];
}

// ---------- filters: two identical pills; each opens a compact checklist right under it ----------
function filterButton(kind, set, options, allText, short, plural) {
  const box = el('f-' + kind), btn = box.querySelector('.bd-pick');
  btn.textContent = !set.size ? allText : set.size === 1 ? short([...set][0]) : `${set.size} ${plural}`;
  btn.classList.toggle('on', !!set.size);
  box.hidden = !options.length && !set.size;
  box._f = { kind, set, options, allText };
  if (box.classList.contains('open')) fillFilter(box);
}
const checkMark = () => {
  const chk = make('span', 'wz-check bd-chk'); const i = make('i');
  const svg = document.createElementNS(NS, 'svg'); svg.setAttribute('viewBox', '0 0 16 16'); svg.setAttribute('aria-hidden', 'true');
  const pth = document.createElementNS(NS, 'path'); pth.setAttribute('d', 'M3.5 8.5l3 3 6-7'); svg.append(pth); i.append(svg); chk.append(i);
  return chk;
};
function fillFilter(box) {
  const { kind, set, options, allText } = box._f, panel = box.querySelector('.bd-fp');
  const item = (label, n, on, fn) => {
    const b = make('button', 'bd-fp-row'); b.type = 'button'; b.setAttribute('role', 'menuitemcheckbox');
    b.setAttribute('aria-pressed', String(on)); b.setAttribute('aria-checked', String(on));
    b.append(checkMark(), make('span', 'bd-fp-name', label), make('span', 'bd-fp-n', n == null ? '' : String(n)));
    b.onclick = fn; return b;
  };
  const total = options.reduce((a, o) => a + o[2], 0);
  panel.replaceChildren(item(allText, total, !set.size, () => { set.clear(); saveFilter(kind); }),
    ...options.map(([k, label, n]) => item(label, n, set.has(k), () => { if (set.has(k)) set.delete(k); else set.add(k); saveFilter(kind); })));
}
function saveFilter(kind) {
  store.set((kind === 'who' ? 'board.who.' : 'board.repos.') + view, [...(kind === 'who' ? pickedWho : picked)[view]]);
  if (cache[view]) render(cache[view]);
}
function closeFilter(box, focus) {
  box.classList.remove('open'); box.querySelector('.bd-fp').hidden = true;
  const b = box.querySelector('.bd-pick'); b.setAttribute('aria-expanded', 'false'); if (focus) b.focus();
}
for (const box of document.querySelectorAll('.bd-f')) {
  box.querySelector('.bd-pick').onclick = () => {
    const open = box.classList.contains('open');
    for (const f of document.querySelectorAll('.bd-f.open')) closeFilter(f);
    if (open || !box._f) return;
    unpop(); box.classList.add('open'); fillFilter(box);
    box.querySelector('.bd-fp').hidden = false; box.querySelector('.bd-pick').setAttribute('aria-expanded', 'true');
  };
}

// The assembly line: four bins, a big number and one word each, arrows between, a return arrow under.
let steps = null;
const arrow = () => {
  const li = make('li', 'bd-arrow'); li.setAttribute('aria-hidden', 'true');
  const svg = document.createElementNS(NS, 'svg'); svg.setAttribute('viewBox', '0 0 20 12');
  const pth = document.createElementNS(NS, 'path'); pth.setAttribute('d', 'M1 6h16M12 1.5L17.5 6 12 10.5'); svg.append(pth); li.append(svg);
  return li;
};
function flow(d, groups, done, st) {
  steps = d.steps && d.steps.length === 3 ? d.steps : [];
  const out = [];
  BINS.forEach((x, n) => {
    if (n) out.push(arrow());
    const count = x.group ? groups[x.group].length : done;
    const li = make('li', 'bd-stepli');
    const b = make('button', 'bd-bin' + (count ? ' on' : '')); b.type = 'button'; b.dataset.step = x.key;
    b.setAttribute('aria-label', `${x.word}: ${count == null ? 'counting' : count}. Who does this?`);
    b.append(make('span', 'bd-bin-n', count == null ? '—' : String(count)), make('span', 'bd-bin-w', x.word));
    if (x.key === 'done') b.title = st.error ? st.error : done == null ? 'Counting…' : 'Closed, all time';
    b.onclick = () => openStep(x, b, d.view);
    li.append(b); out.push(li);
  });
  el('steps').replaceChildren(...out);
}
function openStep(x, anchor, kind) {
  if (x.key === 'open') {
    const s = (steps || []).find(y => y.key === 'open');
    const who = s ? s.role : kind === 'goals' ? 'James' : 'Anyone on the team';
    return pop(anchor, who, kind === 'goals' ? 'Opens goals. They wait here until the builder picks them up.' : 'Opens bugs. They wait here until the builder picks them up.');
  }
  const [who, text] = POP[x.key];
  pop(anchor, x.key === 'build' && steps && steps[1] ? steps[1].role : who, text);
}

const dur = sec => {
  if (sec == null) return null;
  if (sec < 3600) return Math.max(1, Math.round(sec / 60)) + 'm';
  if (sec < 86400) return Math.round(sec / 3600) + 'h';
  const days = sec / 86400;
  return (days < 10 ? Math.round(days * 10) / 10 : Math.round(days)) + 'd';
};
function summary(items) {
  const avg = xs => xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
  const waits = items.map(i => i.waiting_for).filter(x => x != null);
  const tries = items.map(i => i.tries).filter(Boolean);
  return { wait: avg(items.map(i => i.wait).filter(x => x != null)), build: avg(items.map(i => i.build).filter(x => x != null)),
           human: avg(waits), longest: waits.length ? Math.max(...waits) : null,
           tries: tries.length ? avg(tries) : null, kicks: items.reduce((a, i) => a + (i.kicks || 0), 0), tried: tries.length };
}
function stats(items, st) {
  const box = el('stats');
  if (st.pending) { box.replaceChildren(make('div', 'bd-stat wide', 'Counting where work waits…')); return; }
  if (st.error) { box.replaceChildren(make('div', 'bd-stat wide', st.error)); return; }
  const s = summary(items);
  const rows = [
    ['Queued for', dur(s.wait), 'Average time from opened to first building label'],
    ['Build time', dur(s.build), 'Average time from first building label to first ready-to-test label'],
    ['In review', s.human == null ? null : dur(s.human) + (s.longest > s.human + 60 ? ` · max ${dur(s.longest)}` : ''), 'Average and longest wait of items now labelled ready-to-test'],
    ['Tries', s.tries == null ? null : String(Math.round(s.tries * 10) / 10), 'Times an item was labelled ready-to-test, on average'],
    ['Kicked back', s.tried ? String(s.kicks) : null, 'Ready-to-test removed without a close (Doesn\u2019t work)'],
  ];
  box.replaceChildren(...rows.map(([label, value, help]) => {
    const div = make('div', 'bd-stat');
    const dd = make('dd', value == null ? 'none' : '', value == null ? '—' : value);
    div.title = value == null ? NO_DATA : help;
    if (value == null) dd.setAttribute('aria-label', '— ' + NO_DATA);
    div.append(make('dt', '', label), dd);
    return div;
  }));
}

const NS = 'http://www.w3.org/2000/svg';
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
    meta.append(document.createTextNode([repoName(i.repo), i.opener || i.author].filter(Boolean).join(' · ') + ' · '), bubble(i.comments || 0));
  }
  a.append(meta);
  wrap.append(a, trySwitch(i));
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
  c.append(make('p', 'bd-hint', [repoName(t.repo), t.opener ? (t.mine ? 'you' : t.opener) : '', `${t.comments || 0} comments`].filter(Boolean).join(' · ')));
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
el('detail').addEventListener('close', () => { openId = null; });

// ---------- start: refresh quietly on focus and every minute ----------
if (!window.WizardApp || WizardApp.version !== 1) {
  say('Wizard system functions are unavailable. Open this preview through Wizard.', 'error');
} else {
  WizardApp.ready({ name: 'board', version: '0.7.0' });
  WizardApp.back.register({ canGoBack: () => false, back: () => false });
}
for (const x of sw.querySelectorAll('[data-view]')) x.setAttribute('aria-selected', String(x.dataset.view === view));
api('api/status').then(s => { show(s); if (s.connected) { load(view); loadSide(); const other = view === 'goals' ? 'bugs' : 'goals'; setTimeout(() => { if (!cache[other]) api('api/split?view=' + other).then(d => { cache[other] = d; }).catch(() => {}); }, 600); } })
  .catch(err => { el('loading').hidden = true; say(err.message, 'error'); });
const quiet = () => me && me.connected && !document.hidden && !typing() && !sheetOpen() && !popFor && !document.querySelector('.bd-f.open');
const tick = () => { if (quiet() && Date.now() - lastLoad > 20000) load(view, true); };
window.addEventListener('focus', tick);
document.addEventListener('visibilitychange', tick);
setInterval(() => { if (quiet()) load(view, true); }, 60000);
