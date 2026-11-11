// Tracker 0.27.0 fixture (run in the real page by tests/test_027.py)
(async () => {
  const now = Date.now(), sleep = ms => new Promise(r => setTimeout(r, ms));
  const A = (id, name, repo) => ({ id, name, repo: 'humanitylabs-org/' + repo, version: '1.0.0', commit: '', source: 'standard' });
  catalog = { apps: [A('wizard-notes', 'Notes', 'wizard-notes'), A('movies', 'Movies', 'movies')] };
  catalogAt = now;
  takeSwitches({ locked: false, switches: [{ id: 'miguel/send-and-go', name: 'Send and go', on: false, kind: 'core', issues: [] }] });
  appSw['wizard-notes'] = { at: now, ok: true, status: 200, switches: [] };
  appSw['movies'] = { at: now, ok: true, status: 200, switches: [] };
  const item = (repo, n, extra) => Object.assign({ id: `humanitylabs-org/${repo}#${n}`, repo: `humanitylabs-org/${repo}`, number: n,
    url: `https://github.com/humanitylabs-org/${repo}/issues/${n}`, title: `${repo} #${n}`, group: 'test', kind: 'feature', category: 'app',
    can_review: true, labels: ['ready-to-test'], created_at: new Date(now - 864e5).toISOString(),
    delivers: [{ repo: `humanitylabs-org/${repo}`, number: n + 100, sha: '' }], open_prs: 0,
    waiting_on: { who: ['Miguel'], kind: 'person' } }, extra);
  const yes = { state: 'yes', text: 'On your Wizard ✓', fix: null, apps: [] };
  const unreleased = { state: 'no', text: 'Not on your Wizard yet', fix: 'Not released yet', apps: [] };
  const cases = {
    noswitch: item('wizard-notes', 18, { no_switch: true, switch: null, switch_how: null, switch_place: null, steps: 'replace the hand-made override with the README snippet; Notes lists the synced notes' }),
    bugfix: item('movies', 30, { kind: 'bug', switch_how: 'Settings › Poster wall', switch_place: { kind: 'app', text: 'Settings › Poster wall', repo: 'humanitylabs-org/movies' }, steps: 'open Movies and scroll' }),
    withswitch: item('wizard-ux', 900, { category: 'core', switch: 'miguel/send-and-go' }),
    nextrel: item('wizard-ux', 1256, { category: 'core', switch: 'miguel/send-and-go' }),
    released: item('wizard-ux', 1257, { category: 'core', switch: 'miguel/send-and-go' }),
  };
  for (const [k, i] of Object.entries(cases)) { onbox.set(i.id, { at: now, key: factsKey(), v: k === 'nextrel' ? unreleased : yes }); adoptSwitch(i); i.nextrel = comingNext(i); }
  const out = {};
  const btnTexts = r => [...r.querySelectorAll('button')].map(b => b.textContent.trim()).filter(Boolean);
  for (const [k, i] of Object.entries(cases)) {
    const card = itemCard(i);
    appBack = { item: i, name: 'Notes', id: 'wizard-notes', at: null };
    modalBar();
    out[k] = { toggle: !!card.querySelector('.bd-try'), popupToggle: !!el('appmodal-try').querySelector('.bd-try'),
      more: !!card.querySelector('.bd-more'), popupMore: !!el('appmodal-bar').querySelector('.bd-more'),
      howto: (card.querySelector('.bd-howto') || {}).textContent || '', nextrel: !!i.nextrel, waiting: !!card.querySelector('.bd-waiton'),
      text: card.textContent, buttons: btnTexts(card.querySelector('.bd-act') || card) };
    if (k === 'withswitch') out.barButtons = btnTexts(el('appmodal-bar'));
  }
  out.nextrel.group = (sectionsOf('core').find(([g]) => g === 'nextrel') || [])[1];
  // the ... menu
  let c1 = itemCard(cases.withswitch); document.body.append(c1);
  c1.querySelector('.bd-more').click();
  out.menu = [...el('pop').querySelectorAll('.bd-menu-i')].map(x => x.textContent.trim());
  unpop(); c1.remove();
  c1 = itemCard(Object.assign({}, cases.bugfix, { shipped: true, can_review: true })); document.body.append(c1);
  c1.querySelector('.bd-more').click();
  out.bugmenu = [...el('pop').querySelectorAll('.bd-menu-i')].map(x => x.textContent.trim());
  unpop(); c1.remove();
  // busy feedback: spinner + disabled at once, 'Still working…' after 8 s, restored after
  const bb = smallBtn('Works', () => {}); document.body.append(bb);
  const end = busyOn(bb);
  const busy = { disabled: bb.disabled, spinner: bb.classList.contains('bd-busy'), ariaBusy: bb.getAttribute('aria-busy') === 'true' };
  await sleep(8300);
  busy.still = !!(bb.nextElementSibling && bb.nextElementSibling.textContent === 'Still working…');
  end(); busy.restored = !bb.disabled && !bb.classList.contains('bd-busy') && !document.querySelector('.bd-stillwork');
  out.busy = busy;
  // Report something else on top of the app pop-up
  let sent = null;
  const realFetch = window.fetch;
  window.fetch = async (u, init) => {
    const s = String(u);
    if (/api\/report$/.test(s) && init && init.method === 'POST') { sent = JSON.parse(init.body); return new Response(JSON.stringify({ sent: 'Sent.', url: 'https://github.com/x/y/issues/1' }), { status: 201, headers: { 'Content-Type': 'application/json' } }); }
    if (/api\/report$/.test(s)) return new Response(JSON.stringify({ screenshots: true, shot_max: 4194304, shot_count: 6, prompts: {} }), { status: 200 });
    return realFetch(u, init);
  };
  const d = el('appmodal');
  appBack = { item: cases.noswitch, name: 'Notes', id: 'wizard-notes', at: null };
  modalBar(); d.showModal();
  el('appmodal-bar').querySelector('.bd-more').click();
  [...el('pop').querySelectorAll('.bd-menu-i')][0].click();
  await sleep(400);
  const rep = { bothOpen: d.open && el('report').open, ctx: el('rr-ctx').textContent, snapShown: !el('rr-snap-row').hidden };
  el('rr-text').value = 'The header overlaps the list on my phone.'; el('rr-text').dispatchEvent(new Event('input', { bubbles: true }));
  el('rr-form').requestSubmit();
  await sleep(500);
  rep.sentBody = sent; rep.popupStillOpen = d.open; rep.reportOpen = el('report').open;
  rep.toast = (document.getElementById('bd-toast') || {}).textContent || '';
  out.report = rep;
  window.fetch = realFetch;
  d.close(); appBack = null;
  return out;
})()
