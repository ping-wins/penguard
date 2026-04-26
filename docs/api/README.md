# API Contracts

The initial API contract lives in `AGENTS.md` and is backed by JSON fixtures in `packages/contracts/fixtures`.

When `apps/api` is running, FastAPI publishes the generated OpenAPI document at:

```txt
http://localhost:8000/openapi.json
```

Contract changes must update:

- Pydantic request/response models in `apps/api`.
- Shared fixtures in `packages/contracts/fixtures`.
- Backend tests in `apps/api/tests`.
- Consumer-facing notes in `AGENTS.md` when payload shapes change.
