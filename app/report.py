"""WizardOS Reporter: one short 'Report or request' form for any owner (0.20).

Kept apart from the Tracker on purpose, so it can become its own app later. This module holds only the form's
logic: what the owner can pick ('What's it about?'), where each pick goes (core repos vs app repos), the issue text
it files (title from the first sentence, version and device filled in), and the plain 'where it landed' line.
The host app supplies GitHub access (create an issue) and its own rules (is a repo core, who builds it).

Step 1: kind = 'bug' (Something's broken) or 'feature' (I'd like something new).
Step 2: about = a core topic key, 'app:<id>' (an installed app, with its repo as a hint) or 'unsure'.
Step 3: text = one box. Bug: what happened, what should happen. Feature: what you want and why.
"""
import re

KINDS = {'bug': "Something's broken", 'feature': "I'd like something new"}
LABELS = {'bug': 'bug', 'feature': 'feature'}

# WizardOS itself, in plain names. Each maps to its core repo (inside the team org).
CORE_TOPICS = [
    {'key': 'home', 'name': 'Home, Chats & Settings', 'repo': 'wizard-ux',
     'words': ('home', 'chat', 'setting', 'shell', 'desk', 'launcher', 'dock', 'window', 'skin', 'theme', 'phone', 'screen')},
    {'key': 'mac', 'name': 'Mac app', 'repo': 'try-wizard',
     'words': ('mac', 'macos', 'dmg', 'menu bar', 'desktop app', 'laptop')},
    {'key': 'updates', 'name': 'Updates & installing', 'repo': 'wizard-app-manager',
     'words': ('update', 'install', 'store', 'upgrade', 'app manager', 'uninstall')},
    {'key': 'agent', 'name': 'Agent', 'repo': 'wizard-agent-service',
     'words': ('agent', 'reply', 'replies', 'answer', 'hermes', 'model', 'voice', 'tool', 'memory')},
]
DEFAULT_TOPIC = 'home'
PROMPTS = {
    'bug': {'label': 'What happened, and what should happen?', 'placeholder': 'What happened? What should have happened instead?'},
    'feature': {'label': 'What would you like, and why?', 'placeholder': 'What you want, and why it would help.'},
}
_NAME = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,99})$')
_SAFE = re.compile(r'[^\w .,:;()+/@#&\'·-]')


class ReportError(ValueError):
    pass


def options():
    """What the form shows before the owner picks anything (the installed apps come from the owner's own Wizard)."""
    return {'kinds': [{'key': k, 'name': v} for k, v in KINDS.items()],
            'core': [{'key': t['key'], 'name': t['name']} for t in CORE_TOPICS],
            'unsure': {'key': 'unsure', 'name': 'Not sure'},
            'prompts': PROMPTS, 'max_text': 8000}


def core_topic(key):
    return next((t for t in CORE_TOPICS if t['key'] == key), None)


def _clean(v, n):
    return _SAFE.sub('', str(v or ''))[:n].strip()


def _repo_hint(v, org):
    """'owner/name' or 'name' (inside the org); anything else is ignored."""
    parts = str(v or '').strip().split('/')
    if len(parts) == 1 and _NAME.match(parts[0]):
        return f'{org}/{parts[0]}'
    if len(parts) == 2 and all(_NAME.match(p) for p in parts):
        return '/'.join(parts)
    return None


def _apps(v):
    out = []
    for a in v if isinstance(v, list) else []:
        if isinstance(a, dict) and isinstance(a.get('id'), str) and _NAME.match(a['id']):
            out.append({'id': a['id'], 'name': _clean(a.get('name') or a['id'], 60), 'repo': a.get('repo')})
    return out[:200]


def guess(text, apps):
    """'Not sure': pick from the words. An installed app named in the text wins; then a core topic's words;
    else Home, Chats & Settings."""
    low = ' ' + re.sub(r'\s+', ' ', (text or '').lower()) + ' '
    for a in sorted(apps, key=lambda a: -len(a['name'])):
        n = a['name'].lower()
        if len(n) >= 3 and re.search(r'(?<![a-z])' + re.escape(n) + r'(?![a-z])', low):
            return 'app', a
    best, hits = None, 0
    for t in CORE_TOPICS:
        h = sum(1 for w in t['words'] if re.search(r'(?<![a-z])' + re.escape(w), low))
        if h > hits:
            best, hits = t, h
    return 'core', best or core_topic(DEFAULT_TOPIC)


