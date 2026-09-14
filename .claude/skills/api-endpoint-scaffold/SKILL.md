---
name: api-endpoint-scaffold
description: Scaffold a new FastAPI endpoint in Cadence conventions — router, Pydantic v2 schemas, service layer, dependency wiring, and a pytest test. Use when adding or extending a backend API resource.
metadata:
  author: cadence
  version: "1.0"
---

Scaffold a new FastAPI endpoint following the layered architecture: **router → service → repository/ORM**, with Pydantic v2 contracts and a pytest test.

## Before generating
1. Read an existing feature module in the backend to match the current structure, naming, and imports. Do **not** assume paths — discover them (`app/`, `src/`, `api/`, etc.).
2. Confirm the resource name, fields, and which operations are needed (list/get/create/update/delete).
3. Check whether the ORM model + migration exist. If not, hand model/migration work to `database-expert` first.

## What to generate (adapt paths to the repo)
- **Schemas** (`schemas/<resource>.py`): Pydantic v2 models — `XxxCreate`, `XxxUpdate`, `XxxRead`. Use `model_config = ConfigDict(from_attributes=True)` on read schemas. Never expose the ORM model directly.
- **Service** (`services/<resource>.py`): business logic operating on an injected `AsyncSession`/`Session`. All DB access lives here, not in the router.
- **Router** (`routers/<resource>.py`): thin `APIRouter` with typed path/query params, `Annotated` dependencies for session and auth, correct status codes and response models. Register it on the app.
- **Test** (`tests/test_<resource>.py`): pytest using the project's test client and DB fixtures. Cover happy path, a validation failure, and not-found/auth where relevant.

## Conventions to enforce
- Type everything; no bare `dict`/`Any` in signatures.
- Validate input at the schema boundary; return typed error responses with proper HTTP codes.
- Keep routers free of business logic.

## After generating
- Run `pytest` for the new test file and report the actual result.
- Summarize the files created/changed and how the route is registered.
