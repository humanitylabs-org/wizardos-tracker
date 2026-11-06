"""Board: Goals and Bugs on GitHub, one API/service layer used by the view and MCP.

Stdlib only. GitHub is the only backend; this app stores just each person's token
(0600, server side, never returned) and one setting (the org). The host gateway owns
authentication; direct ports stay loopback.
"""
import hashlib
import html as htmllib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent if '__file__' in globals() else Path(os.environ.get('APP_ROOT', '.')).resolve()
DATA = Path(os.environ.get('DATA_DIR', ROOT / '.data'))
PRIVATE = DATA / 'private'
APP_ID = 'board'
VERSION = '0.4.0'
GITHUB = os.environ.get('GITHUB_API', 'https://api.github.com').rstrip('/')
DEFAULT_ORG = os.environ.get('BOARD_DEFAULT_ORG', 'humanitylabs-org')
TOKEN_URL = 'https://github.com/settings/personal-access-tokens/new'
# Only these people may open Goals in the app (GitHub logins, comma separated).
GOAL_AUTHORS = {x.strip().lower() for x in os.environ.get('GOAL_AUTHORS', 'jdefleur').split(',') if x.strip()}
# The builder agent's GitHub account: it labels finished work ready-to-test and says what to check.
BUILDER = os.environ.get('BOARD_BUILDER', 'wizardosbuilder').strip().lower()
DEFAULT_REPO = os.environ.get('BOARD_DEFAULT_REPO', 'wizard-ux')
MEDIA_REPO = os.environ.get('BOARD_MEDIA_REPO', 'humanitylabs-org/wizard-issue-media')
CACHE_SECONDS = 60
STATIC_TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml'}
NAME = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,99})$')
TASK = re.compile(r'^(\s*[-*+]\s+\[)([ xX])(\]\s?)(.*)$')
LOCK = threading.Lock()


