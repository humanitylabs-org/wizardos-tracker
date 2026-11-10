# App switches (`wizard.app-switches/1`)

Tracker 0.21. How an app lets the WizardOS Tracker's **Try it** toggle (a Human review card) switch one of the app's own
feature switches for the box owner, without "open Settings and find it".

## The app
1. Keeps each switch's state **on the box, per owner** (not per device / not only in `localStorage`), so the card, the
   app's own Settings and the owner's agent all see one state. Off by default.
2. Serves, on its own same-origin path (`https://<box>:8444/<app-id>/`):
   - `GET  /<app-id>/api/switches` →
     ```json
     {"contract": "wizard.app-switches/1",
      "switches": [{"id": "drafts-first", "name": "Drafts at top",
                    "description": "Chats with a waiting draft lead the Inbox.",
                    "on": false, "default": false,
                    "issues": ["humanitylabs-org/wizard-messenger#133"]}]}
     ```
   - `POST /<app-id>/api/switches` with `Content-Type: application/json`, header `X-Wizard-Switch: 1`, the box's own
     `Origin`, body `{"id": "drafts-first", "on": true}` → the same listing (200). Unknown id 404, not the owner 403,
     bad body 400. Errors are JSON `{"error": "…"}`.
   - An app whose owner pages already live under `api/view/` (Messenger) may serve the same at
     `/<app-id>/api/view/switches` instead; the Tracker tries `api/switches` first, then `api/view/switches`.
   - Owner only: the same identity check the app already uses for its owner pages (Tailscale identity / owner session).
     No agent key, no container networking. The Tracker calls it from the same origin with the browser's own
     cookies (`credentials: same-origin`), so an app's owner session cookie works as is.
3. Optionally lists them in `wizard.md` (`switches:` with `id`, `name`, `issues`) so tools can see them without asking.
4. The app's agent tools may expose the same switches (e.g. `<app>_switches` / `<app>_switch_set`).

## The Tracker
- For a Human review item whose hand-over `Switch:` line points into an app (`switch_place.kind == 'app'`), the page
  fetches `/<app-id>/api/switches` (same origin, cached 60 s). It picks the switch whose `issues` contains the item
  (`owner/repo#N`), else the one whose `name` appears in the Switch line. Found: a real toggle on the card and in
  Settings › Try changes. Not served yet: the place in words plus **Open <app>**.
- After **Open <app>** closes, it re-reads that app's switches (the owner may have flipped it inside the app).

## The builder
A feature in an app repo is built behind a switch served this way; the hand-over keeps the plain `Switch:` line
(`Switch: Settings > Drafts at top`) and the switch's `issues` names the issue.
