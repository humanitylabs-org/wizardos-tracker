'use strict';
// Board: three tabs over GitHub (Goals, To test, Issues) and one "+ New". All calls go to this app's own API.
const el = id => document.getElementById(id);
const make = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
const link = (cls, text, href) => { const a = make('a', cls, text); a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a; };
const EMPTY = { goals: 'No goals yet.', test: 'Nothing to test right now.', issues: 'No open issues.' };
const STATUS = { new: ['Not started', 'off'], doing: ['In progress', ''], ready: ['Ready to test', 'warn'], done: ['Done', 'ok'] };
let me = null, tab = 'goals', repoFilter = '', repoList = [], loadGen = 0;
const cache = {};

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
function short(repo) { return repo && me && repo.toLowerCase().startsWith(me.org.toLowerCase() + '/') ? repo.slice(me.org.length + 1) : repo; }

// ---------- sign in ----------
function renderAccount(s) {
  me = s;
  const on = !!s.connected;
  el('signin').hidden = on; el('pane').hidden = !on; el('bar').hidden = !on; el('tabs').hidden = !on; el('loading').hidden = true;
  if (!on) return;
  const a = s.account || {};
  el('me-login').textContent = a.login || 'GitHub';
  const img = el('avatar'); img.src = 'api/avatar?u=' + encodeURIComponent(a.login || ''); img.onerror = () => { img.removeAttribute('src'); };
}
el('connect-form').onsubmit = async e => {
  e.preventDefault();
  const t = el('token'), b = el('connect');
  b.disabled = true; t.disabled = true; say('Checking with GitHub…', 'note');
  try { const s = await api('api/connect', { token: t.value }); t.value = ''; say(''); renderAccount(s); toast(`Signed in as ${s.account.login}.`); await start(); }
  catch (err) { say(err.message, 'error'); }
  finally { b.disabled = false; t.disabled = false; }
};

// ---------- tabs ----------
function pick(next) {
  tab = next;
  for (const b of el('tabs').querySelectorAll('[data-tab]')) b.setAttribute('aria-selected', String(b.dataset.tab === tab));
  el('filter').hidden = tab !== 'issues';
  el('hint').hidden = true;
  if (cache[tab]) render(cache[tab]);
  load(tab);
  el('scroll').scrollTop = 0;
}
el('tabs').addEventListener('click', e => { const b = e.target.closest('[data-tab]'); if (b && b.dataset.tab !== tab) pick(b.dataset.tab); });
el('f-repo').onchange = () => { repoFilter = el('f-repo').value; delete cache.issues; el('list').replaceChildren(); load('issues'); };
el('refresh').onclick = () => { load(tab, true); for (const t of ['goals', 'test', 'issues']) if (t !== tab) load(t, true, true); };

async function load(which, refresh = false, quiet = false) {
  const gen = quiet ? loadGen : ++loadGen;
  const q = new URLSearchParams({ tab: which });
  if (which === 'issues' && repoFilter) q.set('repo', repoFilter);
  if (refresh) q.set('refresh', '1');
  if (!quiet) { el('refresh').classList.add('spin'); if (!cache[which]) { el('list').replaceChildren(); el('empty').hidden = false; el('empty').textContent = 'Loading…'; } }
  try {
    const d = await api('api/view?' + q);
    cache[which] = d; count(which);
    if (which === tab && (quiet || gen === loadGen)) render(d);
    if (!quiet) say('');
  } catch (err) {
    if (err.status === 401) { const s = await api('api/status').catch(() => null); if (s) renderAccount(s); }
    if (!quiet) say(err.message, 'error');
  } finally { if (!quiet && gen === loadGen) el('refresh').classList.remove('spin'); }
}
function count(which) { const d = cache[which]; el('n-' + which).textContent = d ? String(d.count) + (d.more ? '+' : '') : ''; }

