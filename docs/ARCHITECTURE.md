# Pivot architecture

Pivot is a single FastAPI application with a Vite/React client. It is intentionally
not split into services: the product has one deployment unit, one database, and a
small number of cohesive workflows.

## Backend

`backend/app/main.py` owns application assembly, middleware, and the remaining
dataset, chat, report, and version HTTP handlers. Focused router modules own
analytics and SQL endpoints. Routes coordinate workflows and translate expected
failures to HTTP responses; they do not own file-format or SQL-engine details.

The backend modules are grouped by responsibility rather than by a generic layer:

- `analytics.py` profiles frames through explicit schema inference and quality
  assessment steps. `pipeline.py` contains pure dataframe transformations.
  `autopilot.py` implements the Auto Pilot workflow.
- `assistant.py` owns conversational dataset analysis. `rag.py` owns document
  extraction and retrieval. `gemini.py` is the sole boundary for Gemini provider
  calls and model JSON parsing.
- `dataset_io.py` owns temporary files, object storage transfer, dataframe loading,
  and profile/overview response construction. `dataset_sql.py` owns the in-memory,
  read-only SQLite adapter and schema-driven SQL generation.
- `store.py`, `database.py`, and `db/models.py` own persistence. They do not depend
  on FastAPI route handlers.
- `auth.py`, `auth_routes.py`, `security.py`, `config.py`, and `storage.py` own
  cross-cutting infrastructure concerns.

When adding a data workflow, keep its calculation with the relevant domain module;
add to `dataset_io.py` only when it is reusable file/storage behavior. Keep HTTP
error translation and request/response handling at the route boundary.

## Frontend

`src/main.jsx` is the client entrypoint. `auth.jsx` owns session state and
`api.js` owns the shared authenticated HTTP client, token refresh, request errors,
and downloads. `frontend/constants.js` and `frontend/storage.js` provide small,
focused browser configuration boundaries. `frontend/components/ui.jsx` contains
shared visual primitives and the schema explorer.

`AppPolished.jsx` remains the application composition root: it owns workspace
state, API workflow coordination, and page selection. Feature components should
move out only when they are independently understandable or reused; the goal is a
predictable feature boundary, not a maximum number of files.

## Verification

Run backend tests with `python -m pytest -q` from the repository root (the local
`.venv` is used in development). Build the client with `npm run build`.
