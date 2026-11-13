// Tracker 0.33.0 fixture (run in the real page by tests/test_033.py)
(async () => {
  const now = Date.now();
  const A = (id, name, repo, extra) => Object.assign({ id, name, repo: 'humanitylabs-org/' + repo, version: '1.0.0', commit: '', source: 'standard' }, extra);
  catalog = { apps: [A('wizard-calendar', 'Calendar', 'wizard-calendar'), A('messenger', 'Messenger', 'wizard-messenger'),
    A('wizard-notes', 'Notes', 'wizard-notes', { update: true })] };
  catalogAt = now;
  takeSwitches({ locked: false, switches: [{ id: 'miguel/send-and-go', name: 'Send and go', on: false, kind: 'core', issues: [] }] });
  appSw['wizard-calendar'] = { at: now, ok: true, status: 200, switches: [
    { id: 'drag-events', name: 'Drag to move and resize', on: false, description: 'Drag events in Day and Week.', issues: [] }] };
  appSw['messenger'] = { at: now, ok: true, status: 200, switches: [
    { id: 'line-photo-groups', name: 'LINE photo groups', on: false, issues: ['humanitylabs-org/wizard-messenger#188'] }] };
  appSw['wizard-notes'] = { at: now, ok: true, status: 200, switches: [] };
  const item = (repo, n, extra) => Object.assign({ id: `humanitylabs-org/${repo}#${n}`, repo: `humanitylabs-org/${repo}`, number: n,
    url: `https://github.com/humanitylabs-org/${repo}/issues/${n}`, title: `${repo} #${n}`, group: 'test', kind: 'feature', category: 'app',
    can_review: true, labels: ['ready-to-test'], created_at: new Date(now - 864e5).toISOString(),
    delivers: [{ repo: `humanitylabs-org/${repo}`, number: n + 100, sha: '' }], open_prs: 0,
    waiting_on: { who: ['Miguel'], kind: 'person' } }, extra);
  const yes = { state: 'yes', text: 'On your Wizard ✓', fix: null, apps: [] };
  const unknown = { state: 'unknown', text: 'Can’t tell', fix: null, apps: [] };
  const cases = {
    // no Switch line; the steps name the app switch in quotes (wizard-calendar#19)
    calendar: item('wizard-calendar', 19, { switch: null, switch_how: null, switch_place: null,
      steps: 'Open Calendar, go to Settings › Try changes and turn on "Drag to move and resize". 2. In Week, drag one of your events down an hour.' }),
    // 'Settings › LINE photo groups' (wizard-messenger#188): the app lists the switch for the issue
    settings: item('wizard-messenger', 188, { switch: null, switch_how: 'Settings › LINE photo groups',
      switch_place: { kind: 'app', text: 'Settings › LINE photo groups', repo: 'humanitylabs-org/wizard-messenger' },
      steps: 'Open Messenger, go to Settings and turn LINE photo groups On. Open a LINE chat, attach 3 photos.' }),
    // steps say turn on, the app has no such switch yet and has an update waiting (wizard-notes#33)
    implied: item('wizard-notes', 33, { switch: null, switch_how: null, switch_place: null,
      steps: 'Update Notes, then turn on gear > Try changes > Images in Read view. Open a note with an image.' }),
    // a core item whose hand-over names the shell tweak in words only
    corenamed: item('wizard-ux', 1400, { category: 'core', switch: null, switch_how: 'Settings › Try new features › Send and go', switch_place: null, steps: '' }),
    // merged without a switch, on this Wizard (wizard-ux#1308)
    live: item('wizard-ux', 1308, { category: 'core', switch: null, switch_how: null, switch_place: null, steps: '' }),
    // no switch, can't tell
    noswitch: item('wizard-agent-service', 440, { category: 'core', switch: null, switch_how: null, switch_place: null, steps: '' }),
    // said 'No Try it switch' (wizard-notes#18)
    said: item('wizard-notes', 18, { no_switch: true, switch: null, switch_how: null, switch_place: null, steps: 'replace the override with the README snippet' }),
    // steps switch something on in an app this Wizard doesn't have (wizard-recorder#1)
    missing: item('wizard-recorder', 1, { switch: null, switch_how: null, switch_place: null, steps: 'In Recorder\'s Try changes, turn on "Live screen" and open Recorder.' }),
  };
  for (const [k, i] of Object.entries(cases)) { onbox.set(i.id, { at: now, key: factsKey(), v: k === 'live' || k === 'calendar' || k === 'settings' ? yes : unknown }); adoptSwitch(i); i.nextrel = comingNext(i); }
  const out = {};
  for (const [k, i] of Object.entries(cases)) {
    const card = itemCard(i); document.body.append(card);
    const tg = card.querySelector('.bd-try');
    out[k] = { toggle: !!tg, grey: !!(tg && tg.getAttribute('aria-disabled') === 'true'), switch: i.switch || null,
      live: (card.querySelector('.bd-live') || {}).textContent || '', text: card.textContent,
      buttons: [...card.querySelectorAll('.bd-act button')].map(b => b.textContent.trim()).filter(Boolean) };
    card.remove();
  }
  openDetail(cases.calendar);
  out.calendar.steps = el('d-steps').textContent;
  out.calendar.detailSwitch = el('d-switch').textContent;
  WzSheet.close(el('detail'));
  openDetail(cases.settings);
  out.settings.steps = el('d-steps').textContent;
  out.settings.detailSwitch = el('d-switch').textContent;
  WzSheet.close(el('detail'));
  // the top: Builder only while paused; the ⋯ menu holds Builder, Stats, Refresh and Settings
  me = { connected: true };
  showBuilder({ running: true });
  out.builderRunningHidden = el('builder').hidden;
  showBuilder({ running: false });
  out.builderPausedShown = !el('builder').hidden;
  showBuilder({ running: true });
  el('top-more').click();
  out.topMenu = [...el('pop').querySelectorAll('.bd-menu-i .bd-menu-t')].map(x => x.textContent.trim());
  unpop();
  return out;
})()