function render(d) {
  const list = el('list');
  const items = d.items || [];
  list.className = 'bd-list' + (d.tab === 'issues' ? ' rows' : '');
  list.replaceChildren(...items.map(d.tab === 'goals' ? goalCard : d.tab === 'test' ? testCard : issueRow));
  el('empty').hidden = items.length > 0;
  el('empty').textContent = d.tab === 'issues' && repoFilter ? `No open issues in ${short(repoFilter)}.` : EMPTY[d.tab];
  el('hint').hidden = !(d.tab === 'test' && items.length);
}

function goalCard(g) {
  const c = make('article', 'bd-card'); c.dataset.id = g.id;
  const h = make('h3', 'bd-title'); h.append(link('', g.title, g.url));
  const [label, tone] = STATUS[g.status] || STATUS.new;
  c.append(h, make('p', 'bd-meta', `Owner: ${g.owner || 'nobody yet'} · ${short(g.repo)}`));
  const row = make('div', 'bd-row');
  const p = g.progress || { done: 0, total: 0 };
  const m = make('span', 'wz-meter');
  m.append(make('span', '', p.total ? `${p.done} of ${p.total} ${p.of === 'done-list items' ? 'steps' : 'issues'} done` : 'No linked issues yet'));
  const bar = make('i'); const fill = make('b'); fill.style.setProperty('--v', (p.total ? Math.round(100 * p.done / p.total) : 0) + '%'); bar.append(fill); m.append(bar);
  row.append(m, make('span', 'wz-pill ' + tone, label));
  c.append(row);
  return c;
}

function testCard(t) {
  const c = make('article', 'bd-card'); c.dataset.id = t.id;
  const h = make('h3', 'bd-title'); h.append(link('', t.title, t.url));
  c.append(h, make('p', 'bd-meta', short(t.repo)));
  if (t.check) {
    const box = make('p', 'bd-check'); box.append(make('b', '', 'What to check'), document.createTextNode(t.check)); c.append(box);
  }
  if (t.pr) c.append(link('bd-link', `See the change (PR #${t.pr.number}) ↗`, t.pr.url));
  const btns = make('div', 'bd-btns');
  const ok = make('button', 'wz-button', 'Works'); ok.type = 'button';
  const no = make('button', 'wz-button secondary', 'Doesn’t work'); no.type = 'button';
  btns.append(ok, no); c.append(btns);
  const status = make('p', 'wz-status'); c.append(status);
  const busy = on => c.querySelectorAll('button, textarea').forEach(x => { x.disabled = on; });
  const done = (msg) => { cache.test.items = cache.test.items.filter(x => x.id !== t.id); cache.test.count = cache.test.items.length; count('test'); render(cache.test); toast(msg); };
  ok.onclick = async () => {
    busy(true); status.textContent = '';
    try { await api('api/test/works', { repo: t.repo, number: t.number }); done('Thanks — marked as working.'); }
    catch (err) { status.textContent = err.message; busy(false); }
  };
  no.onclick = () => {
    if (c.querySelector('.bd-fail')) { c.querySelector('textarea').focus(); return; }
    const f = make('form', 'bd-fail'); f.autocomplete = 'off';
    const ta = make('textarea', 'wz-input bd-area'); ta.rows = 3; ta.required = true; ta.minLength = 3; ta.maxLength = 4000;
    ta.placeholder = 'What went wrong?'; ta.setAttribute('aria-label', 'What went wrong');
    const send = make('button', 'wz-button', 'Send'); send.type = 'submit';
    f.append(ta, send); btns.after(f); ta.focus();
    hold(true);
    f.onsubmit = async e => {
      e.preventDefault(); busy(true); status.textContent = '';
      try { await api('api/test/fails', { repo: t.repo, number: t.number, note: ta.value }); hold(false); done('Sent back to the builder.'); }
      catch (err) { status.textContent = err.message; busy(false); }
    };
  };
  return c;
}

