# Security and responsible reporting

Report security concerns privately to the repository owner rather than publishing API keys, run capabilities, or exploit payloads in issues.

No credentials are included. Use server-side Gemini configuration and a separate operator secret. The UI does not persist that operator secret. Never put secrets in `VITE_*`, checked-in fixtures, screenshots, or reports.

The default Compose deployment binds the frontend to loopback and exposes no backend port. This is a local/demo configuration. Anonymous mission capabilities provide per-run isolation, not enterprise authentication or protection against every resource-exhaustion attack. A global quota can be consumed by any visitor; put identity and per-user controls in place before public API exposure.

Dependencies are locked for reproducibility, not guaranteed vulnerability-free. Review advisories and update locks regularly. Container base tags should be pinned to reviewed digests for a controlled deployment.

The simulator has no spacecraft command channel. Acceptance changes only an owned SQLite run state, or local replay state when the backend is absent.
