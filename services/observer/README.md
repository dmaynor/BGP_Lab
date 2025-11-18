# Observer Service

The observer provides a student-friendly dashboard powered by FastAPI
and HTMX. It surfaces topology information, exposes packet capture
metadata, and proxies scenario actions through the Attack Controller.

## Key components

- `/api/status` – pulls scenario list from the attack controller and
  merges it with the generated topology metadata.
- `/api/pcaps` – lists PCAP files from the shared capture volume.
- `/` – HTMX dashboard that polls the API endpoints.

## Development

```bash
cd services/observer
uvicorn observer_backend.main:app --reload --port 8080
```

Set `ATTACK_CONTROLLER_URL` if you need to target a remote attack
controller during development.