function issueRow(i) {
  const a = link('bd-item', null, i.url); a.dataset.id = i.id;
  const txt = make('span', 'bd-txt');
  txt.append(make('b', '', i.title), make('span', 'bd-meta', `${short(i.repo)} · by ${i.author || 'unknown'}`));
  a.append(txt);
  if (i.waiting) a.append(make('span', 'wz-pill warn', 'Being tested'));
  else if (i.approved) a.append(make('span', 'wz-pill ok', 'Approved'));
  else if (i.kind === 'bug') a.append(make('span', 'wz-pill off', 'Bug'));
  return a;
}

async function loadRepos() {
  try {
    const r = await api('api/repos'); repoList = r.repos;
    const sel = el('f-repo');
    sel.replaceChildren(new Option('All repos', ''));
    for (const x of repoList) sel.append(new Option(x.name, x.full_name));
    sel.value = repoFilter;
  } catch (_) { repoList = []; }
}

// ---------- the one sheet ----------
const sheet = el('sheet');
let sheetHold = null;
function openSheet(title, build) {
  el('sheet-h').textContent = title; el('sheet-msg').textContent = '';
  const body = el('sheet-body'); body.replaceChildren(); build(body);
  WzSheet.open(sheet);
}
function closeSheet() { WzSheet.close(sheet); }
sheet.addEventListener('close', () => hold(false));
function hold(on) {
  if (on && !sheetHold && window.WizardApp && WizardApp.version === 1) sheetHold = WizardApp.update.hold('Unsaved Board text');
  if (!on && sheetHold) { sheetHold.release(); sheetHold = null; }
}
function field(label, input) { const w = make('label', 'bd-field'); w.append(make('span', 'bd-label', label), input); return w; }

function repoPicker(start) {
  // Searchable: shows the chosen repo; "Change" opens a filter box over the org's repos.
  const wrap = make('div', 'bd-field');
  wrap.append(make('span', 'bd-label', 'Repo'));
  const state = { value: start };
  const picked = make('div', 'bd-picked'); const name = make('b'); const change = make('button', '', 'Change'); change.type = 'button';
  picked.append(name, change);
  const search = make('input', 'wz-input'); search.type = 'search'; search.placeholder = 'Search repos'; search.setAttribute('aria-label', 'Search repos'); search.hidden = true;
  const opts = make('div', 'bd-repos'); opts.hidden = true;
  const show = () => { name.textContent = short(state.value) || 'Pick a repo'; };
  const fill = () => {
    const q = search.value.trim().toLowerCase();
    const rows = repoList.filter(r => !q || r.name.toLowerCase().includes(q)).slice(0, 40);
    opts.replaceChildren(...rows.map(r => { const b = make('button', '', r.name); b.type = 'button'; b.onclick = () => { state.value = r.full_name; show(); search.hidden = opts.hidden = true; picked.hidden = false; }; return b; }));
    if (!rows.length) opts.append(make('p', 'bd-meta', '  No repo matches.'));
  };
  change.onclick = () => { picked.hidden = true; search.hidden = opts.hidden = false; search.value = ''; fill(); search.focus(); };
  search.oninput = fill;
  wrap.append(picked, search, opts); show();
  return { node: wrap, get: () => state.value };
}

