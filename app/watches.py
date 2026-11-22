"""0.55.0 Agent watches (humanitylabs-org/wizardos-tracker#146, app switch `agent-watches`, off by default).

An agent that files a bug or feature through the Tracker may name its own thread (`watch_thread`). The Tracker then
watches that item itself with the GitHub sign-in it already has (no model turns) and wakes the thread only when the
item really moved, at most once every 10 minutes, with one check-in every 24 hours. The watch ends by itself when the
release with the fix is the version installed on this Wizard (one last wake: installed, go check it), or when the item
is closed as not planned / dropped / won't fix (one last wake too). A watch never messages the owner: the woken agent
decides what to say.

This module is the pure part (no GitHub, no files, no clock): fingerprints, what changed, when to wake, when to end.
app/server.py reads GitHub, keeps the watches (DATA_DIR/private/watches.json) and calls the wake adapter.
"""
import re

SWITCH = 'agent-watches'
POLL_SECONDS = 300          # one look every 5 minutes: a change wakes its thread within 10 minutes
MIN_GAP = 600               # never wake the same watch twice within 10 minutes
HEARTBEAT = 86400           # a quiet watch still wakes its thread once a day
MAX_AGE = 90 * 86400        # a watch older than this ends (one last wake) so nothing is watched forever
MAX_ACTIVE = 60             # active watches kept on one box
MAX_PENDING = 8             # reasons kept while a change waits for the 10-minute gap
NOTE_MAX = 600
THREAD_RE = re.compile(r'^[A-Za-z0-9._:-]{1,160}$')   # the Agent Service's own session id rule
NOT_PLANNED_LABELS = {'dropped', 'wontfix', "won't fix", 'wont-fix'}
UNSETTLED = {'UNKNOWN', None, ''}   # GitHub is still working out mergeability: keep the last real answer


class WatchError(ValueError):
    """A bad watch_thread / watch_note: the tool refuses before anything is filed."""


def watch_args(args):
    """(thread, note) from a filing tool's arguments, or (None, None) when no watch was asked for.
    Raises WatchError for a bad value, so the filing is refused before it creates anything."""
    thread, note = args.get('watch_thread'), args.get('watch_note')
    if thread is None or thread == '':
        if note not in (None, ''):
            raise WatchError('watch_note needs watch_thread (the thread to wake).')
        return None, None
    if not isinstance(thread, str) or not THREAD_RE.match(thread.strip()):
        raise WatchError('watch_thread must be your Wizard thread id (letters, digits, . _ : -, at most 160).')
    if note is not None and not isinstance(note, str):
        raise WatchError('watch_note must be text.')
    note = re.sub(r'[\u0000-\u001f\u007f]+', ' ', note or '').strip()
    if len(note) > NOTE_MAX:
        raise WatchError(f'watch_note is too long ({NOTE_MAX} characters max).')
    return thread.strip(), note


def _settled(value, old):
    return old if value in UNSETTLED and old not in UNSETTLED else value


def fingerprint(snap, own, old=None):
    """What counts as movement on one item. `snap` (built by server.watch_snapshot):
    {state, reason, labels, comments: [{id, author}] oldest first, comments_total, prs: [{id, state, merged, head,
    mergeable, merge_state}]}. Comments by `own` (the watching account) never count. A PR whose mergeability GitHub is
    still computing keeps its last known value, so a push doesn't wake twice."""
    own = (own or '').lower()
    comments = snap.get('comments') or []
    others = [c for c in comments if (c.get('author') or '').lower() != own]
    complete = (snap.get('comments_total') or 0) <= len(comments)
    last = others[-1] if others else {}
    prev = {p['id']: p for p in ((old or {}).get('prs') or [])}
    prs = []
    for p in sorted(snap.get('prs') or [], key=lambda p: p['id']):
        was = prev.get(p['id']) or {}
        live = (p.get('state') or '').lower() == 'open'
        prs.append({'id': p['id'], 'state': (p.get('state') or '').lower(), 'merged': bool(p.get('merged')),
                    'head': (p.get('head') or '')[:12],
                    'mergeable': _settled(p.get('mergeable'), was.get('mergeable')) if live else None,
                    'merge_state': _settled(p.get('merge_state'), was.get('merge_state')) if live else None})
    return {'state': (snap.get('state') or '').lower(), 'reason': (snap.get('reason') or '').lower() or None,
            'labels': sorted({str(l) for l in snap.get('labels') or []}, key=str.lower),
            # with more comments than one read returns, an own comment can push an older one out: count only then
            'comments': {'n': len(others) if complete else None, 'last': last.get('author'), 'last_id': last.get('id')},
            'prs': prs}


