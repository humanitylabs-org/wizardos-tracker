// Tracker 0.55.1 fixture (run in the real page by tests/test_0551.py): the WizardOS update while Wizard is busy. The
// box is stood in for by a small copy of the App Manager's _updates route (wam/cli.py + wam/updates.py): while work is
// running, POST {action: 'apply'} starts nothing and answers started:false + waiting + waiting_for; {when_idle: true}
// queues it; {anyway: true} starts it; `failed` / `failure_reason` keep describing the LAST install. Nothing is installed.
(async () => {
  const timer = window.setTimeout;
  window.setTimeout = (f, ms, ...a) => timer(f, ms === 3000 ? 30 : ms, ...a);   // followOS asks the box every 3 s: quicker here
  const nap = ms => new Promise(r => timer(r, ms));
  const until = async (f, ms = 5000) => { for (const end = Date.now() + ms; Date.now() < end; await nap(15)) if (f()) return true; return false; };
  const OLD = 'wizard-agent-service: update to release source failed';
  const BASE = { channel: 'latest', installed: '0.3.350', latest: '0.3.362', stable: '0.3.340', update_available: true, installing: false, interrupted: false,
    failed: true, failure_reason: OLD, retry_target: '0.3.362', superseded: false, quick: false, waits_for_work: true, when_idle: null };
  const WORK = ['A chat reply', 'Replying in “Mac app trial”', 'A helper agent', 'A scheduled job'].map(name => ({ kind: 'agent', name, source: 'work', stops_at: 'hermes', since: null }));
  const QUEUED = { target: '0.3.362', when_idle: true, requested_at: '2026-11-25T03:00:00Z', ask_at: 4102444800, quiet: false, asked: false };
  const box = { st: null, work: [], posts: [], gets: 0, started: 0 };
  const status = () => ({ ...box.st, waiting_for: box.work });
  const answer = b => {
    if (b.action === 'when_idle_cancel') { box.st.when_idle = null; return status(); }
    if (box.work.length && !b.anyway) {
      if (!b.when_idle) return { ...status(), started: false, waiting: true };
      box.st.when_idle = { ...QUEUED };
      return { ...status(), started: false, note: 'WizardOS updates as soon as Wizard has finished.' };
    }
    box.started++;
    return { ...status(), started: true };   // the status from before the start, as updates.apply answers
  };
  window.fetch = (u, init) => {
    if (!String(u).includes('store-install/_updates')) return new Promise(() => {});   // nothing else answers
    let body;
    if (init && init.method === 'POST') { const b = JSON.parse(init.body); box.posts.push(b); body = answer(b); }
    else { box.gets++; body = status(); }
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }));
  };
  const calls = [];
  loadCatalog = async () => catalog;
  resumeRuns = async () => {};
  checkVersion = async () => {};
  updateApp_ = async id => { calls.push(id); const a = fresh(id), r = newRun(id, a.name, a.latest); await nap(60); a.update = false; runEnd(r, true); };
  const reset = (st, work, apps) => {
    unpop(); runs.clear(); wizBusy.clear(); wizFail = {}; localStorage.clear(); queue = null; calls.length = 0;
    box.st = { ...BASE, ...(st || {}) }; box.work = work || []; box.posts = []; box.gets = 0; box.started = 0;
    catalog = { apps: apps || [] }; updates = status(); selfUpdate();
  };
  const tx = n => n ? n.textContent.replace(/\s+/g, ' ').trim() : null;
  const pill = () => { const p = el('selfupd').querySelector('.bd-updpill'); return p ? { text: tx(p.querySelector('.bd-updpill-t')), btn: tx(el('selfupd-go')), bad: p.classList.contains('bad') } : null; };
  const asked = () => { const p = el('pop'); return p.hidden ? null : { text: tx(p.querySelector('span')), btns: [...p.querySelectorAll('button')].map(tx) }; };
  const tap = t => [...el('pop').querySelectorAll('button')].find(b => tx(b) === t).click();
  const panels = () => [...el('selfupd').querySelectorAll('.bd-upd')].map(p => [p.dataset.upd, p.className.replace('bd-upd ', ''), tx(p.querySelector('.bd-upd-why'))]);
  const run = () => { const r = runs.get('os'); return r ? [r.state, r.step, r.reason] : null; };
  const snap = () => ({ posts: box.posts.slice(), started: box.started, ask: asked(), pill: pill(), panels: panels(), run: run(), osrun: store.get('board.osrun') });
  const busyTap = async () => { el('selfupd-go').click(); const c = asked(); tap('Update'); await until(() => asked() && asked().btns.includes('Update anyway')); return c; };
  const out = {};

  // 1. the owner's tap: the last update failed two days ago, Wizard is in the middle of a chat reply, he taps Try again
  reset({}, WORK);
  out.before = pill();
  out.confirm = await busyTap();
  out.busy = snap();
  out.inView = (() => { const r = el('pop').getBoundingClientRect(); return r.width > 0 && r.top >= 0 && r.bottom <= innerHeight; })();

  // 2. 'Update when it finishes': queued on the box, the pill says so, with Cancel
  tap('Update when it finishes');
  await until(() => box.posts.length === 2 && pill() && pill().btn === 'Cancel');
  out.later = snap();
  store.set('board.updopen', true); selfUpdate();   // the full list says the same on WizardOS's own line
  out.laterOpen = { rows: [...el('selfupd').querySelectorAll('.bd-selfupd-row')].map(r => [r.dataset.updRow, tx(r.querySelector('button'))]),
    why: tx(el('selfupd').querySelector('[data-upd-why="os"]')), all: tx(el('selfupd-go')) };
  store.set('board.updopen', false); selfUpdate();

  // 3. Cancel takes it off the box again
  el('selfupd-go').click();
  await until(() => box.posts.length === 3 && pill() && pill().btn !== 'Cancel');
  out.cancelled = { post: box.posts[2], pill: pill(), waits: box.st.when_idle };

  // 4. a page that loads while the box has it queued (asked in Settings, or before a reload) says so too
  reset({ when_idle: { ...QUEUED } }, WORK);
  out.loaded = pill();
  reset({ when_idle: { ...QUEUED }, installing: true }, WORK);   // it has begun: no longer 'waits'
  out.loadedInstalling = { waits: osWaits(), pill: pill() };
  // ...and Update (all) leaves the waiting WizardOS update alone (no failure on the box here: only the waiting holds it back)
  reset({ when_idle: { ...QUEUED }, failed: false, failure_reason: null, retry_target: null }, WORK, [{ id: 'a1', name: 'Alpha', version: '1', latest: '2', update: true, status: 'running', release: { version: '2' } }]);
  out.withApp = pill();
  el('selfupd-go').click();
  await until(() => calls.length && !draining && ![...runs.values()].some(r => r.state === 'running'));
  out.withAppDone = { calls: calls.slice(), posts: box.posts.slice() };

  // ...and an Update all that reaches a WizardOS update while Wizard is busy asks too; WizardOS is not counted as updated
  reset({ failed: false, failure_reason: null, retry_target: null }, WORK, [{ id: 'a1', name: 'Alpha', version: '1', latest: '2', update: true, status: 'running', release: { version: '2' } }]);
  out.allPill = pill();
  let counted = null; const save = queueSave; queueSave = () => { if (queue) counted = queue.done.slice(); save(); };
  el('selfupd-go').click();
  await until(() => asked() && asked().btns.includes('Update anyway') && !draining);
  queueSave = save;
  out.all = { calls: calls.slice(), posts: box.posts.slice(), ask: asked().text, run: run(), counted, left: store.get('board.updq'), failed: store.get('board.updq.last'), pill: pill() };
  unpop();

  // 5. 'Update anyway': the box starts it. Its next answers still carry the OLD failure (nothing has run yet), then the
  //    install runs (the old receipt still says failed while it does), then the release is installed
  reset({}, WORK);
  await busyTap();
  tap('Update anyway');
  await until(() => box.gets >= 3);
  out.anywayStale = snap();                       // three answers with the old failure: still running, not failed
  Object.assign(box.st, { installing: true, failure_reason: 'install-failed', retry_target: null });
  const g = box.gets; await until(() => box.gets >= g + 3);
  out.anywayInstalling = snap();
  Object.assign(box.st, { installing: false, failed: false, failure_reason: null, installed: '0.3.362', update_available: false });
  await until(() => run() && run()[0] !== 'running');
  out.anywayDone = snap();

  // 6. followOS on its own: what counts as this run's failure
  const follow = async (old, ageMs, change) => {
    const r = newRun('os', 'WizardOS', '0.3.362'); r.at = Date.now() - ageMs;
    const g0 = box.gets, p = followOS(r, '0.3.350', old).then(() => 'done', e => e.message);
    if (change) { await until(() => box.gets >= g0 + 2); const mid = run()[0]; change(box.st); return [mid, await p, box.gets - g0 > 2]; }
    return [await p, box.gets - g0];
  };
  reset({}, []); const sig = osFailSig(updates);
  out.graceOver = await follow(sig, 91000);                                   // the same old failure, 91 s after the tap: failed, as before
  reset({}, []); out.noMemory = await follow(undefined, 0);                   // nothing remembered (an older page's run): failed at once, as before
  reset({ failure_reason: 'Not enough disk space' }, []);
  out.newReason = await follow(sig, 0);                                       // a different reason: this run's, at once
  reset({ failed: false, failure_reason: null, interrupted: true }, []);
  out.interrupted = await follow(sig, 0);
  reset({ installing: true }, []);
  out.failedAfterInstalling = await follow(sig, 0, st => { st.installing = false; });   // it ran, then the same reason again: this run's, at once

  // 7. the question itself: up to three names, the rest counted; none known still asks
  reset({}, []);
  osBusyAsk(null, null, { waiting_for: WORK.slice(0, 1) }); out.askOne = asked().text;
  osBusyAsk(null, null, { waiting_for: [] }); out.askNone = asked().text;
  unpop();
  return out;
})()
