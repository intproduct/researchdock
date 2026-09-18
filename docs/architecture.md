# v0.1 architecture

The browser is a React/Vite application. It calls a FastAPI API using the template's bearer authentication. The API stores project metadata, registered devices and latest working-copy observations in SQLModel tables. Local development uses SQLite; Compose targets PostgreSQL. The frontend and backend are independently built and are served under one origin through Nginx.

The separately installable Python agent uses the standard library and the system Git executable. Users explicitly pair a device and bind Git root directories to project UUIDs. The agent executes read-only Git commands without shell interpolation, disables optional index locks and fsmonitor hooks, and never fetches or pushes. It sends counts and commit metadata, not filenames, patches or file contents. Paths and sanitized remote URLs are metadata and are visible to the project owner.

Device pairing is an authenticated login followed by issuance of a random, revocable device token. The backend stores only its SHA-256 hash. The client keeps its token in its per-user SQLite state; Unix permissions are tightened, Windows uses the user's profile permissions. Native credential-vault integration and signed agent distribution are future work. Remote connections require HTTPS; local loopback may use HTTP.

The agent's SQLite outbox stores the latest observation for each working copy. It coalesces intermediate states during outages; it is not an audit history or a backup. A locally allocated sequence is monotonically increasing; the API applies an atomic conditional update so duplicate or older deliveries cannot replace newer observations. Device last_seen records server receipt time. A failed local scan preserves the previous observation and returns a nonzero CLI exit code.

Git comparison states are synced/ahead/behind/diverged/unrelated/unknown. They compare HEAD with the existing local upstream ref. The system does not know the current GitHub state until a future authenticated remote-refresh integration is implemented. A dirty worktree remains dirty even when its HEAD equals the upstream. Shallow clones and detached HEAD return unknown. No-Git folders are intentionally rejected in this version.

Project updates include an expected revision and use a conditional database update. A stale update gets HTTP 409. This prevents overwriting concurrent edits but does not yet preserve a full revision history. Current status and next action are editable; append-only research memory and provenance-linked knowledge compilation are planned separately.

Future increments: explicit GitHub connections and shared-history comparison; safe sync plans/checkpoints; non-Git import; DVC and literature connectors; source-version/evidence model; research history; encrypted backup/restore; controlled remote computation. Each requires its own tests and acceptance criteria.
