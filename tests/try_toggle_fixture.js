// Tracker 0.24.2 regression fixture (run in the real page by tests/test_0242.py): render Human review cards and the
// app pop-up bar for items with a core switch, app switches, and an item needing an update; report the toggles.
(() => {
  const now = Date.now();
  const A = (id, name, repo) => ({ id, name, repo: 'humanitylabs-org/' + repo, version: '1.0.0', commit: '', source: 'standard' });
  catalog = { apps: [A('wizard-calendar', 'Calendar', 'wizard-calendar'), A('messenger', 'Messenger', 'wizard-messenger'), A('movies', 'Movies', 'movies')] };
  catalogAt = now;
  // The box catalog: one core switch, and (App Manager #574/#575) Messenger's own switch as an app row
  takeSwitches({ locked: false, switches: [
    { id: 'miguel/send-and-go', name: 'Send and go', on: false, kind: 'core', issues: [] },
    { id: 'messenger:drafts-first', name: 'Drafts at top', on: false, kind: 'app', issues: ['humanitylabs-org/wizard-messenger#133'] }] });
  appSw['wizard-calendar'] = { at: now, ok: true, status: 200, switches: [
    { id: 'compact-header', name: 'Compact top bar', on: false, issues: ['humanitylabs-org/wizard-calendar#20'] }] };
  appSw['movies'] = { at: now, ok: true, status: 200, switches: [] };
  const item = (repo, n, extra) => Object.assign({ id: `humanitylabs-org/${repo}#${n}`, repo: `humanitylabs-org/${repo}`, number: n,
    title: `${repo} #${n}`, group: 'test', kind: 'feature', category: 'app', can_review: true, labels: ['ready-to-test'],
    created_at: new Date(now - 864e5).toISOString(), delivers: [{ repo: `humanitylabs-org/${repo}`, number: n + 100 }], open_prs: 0 }, extra);
  const place = (repo, text) => ({ switch_how: text, switch_place: { kind: 'app', text, repo: 'humanitylabs-org/' + repo } });
  const cases = {
    core: item('wizard-ux', 900, { category: 'core', switch: 'miguel/send-and-go' }),
    app: item('wizard-calendar', 20, place('wizard-calendar', 'Settings › Compact top bar')),
    app_catalog: item('wizard-messenger', 133, place('wizard-messenger', 'Settings › Drafts at top')),
    needs_update: item('movies', 15, place('movies', 'Settings › Poster wall')),
    app_unreachable: item('wizard-calendar', 21, place('wizard-calendar', 'Settings › Trackpad day swipe')),
  };
  const ob = { state: 'yes', text: 'On your Wizard ✓', fix: null, apps: [] };
  for (const [k, i] of Object.entries(cases)) {
    onbox.set(i.id, { at: now, key: factsKey(), v: k === 'needs_update' ? { state: 'no', text: 'Not on your Wizard yet', fix: 'Update Movies', apps: ['movies'] } : ob });
    adoptSwitch(i);
  }
  const out = {};
  const look = (k, i) => {
    const card = itemCard(i), t = card.querySelector('.bd-try');
    appBack = { item: i, name: 'X', id: 'x', at: null };
    modalBar();
    const p = el('appmodal-try').querySelector('.bd-try');
    out[k] = { card: !!t, popup: !!p, cardGrey: !!(t && t.getAttribute('aria-disabled') === 'true'), popupGrey: !!(p && p.getAttribute('aria-disabled') === 'true'),
      cardWhy: (card.querySelector('.bd-why-s') || {}).textContent || '', popupWhy: (el('appmodal-try').querySelector('.bd-try-why') || {}).textContent || '',
      appSwitch: (t && t.dataset.appSwitch) || '', coreSwitch: (t && t.dataset.switch) || '' };
  };
  for (const [k, i] of Object.entries(cases)) {
    if (k === 'app_unreachable') appSw['wizard-calendar'] = { at: now, ok: false, status: 403, switches: [] };   // 0.24.1's bug
    look(k, i);
  }
  appBack = null;
  return out;
})()
