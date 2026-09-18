# Research Manager engineering rules

- Read `docs/status.md` before continuing work; distinguish implemented features from the roadmap.
- The repository is an independent application, based on the MIT FastAPI full-stack template. Preserve upstream attribution in THIRD_PARTY_NOTICES.md and LICENSE.
- Backend: `backend/app/`; frontend: `frontend/src/`; agent: `agent/research_agent/`.
- The agent is read-only in v0.1. Never introduce fetch, push, checkout, reset, cleanup, hook execution or source-file upload into a scan.
- Projects have UUID identity; do not merge them by folder name, timestamp or AI similarity.
- A Git comparison refers to an explicitly identified cached upstream. Missing or shallow history means unknown. Dirty state is independent of commit equality.
- Enforce ownership on the server. Device credentials can only access the agent endpoints; store only credential hashes server-side. Exclude all credentials and runtime data from Git.
- Observation sequence updates and project revision checks must be atomic. Tests must cover duplicate/out-of-order observations, revoked devices and cross-account access.
- Migrations are explicit Alembic revisions. Do not run schema migration during read requests. SQLite is for local development; PostgreSQL is the deployment target.
- Use `python -m pytest backend/tests agent/tests -q`, `npm --prefix frontend run build`, and targeted static checks for relevant changes. Run tests against isolated databases and temporary Git repositories, never the user's active worktrees.
- Update README/docs/status.md for changes to startup, scope or known limitations. Do not record passwords or tokens in documentation.

## Implementation and review handoff

- For the user-approved Claude Code/Kimi implementation and Codex review workflow, read docs/handoff/START_HERE.zh-CN.md and the selected task card.
- T01 is the first implementation task. T02 starts after T01 is independently accepted and locally integrated. Later roadmap items are not automatically authorized for implementation.
- Record actual base/head commits and verification evidence; implementation reports do not constitute independent acceptance.