def describe(old, new):
    """Plain words for what moved between two fingerprints (newest facts only, never a diff dump)."""
    out = []
    if old.get('state') != new.get('state') or old.get('reason') != new.get('reason'):
        if new.get('state') == 'closed':
            out.append('closed' + (' as ' + new['reason'].replace('_', ' ') if new.get('reason') else ''))
        else:
            out.append('reopened' if old.get('state') == 'closed' else 'state is now ' + str(new.get('state')))
    a, b = set(old.get('labels') or []), set(new.get('labels') or [])
    if a != b:
        parts = ['+' + x for x in sorted(b - a)] + ['-' + x for x in sorted(a - b)]
        out.append('labels ' + ' '.join(parts))
    oc, nc = old.get('comments') or {}, new.get('comments') or {}
    if oc.get('last_id') != nc.get('last_id') and nc.get('last_id'):
        out.append('new comment by ' + (nc.get('last') or 'someone'))
    elif oc.get('n') != nc.get('n') and oc.get('n') is not None and nc.get('n') is not None:
        out.append('a comment was removed' if (nc['n'] or 0) < (oc['n'] or 0) else 'new comment')
    before = {p['id']: p for p in old.get('prs') or []}
    for p in new.get('prs') or []:
        was = before.get(p['id'])
        if not was:
            out.append(f"PR {p['id']} linked" + (' (merged)' if p['merged'] else ''))
            continue
        if p['merged'] and not was['merged']:
            out.append(f"PR {p['id']} merged")
        elif p['state'] != was['state']:
            out.append(f"PR {p['id']} {'reopened' if p['state'] == 'open' else p['state']}")
        if p['head'] != was['head'] and not p['merged']:
            out.append(f"PR {p['id']} has new commits")
        if p['mergeable'] != was['mergeable'] and p['mergeable'] not in UNSETTLED:
            out.append(f"PR {p['id']} is now {p['mergeable'].lower()}")
        elif p['merge_state'] != was['merge_state'] and p['merge_state'] not in UNSETTLED:
            out.append(f"PR {p['id']} merge state {p['merge_state'].lower()}")
    return '; '.join(out) or 'it changed on GitHub'


def end_reason(snap, installed, age=0):
    """Why a watch ends now, or None. 'installed': the merged fix is in the version running on this Wizard (and no
    linked PR is still open). 'not_planned': closed as not planned / duplicate, or labelled dropped / wontfix.
    'closed': closed done with no linked change to follow. 'expired': watched for MAX_AGE."""
    low = {str(l).lower() for l in snap.get('labels') or []}
    state, reason = (snap.get('state') or '').lower(), (snap.get('reason') or '').lower()
    if low & NOT_PLANNED_LABELS or (state == 'closed' and reason in ('not_planned', 'duplicate')):
        return 'not_planned'
    if installed and not snap.get('open_prs'):
        return 'installed'
    if state == 'closed' and not snap.get('delivers') and not snap.get('open_prs'):
        return 'closed'
    if age >= MAX_AGE:
        return 'expired'
    return None


END_TEXT = {
    'installed': 'is installed on this Wizard: the release with its fix is the version running here. Go check it',
    'not_planned': 'was closed as not planned (dropped, won\u2019t fix or a duplicate)',
    'closed': 'was closed with no linked change to follow',
    'expired': 'has been watched for 90 days, so the watch ends',
    'stopped': 'is no longer watched (watch_stop)',
}