def resolve(about, org, app_repo=None, app_name=None, text='', apps=None, core_repos=()):
    """The repo a pick goes to -> {'repo', 'name', 'area': 'core'|'app', 'picked': bool}. Core topics map to their
    core repo in the org; an installed app to its own repo (its repo hint, owner/name); 'unsure' lets the server pick."""
    about = str(about or '').strip()
    picked = False
    if about == 'unsure' or not about:
        kind, hit = guess(text, _apps(apps))
        picked = True
        if kind == 'app':
            about, app_repo, app_name = 'app:' + hit['id'], hit['repo'], hit['name']
        else:
            about = hit['key']
    t = core_topic(about)
    if t:
        return {'repo': f"{org}/{t['repo']}", 'name': t['name'], 'area': 'core', 'picked': picked}
    if about.startswith('app:'):
        aid = about[4:]
        if not _NAME.match(aid):
            raise ReportError('Pick what it is about.')
        repo = _repo_hint(app_repo, org) or f'{org}/{aid}'
        name = _clean(app_name, 60) or aid
        core = repo.split('/')[-1].lower() in {c.lower() for c in core_repos}
        return {'repo': repo, 'name': name, 'area': 'core' if core else 'app', 'picked': picked}
    # agents may name a repo directly ('wizard-messenger' or 'owner/name')
    repo = _repo_hint(about, org)
    if not repo:
        raise ReportError('Pick what it is about.')
    core = repo.split('/')[-1].lower() in {c.lower() for c in core_repos}
    return {'repo': repo, 'name': _clean(app_name, 60) or repo.split('/')[-1], 'area': 'core' if core else 'app', 'picked': picked}


def title_of(text, limit=90):
    """The issue title: the first sentence (or line) of the one text box, cut at a word."""
    first = re.split(r'(?<=[.!?])\s|\n', text.strip(), maxsplit=1)[0].strip().rstrip('.')
    if len(first) <= limit:
        return first
    cut = first[:limit].rsplit(' ', 1)[0]
    return (cut if len(cut) > limit // 2 else first[:limit]).rstrip(' ,;:') + '…'


def compose(args):
    """Check the owner's input -> (kind, text, footer lines). Raises ReportError with a plain message."""
    kind = args.get('kind')
    if kind not in KINDS:
        raise ReportError("Pick Something's broken or I'd like something new.")
    text = args.get('text')
    if not isinstance(text, str) or len(text.strip()) < 8:
        raise ReportError('Say a little more (a sentence is enough).')
    if len(text) > 8000:
        raise ReportError('That is too long (8000 characters max).')
    return kind, text.strip()


def footer(args, where):
    """The auto-filled facts at the end of the issue: version, device, the app's version, how it was filed."""
    bits = []
    v = _clean(args.get('wizard_version'), 60)
    if v:
        bits.append('WizardOS ' + v)
    av = _clean(args.get('app_version'), 40)
    if where['area'] == 'app' and av:
        bits.append(f"{where['name']} {av}")
    d = _clean(args.get('device'), 80)
    if d:
        bits.append(d)
    head = 'Filed with Report or request' + (" · 'Not sure': picked " + where['name'] if where['picked'] else '')
    return '\n\n---\n' + head + ('\n' + ' · '.join(bits) if bits else '')


def body_of(kind, text, args, where):
    return text + footer(args, where)


def landed(kind, where, next_step):
    """'Filed as a bug in Messenger · the builder starts soon' / 'Filed as a core feature · waits for James or Miguel
    to approve'. next_step is the host's own words for what happens next."""
    if kind == 'feature' and where['area'] == 'core':
        head = 'Filed as a core feature'
    elif kind == 'feature':
        head = f"Filed as a feature for {where['name']}"
    else:
        head = f"Filed as a bug in {where['name']}"
    return head + (' · ' + next_step if next_step else '')