function openNew() {
  openSheet('New', body => {
    const f = make('form', 'bd-form'); f.autocomplete = 'off';
    let type = me.can_goal ? (tab === 'goals' ? 'goal' : 'issue') : 'issue';
    if (me.can_goal) {
      const seg = make('div', 'bd-seg'); seg.setAttribute('role', 'group'); seg.setAttribute('aria-label', 'Type');
      for (const [v, t] of [['issue', 'Issue'], ['goal', 'Goal']]) {
        const b = make('button', '', t); b.type = 'button'; b.dataset.v = v; b.setAttribute('aria-pressed', String(v === type));
        b.onclick = () => { type = v; seg.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x === b))); title.placeholder = place(); go.textContent = v === 'goal' ? 'Add goal' : 'Add issue'; };
        seg.append(b);
      }
      f.append(field('Type', seg));
    }
    const def = repoList.find(r => r.name.toLowerCase() === (me.default_repo || '').toLowerCase());
    const repo = repoPicker(def ? def.full_name : (repoList[0] || {}).full_name || `${me.org}/${me.default_repo}`);
    const place = () => type === 'goal' ? 'The outcome, e.g. Everyone can test on their phone' : 'What is wrong or missing, in one line';
    const title = make('input', 'wz-input'); title.required = true; title.minLength = 3; title.maxLength = 200; title.placeholder = place();
    const text = make('textarea', 'wz-input bd-area'); text.rows = 4; text.maxLength = 8000; text.placeholder = 'Details: what happens, what should happen';
    const go = make('button', 'wz-button', type === 'goal' ? 'Add goal' : 'Add issue'); go.type = 'submit';
    f.append(repo.node, field('Title', title), field('Description', text));
    f.append(me.screenshots ? make('p', 'bd-soon', 'Screenshots: paste a picture into the issue on GitHub after adding it.') : make('p', 'bd-soon', 'Screenshots coming soon'));
    const acts = make('div', 'wz-actions'); acts.append(go); f.append(acts);
    f.oninput = () => hold(!!(title.value.trim() || text.value.trim()));
    f.onsubmit = async e => {
      e.preventDefault();
      const all = [...f.querySelectorAll('button, input, textarea')]; all.forEach(x => { x.disabled = true; }); el('sheet-msg').textContent = '';
      try {
        const r = await api('api/new', { type, repo: repo.get(), title: title.value, body: text.value });
        hold(false); closeSheet();
        const d = cache[r.tab];
        if (d && !d.items.some(x => x.id === r.item.id) && !(r.tab === 'issues' && repoFilter && repoFilter !== r.item.repo)) { d.items.unshift(r.item); d.count = d.items.length; count(r.tab); }
        pick(r.tab);
        toast(r.warning || (type === 'goal' ? 'Goal added.' : 'Issue added.'));
      } catch (err) { el('sheet-msg').textContent = err.message; all.forEach(x => { x.disabled = false; }); }
    };
    body.append(f);
    setTimeout(() => title.focus(), 50);
  });
}
el('new').onclick = openNew;

el('me').onclick = () => openSheet('Your account', body => {
  const a = me.account || {};
  const row = make('div', 'bd-acct');
  const av = make('span', 'bd-avatar'); const img = make('img'); img.alt = ''; img.src = el('avatar').src || ''; av.append(img);
  const t = make('span', 'bd-txt'); t.append(make('b', '', a.login || 'GitHub'), make('p', 'bd-meta', `Signed in with your GitHub token · ${me.org}`));
  row.append(av, t); body.append(row);
  if (!me.can_goal) body.append(make('p', 'bd-meta', 'You can add Issues. Goals are added by the goal owners.'));
  const acts = make('div', 'wz-actions');
  const out = make('button', 'wz-button destructive', 'Sign out'); out.type = 'button';
  out.onclick = async () => { out.disabled = true; try { renderAccount(await api('api/disconnect', {})); closeSheet(); toast('Signed out.'); } catch (err) { el('sheet-msg').textContent = err.message; out.disabled = false; } };
  acts.append(out); body.append(acts);
});

// ---------- start ----------
async function start() { pick('goals'); load('test', false, true); load('issues', false, true); loadRepos(); }
if (!window.WizardApp || WizardApp.version !== 1) {
  say('Wizard system functions are unavailable. Open this preview through Wizard.', 'error');
} else {
  WizardApp.ready({ name: 'board', version: '0.2.0' });
  WizardApp.back.register({ canGoBack: () => false, back: () => false });
}
api('api/status').then(async s => { renderAccount(s); if (s.connected) await start(); })
  .catch(err => { el('loading').hidden = true; say(err.message, 'error'); });
let lastFocus = Date.now();
window.addEventListener('focus', () => { if (me && me.connected && Date.now() - lastFocus > 30000 && !sheet.open) { lastFocus = Date.now(); load(tab); } });
