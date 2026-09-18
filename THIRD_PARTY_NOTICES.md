# Third-party provenance

This repository was bootstrapped from **Full Stack FastAPI Template**:

- Repository: https://github.com/fastapi/full-stack-fastapi-template
- Commit: `cb740b656d7a0a6c5e12c7bf8e50343ec94ee9c7`
- License: MIT; original notice preserved in `LICENSE`.
- Reused: authentication, account/admin UI, SQLModel foundation, API client, UI components, and account tests.
- Adapted: independent frontend build, local SQLite option, initial migration, configuration, Chinese research interface, deployment and startup scripts.

New research models, device protocol, read-only agent and project interface are implemented in this repository. Ran-ASKS was used as an architectural reference; its PolyForm Noncommercial source code and its data were not copied into this application.

Python versions are recorded in `requirements.lock`; JavaScript dependencies are recorded in `frontend/package-lock.json`. These components retain their own licenses. Optional DVC, Zotero, MLflow and object storage integrations are roadmap items, not bundled services.
