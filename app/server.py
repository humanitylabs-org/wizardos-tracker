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
VERSION = '0.12.0'
GITHUB = os.environ.get('GITHUB_API', 'https://api.github.com').rstrip('/')
DEFAULT_ORG = os.environ.get('BOARD_DEFAULT_ORG', 'humanitylabs-org')
TOKEN_URL = 'https://github.com/settings/personal-access-tokens/new'
# Only these people may open Goals in the app (GitHub logins, comma separated).
GOAL_AUTHORS = {x.strip().lower() for x in os.environ.get('GOAL_AUTHORS', 'jdefleur').split(',') if x.strip()}
# The builder agent's GitHub account: it labels finished work ready-to-test and says what to check.
BUILDER = os.environ.get('BOARD_BUILDER', 'wizardosbuilder').strip().lower()
DEFAULT_REPO = os.environ.get('BOARD_DEFAULT_REPO', 'wizard-ux')
MEDIA_REPO = os.environ.get('BOARD_MEDIA_REPO', 'humanitylabs-org/wizard-issue-media')
# 0.12: the human UI is for the team only. Signing in needs an active member of this org, and a person's
# own GitHub account (agent and builder accounts are refused; agents use the MCP tools instead).
TEAM_ORG = os.environ.get('BOARD_TEAM_ORG', 'humanitylabs-org').strip()
AGENT_LOGINS = {'oscarhenrycollins', 'defleur-agents', 'wizardosbuilder'}
MEMBER_SECONDS = 600
NOT_MEMBER = f'This tracker is for the Wizard OS team. Ask an owner of {TEAM_ORG} to add you.'
NOT_HUMAN = "Sign in with your own GitHub account, not your agent's. Agents use the Tracker's tools instead."
CACHE_SECONDS = 60
STATS_SECONDS = 300
STATIC_TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml'}
NAME = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,99})$')
TASK = re.compile(r'^(\s*[-*+]\s+\[)([ xX])(\]\s?)(.*)$')
LOCK = threading.Lock()


class Problem(Exception):
    def __init__(self, code, message, reason=None):
        super().__init__(message)
        self.code, self.message, self.reason = code, message, reason


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
    if not agent:
        _check_person(key, acct)
    return key, acct


# ---------- 0.12: team-only, human-only (the human UI; MCP tools are unchanged) ----------

_members = {}  # (token id, org, login) -> (checked at, member?)


def agent_logins(base=None):
    """Agent and builder accounts: the fixed set, the roster's agents and builder, and policy.json `agents`."""
    out = set(AGENT_LOGINS) | {BUILDER}
    try:
        base = base or policy_base()
        out |= {a['login'].lower() for t in base['team'] for a in t['agents']}
        out |= {x.lower() for x in base['builder']['logins']}
    except Exception:  # noqa: BLE001 -- a broken policy file never opens the gate wider
        pass
    extra = _policy_file().get('agents')
    if isinstance(extra, list):
        out |= {(x.get('login') if isinstance(x, dict) else x).lower() for x in extra
                if isinstance(x.get('login') if isinstance(x, dict) else x, str)}
    return out


def is_agent_login(login):
    return (login or '').strip().lower() in agent_logins()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_no_redirect = urllib.request.build_opener(_NoRedirect)


