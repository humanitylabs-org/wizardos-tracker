'use strict';
// WizardOS Reporter 0.21: the one 'Report or request' form, two steps (Miguel). Step 1: Something's broken / I'd like
// something new. Step 2: one big text box (optional screenshot), Send. No 'what's it about', no confirm: the server files
// it in wizard-os with labels triage + bug/feature (version and device filled in), and the WizardOS Builder's triage
// step moves it to the right repo. Its own module (with app/report.py and /api/report) so it can become its own app.
// Host hooks: WizardReporter.onFiled(result) and WizardReporter.onUpdate(button) (optional).
(() => {
  const $ = id => document.getElementById(id);
  const mk = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
  const UPDATES = '/wizard-os-home/store-install/_updates';
  const KINDS = [['bug', 'Something’s broken'], ['feature', 'I’d like something new']];
  const SENT = 'Sent. The builder files it in the right place in a minute or two.';
  let opts = null, updates = null, kind = null, busy = false, shots = null, ctx = null, still = null;
  const getJSON = u => fetch(u, { credentials: 'same-origin', cache: 'no-store' }).then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)));

  // 'Mac · Chrome', 'iPhone · Safari'
  function device() {
    const ua = navigator.userAgent || '';
    const os = /iPhone/.test(ua) ? 'iPhone' : /iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1) ? 'iPad'
      : /Android/.test(ua) ? 'Android' : /Macintosh|Mac OS X/.test(ua) ? 'Mac' : /Windows/.test(ua) ? 'Windows' : /Linux/.test(ua) ? 'Linux' : 'Unknown device';
    const br = /Edg\//.test(ua) ? 'Edge' : /Firefox\//.test(ua) ? 'Firefox' : /Chrome\//.test(ua) ? 'Chrome' : /Safari\//.test(ua) ? 'Safari' : 'browser';
    return `${os} · ${br}`;
  }
  const channel = u => u && u.channel === 'latest' ? 'For testers' : u && u.channel === 'stable' ? 'For everyone' : '';
  const wizardVersion = () => updates && updates.installed ? updates.installed + (channel(updates) ? ` (${channel(updates)})` : '') : '';
  const newest = u => u.latest_for_channel || (u.channel === 'latest' ? u.latest : u.stable);

  function paint() {
    const p = (opts && opts.prompts) || {};
    const box = $('rr-kinds');
    box.replaceChildren(...KINDS.map(([key, name]) => {
      const b = mk('button', 'rr-pick rr-kind', name); b.type = 'button'; b.setAttribute('role', 'radio');
      b.setAttribute('aria-checked', String(key === kind)); b.dataset.key = key;
      b.onclick = () => { const first = !kind; kind = key; paint(); if (first) $('rr-text').focus(); };
      return b;
    }));
    $('rr-s2').hidden = !kind;
    const pr = p[kind] || {};
    $('rr-ask').textContent = pr.label || (kind === 'feature' ? 'What would you like, and why?' : 'What happened, and what should happen?');
    $('rr-text').placeholder = (pr.placeholder || '') + (kind ? ' If it’s about one app, name it.' : '');
    const w = $('rr-warn');
    w.hidden = !(kind === 'bug' && updates && updates.update_available);
    if (!w.hidden) {
      w.replaceChildren(document.createTextNode(`This Wizard runs WizardOS ${updates.installed}; ${newest(updates)} is out. Update first: it may already be fixed. `));
      if (typeof api.onUpdate === 'function') { const b = mk('button', 'bd-mini', 'Update'); b.type = 'button'; b.onclick = () => api.onUpdate(b); w.append(b); }
    }
    $('rr-shot-row').hidden = !(opts && opts.screenshots);
    $('rr-auto').textContent = 'Adds: ' + [wizardVersion() && 'WizardOS ' + wizardVersion(), device()].filter(Boolean).join(' · ');
    $('rr-go').disabled = busy || !(kind && $('rr-text').value.trim().length >= 8);
    $('rr-go').textContent = 'Send';
    // 0.27: a spinner on Send while it goes; 'Still working…' after 8 s (busy feedback everywhere)
    $('rr-go').classList.toggle('bd-busy', busy); if (busy) $('rr-go').setAttribute('aria-busy', 'true'); else $('rr-go').removeAttribute('aria-busy');
    paintCtx();
  }

  // 0.27: 'Report something else' from inside testing: the item under test, as one line with a link, and a one-tap
  // screenshot of the screen the tester is on (ctx.shoot). Its own report: the item under test is never touched.
  function paintCtx() {
    const line = $('rr-ctx'), snap = $('rr-snap-row');
    if (!line || !snap) return;
    line.hidden = !ctx; snap.hidden = !(ctx && ctx.shoot && !ctx.shot && opts && opts.screenshots);
    if (!ctx) return;
    const c = ctx.context, a = mk('a', 'bd-link');
    a.href = c.url || `https://github.com/${c.repo}/issues/${c.number}`; a.target = '_blank'; a.rel = 'noopener noreferrer';
    a.textContent = `${c.repo.split('/').pop()}#${c.number}`; if (c.title) a.title = c.title;
    line.replaceChildren(document.createTextNode('Found while testing '), a, document.createTextNode(c.app_name ? ` · ${c.app_name}` : ''));
  }
  async function snapshot() {
    const b = $('rr-snap'), st = $('rr-status'), say = (t, note) => { st.textContent = t; st.classList.toggle('note', !!note); };
    if (!ctx || !ctx.shoot || b.disabled) return;
    b.disabled = true; b.classList.add('bd-busy'); say('Taking a screenshot of this screen…', true);
    try {
      const got = await ctx.shoot();
      shots.addData(got.type, got.url);
      say(''); ctx.shot = true; paintCtx();   // one tap: the thumbnail shows it; Add another stays for more
    } catch (err) {
      say(`Couldn’t capture this screen${err && err.message ? ' (' + err.message + ')' : ''}. Paste a screenshot into the box, or tap Add a screenshot.`);
      const pick = $('rr-shot-row').querySelector('.rr-shot-pick'); if (pick) pick.focus();
    } finally { b.disabled = false; b.classList.remove('bd-busy'); }
  }

  async function load() {
    const [o, up] = await Promise.allSettled([getJSON('api/report'), getJSON(UPDATES)]);
    if (o.status === 'fulfilled') opts = o.value;
    if (up.status === 'fulfilled') updates = up.value;
    paint();
  }

  // 0.24.2: several screenshots with thumbnails (pick, paste or drop), shared with the Doesn't work note (app.js).
  // attacher(row, say) -> { add(files), list(), clear(), payload() }; row gets the thumbnails and an Add button.
  function attacher(row, say) {
    let items = [];
    const max = () => (opts && opts.shot_max) || 4 * 1024 * 1024, count = () => (opts && opts.shot_count) || 6;
    const thumbs = mk('span', 'rr-thumbs');
    const pick = mk('label', 'bd-mini rr-shot-pick');
    const input = mk('input'); input.type = 'file'; input.multiple = true; input.hidden = true;
    input.accept = 'image/png,image/jpeg,image/webp,image/gif';
    input.onchange = () => { add(input.files); input.value = ''; };
    pick.append(document.createTextNode('Add a screenshot'), input);
    row.replaceChildren(thumbs, pick);
    function draw() {
      thumbs.replaceChildren(...items.map((it, n) => {
        const t = mk('span', 'rr-thumb'), img = mk('img'); img.src = it.url; img.alt = 'Screenshot ' + (n + 1);
        const x = mk('button', 'rr-thumb-x', '×'); x.type = 'button'; x.setAttribute('aria-label', 'Remove screenshot ' + (n + 1));
        x.onclick = () => { items = items.filter(o => o !== it); draw(); };
        t.append(img, x); return t;
      }));
      pick.firstChild.textContent = items.length ? 'Add another' : 'Add a screenshot';
      pick.hidden = items.length >= count();
    }
    function add(files) {
      for (const file of [...(files || [])]) {
        if (items.length >= count()) { say(`Up to ${count()} screenshots.`); break; }
        if (!/^image\/(png|jpeg|webp|gif)$/.test(file.type)) { say('Use a PNG, JPEG, WebP or GIF image.'); continue; }
        if (file.size > max()) { say('That screenshot is too big (4 MB max).'); continue; }
        const it = { type: file.type, url: '' }; items.push(it);
        const r = new FileReader();
        r.onload = () => { it.url = String(r.result); say(''); draw(); };
        r.onerror = () => { items = items.filter(o => o !== it); say('That screenshot could not be read.'); draw(); };
        r.readAsDataURL(file);
      }
      draw();
    }
    // 0.27: a screenshot taken in the page (the framed app), as a data URL
    function addData(type, url) {
      if (items.length >= count()) { say(`Up to ${count()} screenshots.`); return; }
      if ((url.length - url.indexOf(',') - 1) * 0.75 > max()) { say('That screenshot is too big (4 MB max).'); return; }
      items.push({ type, url }); draw();
    }
    const imagesOf = dt => [...((dt && dt.files) || [])].filter(x => /^image\//.test(x.type));
    draw();
    return { add, addData, imagesOf, list: () => items, clear() { items = []; draw(); },
      payload: () => items.filter(it => it.url).map(it => ({ type: it.type, data: it.url.split(',', 2)[1] })) };
  }

  // open() for the + button; open({context: {repo, number, title, url, app, app_name}, shoot, onSent}) from testing
  function open(from) {
    ctx = from && from.context && from.context.repo ? from : null;
    kind = ctx ? 'bug' : null; busy = false;
    shots = shots || attacher($('rr-shot-row'), t => { $('rr-status').textContent = t; });
    shots.clear();
    $('rr-text').value = ''; $('rr-status').textContent = ''; $('rr-status').classList.remove('note');
    $('rr-form').hidden = false; $('rr-done').hidden = true;
    paint();
    $('rr-snap').textContent = 'Attach a screenshot of this screen';
    WzSheet.open($('report'));
    const first = ctx ? $('rr-text') : $('rr-kinds').querySelector('.rr-pick'); if (first) first.focus();
    return load().catch(() => {});
  }

  async function send(e) {
    e.preventDefault();
    if (busy) return;
    const text = $('rr-text').value.trim();
    if (!kind || text.length < 8) { $('rr-status').textContent = 'Say a little more (a sentence is enough).'; return; }
    busy = true; paint(); $('rr-status').textContent = 'Sending…'; $('rr-status').classList.add('note');
    clearTimeout(still); still = setTimeout(() => { if (busy) $('rr-status').textContent = 'Still working…'; }, 8000);
    const c = ctx && ctx.context;
    const body = { kind, text, device: device(), wizard_version: wizardVersion(),
      screenshots: shots && shots.list().length ? shots.payload() : undefined,
      ...(c ? { context: { repo: c.repo, number: c.number, title: c.title || '', app: c.app || '', app_name: c.app_name || '' }, app_name: c.app_name || undefined } : {}) };
    try {
      const r = await fetch('api/report', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const out = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(out.error || 'Something went wrong. Try again.');
      if (ctx) {   // from testing: straight back to where you were, with a small 'Sent'
        const sent = ctx.onSent; ctx = null;
        busy = false; WzSheet.close($('report'));
        if (typeof sent === 'function') try { sent(out); } catch (_) {}
      } else {
        $('rr-landed').textContent = (out.sent || SENT) + (out.warning ? ' ' + out.warning : '');
        $('rr-link').href = out.url || '#';
        $('rr-form').hidden = true; $('rr-done').hidden = false; $('rr-close').focus();
      }
      if (typeof api.onFiled === 'function') try { api.onFiled(out); } catch (_) {}
    } catch (err) { $('rr-status').classList.remove('note'); $('rr-status').textContent = err.message || 'Something went wrong. Try again.'; }
    finally { clearTimeout(still); busy = false; paint(); if (/^(Sending…|Still working…)$/.test($('rr-status').textContent)) $('rr-status').textContent = ''; }
  }

  const api = { open, onFiled: null, onUpdate: null, device, attacher, options: () => opts, load };
  window.WizardReporter = api;
  const wire = () => {
    $('rr-form').addEventListener('submit', send);
    $('rr-text').addEventListener('input', paint);
    for (const ev of ['paste', 'drop']) $('rr-text').addEventListener(ev, e => {   // paste or drop screenshots into the box
      const fs = shots ? shots.imagesOf(e.clipboardData || e.dataTransfer) : [];
      if (fs.length && opts && opts.screenshots) { e.preventDefault(); shots.add(fs); }
    });
    $('rr-cancel').onclick = () => WzSheet.close($('report'));
    $('rr-snap').onclick = () => snapshot();
    $('report').addEventListener('close', () => { ctx = null; });
    $('rr-close').onclick = () => WzSheet.close($('report'));
    const b = $('report-open'); if (b) b.onclick = () => open();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire); else wire();
})();
