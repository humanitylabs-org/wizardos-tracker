"""0.38.2 (James, Archimedes: humanitylabs-org/wizardos-tracker#97): Update all survives the page being suspended or
reloaded. Runs the page's own queue code under node: a first page starts Update all and dies mid-way (its promises never
settle), a second page loads with the same localStorage and finishes the list; failures are kept for the banner.
Run: python3 -m unittest discover -s tests"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

JS = (Path(__file__).resolve().parent.parent / 'web/app.js').read_text()
A = '// ---------- 0.38.2 Update all survives the page going away'
B = '// ---------- end Update all queue ----------'


def block():
    return JS[JS.index(A):JS.index(B)]


# One "page": the queue code plus stubs for what it calls. `disk` is localStorage, shared across page loads.
PAGE = r"""
const disk = JSON.parse(process.env.DISK || '{}');
const store = { get: k => (k in disk ? JSON.parse(disk[k]) : null), set: (k, v) => { disk[k] = JSON.stringify(v); } };
const runs = new Map(), wizFail = {}, calls = [];
const sleep = ms => new Promise(r => setImmediate(r));
const selfUpdate = () => {};
let updates = null;   // 0.50.1: the queue reads the WizardOS state (an app waits while it installs)
const loadCatalog = async () => {};
let pending = [];
const pendingUpdates = () => pending.map(k => ({ key: k, name: k }));
let behaviour = {};   // key -> 'hang' | 'ok' | reason (fails)
async function updateApp(id) { return fake(id); }
async function updateWizardOS(btn, item) { return fake('os'); }
async function fake(key) {
  calls.push(key);
  const how = behaviour[key] || 'ok';
  if (how === 'hang') return new Promise(() => {});   // the page is suspended / killed while this app updates
  await sleep();
  pending = pending.filter(k => k !== key);
  if (how === 'ok') { delete wizFail[key]; if (key === 'os') runs.set('os', { state: 'done' }); }
  else if (key === 'os') runs.set('os', { state: 'failed', reason: how });
  else wizFail[key] = { at: Date.now(), reason: how };
}
""" 


@unittest.skipUnless(shutil.which('node'), 'node missing')
class InterruptedUpdateAll(unittest.TestCase):
    def page(self, disk, body):
        src = PAGE + block() + '\n(async () => {\n' + body + '\n})().catch(e => { console.error(e.stack || e); process.exit(1); });'
        out = subprocess.run(['node', '-e', src], capture_output=True, text=True, timeout=30, env={'DISK': json.dumps(disk), 'PATH': '/usr/bin:/bin:/usr/local/bin'})
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_reload_mid_update_all_finishes_every_app(self):
        # Page 1: Update all with five apps + WizardOS + the Tracker; the first three hang (the phone sleeps, then the
        # webview is reloaded). Nothing past the first three may have started, and the rest must be on disk.
        one = self.page({}, """
pending = ['a', 'b', 'c', 'd', 'e', 'os', 'wizardos-tracker'];
behaviour = { a: 'hang', b: 'hang', c: 'hang' };
queueStart([{ key: 'wizardos-tracker', name: 'the Tracker' }, { key: 'os', name: 'WizardOS' }, ...['a', 'b', 'c', 'd', 'e'].map(k => ({ key: k, name: k }))]);
for (let n = 0; n < 20; n++) await sleep();
console.log(JSON.stringify({ calls, disk }));""")
        self.assertEqual(one['calls'], ['a', 'b', 'c'])                     # three at a time
        q = json.loads(one['disk']['board.updq'])
        self.assertEqual([x['key'] for x in q['todo']], ['d', 'e', 'os', 'wizardos-tracker'])
        self.assertEqual(sorted(q['doing']), ['a', 'b', 'c'])

        # Page 2 (the reload): `a` is still updating on the box (resumeRuns follows it; it ends fine), `b` never reached
        # the App Manager (still pending, not running: start it again), `c` failed while the page was away.
        since = max(v['since'] for v in q['doing'].values())
        two = self.page(one['disk'], f"""
pending = ['b', 'd', 'e', 'os', 'wizardos-tracker'];
runs.set('a', {{ state: 'running' }});
setTimeout(() => runs.set('a', {{ state: 'done' }}), 30);
wizFail.c = {{ at: {since} + 5, reason: 'Image pull failed.' }};
behaviour = {{ e: 'Disk full.' }};
const order = [];
const was = fake; fake = async k => {{ order.push([k, Object.keys(queue.doing).sort()]); return was(k); }};
await drainQueue();
console.log(JSON.stringify({{ calls, order, disk }}));""")
        self.assertEqual(sorted(two['calls'][:3]), ['b', 'd', 'e'])        # the rest of the list, `b` again, never `a`/`c`
        self.assertEqual(two['calls'][3:], ['os', 'wizardos-tracker'])     # WizardOS after the apps, the Tracker last
        self.assertNotIn('a', two['calls'])
        self.assertNotIn('c', two['calls'])
        for key, doing in two['order']:
            if key in ('os', 'wizardos-tracker'):
                self.assertEqual(doing, [key])                              # nothing else runs beside them
        self.assertIsNone(json.loads(two['disk']['board.updq']))           # queue finished and cleared
        last = json.loads(two['disk']['board.updq.last'])
        self.assertEqual(sorted((f['key'], f['reason']) for f in last['failed']), [('c', 'Image pull failed.'), ('e', 'Disk full.')])
        self.assertEqual(last['done'], 5)                                   # a, b, d, os, the Tracker

    def test_page_that_returns_after_everything_ended_reports_without_rerunning(self):
        disk = {'board.updq': json.dumps({'at': 0, 'todo': [], 'doing': {}, 'done': [], 'failed': []})}
        # a queue older than three hours is dropped, never resumed
        old = self.page(disk, "console.log(JSON.stringify({ q: queueGet(), open: queueOpen() }));")
        self.assertEqual(old, {'q': None, 'open': False})
        got = self.page({}, """
pending = ['m'];
queue = { at: Date.now(), todo: [], doing: { m: { since: Date.now() - 1000, name: 'Messenger' } }, done: [], failed: [] };
store.set('board.updq', queue);
wizFail.m = { at: Date.now(), reason: 'Messenger ended up stopped, so it can’t open.' };
pending = [];
await drainQueue();
console.log(JSON.stringify({ calls, last: store.get('board.updq.last'), open: queueOpen() }));""")
        self.assertEqual(got['calls'], [])
        self.assertFalse(got['open'])
        self.assertEqual(got['last']['failed'], [{'key': 'm', 'name': 'Messenger', 'reason': 'Messenger ended up stopped, so it can’t open.'}])

    def test_wiring(self):
        self.assertIn('if (queueOpen() && !draining) drainQueue()', JS)
        self.assertIn("document.addEventListener('visibilitychange', () => { if (!document.hidden && queueOpen() && !draining) checkSelfUpdate(true); });", JS)
        self.assertIn("queueStart(pendingUpdates().filter(x => !(x.key === 'os' && osHeld())))", JS)   # 0.50.1, 0.55.1
        self.assertIn("didn’t update: ${f.reason}", JS)
        self.assertNotIn('for (const x of pendingUpdates()) { await', JS)   # the old page-memory loop is gone


if __name__ == '__main__':
    unittest.main()