def wake_text(w, snap, reasons, end=None, beat=False):
    """The one-shot run's prompt: what changed and where to look. Quoted GitHub facts, not instructions."""
    iid, title = w['id'], (snap.get('title') or w.get('title') or '').strip()
    head = f'[Tracker watch] {iid}' + (f' \u201c{title[:140]}\u201d' if title else '')
    lines = []
    if end:
        lines.append(f'{head} {END_TEXT[end]}. This is the watch\u2019s last wake.')
    if reasons:
        lines.append(('Also moved: ' if end else f'{head} moved: ') + '; '.join(reasons)[:900] + '.')
    if beat and not end and not reasons:
        lines.append(f'{head}: daily check-in, nothing moved in 24 hours.')
    look = [snap.get('url') or w.get('url') or ''] + [p.get('url') for p in snap.get('prs') or [] if p.get('url')][:4]
    lines.append('Look at: ' + ' '.join(x for x in look if x))
    if w.get('note'):
        lines.append('Your note when you filed it: ' + w['note'])
    lines.append('The WizardOS Tracker watches this item for this thread with no model turns and wakes it only when '
                 'the item moves (at most once every 10 minutes, plus a daily check-in); it stops by itself once the fix '
                 'is installed here. Read the live state yourself before acting. Nothing was sent to your person: '
                 'tell them only if it needs them, otherwise reply [SILENT].'
                 + ('' if end else ' To stop watching sooner, call the Tracker\u2019s watch_stop with this issue.'))
    return '\n'.join(lines)


def step(w, snap, now, own, installed=False):
    """One look at one watch -> (updated watch, wake or None). wake = {name, text, final}.
    The first look only records where the item stands (filing is not movement). A change inside the 10-minute gap is
    kept in `pending` and goes out with the next wake, so nothing is lost and nothing wakes twice."""
    w = dict(w)
    if w.get('ended'):
        return w, None
    pending = list(w.get('pending') or [])
    moved = snap.get('moved_to')
    if moved and moved != w['id']:
        pending.append(f"moved from {w['id']} to {moved}")
        repo, _, n = moved.partition('#')
        w.update(id=moved, repo=repo, number=int(n), fp=None, pending=pending[-MAX_PENDING:],
                 url=f'https://github.com/{repo}/issues/{n}')
        return w, None
    fp = fingerprint(snap, own, w.get('fp'))
    if w.get('fp') is None:
        w['first_seen'] = w.get('first_seen') or now
    elif fp != w['fp']:
        pending.append(describe(w['fp'], fp))
    w['fp'] = fp
    w['title'] = snap.get('title') or w.get('title')
    end = end_reason(snap, installed, now - (w.get('since') or now))
    beat = now - (w.get('last_wake') or w.get('first_seen') or now) >= HEARTBEAT
    if not (pending or end or beat):
        w['pending'] = []
        return w, None
    if w.get('last_wake') and now - w['last_wake'] < MIN_GAP:
        w['pending'] = pending[-MAX_PENDING:]
        return w, None
    text = wake_text(w, snap, pending[-MAX_PENDING:], end, beat)
    w.update(last_wake=now, pending=[], wakes=(w.get('wakes') or 0) + 1)
    if end:
        w['ended'] = {'at': now, 'why': end}
    name = 'Tracker watch \u00b7 ' + w['id'] + (' \u00b7 last wake' if end else '')
    return w, {'name': name[:120], 'text': text, 'final': bool(end)}


# ---------- the wake adapter ----------
# WizardOS has no sanctioned route yet for an installed app to start a run in a named agent thread: the Agent Service's
# /wizard/internal/schedules/create takes only the main agent plugin's loopback credential, /wizard/v1/schedules is
# owner-only, and app deliveries (POST /wizard/v1/apps/<id>/deliveries, app token) write an assistant-only message
# into an app-derived thread and start no run. Until the Agent Service offers one, wakes are kept on the watch
# (`held`) and reported by watch_list; nothing is sent and no host credential is copied into this app.

class NoAppWakeRoute:
    available = False
    why = ('This Wizard has no way yet for an app to wake an agent thread, so the Tracker keeps each wake on the '
           'watch (watch_list shows them) instead of sending it. Keep your own check on the item until it can.')

    def send(self, thread, name, text, key):
        return {'sent': False, 'why': self.why}
