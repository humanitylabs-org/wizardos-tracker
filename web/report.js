'use strict';
// WizardOS Reporter 0.20: the one 'Report or request' form. Its own module (with app/report.py and /api/report) so it
// can become a standalone app any owner uses. Step 1: Something's broken / I'd like something new. Step 2: What's it
// about? (WizardOS itself in plain names, then each app installed on this Wizard by name, or Not sure; the server maps
// the pick to a repo). Step 3: one text box with the right prompt, plus an 'update first' warning for bugs when this
// Wizard isn't on the latest WizardOS. Send files it (version and device filled in) and says where it landed.
// Host hooks: WizardReporter.onFiled(result) and WizardReporter.onUpdate(button) (optional).
(() => {
  const $ = id => document.getElementById(id);
  const mk = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
  const STORE_DATA = '/wizard-os-home/store-data/', UPDATES = '/wizard-os-home/store-install/_updates';
  const KINDS = [['bug', 'Something’s broken'], ['feature', 'I’d like something new']];
  let opts = null, apps = [], updates = null, kind = null, about = null, busy = false;
  const getJSON = u => fetch(u, { credentials: 'same-origin', cache: 'no-store' }).then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)));

  // 'Mac · Chrome', 'iPhone · Safari', plus 'in the Wizard app' when hosted by the shell
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

  function picks(box, items, current, onPick) {
    box.replaceChildren(...items.map(([key, name]) => {
      const b = mk('button', 'rr-pick', name); b.type = 'button'; b.setAttribute('role', 'radio');
      b.setAttribute('aria-checked', String(key === current)); b.dataset.key = key;
      b.onclick = () => onPick(key);
      return b;
    }));
  }
  function appOf(key) { return key && key.startsWith('app:') ? apps.find(a => 'app:' + a.id === key) : null; }

  function paint() {
    const p = (opts && opts.prompts) || {};
    picks($('rr-kinds'), KINDS, kind, k => { kind = k; paint(); $('rr-s2').hidden || (about && $('rr-text').focus()); });
    $('rr-kinds').querySelectorAll('.rr-pick').forEach(b => b.classList.add('rr-kind'));
    $('rr-s2').hidden = !kind;
    const core = ((opts && opts.core) || []).map(t => [t.key, t.name]);
    picks($('rr-core'), core, about, pick);
    $('rr-apps-h').hidden = $('rr-apps').hidden = !apps.length;
    picks($('rr-apps'), apps.map(a => ['app:' + a.id, a.name]), about, pick);
    picks($('rr-unsure'), [['unsure', 'Not sure']], about, pick);
    $('rr-s3').hidden = !(kind && about);
    const pr = p[kind] || {};
    $('rr-ask').textContent = pr.label || 'Tell us';
    $('rr-text').placeholder = pr.placeholder || '';
    const w = $('rr-warn');
    w.hidden = !(kind === 'bug' && updates && updates.update_available);
    if (!w.hidden) {
      w.replaceChildren(document.createTextNode(`This Wizard runs WizardOS ${updates.installed}; ${newest(updates)} is out. Update first: it may already be fixed. `));
      if (typeof api.onUpdate === 'function') { const b = mk('button', 'bd-mini', 'Update'); b.type = 'button'; b.onclick = () => api.onUpdate(b); w.append(b); }
    }
    const a = appOf(about);
    $('rr-auto').textContent = 'Adds: ' + [wizardVersion() && 'WizardOS ' + wizardVersion(), a && a.version && `${a.name} ${a.version}`, device()].filter(Boolean).join(' · ');
    $('rr-go').disabled = busy || !(kind && about && $('rr-text').value.trim().length >= 8);
    $('rr-go').textContent = kind === 'feature' ? 'Send request' : kind === 'bug' ? 'Send report' : 'Send';
  }
  function pick(k) { const first = !about; about = k; paint(); if (first) $('rr-text').focus(); }

  async function load() {
    const [o, inst, up] = await Promise.allSettled([getJSON('api/report'), getJSON(STORE_DATA + 'wizard/v1/installed-apps'), getJSON(UPDATES)]);
    if (o.status === 'fulfilled') opts = o.value;
    if (up.status === 'fulfilled') updates = up.value;
    const core = new Set(((opts && opts.core_repos) || []).map(r => String(r).toLowerCase()));
    if (inst.status === 'fulfilled') {
      const seen = new Set();
      apps = (inst.value.wam || []).filter(w => w && w.id && w.name && !core.has(String(w.repo || '').split('/').pop().toLowerCase()) && !seen.has(w.id) && seen.add(w.id))
        .map(w => ({ id: w.id, name: w.name, repo: w.repo || '', version: w.version || '' }))
        .sort((a, b) => a.name.localeCompare(b.name));
    }
    paint();
  }

  function open() {
    kind = null; about = null; busy = false;
    $('rr-text').value = ''; $('rr-status').textContent = '';
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
    if (!kind || !about || text.length < 8) { $('rr-status').textContent = text.length < 8 ? 'Say a little more (a sentence is enough).' : 'Pick both choices above.'; return; }
    busy = true; paint(); $('rr-status').textContent = 'Sending…';
    const a = appOf(about);
    const body = { kind, about, text, device: device(), wizard_version: wizardVersion(),
      app_repo: a ? a.repo : undefined, app_name: a ? a.name : undefined, app_version: a ? a.version : undefined,
      apps: about === 'unsure' ? apps.map(x => ({ id: x.id, name: x.name, repo: x.repo })) : undefined };
    try {
      const r = await fetch('api/report', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const out = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(out.error || 'Something went wrong. Try again.');
      $('rr-landed').textContent = out.landed + (out.warning ? '. ' + out.warning : '');
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
    $('rr-cancel').onclick = () => WzSheet.close($('report'));
    $('rr-close').onclick = () => WzSheet.close($('report'));
    const b = $('report-open'); if (b) b.onclick = () => open();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire); else wire();
})();
