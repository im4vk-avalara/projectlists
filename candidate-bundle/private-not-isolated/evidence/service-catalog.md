# Service Catalog

| Service | Host | Discriminating request | Expected response when reached |
|---|---|---|---|
| Assistant API | `assistant.internal.lab` | `GET /openapi.json` | `200`, `X-Lab-Service: assistant-api` |
| Workflow API | `workflow.internal.lab` | `GET /api/v1/sessions` | `401` without caller identity |
| Admin API | `admin.internal.lab` | `GET /healthz` | `200`, `X-Lab-Service: admin-api` |

## Operational note

`workflow-api` predates the current access plane and assumes a trusted upstream
has authenticated each caller. Its root path is not a documented health check.
