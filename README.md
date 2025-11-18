# BGP Attack Lab (Next-Gen)

This repository provides a containerized playground for demonstrating
BGP attacks and defensive controls. The original lab focused on a
3-router topology; this iteration adds the scaffolding required to scale
to dozens of ASNs, ship generated configs, and present a safe, student
facing dashboard.

## Highlights

- **Single source of truth** – `lab_config.yaml` describes routers,
  links, prefix owners, and scenario metadata.
- **Generator pipeline** – `tools/lab_gen.py` reads the configuration and
  renders docker-compose, FRR, and topology metadata using Jinja2
  templates.
- **Attack Controller** – FastAPI service that wraps the existing
  `orchestrator.py` script behind an internal API.
- **Observer** – FastAPI + HTMX dashboard that surfaces scenario state
  and PCAP listings without giving students direct router access.

## Repository layout

```
.
├── docker-compose.yml
├── lab_config.yaml
├── tools/
│   ├── lab_gen.py
│   └── templates/
├── services/
│   ├── attack_controller/
│   └── observer/
├── orchestrator.py
└── frr/
    ├── r1/
    ├── r2/
    └── r3/
```

## lab_config.yaml format

The file captures:

- `metadata`: lab name, description, and ASN ranges
- `roles`: policy defaults for core/transit/edge devices
- `routers`: ASNs, router-IDs, local networks, and link relationships
- `links`: Layer-2 fabrics with IPv4 subnets
- `prefix_owners`: which routers originate which prefixes
- `scenarios`: scenario descriptions + orchestrator entry points
- `services`: observer and attack-controller metadata
- `pcap_pipeline`: capture buffer details and shared volumes

See the included `lab_config.yaml` for a documented example.

## Generator usage

```bash
python3 tools/lab_gen.py lab_config.yaml --output-dir generated_lab
```

Use `--validate-only` to confirm the configuration without writing any
artifacts. The generator currently outputs:

- `generated_lab/docker-compose.generated.yml`
- `generated_lab/frr/<router>/frr.conf`
- `generated_lab/topology-metadata.json`

## Services

### Attack Controller

- Located in `services/attack_controller`
- Provides `/healthz`, `/scenarios`, and `/scenario/{name}` endpoints
- Reads scenarios from `lab_config.yaml`
- Shells out to `orchestrator.py` until its logic is inlined

### Observer

- Located in `services/observer`
- Serves HTMX dashboard + JSON APIs for status and PCAP metadata
- Communicates exclusively with the Attack Controller
- Mounts the shared `lab_state` volume read-only for packet captures

## docker compose

The root `docker-compose.yml` includes the legacy 3-router lab plus the
new observer and attack controller containers. Future iterations will
replace these static definitions with generator output once multi-AS
scenarios are ready.

## Roadmap

1. Expand generator coverage (policy templates, netprobe, PCAP ring
   buffers)
2. Integrate orchestrator logic directly into the Attack Controller
3. Build topology visualization + per-prefix views in the Observer
4. Introduce RPKI/RPKI caches, route-leak scenarios, and telemetry
   backends
