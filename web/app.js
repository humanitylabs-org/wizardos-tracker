'use strict';
// Wizard OS Tracker 0.3: Goals | Bugs. Each shows Ready to test (Works / Doesn't work) above In progress.
// Everything else is said in chat with the agent, so the view has no create, filter or account UI.
const el = id => document.getElementById(id);
const make = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
const link = (cls, href) => { const a = make('a', cls); a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a; };
const EMPTY = { goals: 'No goals yet.', bugs: 'No bugs. Nice.' };
let me = null, view = location.hash === '#bugs' ? 'bugs' : 'goals', gen = 0, held = null, lastLoad = 0;
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
function hold(on) {
  if (on && !held && window.WizardApp && WizardApp.version === 1) held = WizardApp.update.hold('Unsaved tracker note');
  if (!on && held) { held.release(); held = null; }
}
const repoName = r => (r || '').split('/').pop();
const typing = () => !!el('board').querySelector('.bd-fail');

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
  else { el('sec-test').hidden = true; el('list-doing').replaceChildren(); el('list-doing').hidden = true; el('empty').hidden = false; el('empty').textContent = 'Loading…'; el('n-doing').textContent = ''; }
  el('scroll').scrollTop = 0;
  load(view);
});

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

function render(d) {
  el('sec-test').hidden = !d.test.length;
  el('n-test').textContent = d.test.length || '';
  el('list-test').replaceChildren(...d.test.map(testCard));
  el('n-doing').textContent = d.doing.length ? d.doing.length + (d.more ? '+' : '') : '';
  el('list-doing').replaceChildren(...d.doing.map(d.view === 'goals' ? goalRow : bugRow));
  el('list-doing').hidden = !d.doing.length;
  el('empty').hidden = d.doing.length > 0;
  el('empty').textContent = EMPTY[d.view];
}

function goalRow(g) {
  const a = link('bd-item', g.url);
  const p = g.progress || { done: 0, total: 0 };
  const pct = p.total ? Math.round(100 * p.done / p.total) : 0;
  const top = make('span', 'bd-top'); top.append(make('b', 'bd-title', g.title));
  if (p.total) top.append(make('span', 'bd-frac', `${p.done}/${p.total}`));
  const bar = make('span', 'bd-bar'); const fill = make('i'); fill.style.width = pct + '%'; bar.append(fill);
  bar.setAttribute('role', 'progressbar'); bar.setAttribute('aria-valuenow', String(pct)); bar.setAttribute('aria-valuemin', '0'); bar.setAttribute('aria-valuemax', '100');
  a.append(top);
  if (p.total) a.append(bar);
  a.append(make('span', 'bd-meta', g.owner || 'No owner yet'));
  return a;
}

function bugRow(b) {
  const a = link('bd-item', b.url);
  a.append(make('b', 'bd-title', b.title), make('span', 'bd-meta', repoName(b.repo)));
  return a;
}

function testCard(t) {
  const c = make('article', 'bd-card');
  const h = link('bd-title', t.url); h.textContent = t.title;
  c.append(h);
  if (t.check) c.append(make('p', 'bd-check', t.check));
  c.append(make('p', 'bd-hint', 'Turn it on in Settings › Tweaks'));
  const btns = make('div', 'bd-btns');
  const ok = make('button', 'wz-button', 'Works'); ok.type = 'button';
  const no = make('button', 'wz-button secondary', 'Doesn’t work'); no.type = 'button';
  btns.append(ok, no); c.append(btns);
  const status = make('p', 'wz-status'); c.append(status);
  const busy = on => c.querySelectorAll('button, textarea').forEach(x => { x.disabled = on; });
  const done = msg => {
    hold(false);
    const d = cache[view]; if (d) { d.test = d.test.filter(x => x.id !== t.id); render(d); }
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
    const row = make('div', 'bd-btns');
    const cancel = make('button', 'wz-button quiet', 'Cancel'); cancel.type = 'button';
    const send = make('button', 'wz-button', 'Send'); send.type = 'submit';
    row.append(cancel, send); f.append(ta, row);
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

// ---------- start: refresh quietly on focus and every minute ----------
if (!window.WizardApp || WizardApp.version !== 1) {
  say('Wizard system functions are unavailable. Open this preview through Wizard.', 'error');
} else {
  WizardApp.ready({ name: 'board', version: '0.3.0' });
  WizardApp.back.register({ canGoBack: () => false, back: () => false });
}
for (const x of sw.querySelectorAll('[data-view]')) x.setAttribute('aria-selected', String(x.dataset.view === view));
api('api/status').then(s => { show(s); if (s.connected) { load(view); const other = view === 'goals' ? 'bugs' : 'goals'; setTimeout(() => { if (!cache[other]) api('api/split?view=' + other).then(d => { cache[other] = d; }).catch(() => {}); }, 600); } })
  .catch(err => { el('loading').hidden = true; say(err.message, 'error'); });
const tick = () => { if (me && me.connected && !document.hidden && !typing() && Date.now() - lastLoad > 20000) load(view, true); };
window.addEventListener('focus', tick);
document.addEventListener('visibilitychange', tick);
setInterval(() => { if (me && me.connected && !document.hidden && !typing()) load(view, true); }, 60000);
