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
  let opts = null, updates = null, kind = null, busy = false, shot = null;
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
    $('rr-shot-l').hidden = !!shot; $('rr-shot-on').hidden = !shot;
    if (shot) $('rr-shot-img').src = shot.url;
    $('rr-auto').textContent = 'Adds: ' + [wizardVersion() && 'WizardOS ' + wizardVersion(), device()].filter(Boolean).join(' · ');
    $('rr-go').disabled = busy || !(kind && $('rr-text').value.trim().length >= 8);
    $('rr-go').textContent = 'Send';
  }

  async function load() {
    const [o, up] = await Promise.allSettled([getJSON('api/report'), getJSON(UPDATES)]);
    if (o.status === 'fulfilled') opts = o.value;
    if (up.status === 'fulfilled') updates = up.value;
    paint();
  }

  function takeShot(file) {
    if (!file) return;
    const max = (opts && opts.shot_max) || 4 * 1024 * 1024;
    if (!/^image\/(png|jpeg|webp|gif)$/.test(file.type)) { $('rr-status').textContent = 'Use a PNG, JPEG, WebP or GIF image.'; return; }
    if (file.size > max) { $('rr-status').textContent = 'That screenshot is too big (4 MB max).'; return; }
    const r = new FileReader();
    r.onload = () => { shot = { type: file.type, url: String(r.result) }; $('rr-status').textContent = ''; paint(); };
    r.readAsDataURL(file);
  }

  function open() {
    kind = null; busy = false; shot = null;
    $('rr-text').value = ''; $('rr-status').textContent = ''; $('rr-shot').value = '';
    $('rr-form').hidden = false; $('rr-done').hidden = true;
    paint();
    WzSheet.open($('report'));
    const first = $('rr-kinds').querySelector('.rr-pick'); if (first) first.focus();
    return load().catch(() => {});
  }

  async function send(e) {
    e.preventDefault();
    if (busy) return;
    const text = $('rr-text').value.trim();
    if (!kind || text.length < 8) { $('rr-status').textContent = 'Say a little more (a sentence is enough).'; return; }
    busy = true; paint(); $('rr-status').textContent = 'Sending…';
    const body = { kind, text, device: device(), wizard_version: wizardVersion(),
      screenshot: shot ? { type: shot.type, data: shot.url.split(',', 2)[1] } : undefined };
    try {
      const r = await fetch('api/report', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const out = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(out.error || 'Something went wrong. Try again.');
      $('rr-landed').textContent = (out.sent || SENT) + (out.warning ? ' ' + out.warning : '');
      $('rr-link').href = out.url || '#';
      $('rr-form').hidden = true; $('rr-done').hidden = false; $('rr-close').focus();
      if (typeof api.onFiled === 'function') try { api.onFiled(out); } catch (_) {}
    } catch (err) { $('rr-status').textContent = err.message; }
    finally { busy = false; paint(); if ($('rr-status').textContent === 'Sending…') $('rr-status').textContent = ''; }
  }

  const api = { open, onFiled: null, onUpdate: null, device };
  window.WizardReporter = api;
  const wire = () => {
    $('rr-form').addEventListener('submit', send);
    $('rr-text').addEventListener('input', paint);
    $('rr-text').addEventListener('paste', e => {   // paste a screenshot straight into the box
      const f = [...((e.clipboardData && e.clipboardData.files) || [])].find(x => /^image\//.test(x.type));
      if (f && opts && opts.screenshots) { e.preventDefault(); takeShot(f); }
    });
    $('rr-shot').addEventListener('change', e => takeShot(e.target.files && e.target.files[0]));
    $('rr-shot-x').onclick = () => { shot = null; $('rr-shot').value = ''; paint(); };
    $('rr-cancel').onclick = () => WzSheet.close($('report'));
    $('rr-close').onclick = () => WzSheet.close($('report'));
    const b = $('report-open'); if (b) b.onclick = () => open();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire); else wire();
})();
