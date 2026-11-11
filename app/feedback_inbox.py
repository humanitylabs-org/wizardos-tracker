"""Tracker 0.26.5: the Feedback app's inbox, as a 'Pending approval' stage.

Reports from people outside the team (anonymous, or a GitHub login not on the team) land in the private
humanitylabs-org/wizardos-feedback-inbox through the Feedback relay (a Cloudflare Worker that holds the
'WizardOS Feedback Relay' GitHub App). A team member reviews them here:

  GET  <relay>/v1/pending           -> {items: [{number, kind, title, text, submitter, created, screenshots}]}
  POST <relay>/v1/review {issue, action: approve|reject, kind?: bug|feature, reason?: text}

both with `Authorization: Bearer <the signed-in person's own GitHub token>`. The relay checks the token with GitHub
and that the login is an active org member. Approve files a copy in wizard-os (labels triage + bug/feature +
from-feedback; the builder's triage step takes it from there); Reject closes the inbox item as not planned.
0.28.1 (Miguel): approve as the other kind (a 'bug' that is really an idea goes to the feature queue, labelled feature,
'changed from bug to idea by @you'), and decline with an optional reason (≤ 500 chars) the sender sees in Feedback.

The token is only ever sent server-side to the relay, never to the browser. Kept apart from server.py on purpose:
the host passes the account (`{'token', 'login'}`) in.
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

RELAY_URL = (os.environ.get('FEEDBACK_RELAY_URL') or 'https://wizardos-feedback-relay.ai-wizards-previews.workers.dev').rstrip('/')
FROM_LABEL = 'from-feedback'
CACHE_SECONDS = 30
TIMEOUT = 20
REASON_MAX = 500
KIND_WORD = {'bug': 'bug', 'feature': 'idea'}
_CTRL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]')


def clean_reason(s):
    """The decline reason as the sender will read it: plain text, control characters stripped, ≤ 500 chars."""
    if s is None:
        return ''
    if not isinstance(s, str):
        raise RelayError(400, 'The reason must be text.')
    t = _CTRL.sub('', s.replace('\r\n', '\n').replace('\r', '\n')).strip()
    if len(t) > REASON_MAX:
        raise RelayError(400, f'Keep the reason under {REASON_MAX} characters.')
    return t

_lock = threading.Lock()
_cache = {}   # login -> (time, answer)


class RelayError(Exception):
    def __init__(self, code, message, reason=''):
        super().__init__(message)
        self.code, self.message, self.reason = code, message, reason


def _http(method, path, token, body=None, opener=None):
    """One relay call -> (status, json). `opener(req, timeout)` is injectable for tests."""
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(RELAY_URL + path, data=data, method=method, headers={
        'Authorization': 'Bearer ' + token, 'Accept': 'application/json', 'User-Agent': 'wizardos-tracker',
        **({'Content-Type': 'application/json'} if data is not None else {})})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=TIMEOUT) as r:
            raw = r.read()
            status = getattr(r, 'status', 200)
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    except (urllib.error.URLError, OSError, ValueError):
        raise RelayError(502, 'The Feedback inbox can’t be reached right now. Try again in a minute.', 'relay_down')
    try:
        out = json.loads(raw or b'{}')
    except ValueError:
        out = {}
    return status, out if isinstance(out, dict) else {}


def _problem(status, out):
    msg = str(out.get('message') or '')[:300]
    if status == 401:
        return RelayError(401, msg or 'Sign in with GitHub first.', 'relay_unauthorized')
    if status == 403:
        return RelayError(403, msg or 'Only WizardOS team members can review feedback.', 'relay_forbidden')
    if status == 404:
        return RelayError(404, msg or 'That item is gone from the inbox. Refresh.', 'relay_not_found')
    if status == 429:
        return RelayError(429, 'Too many tries. Wait a minute.', 'relay_rate_limited')
    return RelayError(502, msg or 'The Feedback inbox didn’t answer. Try again.', 'relay_error')


SAFE_URL = re.compile(r'^https://[A-Za-z0-9.-]+/[^\s"<>]*$')


def _item(x):
    """Only the fields the page shows, cleaned (text stays plain text: the page renders it with textContent)."""
    if not isinstance(x, dict) or not isinstance(x.get('number'), int):
        return None
    kind = x.get('kind') if x.get('kind') in ('bug', 'feature') else 'bug'
    sub = str(x.get('submitter') or 'anonymous')
    sub = sub if re.fullmatch(r'anonymous|@[A-Za-z0-9-]{1,39}', sub) else 'anonymous'
    return {'id': f"feedback#{x['number']}", 'number': x['number'], 'kind': kind,
            'kind_word': 'Bug' if kind == 'bug' else 'Idea', 'title': str(x.get('title') or '')[:300],
            'text': str(x.get('text') or '')[:8000], 'submitter': sub,
            'submitter_word': 'Anonymous' if sub == 'anonymous' else sub,
            'created': str(x.get('created') or '') or None,
            'screenshots': [u for u in (x.get('screenshots') or []) if isinstance(u, str) and SAFE_URL.match(u)][:6]}


def pending(acct, refresh=False, opener=None):
    """GET /api/feedback/pending -> {items, count}. Cached 30 s per person."""
    login = (acct.get('login') or '').lower()
    now = time.time()
    with _lock:
        hit = _cache.get(login)
    if hit and not refresh and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    status, out = _http('GET', '/v1/pending', acct['token'], opener=opener)
    if status != 200:
        raise _problem(status, out)
    items = [i for i in (_item(x) for x in out.get('items') or []) if i]
    ans = {'items': items, 'count': len(items), 'relay': RELAY_URL}
    with _lock:
        _cache[login] = (now, ans)
    return ans


def review(acct, args, opener=None):
    """POST /api/feedback/review {number, action: approve|reject, kind?: bug|feature (approve as), reason?: text (reject)}
    -> what the relay did (idempotent there)."""
    action = args.get('action')
    if action not in ('approve', 'reject'):
        raise RelayError(400, "action must be 'approve' or 'reject'.")
    number = args.get('number', args.get('issue'))
    if isinstance(number, str) and number.isdigit():
        number = int(number)
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise RelayError(400, 'number must be an inbox item number.')
    kind = args.get('kind')
    if kind in ('', None):
        kind = None
    elif kind not in ('bug', 'feature'):
        raise RelayError(400, "kind must be 'bug' or 'feature'.")
    reason = clean_reason(args.get('reason')) if action == 'reject' else ''
    body = {'issue': number, 'action': action}
    if action == 'approve' and kind:
        body['kind'] = kind
    if reason:
        body['reason'] = reason
    status, out = _http('POST', '/v1/review', acct['token'], body, opener=opener)
    if status != 200:
        raise _problem(status, out)
    with _lock:
        _cache.clear()   # everyone's list changed
    twin = out.get('twin') if isinstance(out.get('twin'), dict) else None
    res = out.get('result') if out.get('result') in ('approved', 'rejected') else action + 'd'
    got = out.get('kind') if out.get('kind') in ('bug', 'feature') else kind
    was = out.get('changed_from') if out.get('changed_from') in ('bug', 'feature') else None
    if res == 'approved':
        msg = f"Approved as {'a bug' if got == 'bug' else 'an idea'}: sent to the builder queue." if got else 'Approved: sent to the builder queue.'
        if was and got and was != got:
            msg += f' (Changed from {KIND_WORD[was]}.)'
    else:
        msg = 'Declined. The sender sees your reason.' if reason and not out.get('already') else 'Declined.'
    return {'number': number, 'result': res, 'already': bool(out.get('already')), 'kind': got, 'changed_from': was,
            'reason': reason or None,
            'twin': {'repo': str(twin.get('repo') or ''), 'number': twin.get('number'), 'url': str(twin.get('url') or '')} if twin else None,
            'message': msg + (' (It was already handled.)' if out.get('already') else '')}


def is_from_feedback(labels):
    return FROM_LABEL in {str(n).lower() for n in labels or []}
