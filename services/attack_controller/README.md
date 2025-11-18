# Attack Controller Service

This container exposes a FastAPI application that wraps the legacy
`orchestrator.py` scenarios with a hardened HTTP interface that is only
reachable from the Observer container.

## Features

- Discovers available scenarios from `lab_config.yaml`
- Provides `/healthz`, `/scenarios`, and `/scenario/{name}` endpoints
- Shells out to `python3 orchestrator.py scenario <entrypoint>` until the
  orchestrator logic is migrated into the service directly

## Development

```bash
cd services/attack_controller
uvicorn app.main:app --reload --port 9000
```

The service expects `LAB_CONFIG` (defaults to `/lab/lab_config.yaml`) to
exist and contain the scenario registry.
