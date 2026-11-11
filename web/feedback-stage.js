'use strict';
// WizardOS Tracker 0.26.5: Pending approval. Reports from the Feedback app by people outside the team wait in the
// private Feedback inbox; a team member approves them (a copy goes to wizard-os with triage + from-feedback, so the
// builder's triage step takes it like any report) or rejects them (Not planned). The page asks the Tracker's own
// server (api/feedback/pending, api/feedback/review); the server asks the Feedback relay with the person's own GitHub
// token, which never reaches this page. The stage shows only while something waits: it leads the strip and the list
// (Bugs: bug reports; Core features and App features: ideas).
// Uses app.js's helpers at call time (make, api, toast, askPop, smallBtn, when, render, cache, view, STAGE_INFO).
(() => {
  const S = { items: [], at: 0, busy: false, gone: new Set(), err: '' };
  const KIND_FOR = { bugs: 'bug', core: 'feature', apps: 'feature' };
  const INFO = 'Sent from the Feedback app by someone outside the team (or not signed in). A team member reads it first: Approve sends it to the builder queue (it lands in Sorting… like any report, marked From Feedback app); Reject closes it as Not planned. The sender sees the result in their Feedback app.';
  const forView = v => { const k = KIND_FOR[v]; return k ? S.items.filter(i => i.kind === k && !S.gone.has(i.number)) : []; };
  const repaint = () => { try { if (cache[view] && !document.querySelector('.bd-confirm')) render(cache[view]); } catch (_) {} };

  async function loadPending(force) {
    if (S.busy || (!force && Date.now() - S.at < 25000)) return;
    S.busy = true;
    try {
      const r = await api('api/feedback/pending' + (force ? '?refresh=1' : ''));
      const before = JSON.stringify(S.items.map(i => i.number));
      S.items = Array.isArray(r.items) ? r.items : []; S.at = Date.now(); S.err = '';
      for (const n of [...S.gone]) if (!S.items.some(i => i.number === n)) S.gone.delete(n);
      if (JSON.stringify(S.items.map(i => i.number)) !== before) repaint();
    } catch (err) {
      // not signed in, or not on the team: the stage simply isn't shown
      S.at = Date.now(); S.err = err.message || '';
      if (err.status === 401 || err.status === 403) { S.items = []; repaint(); }
    } finally { S.busy = false; }
  }

  function bins(v, list) {
    if (!forView(v).length) return list;
    if (typeof STAGE_INFO === 'object' && !STAGE_INFO.feedback) STAGE_INFO.feedback = INFO;
    return [{ key: 'feedback', word: 'Pending approval', groups: ['feedback'], info: 'feedback', tip: 'From the Feedback app: a team member approves or rejects it' }, ...list];
  }

  const ago = iso => { const t = Date.parse(iso || ''); if (isNaN(t)) return ''; const m = Math.round((Date.now() - t) / 60000);
    return m < 1 ? 'just now' : m < 60 ? m + ' min ago' : m < 1440 ? Math.round(m / 60) + ' h ago' : when(iso); };

  function fbChip(text, cls = '') { return make('span', 'bd-fbchip' + (cls ? ' ' + cls : ''), text); }

  function card(i) {
    const c = make('article', 'bd-card bd-card-calm bd-icard bd-fbcard'); c.dataset.feedback = String(i.number);
    const chips = make('p', 'bd-fbchips');
    chips.append(fbChip('From Feedback app', 'src'), fbChip(i.kind_word || (i.kind === 'bug' ? 'Bug' : 'Idea'), i.kind === 'bug' ? 'bug' : 'idea'));
    c.append(chips);
    c.append(make('h3', 'bd-title bd-fbtitle', i.title || 'Feedback'));
    const body = make('p', 'bd-fbtext', i.text || ''); c.append(body);   // the full text, plain (textContent)
    if (i.screenshots && i.screenshots.length) {
      const s = make('p', 'bd-fbshots');
      i.screenshots.forEach((u, n) => { const a = link('bd-shot wz-button secondary', u); a.textContent = `Screenshot ${i.screenshots.length > 1 ? n + 1 + ' ' : ''}↗`; a.title = 'Opens on GitHub (the team’s private media)'; s.append(a); });
      c.append(s);
    }
    const row = make('div', 'bd-act bd-fbact');
    const status = make('span', 'bd-why-s bd-fbstate'); status.setAttribute('role', 'status');
    const yes = smallBtn('Approve', b => askPop(b, 'Approve it? It goes to the builder queue, marked From Feedback app.', 'Approve', () => act(i, 'approve', c, status)));
    yes.classList.add('bd-mini-go');
    const no = smallBtn('Reject', b => askPop(b, 'Reject it? It closes as Not planned and the sender sees that.', 'Reject', () => act(i, 'reject', c, status)));
    row.append(yes, no, status); c.append(row);
    c.append(make('p', 'bd-hint', ['Feedback #' + i.number, i.submitter_word || (i.submitter === 'anonymous' ? 'Anonymous' : i.submitter), ago(i.created)].filter(Boolean).join(' · ')));
    return c;
  }

  async function act(i, action, c, status) {
    // the tap registers at once: the card dims and says what it is doing before any network
    c.classList.add('busy'); c.setAttribute('aria-busy', 'true');
    for (const b of c.querySelectorAll('button')) b.disabled = true;
    status.textContent = action === 'approve' ? 'Approving…' : 'Rejecting…';
    try {
      const r = await api('api/feedback/review', { number: i.number, action });
      S.gone.add(i.number); S.items = S.items.filter(x => x.number !== i.number);
      c.classList.add('leaving');
      setTimeout(repaint, 180);
      toast(r.message || (action === 'approve' ? 'Approved: sent to the builder queue.' : 'Rejected: not planned.'));
      if (action === 'approve') setTimeout(() => { try { loadPending(true); load(view, true); } catch (_) {} }, 1500);
    } catch (err) {
      c.classList.remove('busy'); c.removeAttribute('aria-busy');
      for (const b of c.querySelectorAll('button')) b.disabled = false;
      status.textContent = err.message || 'Something went wrong. Try again.';
    }
  }

  // a small 'From Feedback app' chip on any card whose issue carries the from-feedback label
  function chip(i) {
    const on = i && (i.from_feedback || (Array.isArray(i.labels) && i.labels.some(l => String(l).toLowerCase() === 'from-feedback')));
    if (!on) return null;
    const t = fbChip('From Feedback app', 'src small'); t.title = 'Sent from the Feedback app, approved by the team';
    return t;
  }

  window.FeedbackStage = { load: loadPending, items: forView, bins, card, chip, _state: S };
})();
