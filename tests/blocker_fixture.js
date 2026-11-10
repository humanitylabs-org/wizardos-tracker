// Tracker 0.24.5 fixture: every card whose blocker is an update shows the Update button right next to the blocker
// text (reviewer or not, card and pop-up bar), and a running update shows its progress panel there instead.
(() => {
  const now = Date.now();
  const A = (id, name, repo, update) => ({ id, name, repo: 'humanitylabs-org/' + repo, version: '1.0.0', latest: '1.1.0', update, commit: '', source: 'standard', release: { source: 'standard', repo: 'humanitylabs-org/' + repo, commit: 'x' } });
  catalog = { apps: [A('movies', 'Movies', 'movies', true), A('wizard-notes', 'Wizard Notes', 'wizard-notes', true), A('wizard-calendar', 'Calendar', 'wizard-calendar', false)] };
  catalogAt = now;
  takeSwitches({ locked: false, switches: [] });
  appSw['wizard-notes'] = { at: now, ok: true, status: 200, switches: [] };
  appSw['wizard-calendar'] = { at: now, ok: true, status: 200, switches: [{ id: 'compact-header', name: 'Compact', on: false, issues: ['humanitylabs-org/wizard-calendar#20'] }] };
  const item = (repo, n, extra) => Object.assign({ id: `humanitylabs-org/${repo}#${n}`, repo: `humanitylabs-org/${repo}`, number: n,
    title: `${repo} #${n}`, group: 'test', kind: 'feature', category: 'app', can_review: true, labels: ['ready-to-test'],
    created_at: new Date(now - 864e5).toISOString(), delivers: [{ repo: `humanitylabs-org/${repo}`, number: n + 100 }], open_prs: 0 }, extra);
  const place = (repo, text) => ({ switch_how: text, switch_place: { kind: 'app', text, repo: 'humanitylabs-org/' + repo } });
  const cases = {
    onbox_no: item('movies', 15, place('movies', 'Settings › Poster wall')),
    app_newer: item('wizard-notes', 19, { switch_how: 'wizard-notes:friendly-phone', switch_place: { kind: 'other', text: 'x' } }),
    other_reviewer: item('movies', 16, Object.assign(place('movies', 'Settings › Poster wall'), { can_review: false, review_rule: 'James checks this one (he filed it)' })),
    not_blocked: item('wizard-calendar', 20, place('wizard-calendar', 'Settings › Compact')),
  };
  const yes = { state: 'yes', text: 'On your Wizard ✓', fix: null, apps: [] }, no = { state: 'no', text: 'Not on your Wizard yet', fix: 'Update Movies', apps: ['movies'] };
  for (const [k, i] of Object.entries(cases)) { onbox.set(i.id, { at: now, key: factsKey(), v: /onbox_no|other_reviewer/.test(k) ? no : yes }); adoptSwitch(i); }
  const out = {};
  const look = (k, i) => {
    const card = itemCard(i), bl = card.querySelector('.bd-blocker');
    appBack = { item: i, name: 'X', id: 'x', at: null }; modalBar();
    const pb = el('appmodal-try').querySelector('.bd-blocker');
    out[k] = { blocker: !!bl, text: bl ? bl.querySelector('.bd-why-s').textContent : '', btn: bl ? (bl.querySelector('button') || {}).textContent : '',
      popup: !!pb, toggle: !!card.querySelector('.bd-try'), panel: !!card.querySelector('.bd-upd') };
  };
  for (const [k, i] of Object.entries(cases)) look(k, i);
  newRun('movies', 'Movies', '1.1.0', cases.onbox_no, null);
  look('running', cases.onbox_no);
  runs.clear(); appBack = null;
  return out;
})()
