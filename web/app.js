'use strict';
// Wizard OS Tracker 0.4: Goals | Bugs, each in status groups (Ready to test, Building, Queued), one
// who-wrote-it filter, and the full issue (body + comments) in a sheet on tap. Creating, accepting and
// closing are said in chat with the agent, so the view has no create or account UI.
const el = id => document.getElementById(id);
const make = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
const link = (cls, href) => { const a = make('a', cls); a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a; };
const EMPTY = { goals: 'No open goals.', bugs: 'No open bugs. Nice.' };
const GROUPS = ['test', 'building', 'queued'];
let me = null, view = location.hash === '#bugs' ? 'bugs' : 'goals', gen = 0, held = null, lastLoad = 0, who = '';
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
const when = iso => {
  if (!iso) return '';
  const d = new Date(iso), days = Math.floor((Date.now() - d) / 864e5);
  if (days < 1) return 'today';
  if (days < 2) return 'yesterday';
  if (days < 30) return days + ' days ago';
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: d.getFullYear() === new Date().getFullYear() ? undefined : 'numeric' });
};
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
  try { const s = await api('api/connect', { token: t.value }); t.value = ''; say(''); show(s); load('goals'); }
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
  else { for (const g of GROUPS) el('sec-' + g).hidden = true; el('totals').textContent = ''; el('empty').hidden = false; el('empty').textContent = 'Loading…'; }
  el('scroll').scrollTop = 0;
  load(view);
});
el('who').addEventListener('change', e => { who = e.target.value; if (cache[view]) render(cache[view]); });

async function load(which, refresh = false) {
  const g = ++gen; lastLoad = Date.now();
  try {
    const d = await api(`api/split?view=${which}${refresh ? '&refresh=1' : ''}`);
    cache[which] = d;
    if (which === view && g === gen && !typing()) render(d);
    say('');
  } catch (err) {
    if (err.status === 401) { const s = await api('api/status').catch(() => null); if (s) show(s); }
    say(err.message, 'error');
  }
}

function authorsOf(d) {
  const n = new Map();
  for (const g of GROUPS) for (const i of d.groups[g]) if (i.author) n.set(i.author, (n.get(i.author) || 0) + 1);
  return [...n.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

function render(d) {
  // Who wrote it: only people present in this view; a pick that is gone falls back to Everyone.
  const people = authorsOf(d);
  if (who && !people.some(([p]) => p === who)) who = '';
  const sel = el('who');
  sel.replaceChildren(new Option('Everyone', ''), ...people.map(([p]) => new Option(p === d.login ? `${p} (you)` : p, p)));
  sel.value = who;
  el('who-wrap').hidden = people.length < 2 && !who;
  const keep = i => !who || i.author === who;
  const groups = Object.fromEntries(GROUPS.map(g => [g, d.groups[g].filter(keep)]));
  const closed = who ? (d.closed_week.authors || []).filter(a => a === who).length : d.closed_week.count;
  const parts = [`${groups.queued.length} queued`, `${groups.building.length} building`, `${groups.test.length} to test`, `${closed} closed this week`];
  el('totals').textContent = parts.join(' · ') + (d.more ? ` · showing ${d.shown} of ${d.total}` : '');
  for (const g of GROUPS) {
    const list = groups[g];
    el('sec-' + g).hidden = !list.length;
    el('n-' + g).textContent = list.length || '';
    if (g === 'test') {  // others' work gets Works / Doesn't work; your own waits quietly in rows below
      const mine = list.filter(i => i.mine), box = make('div', 'bd-list rows');
      box.append(...mine.map(i => row(i, d.view)));
      el('list-test').replaceChildren(...list.filter(i => !i.mine).map(testCard), ...(mine.length ? [box] : []));
    } else el('list-' + g).replaceChildren(...list.map(i => row(i, d.view)));
  }
  const none = !GROUPS.some(g => groups[g].length);
  el('empty').hidden = !none;
  el('empty').textContent = who ? `Nothing open from ${who}.` : EMPTY[d.view];
}

function row(i, kind) {
  const a = link('bd-item', i.url);
  a.onclick = e => { if (!plainClick(e)) return; e.preventDefault(); openDetail(i); };
  const top = make('span', 'bd-top'); top.append(make('b', 'bd-title', i.title));
  const waiting = i.mine && i.group === 'test' ? 'waiting for a tester' : '';
  if (kind === 'goals') {
    const p = i.progress || { done: 0, total: 0 };
    const pct = p.total ? Math.round(100 * p.done / p.total) : 0;
    if (p.total) top.append(make('span', 'bd-frac', `${p.done}/${p.total}`));
    a.append(top);
    if (p.total) {
      const bar = make('span', 'bd-bar'); const fill = make('i'); fill.style.width = pct + '%'; bar.append(fill);
      bar.setAttribute('role', 'progressbar'); bar.setAttribute('aria-valuenow', String(pct)); bar.setAttribute('aria-valuemin', '0'); bar.setAttribute('aria-valuemax', '100');
      a.append(bar);
    }
    a.append(make('span', 'bd-meta', [i.owner || 'No owner yet', waiting].filter(Boolean).join(' · ')));
  } else {
    a.append(top, make('span', 'bd-meta', [repoName(i.repo), i.author, waiting].filter(Boolean).join(' · ')));
  }
  return a;
}

function testCard(t) {
  const c = make('article', 'bd-card');
  const h = link('bd-title', t.url); h.textContent = t.title;
  h.onclick = e => { if (!plainClick(e)) return; e.preventDefault(); openDetail(t); };
  c.append(h);
  if (t.check) c.append(make('p', 'bd-check', t.check));
  c.append(make('p', 'bd-hint', [repoName(t.repo), t.author, 'turn it on in Settings › Tweaks'].filter(Boolean).join(' · ')));
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
function openDetail(i) {
  const dlg = el('detail');
  openId = i.id;
  el('d-title').textContent = i.title;
  el('d-meta').textContent = [`${i.repo}#${i.number}`, i.author].filter(Boolean).join(' · ');
  el('d-gh').href = i.url;
  el('d-labels').textContent = '';
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
  WizardApp.ready({ name: 'board', version: '0.4.0' });
  WizardApp.back.register({ canGoBack: () => false, back: () => false });
}
for (const x of sw.querySelectorAll('[data-view]')) x.setAttribute('aria-selected', String(x.dataset.view === view));
api('api/status').then(s => { show(s); if (s.connected) { load(view); const other = view === 'goals' ? 'bugs' : 'goals'; setTimeout(() => { if (!cache[other]) api('api/split?view=' + other).then(d => { cache[other] = d; }).catch(() => {}); }, 600); } })
  .catch(err => { el('loading').hidden = true; say(err.message, 'error'); });
const quiet = () => me && me.connected && !document.hidden && !typing() && !sheetOpen();
const tick = () => { if (quiet() && Date.now() - lastLoad > 20000) load(view, true); };
window.addEventListener('focus', tick);
document.addEventListener('visibilitychange', tick);
setInterval(() => { if (quiet()) load(view, true); }, 60000);
