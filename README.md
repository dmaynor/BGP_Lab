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

## Python Virtual Environment Setup

This lab uses Python scripts and services that require specific
dependencies. It is recommended to use a virtual environment to manage
these dependencies separately from your system Python installation.

### Creating and Using a Virtual Environment

**On Linux/macOS:**

```bash
# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# When you're done working, deactivate the virtual environment
deactivate
```

**On Windows:**

```powershell
# Create a virtual environment
python -m venv venv

# Activate the virtual environment
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# When you're done working, deactivate the virtual environment
deactivate
```

Once activated, your shell prompt will typically show `(venv)` to indicate
the virtual environment is active. All Python commands will use the
isolated environment's packages.

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
cd generated_lab
docker compose up -d
```

Use `--validate-only` to confirm the configuration without writing any
artifacts. When run without `--validate-only`, the generator produces the
following layout (all relative to `generated_lab/`):

```
generated_lab/
├── docker-compose.yml
├── frr/
│   └── <router>/
│       ├── daemons
│       └── frr.conf
└── topology-metadata.json
```

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

Two compose entry points exist today:

- **Baseline lab:** the root `docker-compose.yml` keeps the original
  3-router topology wired to the Attack Controller and Observer. This is
  useful for quick smoke tests while the generator continues to evolve.
- **Generated labs:** run `lab_gen.py` (see above) and then operate from
  `generated_lab/docker-compose.yml`. This path scales to multi-AS
  topologies because routers, bridges, and FRR configs are generated from
  `lab_config.yaml`.

Future iterations will likely promote the generated compose file to the
primary entry point once the workflow hardens.

## Roadmap

1. Expand generator coverage (policy templates, netprobe, PCAP ring
   buffers)
2. Integrate orchestrator logic directly into the Attack Controller
3. Build topology visualization + per-prefix views in the Observer
4. Introduce RPKI/RPKI caches, route-leak scenarios, and telemetry
   backends