class Problem(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


# ---------- private storage (0700 dir, 0600 files) ----------

def _private():
    PRIVATE.mkdir(parents=True, exist_ok=True)
    os.chmod(PRIVATE, 0o700)
    return PRIVATE


def _read(name, default):
    try:
        return json.loads((_private() / name).read_text())
    except (FileNotFoundError, ValueError, OSError):
        return default


def _write(name, value):
    d = _private()
    tmp = d / (name + '.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(value, f, indent=1)
    os.chmod(tmp, 0o600)
    tmp.replace(d / name)


def secure_start():
    for p in _private().iterdir():
        if p.is_file():
            os.chmod(p, 0o600)


def accounts():
    a = _read('accounts.json', {})
    if not isinstance(a, dict):
        a = {}
    a.setdefault('people', {})
    return a


def settings():
    s = _read('settings.json', {})
    org = s.get('org') if isinstance(s, dict) and isinstance(s.get('org'), str) and NAME.match(s['org']) else DEFAULT_ORG
    return {'org': org}


def person_key(person):
    p = (person or '').strip().lower()
    return p if p and len(p) <= 200 else 'owner'


def account_for(person=None, agent=False):
    """The token used for one request. People use their own; agents (MCP) use the
    box's default account: the first person who connected."""
    a = accounts()
    people = a['people']
    if agent:
        key = a.get('default') if a.get('default') in people else next(iter(people), None)
    else:
        key = person_key(person)
    acct = people.get(key) if key else None
    if not acct or not acct.get('token'):
        raise Problem(401, 'No GitHub account is connected in Board. Ask the owner to connect one in the app.' if agent else 'Connect your GitHub account first.')
    return key, acct


def public_account(acct):
    return {k: acct.get(k) for k in ('login', 'name', 'html_url', 'kind', 'scopes', 'saved_at')}


# ---------- GitHub client (60 s read cache per token) ----------

_cache = {}


def _tid(token):
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def _forget(token):
    t = _tid(token)
    with LOCK:
        for k in [k for k in _cache if k[0] == t]:
            _cache.pop(k, None)


def gh(token, method, path, body=None, cache=True, accept='application/vnd.github+json'):
    url = GITHUB + path
    key = (_tid(token), method, url, json.dumps(body, sort_keys=True) if body is not None else '', accept)
    if cache and method in ('GET', 'GRAPHQL'):
        with LOCK:
            hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
    data = None if body is None else json.dumps(body).encode()
    headers = {'Authorization': 'Bearer ' + token, 'Accept': accept,
               'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'wizard-board/' + VERSION}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, method='POST' if method == 'GRAPHQL' else method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = r.read(8 * 1024 * 1024)
    except urllib.error.HTTPError as e:
        try:
            msg = str(json.loads(e.read(65536) or b'{}').get('message') or '')
        except ValueError:
            msg = ''
        if e.code == 401:
            raise Problem(401, 'GitHub refused this token (wrong or expired). Connect again with a new one.') from None
        if e.code in (403, 429) and 'rate limit' in msg.lower():
            raise Problem(429, 'GitHub rate limit reached. Try again in a minute.') from None
        if e.code in (403, 404):
            raise Problem(e.code, 'Your GitHub token cannot do that here' + (f' ({msg}).' if msg else '.')) from None
        if e.code == 422:
            raise Problem(400, 'GitHub refused the change' + (f': {msg}' if msg else '.')) from None
        raise Problem(502, f'GitHub answered {e.code}' + (f': {msg}' if msg else '.')) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise Problem(502, 'Could not reach GitHub. Check the internet connection and try again.') from None
    out = json.loads(payload or b'null')
    if method == 'GRAPHQL' and isinstance(out, dict) and out.get('errors') and not out.get('data'):
        raise Problem(502, ('GitHub: ' + '; '.join(str(e.get('message', '')) for e in out['errors']))[:300])
    if method in ('GET', 'GRAPHQL'):
        if cache:
            with LOCK:
                _cache[key] = (time.time(), out)
                if len(_cache) > 500:
                    for k in sorted(_cache, key=lambda k: _cache[k][0])[:100]:
                        _cache.pop(k, None)
    else:
        _forget(token)
    return out


def graphql(token, query, variables, cache=True):
    return gh(token, 'GRAPHQL', '/graphql', {'query': query, 'variables': variables}, cache=cache)


# ---------- account ----------

def connect(person, args):
    token = args.get('token')
    if not isinstance(token, str) or not 20 <= len(token.strip()) <= 400 or any(c.isspace() for c in token.strip()):
        raise Problem(400, 'Paste a GitHub personal access token (it starts with github_pat_ or ghp_).')
    token = token.strip()
    req = urllib.request.Request(GITHUB + '/user', headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                                                            'User-Agent': 'wizard-board/' + VERSION, 'X-GitHub-Api-Version': '2022-11-28'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            user = json.loads(r.read(1 << 20))
            scopes = r.headers.get('X-OAuth-Scopes')
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise Problem(400, 'GitHub did not accept this token. Check it was copied whole and has not expired.') from None
        raise Problem(502, f'GitHub answered {e.code}. Try again.') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise Problem(502, 'Could not reach GitHub to check the token. Try again.') from None
    kind = 'fine-grained' if token.startswith('github_pat_') else 'classic' if token.startswith('ghp_') else 'token'
    acct = {'token': token, 'login': user.get('login'), 'name': user.get('name'), 'avatar_url': user.get('avatar_url'),
            'html_url': user.get('html_url'), 'kind': kind, 'scopes': scopes, 'saved_at': int(time.time())}
    with LOCK:
        a = accounts()
        key = person_key(person)
        a['people'][key] = acct
        if a.get('default') not in a['people']:
            a['default'] = key
        _write('accounts.json', a)
    return status(person)


def disconnect(person):
    with LOCK:
        a = accounts()
        key = person_key(person)
        old = a['people'].pop(key, None)
        if a.get('default') == key:
            a['default'] = next(iter(a['people']), None)
        _write('accounts.json', a)
    if old and old.get('token'):
        _forget(old['token'])
    return status(person)


def status(person=None):
    a = accounts()
    acct = a['people'].get(person_key(person))
    return {'connected': bool(acct and acct.get('token')), 'account': public_account(acct) if acct else None,
            'org': settings()['org'], 'token_url': TOKEN_URL,
            'agent_account': (a['people'].get(a.get('default')) or {}).get('login'), 'version': VERSION,
            'can_goal': bool(acct and (acct.get('login') or '').lower() in GOAL_AUTHORS),
            'default_repo': DEFAULT_REPO, 'screenshots': bool(acct and acct.get('token') and _media_ready(acct['token']))}


def _media_ready(token):
    """Screenshots need the shared media repo. Board never creates it; it only checks it exists."""
    try:
        gh(token, 'GET', '/repos/' + MEDIA_REPO)
        return True
    except Problem:
        return False


def set_org(args):
    org = args.get('org')
    if not isinstance(org, str) or not NAME.match(org.strip()):
        raise Problem(400, 'Use a GitHub organisation or user name.')
    with LOCK:
        cur = _read('settings.json', {})
        _write('settings.json', {**(cur if isinstance(cur, dict) else {}), 'org': org.strip()})
    return {'org': settings()['org']}


# ---------- board ----------

def tasks_of(body):
    out = []
    for line in (body or '').splitlines():
        m = TASK.match(line)
        if m:
            out.append({'index': len(out), 'done': m.group(2) in 'xX', 'text': m.group(4).strip()})
    return out


ISSUE_FIELDS = '''
  number title url state stateReason body createdAt updatedAt closedAt
  author { login }
  repository { nameWithOwner name }
  labels(first: 20) { nodes { name } }
  closedByPullRequestsReferences(first: 20, includeClosedPrs: true) { nodes { number title url state repository { nameWithOwner } } }
  timelineItems(itemTypes: [CROSS_REFERENCED_EVENT, CONNECTED_EVENT], first: 50) { nodes {
    ... on CrossReferencedEvent { source { ... on PullRequest { number title url state repository { nameWithOwner } } } }
    ... on ConnectedEvent { subject { ... on PullRequest { number title url state repository { nameWithOwner } } } }
  } }
'''
SEARCH = ('query($q: String!) { search(query: $q, type: ISSUE, first: 100) { issueCount nodes { ... on Issue {'
          + ISSUE_FIELDS + ' comments { totalCount } } } } }')
ONE = ('query($o: String!, $r: String!, $n: Int!) { repository(owner: $o, name: $r) { issue(number: $n) {'
       + ISSUE_FIELDS + ' comments(last: 30) { totalCount nodes { author { login } body createdAt url } } } } }')


def _prs(node):
    seen = {}
    for p in (node.get('closedByPullRequestsReferences') or {}).get('nodes') or []:
        if p and p.get('url'):
            seen[p['url']] = p
    for t in (node.get('timelineItems') or {}).get('nodes') or []:
        p = (t or {}).get('source') or (t or {}).get('subject')
        if p and p.get('url'):
            seen[p['url']] = p
    return [{'number': p['number'], 'title': p.get('title'), 'url': p['url'], 'state': (p.get('state') or '').lower(),
             'repo': (p.get('repository') or {}).get('nameWithOwner')} for p in seen.values()]


def shape(node):
    labels = [l['name'] for l in (node.get('labels') or {}).get('nodes') or []]
    low = [l.lower() for l in labels]
    tasks = tasks_of(node.get('body'))
    prs = _prs(node)
    return {'id': f"{node['repository']['nameWithOwner']}#{node['number']}", 'repo': node['repository']['nameWithOwner'],
            'number': node['number'], 'title': node.get('title'), 'url': node.get('url'),
            'type': 'goal' if 'goal' in low else 'bug' if 'bug' in low else 'other',
            'state': (node.get('state') or '').lower(), 'state_reason': (node.get('stateReason') or '').lower() or None,
            'accepted': 'accepted' in low, 'labels': labels, 'author': (node.get('author') or {}).get('login'),
            'created_at': node.get('createdAt'), 'updated_at': node.get('updatedAt'), 'closed_at': node.get('closedAt'),
            'comments': (node.get('comments') or {}).get('totalCount', 0),
            'tasks_done': sum(t['done'] for t in tasks), 'tasks_total': len(tasks),
            'open_prs': sum(1 for p in prs if p['state'] == 'open'), 'prs': prs}


def _repo(org, repo):
    """A repo filter: 'name' (inside the org) or 'owner/name'."""
    if not repo:
        return None
    if not isinstance(repo, str):
        raise Problem(400, 'repo must be a name.')
    parts = repo.strip().split('/')
    if len(parts) == 1 and NAME.match(parts[0]):
        return f'{org}/{parts[0]}'
    if len(parts) == 2 and all(NAME.match(p) for p in parts):
        return '/'.join(parts)
    raise Problem(400, 'repo must be name or owner/name.')


# GitHub search lags writes by up to a minute or two. Items this box just changed are kept for a
# short while and laid over search results, so a new goal never vanishes on the next refresh.
RECENT_SECONDS = 180
_recent = {}


def _remember(token, item):
    small = {k: v for k, v in item.items() if k not in ('body', 'tasks', 'comment_list', 'prs')}
    with LOCK:
        _recent[(_tid(token), item['id'])] = (time.time(), small)


def _merge_recent(token, items, f):
    now, t = time.time(), _tid(token)
    with LOCK:
        mine = [v for (k, _), (at, v) in list(_recent.items()) if k == t and now - at < RECENT_SECONDS]
        for key in [k for k, (at, _) in _recent.items() if now - at >= RECENT_SECONDS]:
            _recent.pop(key, None)
    by_id = {i['id']: i for i in items}
    for r in mine:
        seen = by_id.get(r['id'])
        if seen and (seen.get('updated_at') or '') >= (r.get('updated_at') or ''):
            continue  # search already has this change (or a newer one)
        fits = (r['state'] == f['state'] and (f['type'] == 'all' or r['type'] == f['type'])
                and r['type'] in ('goal', 'bug')
                and (r['repo'].lower() == f['repo'].lower() if f['repo'] else r['repo'].lower().startswith(f['org'].lower() + '/'))
                and (r['type'] != 'bug' or f['accepted'] == 'any' or r['accepted'] == (f['accepted'] == 'yes')))
        if fits:
            by_id[r['id']] = r
        else:
            by_id.pop(r['id'], None)
    return sorted(by_id.values(), key=lambda i: i.get('updated_at') or '', reverse=True)


def board_list(person=None, args=None, agent=False):
    args = args or {}
    _, acct = account_for(person, agent)
    org = args.get('org') or settings()['org']
    if not isinstance(org, str) or not NAME.match(org):
        raise Problem(400, 'Use a GitHub organisation or user name.')
    kind, state, accepted = args.get('type') or 'all', args.get('state') or 'open', args.get('accepted') or 'any'
    if kind not in ('all', 'goal', 'bug') or state not in ('open', 'closed') or accepted not in ('any', 'yes', 'no'):
        raise Problem(400, 'Filters: type all|goal|bug, state open|closed, accepted any|yes|no.')
    repo = _repo(org, args.get('repo'))
    q = f"{'repo:' + repo if repo else 'org:' + org} is:issue is:{state} label:{ {'all': 'goal,bug', 'goal': 'goal', 'bug': 'bug'}[kind] } sort:updated-desc"
    if kind == 'bug' and accepted != 'any':
        q += ' label:accepted' if accepted == 'yes' else ' -label:accepted'
    if args.get('refresh'):
        _forget(acct['token'])
    found = ((graphql(acct['token'], SEARCH, {'q': q}).get('data') or {}).get('search') or {})
    items = [shape(n) for n in found.get('nodes') or [] if n and n.get('number')]
    items = _merge_recent(acct['token'], items, {'org': org, 'repo': repo, 'type': kind, 'state': state, 'accepted': accepted})
    if kind == 'all' and accepted != 'any':
        items = [i for i in items if i['type'] != 'bug' or i['accepted'] == (accepted == 'yes')]
    for i in items:
        i.pop('prs', None)
    total = found.get('issueCount', len(items))
    return {'org': org, 'repo': repo, 'query': q, 'count': len(items), 'total': total, 'truncated': total > len(items),
            'goals': [i for i in items if i['type'] == 'goal'], 'bugs': [i for i in items if i['type'] == 'bug'],
            'fetched_at': int(time.time()), 'account': acct.get('login')}


def _target(args):
    repo, number = args.get('repo'), args.get('number')
    if isinstance(args.get('issue'), str):
        m = re.fullmatch(r'(?:https://github\.com/)?([\w.-]+)/([\w.-]+)(?:#|/issues/)(\d+)', args['issue'].strip())
        if not m:
            raise Problem(400, 'issue must look like owner/repo#123 or an issue URL.')
        repo, number = f'{m.group(1)}/{m.group(2)}', int(m.group(3))
    if isinstance(number, str) and number.isdigit():
        number = int(number)
    full = _repo(settings()['org'], repo)
    if not full or not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise Problem(400, 'Name the issue: repo and number (or issue "owner/repo#123").')
    return full, number


def _read_issue(acct, full, number, fresh):
    owner, name = full.split('/')
    node = ((graphql(acct['token'], ONE, {'o': owner, 'r': name, 'n': number}, cache=not fresh).get('data') or {}).get('repository') or {}).get('issue')
    if not node:
        raise Problem(404, f'{full}#{number} was not found, or your token cannot see it.')
    out = shape(node)
    out['body'] = node.get('body') or ''
    out['tasks'] = tasks_of(node.get('body'))
    out['comment_list'] = [{'author': (c.get('author') or {}).get('login'), 'body': c.get('body'), 'created_at': c.get('createdAt'), 'url': c.get('url')}
                           for c in (node.get('comments') or {}).get('nodes') or []]
    if fresh:
        _remember(acct['token'], out)
    return out


def board_get(person=None, args=None, agent=False, fresh=False):
    _, acct = account_for(person, agent)
    full, number = _target(args or {})
    return _read_issue(acct, full, number, fresh)


def _text(v, field, lo, hi):
    if not isinstance(v, str) or not lo <= len(v.strip()) <= hi:
        raise Problem(400, f'{field} must be {lo}–{hi} characters.')
    return v.strip()


def _create(acct, full, title, body, label):
    issue = gh(acct['token'], 'POST', f'/repos/{full}/issues', {'title': title, 'body': body, 'labels': [label]})
    if label not in [l.get('name', '').lower() for l in issue.get('labels') or []]:
        # GitHub silently drops labels for people without write access; try once more, then say so.
        try:
            gh(acct['token'], 'POST', f"/repos/{full}/issues/{issue['number']}/labels", {'labels': [label]})
        except Problem:
            pass
    out = _read_issue(acct, full, issue['number'], True)
    out['labelled'] = label in [l.lower() for l in out['labels']]
    if not out['labelled']:
        out['warning'] = f'GitHub dropped the {label} label (you may not have write access to this repo), so it will not show on the board.'
    return out


def _owner_request(args, agent, what):
    if agent:
        r = args.get('owner_request')
        if not isinstance(r, str) or len(r.strip()) < 8:
            raise Problem(403, f'Agents may not {what} on their own. Only do it when a human asked; pass their words as owner_request.')


def add_goal(person, args, agent=False):
    _owner_request(args, agent, 'open goals')
    _, acct = account_for(person, agent)
    full = _repo(settings()['org'], args.get('repo'))
    if not full:
        raise Problem(400, 'Pick a repo for the goal.')
    title = _text(args.get('title'), 'Title', 3, 200)
    done = args.get('done') or []
    if isinstance(done, str):
        done = done.splitlines()
    if not isinstance(done, list) or not all(isinstance(d, str) for d in done):
        raise Problem(400, 'done must be a list of lines.')
    done = [d for d in (re.sub(r'^\s*(?:[-*+]\s*)?(?:\[[ xX]\]\s*)?', '', d).strip() for d in done) if d]
    if not 1 <= len(done) <= 20 or any(len(d) > 200 for d in done):
        raise Problem(400, 'Give the goal 1–20 done-list lines (up to 200 characters each).')
    intro = args.get('body') or ''
    if not isinstance(intro, str) or len(intro) > 4000:
        raise Problem(400, 'The description is too long (4000 characters max).')
    intro = intro.strip()
    body = (intro + '\n\n' if intro else '') + '## Done when\n\n' + '\n'.join(f'- [ ] {d}' for d in done) + '\n'
    return _create(acct, full, title, body, 'goal')


def report_bug(person, args, agent=False):
    _, acct = account_for(person, agent)
    full = _repo(settings()['org'], args.get('repo'))
    if not full:
        raise Problem(400, 'Pick a repo for the bug.')
    title = _text(args.get('title'), 'Title', 3, 200)
    body = args.get('body') or ''
    if not isinstance(body, str) or len(body) > 8000:
        raise Problem(400, 'The description is too long (8000 characters max).')
    return _create(acct, full, title, body.strip(), 'bug')


def _current(acct, full, number):
    return gh(acct['token'], 'GET', f'/repos/{full}/issues/{number}', cache=False)


def accept_bug(person, args, agent=False):
    _owner_request(args, agent, 'accept bugs')
    _, acct = account_for(person, agent)
    full, number = _target(args)
    names = [l.get('name', '').lower() for l in _current(acct, full, number).get('labels') or []]
    if 'bug' not in names:
        raise Problem(400, 'Only bugs can be accepted.')
    if 'accepted' not in names:
        gh(acct['token'], 'POST', f'/repos/{full}/issues/{number}/labels', {'labels': ['accepted']})
    out = _read_issue(acct, full, number, True)
    if not out['accepted']:
        raise Problem(403, 'GitHub did not add the accepted label (write access to this repo is needed).')
    return out


def set_state(person, args, state, agent=False):
    full, number = _target(args)
    _, acct = account_for(person, agent)
    cur = _current(acct, full, number)
    if agent and 'goal' in [l.get('name', '').lower() for l in cur.get('labels') or []]:
        raise Problem(403, 'Agents never close or reopen goals; only humans do, in the app.')
    _owner_request(args, agent, 'close or reopen issues')
    if cur.get('state') != state:
        patch = {'state': state}
        if state == 'closed':
            reason = args.get('reason') or 'completed'
            if reason not in ('completed', 'not_planned'):
                raise Problem(400, 'reason must be completed or not_planned.')
            patch['state_reason'] = reason
        gh(acct['token'], 'PATCH', f'/repos/{full}/issues/{number}', patch)
    out = _read_issue(acct, full, number, True)
    if out['state'] != state:
        raise Problem(502, 'GitHub did not change the state. Refresh and try again.')
    return out


def set_task(person, args):
    _, acct = account_for(person)
    full, number = _target(args)
    index, checked, expect = args.get('index'), args.get('done'), args.get('text')
    if not isinstance(index, int) or isinstance(index, bool) or not isinstance(checked, bool):
        raise Problem(400, 'index must be a number and done true or false.')
    lines = (_current(acct, full, number).get('body') or '').split('\n')
    found = [i for i, l in enumerate(lines) if TASK.match(l.rstrip('\r'))]
    if not 0 <= index < len(found):
        raise Problem(409, 'The done-list changed on GitHub. Refresh and try again.')
    i = found[index]
    cr = '\r' if lines[i].endswith('\r') else ''
    m = TASK.match(lines[i].rstrip('\r'))
    if isinstance(expect, str) and m.group(4).strip() != expect.strip():
        raise Problem(409, 'That line changed on GitHub. Refresh and try again.')
    if (m.group(2) in 'xX') != checked:
        lines[i] = m.group(1) + ('x' if checked else ' ') + m.group(3) + m.group(4) + cr
        gh(acct['token'], 'PATCH', f'/repos/{full}/issues/{number}', {'body': '\n'.join(lines)})
    out = _read_issue(acct, full, number, True)
    if out['tasks'][index]['done'] != checked:
        raise Problem(502, 'GitHub did not save the tick. Refresh and try again.')
    return out


def add_comment(person, args, agent=False):
    _, acct = account_for(person, agent)
    full, number = _target(args)
    body = _text(args.get('body'), 'Comment', 1, 8000)
    c = gh(acct['token'], 'POST', f'/repos/{full}/issues/{number}/comments', {'body': body})
    got = gh(acct['token'], 'GET', f"/repos/{full}/issues/comments/{c['id']}", cache=False)
    if (got.get('body') or '').strip() != body:
        raise Problem(502, 'GitHub did not save the comment.')
    return {'repo': full, 'number': number, 'comment_url': got.get('html_url'), 'saved': True}


def repos(person):
    _, acct = account_for(person)
    org = settings()['org']
    try:
        rows = gh(acct['token'], 'GET', f'/orgs/{org}/repos?per_page=100&sort=pushed&type=all')
    except Problem as e:
        if e.code != 404:
            raise
        rows = gh(acct['token'], 'GET', f'/users/{org}/repos?per_page=100&sort=pushed')
        me = gh(acct['token'], 'GET', '/user')
        if (me.get('login') or '').lower() == org.lower():  # your own account: include private repos
            rows = [r for r in gh(acct['token'], 'GET', '/user/repos?per_page=100&affiliation=owner&sort=pushed') if r['owner']['login'].lower() == org.lower()]
    rows = [r for r in rows if not r.get('archived') and r.get('has_issues', True)]
    return {'org': org, 'repos': sorted([{'name': r['name'], 'full_name': r['full_name'], 'private': r.get('private', False),
                                          'can_write': bool((r.get('permissions') or {}).get('push'))} for r in rows], key=lambda r: r['name'].lower())}


def boxes(person):
    """Which wizard-ux this box runs vs main. The box's own version file is outside this
    app's container, so that half stays 'coming soon' rather than asking for host access."""
    out = {'box': {'available': False, 'note': 'Coming soon: the app cannot read this box’s version yet.'}, 'main': None}
    try:
        _, acct = account_for(person)
        c = gh(acct['token'], 'GET', '/repos/humanitylabs-org/wizard-ux/commits/main')
        out['main'] = {'sha': (c.get('sha') or '')[:7], 'message': ((c.get('commit') or {}).get('message') or '').split('\n')[0][:120],
                       'date': ((c.get('commit') or {}).get('committer') or {}).get('date'), 'url': c.get('html_url')}
    except Problem as e:
        out['main_error'] = e.message
    return out


_avatars = {}


def avatar(person):
    """The connected account's picture, fetched by the box so the view loads only from itself."""
    url = ((accounts()['people'].get(person_key(person))) or {}).get('avatar_url') or ''
    if not url.startswith('https://avatars.githubusercontent.com/'):
        raise Problem(404, 'No picture.')
    hit = _avatars.get(url)
    if hit and time.time() - hit[0] < 3600:
        return hit[1], hit[2]
    try:
        with urllib.request.urlopen(urllib.request.Request(url + ('&' if '?' in url else '?') + 's=96', headers={'User-Agent': 'wizard-board'}), timeout=10) as r:
            data, kind = r.read(512 * 1024), r.headers.get('Content-Type', '')
    except (urllib.error.URLError, OSError):
        raise Problem(502, 'No picture.') from None
    if kind not in ('image/png', 'image/jpeg', 'image/gif', 'image/webp'):
        raise Problem(502, 'No picture.')
    _avatars[url] = (time.time(), data, kind)
    return data, kind



# ---------- the three tabs (Goals, To test, Issues) ----------

VIEW_FIELDS = (' number title url body createdAt updatedAt author { login } assignees(first: 1) { nodes { login } }'
               ' repository { nameWithOwner } labels(first: 20) { nodes { name } }'
               ' comments(last: 20) { nodes { author { login } body createdAt } }'
               ' timelineItems(itemTypes: [CROSS_REFERENCED_EVENT, CONNECTED_EVENT], last: 60) { nodes {'
               '  ... on CrossReferencedEvent { source { __typename'
               '    ... on Issue { number url state repository { nameWithOwner } }'
               '    ... on PullRequest { number url state title repository { nameWithOwner } } } }'
               '  ... on ConnectedEvent { subject { __typename ... on PullRequest { number url state title repository { nameWithOwner } } } }'
               ' } }')
VIEW = 'query($q: String!) { search(query: $q, type: ISSUE, first: 80) { issueCount nodes { ... on Issue {' + VIEW_FIELDS + ' } } } }'
MAX_ITEMS = 300
# Lists page through search: light rows (no timeline or comments) 100 at a time for Bugs; the heavy
# fields (linked issues for goal progress, the builder's last comment for Ready to test) only where shown.
LIGHT_FIELDS = VIEW_FIELDS.split(' comments(last')[0]
HEAVY_FIELDS = VIEW_FIELDS.replace('comments(last: 20)', 'comments(last: 10)')
_PAGE = 'search(query: $q, type: ISSUE, first: %d, after: $after) { issueCount pageInfo { hasNextPage endCursor } nodes { ... on Issue {%s } } }'
PAGES = {heavy: ('query($q: String!, $after: String) { ' + _PAGE % (size, fields) + ' }',
                 # first page also counts what closed this week (authors too, so the who-wrote-it filter applies)
                 'query($q: String!, $after: String, $c: String!) { ' + _PAGE % (size, fields)
                 + ' closed: search(query: $c, type: ISSUE, first: 100) { issueCount nodes { ... on Issue { author { login } } } } }')
         for heavy, size, fields in ((False, 100, LIGHT_FIELDS), (True, 40, HEAVY_FIELDS))}
_tested = {}   # (token id, issue id) -> time: tested here, hidden from To test while search catches up
_made = {}     # (token id, issue id) -> (time, tab, item): created here, shown while search catches up


def _plain(text, limit):
    """Markdown-ish text to one short plain paragraph."""
    t = re.sub(r'```.*?```', ' ', text or '', flags=re.S)
    t = re.sub(r'<!--.*?-->', ' ', t, flags=re.S)
    t = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', t)
    t = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', t)
    t = re.sub(r'^\s{0,3}(#{1,6}|>|[-*+]\s+\[[ xX]\]|[-*+]|\d+\.)\s*', '', t, flags=re.M)
    t = re.sub(r'[*_`]{1,3}', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t if len(t) <= limit else t[:limit - 1].rsplit(' ', 1)[0] + '…'


def _refs(node):
    """Issues and PRs that link to or mention this issue (deduplicated, not itself)."""
    me, seen = node.get('url'), {}
    for t in (node.get('timelineItems') or {}).get('nodes') or []:
        x = (t or {}).get('source') or (t or {}).get('subject')
        if x and x.get('url') and x['url'] != me:
            seen[x['url']] = {'kind': 'pr' if x.get('__typename') == 'PullRequest' else 'issue', 'number': x.get('number'),
                              'url': x['url'], 'state': (x.get('state') or '').lower(), 'title': x.get('title'),
                              'repo': (x.get('repository') or {}).get('nameWithOwner')}
    return list(seen.values())


def _card(node, tab):
    labels = [l['name'].lower() for l in (node.get('labels') or {}).get('nodes') or []]
    author = (node.get('author') or {}).get('login')
    assignee = next((a.get('login') for a in (node.get('assignees') or {}).get('nodes') or [] if a), None)
    repo = node['repository']['nameWithOwner']
    out = {'id': f"{repo}#{node['number']}", 'repo': repo, 'number': node['number'], 'title': node.get('title'),
           'url': node.get('url'), 'author': author, 'updated_at': node.get('updatedAt'),
           'kind': 'goal' if 'goal' in labels else 'bug' if 'bug' in labels else 'issue',
           'waiting': 'ready-to-test' in labels, 'approved': 'approved' in labels}
    refs = _refs(node)
    if tab == 'goals':
        linked = [r for r in refs if r['kind'] == 'issue']  # issues that link to or mention the goal
        done = sum(1 for r in linked if r['state'] in ('closed', 'merged'))
        tasks = tasks_of(node.get('body'))
        if linked:
            prog = {'done': done, 'total': len(linked), 'of': 'linked issues'}
        elif tasks:
            prog = {'done': sum(t['done'] for t in tasks), 'total': len(tasks), 'of': 'done-list items'}
        else:
            prog = {'done': 0, 'total': 0, 'of': ''}
        status = ('ready' if 'ready-to-test' in labels else 'done' if prog['total'] and prog['done'] == prog['total']
                  else 'doing' if prog['done'] or linked else 'new')
        out.update(owner=assignee or author, progress=prog, status=status)
    elif tab == 'test':
        said = [c for c in (node.get('comments') or {}).get('nodes') or []
                if ((c.get('author') or {}).get('login') or '').lower() == BUILDER]
        out['check'] = re.sub(r'^(ready (to|for) test(ing)?)[.:!\s—-]*', '', _plain(said[-1]['body'], 320), flags=re.I) if said else ''
        out['check_from'] = 'builder' if said else ''
        if not said:  # first real line of the description (not a "Part of #13" link line)
            lines = [_plain(x, 220) for x in re.split(r'\n\s*\n|\r?\n', node.get('body') or '')]
            out['check'] = next((x for x in lines if x and not re.fullmatch(r'(part of|closes|fixes|refs?)\s+\S*#\d+\.?', x, re.I)), '')
        prs = [r for r in refs if r['kind'] == 'pr']
        pr = next((r for r in prs if r['state'] == 'open'), None) or next((r for r in prs if r['state'] == 'merged'), None) or (prs[0] if prs else None)
        out['pr'] = {'url': pr['url'], 'number': pr['number'], 'repo': pr['repo']} if pr else None
    return out


def board_view(person, args):
    """One tab of the board, already filtered for the person looking."""
    _, acct = account_for(person)
    tab = args.get('tab') or 'goals'
    if tab not in ('goals', 'test', 'issues'):
        raise Problem(400, 'tab must be goals, test or issues.')
    org = settings()['org']
    repo = _repo(org, args.get('repo'))
    login = (acct.get('login') or '').strip()
    scope = 'repo:' + repo if repo else 'org:' + org
    q = {'goals': f'{scope} is:issue is:open label:goal',
         'test': f'{scope} is:issue is:open label:ready-to-test' + (f' -author:{login}' if NAME.match(login) else ''),
         'issues': f'{scope} is:issue is:open -label:goal'}[tab] + ' sort:updated-desc'
    if args.get('refresh'):
        _forget(acct['token'])
    found = ((graphql(acct['token'], VIEW, {'q': q}).get('data') or {}).get('search') or {})
    nodes = [n for n in found.get('nodes') or [] if n and n.get('number')]
    if tab == 'issues':  # bugs and unlabelled issues; ones waiting for someone else's test live in To test
        def plain_or_bug(n):
            names = {l['name'].lower() for l in (n.get('labels') or {}).get('nodes') or []}
            mine = ((n.get('author') or {}).get('login') or '').lower() == login.lower()
            return names <= {'bug', 'ready-to-test', 'approved', 'accepted'} and ('ready-to-test' not in names or mine)
        nodes = [n for n in nodes if plain_or_bug(n)]
    items = [_card(n, tab) for n in nodes]
    t, now = _tid(acct['token']), time.time()
    with LOCK:
        for k in [k for k, v in _tested.items() if now - v > RECENT_SECONDS]:
            _tested.pop(k, None)
        for k in [k for k, v in _made.items() if now - v[0] > RECENT_SECONDS]:
            _made.pop(k, None)
        hidden = {i for (k, i) in _tested if k == t}
        made = [v for (k, _), v in _made.items() if k == t and v[1] == tab]
    if tab == 'test':
        items = [i for i in items if i['id'] not in hidden]
    have = {i['id'] for i in items}
    for _, _, it in made:
        if it['id'] not in have and (not repo or it['repo'].lower() == repo.lower()):
            items.insert(0, it)
    return {'tab': tab, 'org': org, 'repo': repo, 'items': items, 'count': len(items),
            'more': found.get('issueCount', len(items)) > len(nodes) and tab != 'issues', 'login': login}


def _view_nodes(token, q, closed_q=None, heavy=False, limit=MAX_ITEMS):
    """Up to `limit` issues for one view, page by page, plus (if asked) this week's closed count."""
    nodes, after, total, closed = [], None, 0, {'issueCount': 0, 'nodes': []}
    rest, first = PAGES[heavy]
    while len(nodes) < limit:
        if after is None and closed_q:
            data = graphql(token, first, {'q': q, 'after': None, 'c': closed_q}).get('data') or {}
            closed = data.get('closed') or closed
        else:
            data = graphql(token, rest, {'q': q, 'after': after}).get('data') or {}
        found = data.get('search') or {}
        total = found.get('issueCount', total)
        nodes += [n for n in found.get('nodes') or [] if n and n.get('number')]
        page = found.get('pageInfo') or {}
        if not page.get('hasNextPage') or not page.get('endCursor'):
            break
        after = page['endCursor']
    return nodes[:limit], total, closed


def board_split(person, args):
    """0.4 screen: Goals or Bugs in status groups: Ready to test (label ready-to-test), Building (label
    building), Queued (every other open one), plus how many of that kind closed in the last 7 days."""
    _, acct = account_for(person)
    view = args.get('view') or 'goals'
    if view not in ('goals', 'bugs'):
        raise Problem(400, 'view must be goals or bugs.')
    org = settings()['org']
    login = (acct.get('login') or '').strip()
    kind = 'label:goal' if view == 'goals' else '-label:goal'
    q = f"org:{org} is:issue is:open {kind} sort:updated-desc"
    week = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%d')
    cq = f"org:{org} is:issue is:closed {kind} closed:>={week}"
    if args.get('refresh'):
        _forget(acct['token'])
    nodes, total, closed = _view_nodes(acct['token'], q, cq, heavy=view == 'goals')
    if view == 'bugs':  # the few waiting for a test get the heavy fields (what to check)
        full, _, _ = _view_nodes(acct['token'], q.replace(' sort:', ' label:ready-to-test sort:'), heavy=True, limit=80)
        by = {(n['repository']['nameWithOwner'], n['number']): n for n in full}
        nodes = [by.get((n['repository']['nameWithOwner'], n['number']), n) for n in nodes]
    t, now = _tid(acct['token']), time.time()
    with LOCK:
        hidden = {i for (k, i), v in _tested.items() if k == t and now - v <= RECENT_SECONDS}
        made = [v for (k, _), v in _made.items() if k == t and now - v[0] <= RECENT_SECONDS and v[1] == ('goals' if view == 'goals' else 'issues')]
    groups = {'test': [], 'building': [], 'queued': []}
    for n in nodes:
        names = {l['name'].lower() for l in (n.get('labels') or {}).get('nodes') or []}
        author = (n.get('author') or {}).get('login') or ''
        mine = bool(login) and author.lower() == login.lower()
        iid = f"{n['repository']['nameWithOwner']}#{n['number']}"
        if 'ready-to-test' in names and iid not in hidden:
            group, card = 'test', _card(n, 'test')
            if view == 'goals':
                card['owner'] = _card(n, 'goals')['owner']
        else:
            group = 'building' if 'building' in names else 'queued'
            card = _card(n, 'goals' if view == 'goals' else 'issues')
        card.update(group=group, mine=mine, created_at=n.get('createdAt'),
                    labels=[l['name'] for l in (n.get('labels') or {}).get('nodes') or []])
        groups[group].append(card)
    have = {i['id'] for g in groups.values() for i in g}
    for _, _, it in made:
        if it['id'] not in have:
            groups['queued'].insert(0, {**it, 'group': 'queued', 'mine': True})
    shown = sum(len(g) for g in groups.values())
    others_test = [c for c in groups['test'] if not c['mine']]
    return {'view': view, 'org': org, 'login': login, 'groups': groups,
            'counts': {k: len(v) for k, v in groups.items()},
            'closed_week': {'count': closed.get('issueCount', 0), 'since': week,
                            'authors': [((x or {}).get('author') or {}).get('login') or '' for x in closed.get('nodes') or []]},
            'total': total, 'shown': shown, 'more': total > len(nodes),
            # 0.3 shape, kept for older views and scripts
            'test': others_test, 'doing': [c for c in groups['test'] if c['mine']] + groups['building'] + groups['queued']}


# ---------- one issue in full, on tap (rendered by GitHub, cleaned here) ----------

class _Clean(HTMLParser):
    """Whitelist HTML cleaner for GitHub's body_html: no scripts, frames, styles, event handlers or
    javascript: links. Images and videos become plain links (the view only loads from itself)."""
    KEEP = {'a', 'p', 'br', 'hr', 'strong', 'b', 'em', 'i', 'del', 's', 'code', 'pre', 'blockquote', 'ul', 'ol', 'li',
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'span', 'div', 'sup', 'sub',
            'kbd', 'details', 'summary', 'input', 'dl', 'dt', 'dd', 'tt', 'g-emoji', 'mark', 'ins'}
    DROP = {'script', 'style', 'iframe', 'object', 'embed', 'svg', 'math', 'form', 'noscript', 'template', 'textarea',
            'select', 'button', 'frame', 'frameset', 'head', 'title', 'link', 'meta', 'base', 'audio', 'canvas', 'option'}
    VOID = {'br', 'hr', 'input', 'img', 'source', 'wbr', 'track', 'area', 'col', 'param'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.skip, self.links = [], [], 0, 0

    @staticmethod
    def url(v):
        v = (v or '').strip()
        if v.startswith('/') and not v.startswith('//'):
            v = 'https://github.com' + v
        return v if re.match(r'^(https?://|mailto:)', v, re.I) and not any(c in v for c in '\x00\n\r\t') else ''

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.skip:
            if tag in self.DROP and tag not in self.VOID:
                self.skip += 1
            return
        if tag in self.DROP:
            self.skip = 1
            return
        if tag in ('img', 'video'):
            src = self.url(a.get('data-canonical-src') or a.get('src'))
            label = ('Video' if tag == 'video' else 'Image') + (f": {a['alt']}" if a.get('alt') and tag == 'img' and a['alt'] != 'image' else '')
            if src and not self.links:
                self.out.append(f'<a class="bd-media" href="{htmllib.escape(src)}" target="_blank" rel="noopener noreferrer">{htmllib.escape(label)} ↗</a>')
            else:
                self.out.append(htmllib.escape(f'[{label}]'))
            if tag == 'video':
                self.skip = 1  # drop any fallback/source children
            return
        if tag not in self.KEEP:
            return
        name = 'span' if tag == 'g-emoji' else tag
        keep = ''
        if tag == 'a':
            href = self.url(a.get('href'))
            if self.links:
                return  # no nested links
            keep = (f' href="{htmllib.escape(href)}" target="_blank" rel="noopener noreferrer"' if href else '')
            self.links += 1
        elif tag == 'input':
            if (a.get('type') or '').lower() != 'checkbox':
                return
            keep = ' type="checkbox" disabled' + (' checked' if 'checked' in a else '')
        elif tag in ('td', 'th') and (a.get('align') or '') in ('left', 'right', 'center'):
            keep = f' align="{a["align"]}"'
        elif tag == 'ol' and (a.get('start') or '').isdigit():
            keep = f' start="{a["start"]}"'
        self.out.append(f'<{name}{keep}>')
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID and self.stack and self.stack[-1] == tag:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.skip:
            if tag in self.DROP or tag == 'video':
                self.skip -= 1
            return
        if tag not in self.stack:
            return
        while self.stack:
            t = self.stack.pop()
            if t == 'a':
                self.links -= 1
            self.out.append(f"</{'span' if t == 'g-emoji' else t}>")
            if t == tag:
                break

    def handle_data(self, data):
        if not self.skip:
            self.out.append(htmllib.escape(data, quote=False))

    def result(self):
        self.close()
        while self.stack:
            t = self.stack.pop()
            self.out.append(f"</{'span' if t == 'g-emoji' else t}>")
        return ''.join(self.out)


def clean_html(raw):
    c = _Clean()
    c.feed(raw or '')
    return c.result()


HTML_JSON = 'application/vnd.github.html+json'


def issue_detail(person, args):
    """Full issue for the in-app detail: GitHub-rendered body and comments, cleaned. Two REST calls,
    cached 60 s per token like every other read."""
    _, acct = account_for(person)
    full, number = _target(args or {})
    if args.get('refresh'):
        _forget(acct['token'])
    it = gh(acct['token'], 'GET', f'/repos/{full}/issues/{number}', accept=HTML_JSON)
    if it.get('pull_request'):
        raise Problem(400, 'That is a pull request, not an issue.')
    count = it.get('comments') or 0
    rows = gh(acct['token'], 'GET', f'/repos/{full}/issues/{number}/comments?per_page=100', accept=HTML_JSON) if count else []
    who = lambda x: ((x or {}).get('user') or {}).get('login')
    return {'id': f'{full}#{number}', 'repo': full, 'number': number, 'title': it.get('title'), 'url': it.get('html_url'),
            'state': it.get('state'), 'author': who(it), 'created_at': it.get('created_at'), 'updated_at': it.get('updated_at'),
            'labels': [l.get('name') for l in it.get('labels') or [] if isinstance(l, dict)],
            'body_html': clean_html(it.get('body_html')),
            'comments': [{'author': who(c), 'created_at': c.get('created_at'), 'url': c.get('html_url'),
                          'body_html': clean_html(c.get('body_html'))} for c in rows if isinstance(c, dict)],
            'comments_total': count}


def _drop_label(acct, full, number, label):
    try:
        gh(acct['token'], 'DELETE', f'/repos/{full}/issues/{number}/labels/{label}')
    except Problem as e:
        if e.code != 404:  # already gone is fine
            raise


def tested(person, args, works):
    _, acct = account_for(person)
    full, number = _target(args)
    login = acct.get('login') or 'someone'
    names = [l.get('name', '').lower() for l in _current(acct, full, number).get('labels') or []]
    if 'ready-to-test' not in names:
        raise Problem(409, 'This is not waiting for a test any more. Refresh to see the latest.')
    if works:
        body = f'Tested: works — @{login}'
    else:
        note = _text(args.get('note'), 'What went wrong', 3, 4000)
        body = f"Tested: doesn't work — @{login}\n\n{note}"
    gh(acct['token'], 'POST', f'/repos/{full}/issues/{number}/comments', {'body': body})
    _drop_label(acct, full, number, 'ready-to-test')
    if works:
        gh(acct['token'], 'POST', f'/repos/{full}/issues/{number}/labels', {'labels': ['approved']})
    now = [l.get('name', '').lower() for l in _current(acct, full, number).get('labels') or []]
    if 'ready-to-test' in now or (works and 'approved' not in now):
        raise Problem(403, 'Your comment is saved, but GitHub did not change the labels (write access to this repo is needed).')
    with LOCK:
        _tested[(_tid(acct['token']), f'{full}#{number}')] = time.time()
    return {'id': f'{full}#{number}', 'repo': full, 'number': number, 'works': works, 'labels': now, 'saved': True}


def new_item(person, args):
    _, acct = account_for(person)
    kind = args.get('type') or 'issue'
    if kind not in ('goal', 'issue'):
        raise Problem(400, 'type must be goal or issue.')
    if kind == 'goal' and (acct.get('login') or '').lower() not in GOAL_AUTHORS:
        raise Problem(403, 'Only goal authors can add Goals. Add it as an Issue instead.')
    full = _repo(settings()['org'], args.get('repo') or DEFAULT_REPO)
    title = _text(args.get('title'), 'Title', 3, 200)
    body = args.get('body') or ''
    if not isinstance(body, str) or len(body) > 8000:
        raise Problem(400, 'The description is too long (8000 characters max).')
    made = _create(acct, full, title, body.strip(), 'goal' if kind == 'goal' else 'bug')
    owner, name = full.split('/')
    node = ((graphql(acct['token'], VIEW_ONE, {'o': owner, 'r': name, 'n': made['number']}, cache=False).get('data') or {}).get('repository') or {}).get('issue')
    tab = 'goals' if kind == 'goal' else 'issues'
    card = _card(node, tab) if node else {'id': made['id'], 'repo': full, 'number': made['number'], 'title': made['title'], 'url': made['url'],
                                         'author': made.get('author'), 'kind': 'goal' if kind == 'goal' else 'bug'}
    if made.get('labelled'):
        with LOCK:
            _made[(_tid(acct['token']), card['id'])] = (time.time(), tab, card)
    return {'tab': tab, 'item': card, 'warning': made.get('warning')}


# ---------- MCP ----------

FILTERS = {'repo': {'type': 'string', 'description': 'Repo name in the org, or owner/name.'},
           'type': {'type': 'string', 'enum': ['all', 'goal', 'bug']},
           'state': {'type': 'string', 'enum': ['open', 'closed']},
           'accepted': {'type': 'string', 'enum': ['any', 'yes', 'no'], 'description': 'Bugs only: accepted by a human or not.'},
           'org': {'type': 'string', 'description': 'GitHub org; defaults to the app setting.'}}
ISSUE = {'issue': {'type': 'string', 'description': 'owner/repo#123 or the issue URL.'},
         'repo': {'type': 'string'}, 'number': {'type': 'integer'}}
ASKED = {'owner_request': {'type': 'string', 'description': "Required: the human's own words asking for this action."}}
TOOLS = [
    {'name': 'board_list', 'description': 'List Goals and Bugs on the board (GitHub issues labelled goal or bug in the org). Goals include done-list progress and open linked PR counts.', 'inputSchema': {'type': 'object', 'properties': FILTERS}},
    {'name': 'board_get', 'description': 'Read one Goal or Bug: body, done-list, linked PRs and recent comments.', 'inputSchema': {'type': 'object', 'properties': ISSUE}},
    {'name': 'board_report_bug', 'description': 'Report a small, specific bug (label bug). Anyone may report. Work starts only after a human accepts it.', 'inputSchema': {'type': 'object', 'properties': {'repo': {'type': 'string'}, 'title': {'type': 'string', 'minLength': 3, 'maxLength': 200}, 'body': {'type': 'string', 'description': 'What happens, what should happen, how to see it.'}}, 'required': ['repo', 'title']}},
    {'name': 'board_comment', 'description': 'Add a comment to a Goal or Bug.', 'inputSchema': {'type': 'object', 'properties': {**ISSUE, 'body': {'type': 'string', 'minLength': 1}}, 'required': ['body']}},
    {'name': 'board_add_goal', 'description': 'HUMANS OPEN GOALS. Use only when a human explicitly asked you to add this goal for them; pass their words as owner_request.', 'inputSchema': {'type': 'object', 'properties': {'repo': {'type': 'string'}, 'title': {'type': 'string'}, 'done': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Done-list lines (1-20).'}, 'body': {'type': 'string'}, **ASKED}, 'required': ['repo', 'title', 'done', 'owner_request']}},
    {'name': 'board_accept_bug', 'description': 'ONLY HUMANS ACCEPT BUGS. Adds label accepted only when a human explicitly asked you to; pass their words as owner_request.', 'inputSchema': {'type': 'object', 'properties': {**ISSUE, **ASKED}, 'required': ['owner_request']}},
    {'name': 'board_close', 'description': 'Close a Bug when a human asked you to (pass their words). Goals are refused: only humans close goals, in the app.', 'inputSchema': {'type': 'object', 'properties': {**ISSUE, 'reason': {'type': 'string', 'enum': ['completed', 'not_planned']}, **ASKED}, 'required': ['owner_request']}},
    {'name': 'board_reopen', 'description': 'Reopen a Bug when a human asked you to (pass their words). Goals are refused: only humans reopen goals.', 'inputSchema': {'type': 'object', 'properties': {**ISSUE, **ASKED}, 'required': ['owner_request']}},
]
CALLS = {
    'board_list': lambda a: board_list(None, a, agent=True),
    'board_get': lambda a: board_get(None, a, agent=True),
    'board_report_bug': lambda a: report_bug(None, a, agent=True),
    'board_comment': lambda a: add_comment(None, a, agent=True),
    'board_add_goal': lambda a: add_goal(None, a, agent=True),
    'board_accept_bug': lambda a: accept_bug(None, a, agent=True),
    'board_close': lambda a: set_state(None, a, 'closed', agent=True),
    'board_reopen': lambda a: set_state(None, a, 'open', agent=True),
}


def rpc(msg):
    if not isinstance(msg, dict):
        return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Expected a JSON-RPC object.'}}
    m, i, p = msg.get('method'), msg.get('id'), msg.get('params') or {}
    if 'id' not in msg:
        return None
    try:
        if m == 'initialize':
            r = {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}}, 'serverInfo': {'name': APP_ID, 'version': VERSION},
                 'instructions': 'Board rules: agents may list, read, report bugs and comment. Never open, close or reopen goals on your own; only humans accept bugs.'}
        elif m == 'tools/list':
            r = {'tools': TOOLS}
        elif m == 'tools/call':
            a = p.get('arguments') or {}
            if not isinstance(a, dict):
                raise Problem(400, 'arguments must be an object.')
            fn = CALLS.get(p.get('name'))
            if not fn:
                return {'jsonrpc': '2.0', 'id': i, 'error': {'code': -32602, 'message': 'Unknown tool.'}}
            value = fn(a)
            r = {'content': [{'type': 'text', 'text': json.dumps(value)}], 'structuredContent': value, 'isError': False}
        elif m == 'ping':
            r = {}
        else:
            return {'jsonrpc': '2.0', 'id': i, 'error': {'code': -32601, 'message': 'Unknown method.'}}
    except Problem as e:
        r = {'content': [{'type': 'text', 'text': e.message}], 'isError': True}
    return {'jsonrpc': '2.0', 'id': i, 'result': r}


def _csv(name):
    return {x.strip().lower() for x in os.environ.get(name, '').split(',') if x.strip()}


# Who may talk to this app. Trust never comes from the request itself: the Host must be one this app
# was configured for (stops DNS rebinding), and a browser Origin on writes must be configured too.
_LOOPBACK = {f"127.0.0.1:{os.environ.get('PORT', '8799')}", f"localhost:{os.environ.get('PORT', '8799')}"}
TRUSTED_HOSTS = _csv('WIZARD_TRUSTED_HOSTS') | _LOOPBACK
TRUSTED_ORIGINS = _csv('WIZARD_TRUSTED_ORIGINS') | {'http://' + h for h in _LOOPBACK}


class Handler(BaseHTTPRequestHandler):
    def refused(self, write=False):
        if (self.headers.get('Host') or '').lower() not in TRUSTED_HOSTS:
            self.send(403, {'error': 'Unknown host.'})
            return True
        if write:
            origin = (self.headers.get('Origin') or '').lower()
            if origin and origin not in TRUSTED_ORIGINS:
                self.send(403, {'error': 'Cross-origin writes refused.'})
                return True
            if not origin and (self.headers.get('Sec-Fetch-Site') or '') == 'cross-site':
                self.send(403, {'error': 'Cross-origin writes refused.'})
                return True
        return False

    def person(self):
        # Each person signs in with their own token. Behind the Wizard gateway the tailnet login names them.
        return self.headers.get('Tailscale-User-Login') or ''

    def send(self, code, body=None, content_type='application/json'):
        b = body if isinstance(body, bytes) else b'' if body is None else json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'self'")
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(b)

    def do_GET(self):
        if self.refused():
            return
        u = urlsplit(self.path)
        path, q = u.path, {k: v[0] for k, v in parse_qs(u.query).items()}
        if path == '/healthz':
            return self.send(200, {'ok': True, 'app': APP_ID, 'version': VERSION})
        try:
            if path == '/api/status':
                return self.send(200, status(self.person()))
            if path == '/api/view':
                return self.send(200, board_view(self.person(), {**q, 'refresh': q.get('refresh') == '1'}))
            if path == '/api/detail':
                return self.send(200, issue_detail(self.person(), {**q, 'refresh': q.get('refresh') == '1'}))
            if path == '/api/split':
                return self.send(200, board_split(self.person(), {**q, 'refresh': q.get('refresh') == '1'}))
            if path == '/api/board':
                return self.send(200, board_list(self.person(), {**q, 'refresh': q.get('refresh') == '1'}))
            if path == '/api/issue':
                return self.send(200, board_get(self.person(), q, fresh=q.get('fresh') == '1'))
            if path == '/api/repos':
                return self.send(200, repos(self.person()))
            if path == '/api/boxes':
                return self.send(200, boxes(self.person()))
            if path == '/api/avatar':
                data, kind = avatar(self.person())
                return self.send(200, data, kind)
        except Problem as e:
            return self.send(e.code, {'error': e.message})
        name = 'index.html' if path == '/' else path[1:]
        kind = STATIC_TYPES.get(Path(name).suffix)
        if kind and '/' not in name and not name.startswith('.') and (ROOT / 'web' / name).is_file():
            return self.send(200, (ROOT / 'web' / name).read_bytes(), kind)
        if path == '/openapi.json':
            return self.send(200, (ROOT / 'openapi.json').read_bytes())
        self.send(405 if path == '/mcp' else 404, {'error': 'Use POST /mcp.' if path == '/mcp' else 'Not found.'})

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        if self.refused(write=True):
            return
        path = urlsplit(self.path).path
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.send(415, {'error': 'Use application/json.'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 <= size <= 65536:
                return self.send(413, {'error': 'Request too large.'})
            body = json.loads(self.rfile.read(size))
            if path == '/mcp':
                if not isinstance(body, dict):
                    return self.send(400, {'error': 'Expected a JSON-RPC object.'})
                out = rpc(body)
                return self.send(202 if out is None else 200, out)
            if not isinstance(body, dict):
                return self.send(400, {'error': 'Expected a JSON object.'})
            who = self.person()
            routes = {
                '/api/connect': lambda: connect(who, body),
                '/api/disconnect': lambda: disconnect(who),
                '/api/settings': lambda: set_org(body),
                '/api/goals': lambda: add_goal(who, body),
                '/api/bugs': lambda: report_bug(who, body),
                '/api/issue/accept': lambda: accept_bug(who, body),
                '/api/issue/close': lambda: set_state(who, body, 'closed'),
                '/api/issue/reopen': lambda: set_state(who, body, 'open'),
                '/api/issue/task': lambda: set_task(who, body),
                '/api/issue/comment': lambda: add_comment(who, body),
                '/api/new': lambda: new_item(who, body),
                '/api/test/works': lambda: tested(who, body, True),
                '/api/test/fails': lambda: tested(who, body, False),
            }
            if path not in routes:
                return self.send(404, {'error': 'Not found.'})
            return self.send(201 if path in ('/api/goals', '/api/bugs', '/api/new') else 200, routes[path]())
        except Problem as e:
            self.send(e.code, {'error': e.message})
        except (ValueError, TypeError, AttributeError, KeyError):
            self.send(400, {'error': 'Invalid request.'})

    def log_message(self, format, *args):
        pass


if __name__ == '__main__':
    secure_start()
    ThreadingHTTPServer((os.environ.get('BIND', '0.0.0.0'), int(os.environ.get('PORT', '8799'))), Handler).serve_forever()
