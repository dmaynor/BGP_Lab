# BGP Attack Lab - Copilot Instructions

## Overview

This is a containerized BGP attack demonstration lab designed for educational purposes. The lab uses FRR (Free Range Routing) in Docker containers to create multi-AS BGP topologies where students can safely explore BGP security vulnerabilities and defensive controls.

## Project Architecture

### Core Components

1. **Lab Configuration**: `lab_config.yaml` is the single source of truth defining routers, links, prefixes, and scenarios
2. **Generator Pipeline**: `tools/lab_gen.py` uses Jinja2 templates to generate docker-compose files, FRR configs, and topology metadata
3. **Orchestrator**: `orchestrator.py` controls the legacy 3-router topology and implements BGP attack scenarios
4. **Services**:
   - **Attack Controller**: FastAPI service (`services/attack_controller/`) exposing scenario control via REST API
   - **Observer**: FastAPI + HTMX dashboard (`services/observer/`) for viewing lab state without direct router access
5. **Network Tools**: Python scripts for linting (`network_lint.py`), repair (`network_repair.py`), and status monitoring

### Technology Stack

- Python 3.x with type hints (`from __future__ import annotations`)
- FastAPI for web services
- Docker Compose for container orchestration
- FRR (Free Range Routing) for BGP routing
- Jinja2 for configuration templating
- YAML for configuration files

## Coding Standards

### Python Style

- Use Python 3 with type hints throughout
- Import `from __future__ import annotations` at the top of files
- Use dataclasses for structured data
- Use descriptive docstrings following the project's style (see `orchestrator.py` for examples)
- Follow PEP 8 conventions
- Prefer f-strings for string formatting
- Use pathlib.Path for file operations

### Code Organization

- Keep business logic separate from orchestration
- Use meaningful variable names that reflect BGP/networking domain (e.g., `asn`, `router_id`, `prefix`)
- Group related functionality into modules
- Maintain backwards compatibility with existing CLI interfaces

### Docker & Configuration

- All router configurations should be generated from `lab_config.yaml`
- Use read-only volume mounts for FRR configs (`:ro` flag)
- Maintain network isolation using Docker networks
- Follow the naming convention: `fabric-{letter}` for inter-router links, `lab_mgmt` for management

## Important Constraints

### Security & Safety

- **NEVER** commit secrets, credentials, or sensitive data
- All routing happens on private Docker networks - maintain this isolation
- Student-facing services (Observer) must NOT provide direct router access
- Validate all user inputs to prevent injection attacks
- Use read-only mounts where possible to prevent accidental modifications

### File Modification Guidelines

- **DO NOT** modify generated files directly (e.g., `docker-compose.yml` in root is hand-crafted but generated versions go to `generated_lab/`)
- **DO** make changes to templates (`tools/templates/`) instead of generated outputs
- **DO** update `lab_config.yaml` to change topology, not individual FRR configs
- **PRESERVE** backwards compatibility with the legacy 3-router setup during the transition period

### Testing & Validation

- Test changes in a containerized environment
- Verify BGP session establishment after configuration changes
- Run the generator with `--validate-only` before committing schema changes
- Check that existing scenarios still work after modifications

## Key Workflows

### Adding a New Scenario

1. Add scenario definition to `scenarios:` section in `lab_config.yaml`
2. Implement the scenario logic in `orchestrator.py`
3. Test using: `python3 orchestrator.py scenario <scenario_name>`
4. Verify it appears in the Attack Controller API

### Modifying the Topology

1. Edit `lab_config.yaml` (add routers, links, or prefixes)
2. Run `python3 tools/lab_gen.py lab_config.yaml --validate-only` to check validity
3. Generate the lab: `python3 tools/lab_gen.py lab_config.yaml --output-dir generated_lab`
4. Test with: `cd generated_lab && docker compose up -d`

### Updating Services

- Attack Controller changes: modify files in `services/attack_controller/app/`
- Observer changes: backend in `services/observer/observer_backend/`, frontend in `services/observer/frontend/`
- Always update `requirements.txt` when adding Python dependencies
- Rebuild Docker images after service changes

## Common Pitfalls to Avoid

- Don't hardcode router names or IP addresses - use the config-driven approach
- Don't break the FRR configuration syntax - validate with `vtysh -C` in the container
- Don't add dependencies that significantly increase image size
- Don't modify running container configs - they'll be lost on restart
- Don't assume the 3-router topology - code should work with N routers from `lab_config.yaml`

## Domain-Specific Terminology

- **ASN**: Autonomous System Number (e.g., 65001-65005 are private ASNs)
- **Origin hijack**: Attacker re-originates a victim's prefix
- **More-specific attack**: Attacker advertises a longer prefix match to steal traffic
- **Route leak**: Transit AS incorrectly re-advertises routes
- **AS_PATH**: The path of ASNs a BGP route has traversed
- **Prefix**: An IP address block in CIDR notation (e.g., 10.10.1.0/24)
- **Fabric**: Layer-2 network segment connecting routers

## Resource Links

- FRR Documentation: https://docs.frrouting.org/
- BGP RFC 4271: https://www.rfc-editor.org/rfc/rfc4271
- Docker Compose Spec: https://docs.docker.com/compose/compose-file/

## Questions to Ask

When unclear about a change, consider:
- How does this affect existing scenarios?
- Will this work with generated topologies beyond the 3-router baseline?
- Does this preserve the ability to run the lab offline?
- Have I tested this in a container environment?
- Does this change require documentation updates in README.md?