def _gh_code(token, path):
    """(status, json or None) for one GET, no redirects followed, nothing cached. Network trouble -> (0, None)."""
    req = urllib.request.Request(GITHUB + path, headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                                                         'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'wizard-board/' + VERSION})
    try:
        with _no_redirect.open(req, timeout=15) as r:
            raw = r.read(1 << 20)
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return 0, None


def _gql_member(token):
    """GraphQL organization.viewerIsAMember: True/False, None when GitHub gave no answer.
    Works for fine-grained tokens, which REST treats as outsiders without the org Members permission."""
    req = urllib.request.Request(GITHUB + '/graphql', data=json.dumps({'query': 'query($o: String!) { organization(login: $o) { viewerIsAMember } }',
                                                                       'variables': {'o': TEAM_ORG}}).encode(), method='POST',
                                 headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json', 'User-Agent': 'wizard-board/' + VERSION})
    try:
        with _no_redirect.open(req, timeout=15) as r:
            out = json.loads(r.read(1 << 20) or b'{}')
    except urllib.error.HTTPError as e:
        return 'bad' if e.code == 401 else None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    v = ((out.get('data') or {}).get('organization') or {}).get('viewerIsAMember') if isinstance(out, dict) else None
    return v if isinstance(v, bool) else None


def team_member(token, login, fresh=False):
    """Is `login` (the token's own user) an active member of TEAM_ORG? Cached 10 minutes.
    Checks in order, the first yes wins: GET /user/memberships/orgs/{org} state active; GraphQL
    viewerIsAMember; GET /orgs/{org}/members/{login} 204 (a 302 means GitHub sees the token as an outsider,
    then /public_members/{login} 204). No only on a definite answer; GitHub down or rate-limited raises 502
    (or keeps the last answer) and never signs anyone out."""
    key = (_tid(token), TEAM_ORG.lower(), (login or '').lower())
    with LOCK:
        hit = _members.get(key)
    if hit and not fresh and time.time() - hit[0] < MEMBER_SECONDS:
        return hit[1]
    code, body = _gh_code(token, f'/user/memberships/orgs/{TEAM_ORG}')
    answered = False
    ok = False
    if code == 200 and isinstance(body, dict):
        answered = True
        ok = body.get('state') == 'active' and ((body.get('user') or {}).get('login') or login).lower() == (login or '').lower()
    if not ok:
        g = _gql_member(token)
        if g == 'bad' or code == 401:
            raise Problem(401, 'GitHub refused this token (wrong or expired). Connect again with a new one.')
        if g is True:
            ok = True
        elif g is False:
            answered = True
    if not ok:
        code2, _ = _gh_code(token, f'/orgs/{TEAM_ORG}/members/{login}')
        if code2 == 204:
            ok = True
        elif code2 == 302:
            code3, _ = _gh_code(token, f'/orgs/{TEAM_ORG}/public_members/{login}')
            ok = code3 == 204
            answered = answered or code3 in (204, 404)
        elif code2 == 404:
            answered = True
    if not ok and not answered:
        if hit:
            return hit[1]
        raise Problem(502, 'Could not check your team membership with GitHub. Try again in a minute.')
    with LOCK:
        _members[key] = (time.time(), ok)
    return ok


def _sign_out(key, why):
    with LOCK:
        a = accounts()
        old = a['people'].pop(key, None)
        if old is None:
            return
        if a.get('default') == key:
            a['default'] = next(iter(a['people']), None)
        _write('accounts.json', a)
    if old.get('token'):
        _forget(old['token'])


def _check_person(key, acct):
    """A saved account that is an agent's, or whose user left the team, is signed out on its next use."""
    login = acct.get('login') or ''
    if is_agent_login(login):
        _sign_out(key, 'agent')
        raise Problem(403, NOT_HUMAN, 'agent')
    if not team_member(acct['token'], login):
        _sign_out(key, 'not_member')
        raise Problem(403, NOT_MEMBER, 'not_member')


def gate(person):
    """Every human write (and every human read through account_for): a signed-in, human team member."""
    return account_for(person)


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
    login = user.get('login') or ''
    # 0.12: team-only and human-only. Nothing is stored for a refused sign-in.
    if is_agent_login(login):
        raise Problem(403, NOT_HUMAN, 'agent')
    if not team_member(token, login):
        raise Problem(403, NOT_MEMBER, 'not_member')
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
    refused = None
    try:
        gate(person)
    except Problem as e:
        if e.reason in ('agent', 'not_member'):
            refused = {'reason': e.reason, 'message': e.message}
        elif e.code != 401:
            raise
    a = accounts()
    acct = a['people'].get(person_key(person))
    return {'refused': refused, 'team_org': TEAM_ORG, 'connected': bool(acct and acct.get('token')), 'account': public_account(acct) if acct else None,
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


ORG_REPOS_SECONDS = 3600
_org_repos = {}


def org_repos(token, org):
    """Every non-archived repo of the org (names, sorted), cached an hour per token/org. Used by the Bugs
    view's Repo chips so repos with no open bugs still show (dimmed). [] when GitHub refuses."""
    key = (_tid(token), org.lower())
    with LOCK:
        hit = _org_repos.get(key)
    if hit and time.time() - hit[0] < ORG_REPOS_SECONDS:
        return hit[1]
    rows = []
    try:
        for page in range(1, 6):
            got = gh(token, 'GET', f'/orgs/{org}/repos?per_page=100&type=all&page={page}')
            got = got if isinstance(got, list) else []
            rows += got
            if len(got) < 100:
                break
    except Problem as e:
        if e.code != 404:
            return hit[1] if hit else []
        try:  # a personal account (the sandbox): its own repos
            rows = []
            for page in range(1, 6):
                got = gh(token, 'GET', f'/users/{org}/repos?per_page=100&type=owner&page={page}')
                got = got if isinstance(got, list) else []
                rows += got
                if len(got) < 100:
                    break
        except Problem:
            return hit[1] if hit else []
    names = sorted({r['full_name'] for r in rows if isinstance(r, dict) and r.get('full_name') and not r.get('archived')}, key=str.lower)
    with LOCK:
        _org_repos[key] = (time.time(), names)
    return names


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

VIEW_FIELDS = (' number title url body createdAt updatedAt author { login } assignees(first: 10) { nodes { login } }'
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
LIGHT_FIELDS = VIEW_FIELDS.split(' comments(last')[0] + ' comments { totalCount }'
HEAVY_FIELDS = VIEW_FIELDS.replace('comments(last: 20) { nodes', 'comments(last: 10) { totalCount nodes')
_PAGE = 'search(query: $q, type: ISSUE, first: %d, after: $after) { issueCount pageInfo { hasNextPage endCursor } nodes { ... on Issue {%s } } }'
PAGES = {heavy: 'query($q: String!, $after: String) { ' + _PAGE % (size, fields) + ' }'
         for heavy, size, fields in ((False, 100, LIGHT_FIELDS), (True, 40, HEAVY_FIELDS))}
# Bottleneck stats: every issue of one kind (open and closed) with its label/close history, 100 a page.
STATS_PAGE = ('query($q: String!, $after: String) { search(query: $q, type: ISSUE, first: 100, after: $after) {'
              ' issueCount pageInfo { hasNextPage endCursor } nodes { ... on Issue { number state createdAt closedAt'
              ' author { login } repository { nameWithOwner }'
              ' timelineItems(itemTypes: [LABELED_EVENT, UNLABELED_EVENT, CLOSED_EVENT, REOPENED_EVENT], first: 100) { nodes {'
              ' __typename ... on LabeledEvent { createdAt label { name } } ... on UnlabeledEvent { createdAt label { name } }'
              ' ... on ClosedEvent { createdAt } ... on ReopenedEvent { createdAt } } } } } } }')
STATS_MAX = 600
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


_LINK_ONLY = re.compile(r'(part of|closes|fixes|refs?|related:?)\s+\S*#\d+\.?', re.I)


def describe(body, limit=400):
    """The first real paragraph of an issue body as plain text: stops at a line that is just ---,
    skips headings, bold-only label lines ("**What happens**"), comments and link-only lines."""
    text = re.sub(r'<!--.*?-->', ' ', body or '', flags=re.S)
    text = re.sub(r'```.*?```', '\n\n', text, flags=re.S)
    lines = []
    for line in text.replace('\r', '').split('\n'):
        if re.fullmatch(r'\s*-{3,}\s*', line):
            break
        if re.match(r'^\s{0,3}#{1,6}\s', line) or re.fullmatch(r'\s*(\*\*|__)[^*_]{1,80}(\*\*|__):?\s*', line):
            lines.append('')  # a heading ends a paragraph and is not part of one
            continue
        lines.append(line)
    for para in re.split(r'\n\s*\n', '\n'.join(lines)):
        plain = _plain(para, limit)
        if plain and not _LINK_ONLY.fullmatch(plain) and re.search(r'\w', plain):
            return plain
    return ''


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
           'waiting': 'ready-to-test' in labels, 'approved': 'approved' in labels,
           'assignees': [a.get('login') for a in (node.get('assignees') or {}).get('nodes') or [] if a and a.get('login')],
           'comments': ((node.get('comments') or {}).get('totalCount')), 'desc': describe(node.get('body'))}
    if out['comments'] is None:
        out['comments'] = len((node.get('comments') or {}).get('nodes') or [])
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


def _view_nodes(token, q, heavy=False, limit=MAX_ITEMS, query=None):
    """Up to `limit` issues for one view, page by page."""
    nodes, after, total = [], None, 0
    rest = query or PAGES[heavy]
    while len(nodes) < limit:
        data = graphql(token, rest, {'q': q, 'after': after}).get('data') or {}
        found = data.get('search') or {}
        total = found.get('issueCount', total)
        nodes += [n for n in found.get('nodes') or [] if n and n.get('number')]
        page = found.get('pageInfo') or {}
        if not page.get('hasNextPage') or not page.get('endCursor'):
            break
        after = page['endCursor']
    return nodes[:limit], total


def _repo_list(arg):
    if not arg:
        return []
    names = [x.strip().lower() for x in str(arg).split(',') if x.strip()]
    return [n.split('/')[-1] for n in names if NAME.match(n.split('/')[-1])]


def board_split(person, args):
    """0.6 screen: Goals or Bugs in status groups: Waiting for review (label ready-to-test, key `test`),
    Building (label building), Queued (every other open one), plus all-time bottleneck stats for that kind."""
    _, acct = account_for(person)
    view = args.get('view') or 'goals'
    if view not in ('goals', 'bugs'):
        raise Problem(400, 'view must be goals or bugs.')
    org = settings()['org']
    login = (acct.get('login') or '').strip()
    kind = 'label:goal' if view == 'goals' else '-label:goal'
    q = f"org:{org} is:issue is:open {kind} sort:updated-desc"
    if args.get('refresh'):
        _forget(acct['token'])
    nodes, total = _view_nodes(acct['token'], q, heavy=view == 'goals')
    if view == 'bugs':  # the few waiting for a test get the heavy fields (what to check)
        full, _ = _view_nodes(acct['token'], q.replace(' sort:', ' label:ready-to-test sort:'), heavy=True, limit=80)
        by = {(n['repository']['nameWithOwner'], n['number']): n for n in full}
        nodes = [by.get((n['repository']['nameWithOwner'], n['number']), n) for n in nodes]
    t, now = _tid(acct['token']), time.time()
    with LOCK:
        hidden = {i for (k, i), v in _tested.items() if k == t and now - v <= RECENT_SECONDS}
        made = [v for (k, _), v in _made.items() if k == t and now - v[0] <= RECENT_SECONDS and v[1] == ('goals' if view == 'goals' else 'issues')]
    groups = {'test': [], 'building': [], 'queued': []}
    base = policy_base()
    for n in nodes:
        names = {l['name'].lower() for l in (n.get('labels') or {}).get('nodes') or []}
        author = (n.get('author') or {}).get('login') or ''
        mine = same_person(author, login, base)  # a person and their own agent count as one: they never review it
        iid = f"{n['repository']['nameWithOwner']}#{n['number']}"
        if 'ready-to-test' in names and iid not in hidden:
            group, card = 'test', _card(n, 'test')
            if view == 'goals':
                card['owner'] = _card(n, 'goals')['owner']
        else:
            group = 'building' if 'building' in names else 'queued'
            card = _card(n, 'goals' if view == 'goals' else 'issues')
        card.update(group=group, mine=mine, opener=person_of(author, base), created_at=n.get('createdAt'),
                    labels=[l['name'] for l in (n.get('labels') or {}).get('nodes') or []])
        groups[group].append(card)
    have = {i['id'] for g in groups.values() for i in g}
    for _, _, it in made:
        if it['id'] not in have:
            groups['queued'].insert(0, {**it, 'group': 'queued', 'mine': True})
    # Stats ride along when cached; otherwise the view asks GET /api/stats right after (keeps the list fast).
    stats = view_stats(acct['token'], org, view, cached_only=not args.get('with_stats')) or {'pending': True, 'items': [], 'done': None}
    repos_wanted = _repo_list(args.get('repos'))
    if repos_wanted:  # optional server-side repo filter (the view filters itself, scripts may use this)
        keep = lambda i: i['repo'].split('/')[-1].lower() in repos_wanted
        groups = {k: [i for i in v if keep(i)] for k, v in groups.items()}
        stats = _filter_stats(stats, keep)
    shown = sum(len(g) for g in groups.values())
    others_test = [c for c in groups['test'] if not c['mine']]
    return {'view': view, 'org': org, 'login': login, 'me_person': person_of(login, base), 'steps': steps_for(view, base), 'groups': groups,
            'targets': base['targets'][view], 'names': display_names(base), 'since': base['since'],
            # 0.9: Bugs shows a Repo chip for every non-archived org repo (owner/name), even with 0 open bugs
            'repos': org_repos(acct['token'], org) if view == 'bugs' else [],
            'counts': {k: len(v) for k, v in groups.items()}, 'done': stats.get('done', 0),
            'stats': {**stats, 'summary': None if stats.get('pending') else summarize(stats.get('items', []))},
            'total': total, 'shown': shown, 'more': total > len(nodes),
            # 0.3 shape, kept for older views and scripts
            'test': others_test, 'doing': [c for c in groups['test'] if c['mine']] + groups['building'] + groups['queued']}


# ---------- bottleneck stats (label history, cached 5 min per token/org/view) ----------

_stats = {}


def _ts(iso):
    try:
        return datetime.fromisoformat((iso or '').replace('Z', '+00:00')).timestamp()
    except ValueError:
        return None


def history_of(ev, opened, closed_at, state, now=None):
    """One issue's workflow numbers from its sorted label/close events [(ts, kind, label)], kinds
    LabeledEvent | UnlabeledEvent | ClosedEvent | ReopenedEvent. Seconds; None when a step never happened.
    wait = opened -> first `building`; build = first `building` -> first `ready-to-test`;
    review_rounds = each `ready-to-test` stint that ended (closed or kicked back); total = opened -> closed;
    tries = times labelled ready-to-test; kicks = ready-to-test removed without a close or `approved`
    within 10 minutes (that is \"Doesn't work\"); kick_to_done = first kick-back -> closed;
    spent = time this item spent in each stage (queued/building/review), done = closed time."""
    now = now or time.time()
    first_build = next((t for t, k, l in ev if k == 'LabeledEvent' and l == 'building'), None)
    first_ready = next((t for t, k, l in ev if k == 'LabeledEvent' and l == 'ready-to-test'), None)
    tries = sum(1 for t, k, l in ev if k == 'LabeledEvent' and l == 'ready-to-test')
    kick_times = []
    for t, k, l in ev:
        if k == 'UnlabeledEvent' and l == 'ready-to-test':
            soon = [x for x in ev if t <= x[0] <= t + 600]
            if not any(x[1] == 'ClosedEvent' or (x[1] == 'LabeledEvent' and x[2] == 'approved') for x in soon):
                kick_times.append(t)
    # Walk the timeline as a small state machine: queued -> building -> review -> (kick: building) -> done.
    spent = {'queued': 0.0, 'building': 0.0, 'review': 0.0}
    rounds, stage, since, built, review_from = [], 'queued', opened if opened is not None else (ev[0][0] if ev else now), False, None
    kicks_set = set(kick_times)
    def move(to, t):
        nonlocal stage, since
        if stage in spent and t >= since:
            spent[stage] += t - since
        stage, since = to, t
    for t, k, l in ev:
        if k == 'LabeledEvent' and l == 'building' and stage == 'queued':
            built = True
            move('building', t)
        elif k == 'LabeledEvent' and l == 'ready-to-test' and stage in ('queued', 'building'):
            built = True
            review_from = t
            move('review', t)
        elif k == 'UnlabeledEvent' and l == 'ready-to-test' and stage == 'review' and t in kicks_set:
            rounds.append(t - review_from)
            move('building', t)
        elif k == 'ClosedEvent' and stage != 'done':
            if stage == 'review' and review_from is not None:
                rounds.append(t - review_from)
            move('done', t)
        elif k == 'ReopenedEvent' and stage == 'done':
            move('building' if built else 'queued', t)
    if stage != 'done':
        move(stage, now)
    labelled = {}
    for t, k, l in ev:
        if k == 'LabeledEvent':
            labelled[l] = t
        elif k == 'UnlabeledEvent':
            labelled.pop(l, None)
    is_open = (state or '').lower() == 'open'
    ready_since = labelled.get('ready-to-test') if is_open else None
    closed_ts = _ts(closed_at) if closed_at else None
    rnd = lambda x: None if x is None else int(x)
    # current stage by labels (what the board shows), not by the walk
    current = 'done' if not is_open else 'review' if 'ready-to-test' in labelled else 'building' if 'building' in labelled else 'queued'
    has = lambda x: x is not None
    return {'wait': rnd(first_build - opened) if has(first_build) and has(opened) else None,
            'build': rnd(first_ready - first_build) if has(first_ready) and has(first_build) and first_ready >= first_build else None,
            'review_rounds': [int(r) for r in rounds if r >= 0],
            'total': rnd(closed_ts - opened) if has(closed_ts) and has(opened) and not is_open else None,
            'tries': tries, 'kicks': len(kick_times),
            'kick_to_done': rnd(closed_ts - kick_times[0]) if kick_times and has(closed_ts) and not is_open else None,
            'waiting_for': rnd(now - ready_since) if ready_since else None,
            'stage': current, 'spent': {k: int(v) for k, v in spent.items()}, 'staged': built or bool(first_build or first_ready),
            'opened_at': rnd(opened), 'closed_at': rnd(closed_ts) if not is_open else None}


def item_history(node, now=None):
    ev = sorted(((_ts(e.get('createdAt')), e.get('__typename'), ((e.get('label') or {}).get('name') or '').lower())
                 for e in (node.get('timelineItems') or {}).get('nodes') or [] if e and _ts(e.get('createdAt'))), key=lambda x: x[0])
    h = history_of(ev, _ts(node.get('createdAt')), node.get('closedAt'), node.get('state'), now)
    h.pop('spent', None)
    return {'id': f"{node['repository']['nameWithOwner']}#{node['number']}", 'repo': node['repository']['nameWithOwner'],
            'author': (node.get('author') or {}).get('login') or '', 'state': (node.get('state') or '').lower(), **h}


def spread(xs):
    """Average, median and the typical range p25–p75 (3+ points); `box` (min, p25, median, p75, max) kept for scripts."""
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return {'n': 0, 'avg': None, 'box': None}
    def q(p):
        i = (len(xs) - 1) * p
        lo = int(i)
        hi = min(lo + 1, len(xs) - 1)
        return int(xs[lo] + (xs[hi] - xs[lo]) * (i - lo))
    return {'n': len(xs), 'avg': int(sum(xs) / len(xs)), 'box': [xs[0], q(.25), q(.5), q(.75), xs[-1]] if len(xs) >= 3 else None,
            'median': q(.5), 'p25': q(.25) if len(xs) >= 3 else None, 'p75': q(.75) if len(xs) >= 3 else None}


def line_stats(items):
    """The assembly-line stats (0.8): per bin avg + box, and the return arrow's kick-back numbers.
    rate = share of items that reached Review and were kicked back at least once; per_item = average
    kick-backs among those kicked back."""
    reviewed = [i for i in items if i.get('tries')]
    kicked = [i for i in items if i.get('kicks')]
    to_done = [i['kick_to_done'] for i in kicked if i.get('kick_to_done') is not None]
    return {'queued': spread([i.get('wait') for i in items]), 'building': spread([i.get('build') for i in items]),
            'review': spread([r for i in items for r in i.get('review_rounds') or []]),
            'done': spread([i.get('total') for i in items]),
            'kick': {'reviewed': len(reviewed), 'kicked': len(kicked),
                     'rate': round(len(kicked) / len(reviewed), 3) if reviewed else None,
                     'per_item': round(sum(i['kicks'] for i in kicked) / len(kicked), 2) if kicked else None,
                     'to_done': int(sum(to_done) / len(to_done)) if to_done else None}}


def summarize(items):
    """Averages over history records (same maths the view runs after its own filters)."""
    avg = lambda xs: int(sum(xs) / len(xs)) if xs else None
    tried = [i['tries'] for i in items if i['tries']]
    waiting = [i['waiting_for'] for i in items if i['waiting_for'] is not None]
    return {'wait_before_build': avg([i['wait'] for i in items if i['wait'] is not None]),
            'build_time': avg([i['build'] for i in items if i['build'] is not None]),
            'waiting_for_human': avg(waiting), 'waiting_longest': max(waiting) if waiting else None,
            'tries_per_item': round(sum(tried) / len(tried), 2) if tried else None,
            'kicked_back': sum(i['kicks'] for i in items), 'done': sum(1 for i in items if i['state'] == 'closed'),
            'items': len(items), 'line': line_stats(items)}


_flows = {}
FLOW_SECONDS = 120
_REST_KIND = {'labeled': 'LabeledEvent', 'unlabeled': 'UnlabeledEvent', 'closed': 'ClosedEvent', 'reopened': 'ReopenedEvent'}


def item_flow(person, args, agent=False):
    """GET /api/flow?repo=&number=: one item's own assembly line from its GitHub timeline (REST timeline API,
    on demand, cached 2 minutes): time spent in Queued, Building and Review, the Done date, kick-backs, stage."""
    _, acct = account_for(person, agent)
    full, number = _target(args or {})
    key = (_tid(acct['token']), full.lower(), number)
    with LOCK:
        hit = _flows.get(key)
    if hit and time.time() - hit[0] < FLOW_SECONDS and not args.get('refresh'):
        return hit[1]
    it = gh(acct['token'], 'GET', f'/repos/{full}/issues/{number}')
    if it.get('pull_request'):
        raise Problem(400, 'That is a pull request, not an issue.')
    rows = []
    for page in range(1, 4):
        got = gh(acct['token'], 'GET', f'/repos/{full}/issues/{number}/timeline?per_page=100&page={page}')
        got = got if isinstance(got, list) else []
        rows += got
        if len(got) < 100:
            break
    ev = sorted(((_ts(e.get('created_at')), _REST_KIND[e.get('event')], ((e.get('label') or {}).get('name') or '').lower())
                 for e in rows if isinstance(e, dict) and e.get('event') in _REST_KIND and _ts(e.get('created_at'))), key=lambda x: x[0])
    h = history_of(ev, _ts(it.get('created_at')), it.get('closed_at'), it.get('state'))
    out = {'id': f'{full}#{number}', 'repo': full, 'number': number, 'state': it.get('state'), **h, 'computed_at': int(time.time())}
    with LOCK:
        _flows[key] = (time.time(), out)
        if len(_flows) > 300:
            for k in sorted(_flows, key=lambda k: _flows[k][0])[:100]:
                _flows.pop(k, None)
    return out


DONE_FIELDS = LIGHT_FIELDS + ' closedAt stateReason'
DONE_PAGE = 'query($q: String!, $after: String) { ' + _PAGE % (50, DONE_FIELDS) + ' }'


def done_list(person, args):
    """GET /api/done?view=goals|bugs: the most recently closed items of that view (up to 50, newest first)."""
    _, acct = account_for(person)
    view = args.get('view') or 'goals'
    if view not in ('goals', 'bugs'):
        raise Problem(400, 'view must be goals or bugs.')
    org = settings()['org']
    kind = 'label:goal' if view == 'goals' else '-label:goal'
    if args.get('refresh'):
        _forget(acct['token'])
    nodes, total = _view_nodes(acct['token'], f'org:{org} is:issue is:closed {kind} sort:updated-desc', limit=50, query=DONE_PAGE)
    base = policy_base()
    ts = since_ts(base)
    items = []
    for n in nodes:
        if not counts_since('closed', n.get('closedAt'), ts):  # 0.11: only closed since the reset date
            continue
        card = _card(n, 'goals' if view == 'goals' else 'issues')
        author = (n.get('author') or {}).get('login') or ''
        card.update(group='done', mine=same_person(author, acct.get('login') or '', base), opener=person_of(author, base),
                    created_at=n.get('createdAt'), closed_at=n.get('closedAt'), state_reason=(n.get('stateReason') or '').lower() or None,
                    labels=[l['name'] for l in (n.get('labels') or {}).get('nodes') or []])
        items.append(card)
    items.sort(key=lambda i: i.get('closed_at') or '', reverse=True)
    repos_wanted = _repo_list(args.get('repos'))
    if repos_wanted:
        items = [i for i in items if i['repo'].split('/')[-1].lower() in repos_wanted]
    return {'view': view, 'org': org, 'items': items, 'count': len(items), 'total': total, 'since': base['since']}


def _filter_stats(stats, keep):
    if stats.get('pending') or stats.get('error'):
        return stats
    items = [i for i in stats.get('items', []) if keep(i)]
    return {**stats, 'items': items, 'done': sum(1 for i in items if i['state'] == 'closed')}


def stats_view(person, args):
    """GET /api/stats: bottleneck numbers for one view (optionally author= and repos=a,b), 5-minute cache."""
    _, acct = account_for(person)
    view = args.get('view') or 'goals'
    if view not in ('goals', 'bugs'):
        raise Problem(400, 'view must be goals or bugs.')
    stats = view_stats(acct['token'], settings()['org'], view)
    repos_wanted, author = _repo_list(args.get('repos')), (args.get('author') or '').strip().lower()
    if repos_wanted or author:
        stats = _filter_stats(stats, lambda i: (not repos_wanted or i['repo'].split('/')[-1].lower() in repos_wanted)
                              and (not author or i['author'].lower() == author))
    return {'view': view, **stats, 'since': policy_base()['since'], 'summary': summarize(stats.get('items', []))}


def view_stats(token, org, view, cached_only=False):
    key = (_tid(token), org, view)
    with LOCK:
        hit = _stats.get(key)
    if hit and time.time() - hit[0] < STATS_SECONDS:
        return _since_stats(hit[1])
    if cached_only:
        return None
    kind = 'label:goal' if view == 'goals' else '-label:goal'
    nodes, total = _view_nodes(token, f'org:{org} is:issue {kind} sort:created-desc', limit=STATS_MAX, query=STATS_PAGE)
    now = time.time()
    items = [item_history(n, now) for n in nodes if n.get('repository')]
    out = {'items': items, 'done': sum(1 for i in items if i['state'] == 'closed'), 'counted': len(items),
           'total': total, 'computed_at': int(now), 'cache_seconds': STATS_SECONDS}
    with LOCK:
        _stats[key] = (now, out)
    return _since_stats(out)


def _since_stats(out):
    """0.11: drop items closed before the reset date (the cache keeps all, so a changed date applies at once)."""
    iso = policy_base()['since']
    ts = _since(iso)[1]
    items = [i for i in out.get('items', []) if counts_since(i.get('state'), i.get('closed_at'), ts)]
    return {**out, 'items': items, 'done': sum(1 for i in items if i['state'] == 'closed'), 'counted': len(items), 'since': iso}


# ---------- policy (Open -> Build -> Review: who does each step) and the builder switch ----------

# 0.6: the workflow is three hand-off steps, Open -> Build -> Review. The team roster groups GitHub logins by
# person (a person and their own agents count as one person: nobody reviews what they or their agent opened).
POLICY_DEFAULT = {
    'team': [
        {'name': 'Miguel', 'logins': ['mistermizel'], 'agents': [{'login': 'oscarhenrycollins', 'name': 'Oscar'}]},
        {'name': 'James', 'logins': ['jdefleur'], 'agents': [{'login': 'defleur-agents', 'name': 'Archimedes'}]},
        {'name': 'Jan', 'logins': ['JanMesaric'], 'agents': []},
        {'name': 'Robert', 'logins': ['hacalastudio'], 'agents': []},
    ],
    'builder': {'name': 'Wizard OS Builder', 'logins': [BUILDER]},
    # Who may open and close items in each view: a list of team names, or "team" for everyone on it.
    'open': {'goals': ['James'], 'bugs': 'team'},
    # 0.9: target time per step (seconds). Drawn as a tick on each bin's range bar; the median turns
    # green-ish within target, amber over. DATA_DIR/policy.json `targets` overrides (seconds or '1h', '3d', '30m').
    'targets': {'bugs': {'queued': 3600, 'building': 4 * 3600, 'review': 86400, 'done': 2 * 86400},
                # 0.10: Goals Queued 1h like Bugs (queue wait is builder pickup, the same for both)
                'goals': {'queued': 3600, 'building': 3 * 86400, 'review': 3 * 86400, 'done': 14 * 86400}},
    # 0.11: reset date. Done, the Done list and every line stat count only items closed on or after it
    # (open items always count). DATA_DIR/policy.json `since` overrides (ISO date/time, UTC if no zone).
    'since': '2026-11-07T00:00:00Z',
}
TARGET_KEYS = {'queued': 'queued', 'open': 'queued', 'building': 'building', 'build': 'building', 'review': 'review', 'test': 'review', 'done': 'done'}
_UNIT = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 7 * 86400}


def _seconds(v):
    """3600, '1h', '3d', '30m', '2w' -> seconds; anything else None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v) if v > 0 else None
    m = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*([smhdw])\s*', str(v or '').lower())
    return int(float(m.group(1)) * _UNIT[m.group(2)]) or None if m else None


TARGET_MIN, TARGET_MAX = 60, 365 * 86400


def _targets(over):
    out = {v: dict(t) for v, t in POLICY_DEFAULT['targets'].items()}
    if isinstance(over, dict):
        for view, t in over.items():
            if view in out and isinstance(t, dict):
                for k, v in t.items():
                    if k in TARGET_KEYS and _seconds(v) and TARGET_MIN <= _seconds(v) <= TARGET_MAX:
                        out[view][TARGET_KEYS[k]] = _seconds(v)
    return out
STEP_TEXT = {
    'open': {'goals': '{who} opens goals and closes them once they work. Nobody else adds or closes a goal.',
             'bugs': 'Anyone on the team, or their own agent, opens a bug and closes it once it works.'},
    'build': 'The Wizard OS Builder writes the code, then labels it ready-to-test and says what to check.',
    'review': "Someone on the team, not whoever opened it, tries it and says Works or Doesn't work.",
}


def _team_entry(t):
    if not isinstance(t, dict) or not isinstance(t.get('name'), str):
        return None
    logins = [x for x in t.get('logins') or [] if isinstance(x, str) and NAME.match(x)]
    agents = [a for a in t.get('agents') or [] if isinstance(a, dict) and isinstance(a.get('login'), str) and NAME.match(a['login'])]
    return {'name': t['name'][:40], 'logins': logins, 'agents': [{'login': a['login'], 'name': str(a.get('name') or '')[:40]} for a in agents]}


def _since(v):
    """'2026-11-07', '2026-11-07T00:00:00Z' -> (iso, unix ts); anything else the default."""
    for raw in (v, POLICY_DEFAULT['since']):
        try:
            d = datetime.fromisoformat(str(raw or '').strip().replace('Z', '+00:00'))
        except ValueError:
            continue
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), d.timestamp()
    return POLICY_DEFAULT['since'], 0.0


def since_ts(base=None):
    return _since((base or policy_base())['since'])[1]


def counts_since(state, closed, ts):
    """0.11: an item counts toward Done and line stats when it is open or was closed on/after the reset date.
    `closed` is unix seconds or an ISO string."""
    if (state or '').lower() != 'closed':
        return True
    c = _ts(closed) if isinstance(closed, str) else closed
    return c is not None and c >= ts


def policy_base():
    """Defaults in code; DATA_DIR/policy.json overrides any of team, builder, open, targets, since."""
    over = _policy_file()
    team = [x for x in (_team_entry(t) for t in (over.get('team') if isinstance(over.get('team'), list) else POLICY_DEFAULT['team'])) if x]
    b = over.get('builder') if isinstance(over.get('builder'), dict) else POLICY_DEFAULT['builder']
    builder = {'name': str(b.get('name') or 'Wizard OS Builder')[:40], 'logins': [x for x in b.get('logins') or [BUILDER] if isinstance(x, str)]}
    opn = dict(POLICY_DEFAULT['open'])
    if isinstance(over.get('open'), dict):
        opn.update({k: v for k, v in over['open'].items() if k in ('goals', 'bugs') and (v == 'team' or isinstance(v, list))})
    return {'team': team, 'builder': builder, 'open': opn, 'targets': _targets(over.get('targets')),
            'since': _since(over.get('since'))[0]}


def display_names(base=None):
    """0.10: login -> the name people know (person logins -> person, an agent -> its own name)."""
    out = {}
    for t in (base or policy_base())['team']:
        for x in t['logins']:
            out[x.lower()] = t['name']
        for a in t['agents']:
            out[a['login'].lower()] = a['name'] or t['name']
    for x in (base or policy_base())['builder']['logins']:
        out.setdefault(x.lower(), (base or policy_base())['builder']['name'])
    return out


def _policy_file():
    try:
        over = json.loads((DATA / 'policy.json').read_text())
    except (FileNotFoundError, ValueError, OSError):
        over = {}
    return over if isinstance(over, dict) else {}


def targets_set(person, args, agent=False):
    """POST /api/targets {view, step, seconds}: one step's target for everyone (DATA_DIR/policy.json).
    0.10: any signed-in person may change it (permissions later); agents only with the human's words."""
    view = args.get('view')
    if view not in ('goals', 'bugs'):
        raise Problem(400, 'view must be goals or bugs.')
    step = TARGET_KEYS.get(str(args.get('step') or '').lower())
    if not step:
        raise Problem(400, 'step must be queued, building, review or done.')
    raw = args.get('seconds', args.get('value'))
    sec = _seconds(raw)
    if not sec or not TARGET_MIN <= sec <= TARGET_MAX:
        raise Problem(400, 'Pick a target between 1 minute and 1 year (seconds, or like 30m, 4h, 3d, 2w).')
    if agent:
        _owner_request(args, agent, 'change step targets')
        who = 'agent'
    else:
        _, acct = account_for(person)
        who = acct.get('login') or person_key(person)
    with LOCK:
        over = _policy_file()
        t = over.get('targets') if isinstance(over.get('targets'), dict) else {}
        v = t.get(view) if isinstance(t.get(view), dict) else {}
        v = {TARGET_KEYS[k]: x for k, x in v.items() if k in TARGET_KEYS}
        v[step] = sec
        t[view] = v
        over['targets'] = t
        meta = over.get('targets_changed') if isinstance(over.get('targets_changed'), dict) else {}
        meta[f'{view}.{step}'] = {'by': who, 'at': int(time.time())}
        over['targets_changed'] = meta
        DATA.mkdir(parents=True, exist_ok=True)
        tmp = DATA / 'policy.json.tmp'
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(over, f, indent=1)
        tmp.replace(DATA / 'policy.json')
    base = policy_base()
    return {'view': view, 'step': step, 'seconds': base['targets'][view][step], 'targets': base['targets'][view],
            'all': base['targets'], 'changed_by': who, 'note': 'Shared: the same targets for everyone. Permissions later.'}


def person_of(login, base=None):
    """The team name a login belongs to (person or their agent); unknown logins are their own person."""
    low = (login or '').lower()
    for t in (base or policy_base())['team']:
        if low in {x.lower() for x in t['logins']} | {a['login'].lower() for a in t['agents']}:
            return t['name']
    return login or ''


def same_person(a, b, base=None):
    return bool(a and b) and person_of(a, base).lower() == person_of(b, base).lower()


def _who(t):
    return {'name': t['name'], 'logins': [{'login': x, 'kind': 'person'} for x in t['logins']]
            + [{'login': a['login'], 'kind': 'agent', 'name': a['name']} for a in t['agents']]}


def steps_for(view, base=None):
    base = base or policy_base()
    team = base['team']
    o = base['open'][view]
    openers = team if o == 'team' else [t for t in team if t['name'].lower() in {str(n).lower() for n in o}]
    names = ' and '.join(t['name'] for t in openers) or 'Nobody'
    return [
        {'key': 'open', 'n': 1, 'name': 'Open', 'group': 'queued', 'count_label': 'Queued',
         'role': 'Anyone on the team' if o == 'team' else names, 'who': [_who(t) for t in openers],
         'about': STEP_TEXT['open'][view].format(who=names), 'next': 'It waits in the queue until the builder picks it up.'},
        {'key': 'build', 'n': 2, 'name': 'Build', 'group': 'building', 'label': 'building', 'count_label': 'Building',
         'role': base['builder']['name'], 'who': [{'name': base['builder']['name'], 'logins': [{'login': x, 'kind': 'agent'} for x in base['builder']['logins']]}],
         'about': STEP_TEXT['build'], 'next': 'Ready for review (label ready-to-test).'},
        {'key': 'review', 'n': 3, 'name': 'Review', 'group': 'test', 'label': 'ready-to-test', 'count_label': 'Waiting for review',
         'role': 'Team, not the opener', 'who': [_who(t) for t in team], 'except': 'whoever opened it (a person and their own agent count as one)',
         'about': STEP_TEXT['review'], 'next': "Works: the opener closes it (Done). Doesn't work: back to Build."},
    ]


def policy(person=None):
    base = policy_base()
    org = settings()['org']
    views = {v: steps_for(v, base) for v in ('goals', 'bugs')}
    lines = [f"Goals: opened and closed by {views['goals'][0]['role']}",
             f"Bugs: opened and closed by {views['bugs'][0]['role'].lower()}",
             f"Build: {base['builder']['name']} only · Review: the team, not the opener"]
    login = None
    try:
        _, acct = account_for(person)
        login = acct.get('login')
    except Problem:
        pass
    return {'version': 2, **base, 'names': display_names(base), 'org': org, 'steps': views, 'me': {'login': login, 'person': person_of(login, base) if login else None},
            # 0.5 shape, kept for scripts
            'goals': {'authors': [x['login'] for w in views['goals'][0]['who'] for x in w['logins']]},
            'builds': {'builders': base['builder']['logins']}, 'lines': lines, 'editable_file': 'DATA_DIR/policy.json'}


def builder_status():
    b = _read('builder.json', {})
    b = b if isinstance(b, dict) else {}
    return {'running': bool(b.get('running')), 'state': 'Running' if b.get('running') else 'Paused',
            'updated_at': b.get('updated_at'), 'updated_by': b.get('updated_by'), 'connected': False,
            'note': 'Not connected to the builder yet: this switch only records the wish. The builder host will poll GET /api/builder.'}


def builder_set(person, args, agent=False):
    if not isinstance(args.get('running'), bool):
        raise Problem(400, 'running must be true or false.')
    _owner_request(args, agent, 'start or pause the builder')
    if not agent:
        gate(person)
    who = 'agent' if agent else ((accounts()['people'].get(person_key(person)) or {}).get('login') or person_key(person))
    with LOCK:
        _write('builder.json', {'running': args['running'], 'updated_at': int(time.time()), 'updated_by': who})
    return builder_status()


# ---------- 0.7 'Try it' switch per item (mock-up: records the wish per person; nothing runs yet) ----------

TRY_NOTE = 'Mock-up: this will switch the change on in your Wizard once it runs a build with it.'


def _try_key(repo, number):
    if not isinstance(repo, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo or ''):
        raise Problem(400, 'repo must be owner/name.')
    if not isinstance(number, int) or isinstance(number, bool) or not 0 < number < 10**9:
        raise Problem(400, 'number must be a positive integer.')
    return f'{repo.lower()}#{number}'


def _try_who(person, agent):
    if agent:
        a = accounts()
        return a.get('default') if a.get('default') in a['people'] else next(iter(a['people']), 'owner')
    return person_key(person)


def try_status(person=None, agent=False):
    """GET /api/try: this person's Try it choices, {items: {"owner/repo#12": {on, at}}}."""
    allp = _read('try.json', {})
    allp = allp if isinstance(allp, dict) else {}
    mine = allp.get(_try_who(person, agent)) or {}
    return {'items': {k: v for k, v in mine.items() if isinstance(v, dict) and v.get('on')}, 'connected': False, 'note': TRY_NOTE}


def try_set(person, args, agent=False):
    if not isinstance(args.get('on'), bool):
        raise Problem(400, 'on must be true or false.')
    key = _try_key(args.get('repo'), args.get('number'))
    if agent:
        _owner_request(args, agent, 'switch a change on or off for them')
    else:
        gate(person)
    who = _try_who(person, agent)
    with LOCK:
        allp = _read('try.json', {})
        allp = allp if isinstance(allp, dict) else {}
        mine = allp.get(who) if isinstance(allp.get(who), dict) else {}
        if args['on']:
            mine[key] = {'on': True, 'at': int(time.time())}
        else:
            mine.pop(key, None)
        allp[who] = dict(list(mine.items())[-500:])
        _write('try.json', allp)
    return {**try_status(person, agent), 'key': key, 'on': args['on']}


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
            'state': it.get('state'), 'author': who(it), 'opener': person_of(who(it)), 'created_at': it.get('created_at'), 'updated_at': it.get('updated_at'),
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
    cur = _current(acct, full, number)
    names = [l.get('name', '').lower() for l in cur.get('labels') or []]
    if 'ready-to-test' not in names:
        raise Problem(409, 'This is not waiting for a test any more. Refresh to see the latest.')
    opener = ((cur.get('user') or {}).get('login') or '')
    if same_person(opener, login):
        raise Problem(403, f'Someone else reviews this: {person_of(opener)} opened it.')
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
    {'name': 'builder_status', 'description': 'Is the Wizard OS Builder switch Running or Paused? (Mock-up: not wired to the builder host yet.)', 'inputSchema': {'type': 'object', 'properties': {}}},
    {'name': 'builder_set', 'description': 'Set the Wizard OS Builder switch (running true = Running, false = Paused) only when a human asked; pass their words as owner_request.', 'inputSchema': {'type': 'object', 'properties': {'running': {'type': 'boolean'}, **ASKED}, 'required': ['running', 'owner_request']}},
    {'name': 'try_status', 'description': "Which items the signed-in person switched 'Try it' on for (mock-up: records the wish, nothing runs yet).", 'inputSchema': {'type': 'object', 'properties': {}}},
    {'name': 'try_set', 'description': "Switch 'Try it' on or off for one item (repo owner/name + number) only when a human asked; pass their words as owner_request. Mock-up.", 'inputSchema': {'type': 'object', 'properties': {'repo': {'type': 'string'}, 'number': {'type': 'integer'}, 'on': {'type': 'boolean'}, **ASKED}, 'required': ['repo', 'number', 'on', 'owner_request']}},
    {'name': 'board_flow', 'description': "One item's own assembly line from its GitHub label timeline: seconds spent in Queued, Building and Review, closed time, kick-backs (ready-to-test removed without a close), current stage.", 'inputSchema': {'type': 'object', 'properties': ISSUE}},
    {'name': 'targets_set', 'description': "Change one step's target time for everyone (view goals|bugs, step queued|building|review|done, seconds or '4h'/'3d') only when a human asked; pass their words as owner_request. Current targets: GET /api/policy.", 'inputSchema': {'type': 'object', 'properties': {'view': {'type': 'string', 'enum': ['goals', 'bugs']}, 'step': {'type': 'string', 'enum': ['queued', 'building', 'review', 'done']}, 'seconds': {'description': 'Seconds (60 to 31536000) or a string like 30m, 4h, 3d, 2w.', 'type': ['integer', 'string']}, **ASKED}, 'required': ['view', 'step', 'seconds', 'owner_request']}},
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
    'builder_status': lambda a: builder_status(),
    'builder_set': lambda a: builder_set(None, a, agent=True),
    'try_status': lambda a: try_status(None, agent=True),
    'try_set': lambda a: try_set(None, a, agent=True),
    'board_flow': lambda a: item_flow(None, a, agent=True),
    'targets_set': lambda a: targets_set(None, a, agent=True),
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
            if path == '/api/stats':
                return self.send(200, stats_view(self.person(), q))
            if path == '/api/flow':
                return self.send(200, item_flow(self.person(), {**q, 'refresh': q.get('refresh') == '1'}))
            if path == '/api/done':
                return self.send(200, done_list(self.person(), {**q, 'refresh': q.get('refresh') == '1'}))
            if path == '/api/builder':
                return self.send(200, builder_status())
            if path == '/api/try':
                return self.send(200, try_status(self.person()))
            if path == '/api/policy':
                return self.send(200, policy(self.person()))
            if path == '/api/targets':
                return self.send(200, {'targets': policy_base()['targets'], 'note': 'Shared: the same targets for everyone. Permissions later.'})
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
            return self.send(e.code, {'error': e.message, **({'reason': e.reason} if e.reason else {})})
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
                '/api/builder': lambda: builder_set(who, body),
                '/api/try': lambda: try_set(who, body),
                '/api/targets': lambda: targets_set(who, body),
            }
            if path not in routes:
                return self.send(404, {'error': 'Not found.'})
            if path not in ('/api/connect', '/api/disconnect'):
                gate(who)  # 0.12: signed in, a human login, an active team member (cached 10 min)
            return self.send(201 if path in ('/api/goals', '/api/bugs', '/api/new') else 200, routes[path]())
        except Problem as e:
            self.send(e.code, {'error': e.message, **({'reason': e.reason} if e.reason else {})})
        except (ValueError, TypeError, AttributeError, KeyError):
            self.send(400, {'error': 'Invalid request.'})

    def log_message(self, format, *args):
        pass


if __name__ == '__main__':
    secure_start()
    ThreadingHTTPServer((os.environ.get('BIND', '0.0.0.0'), int(os.environ.get('PORT', '8799'))), Handler).serve_forever()
