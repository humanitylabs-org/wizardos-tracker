# Source and license notice

Board adapts Wizard App Manager's hello-wizard reference template (stdlib Python service shared by the API and MCP, vanilla view, canonical Wizard style snapshot). Modifications: November 2026, Hermes Agent for Humanity Labs. Distributed under GPL-3.0-only, matching LICENSE; no warranty.

The view loads the centrally maintained `/wizard-os-home/core/app-client.js` (shared system functions v1); there is no per-app appearance transport or Back root guard. The kit files (`wizard-tokens.css`, `wizard-ui.css`, `wizard-sheet.js`, `boot.js`) are the pinned canonical snapshot (see `appearance-provenance.json`) and are not edited. GitHub is reached over its public REST and GraphQL APIs with each person's own token. No third-party code is bundled; Python and the base image keep their upstream licenses.
