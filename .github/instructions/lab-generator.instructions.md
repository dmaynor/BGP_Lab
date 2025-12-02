---
appliesTo:
  - tools/lab_gen.py
  - tools/netprobe.py
  - tools/templates/**
---

# Lab Generator and Tooling

## Purpose

The lab generator (`tools/lab_gen.py`) is the core infrastructure component that transforms `lab_config.yaml` into a runnable Docker Compose environment with FRR router configurations.

## Architecture

### Input: lab_config.yaml

A single YAML file describing:
- Routers (ASN, role, networks, peers)
- Links (Layer-2 fabrics with IP subnets)
- Prefix ownership and propagation
- Scenarios and services
- PCAP pipeline configuration

### Output: Generated Lab

```
generated_lab/
├── docker-compose.yml
├── frr/
│   └── <router>/
│       ├── daemons
│       └── frr.conf
└── topology-metadata.json
```

## Key Principles

### Configuration Validation

When modifying `lab_gen.py`:

1. **Validate early**: Check config structure before generating anything
2. **Provide clear errors**: Tell users exactly what's wrong in their YAML
3. **Use --validate-only**: Support dry-run mode without writing files
4. **Version check**: Ensure `version: 1` at the top of lab_config.yaml

Example validation:
```python
def validate_router(router_def: Dict) -> List[str]:
    """Return list of validation errors, empty if valid."""
    errors = []
    required = ["name", "asn", "router_id", "role"]
    for field in required:
        if field not in router_def:
            errors.append(f"Router missing required field: {field}")
    
    # Validate ASN range
    asn = router_def.get("asn", 0)
    if not (64512 <= asn <= 65534 or 4200000000 <= asn <= 4294967294):
        errors.append(f"ASN {asn} outside private range")
    
    return errors
```

### Template Design

Jinja2 templates in `tools/templates/`:

- **docker-compose.yml.j2**: Generates the compose file with router services, networks, and volumes
- **frr.conf.j2**: Generates FRR BGP configuration for each router
- **daemons.j2**: Enables required FRR daemons (bgpd, zebra, etc.)

Template best practices:
```jinja
{# Good: Clear logic, proper escaping #}
router bgp {{ router.asn }}
  bgp router-id {{ router.router_id }}
  no bgp ebgp-requires-policy
  
  {% for network in router.networks %}
  network {{ network }}
  {% endfor %}
  
  {% for peer in router.peers %}
  {# Calculate peer IP from link subnet #}
  neighbor {{ calculate_peer_ip(peer.link, peer.neighbor) }} remote-as {{ get_peer_asn(peer.neighbor) }}
  {% endfor %}

{# Bad: Complex logic in template #}
{% if router.role == 'core' and router.asn > 65000 %}
  {# ... complex conditional that should be in Python #}
{% endif %}
```

### IP Address Management

The generator must:
- Parse CIDR notation subnets from `links:` section
- Assign IP addresses to router interfaces automatically
- Avoid IP conflicts
- Use consistent assignment (same input = same output)

Example approach:
```python
def assign_link_ips(link_name: str, subnet: str, routers: List[str]) -> Dict[str, str]:
    """Assign IPs from subnet to routers on this link."""
    network = ipaddress.ip_network(subnet)
    hosts = list(network.hosts())
    
    assignments = {}
    for idx, router in enumerate(sorted(routers)):  # Sort for determinism
        if idx >= len(hosts):
            raise ValueError(f"Not enough IPs in {subnet} for {len(routers)} routers")
        assignments[router] = str(hosts[idx])
    
    return assignments
```

### Jinja2 Environment Setup

```python
env = Environment(
    loader=FileSystemLoader('tools/templates'),
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True
)

# Register custom filters/functions
env.filters['to_json'] = json.dumps
env.globals['get_peer_asn'] = lambda name: router_map[name].asn
```

## Testing Your Changes

### Validation Tests

```bash
# Should pass
python3 tools/lab_gen.py lab_config.yaml --validate-only

# Should fail with clear error
python3 tools/lab_gen.py bad_config.yaml --validate-only
```

### Generation Tests

```bash
# Generate to temp directory
python3 tools/lab_gen.py lab_config.yaml --output-dir /tmp/test_lab

# Verify output structure
ls /tmp/test_lab/docker-compose.yml
ls /tmp/test_lab/frr/r1/frr.conf

# Validate generated compose file
cd /tmp/test_lab
docker compose config  # Should parse without errors

# Don't start - just validate syntax
```

### FRR Configuration Validation

```bash
# Check FRR config syntax
docker run --rm -v /tmp/test_lab/frr/r1:/etc/frr:ro frrouting/frr:stable \
    vtysh -C -f /etc/frr/frr.conf
```

## Common Tasks

### Adding a New Router Role

1. Add role definition to `roles:` in lab_config.yaml schema
2. Update template logic to handle new role (e.g., different BGP policies)
3. Document the role's behavior in comments

### Supporting New FRR Features

1. Update FRR config template with new syntax
2. Ensure backwards compatibility (use conditionals if feature is optional)
3. Add example to lab_config.yaml
4. Test with target FRR version

### Extending Metadata Output

`topology-metadata.json` is consumed by the Observer UI:
- Keep it JSON serializable (no custom objects)
- Include everything needed for visualization
- Version the schema if making breaking changes

## DO NOT

- Don't generate configs with syntax errors - always validate
- Don't lose data - if output-dir exists, prompt before overwriting (or use --force flag)
- Don't put secrets in templates - all sensitive data should be in environment or runtime config
- Don't assume small topologies - code must scale to dozens of routers
- Don't break existing `lab_config.yaml` files - maintain schema compatibility
- Don't write to the repository root - generated files go to --output-dir

## netprobe.py

This tool runs network diagnostics (ping, traceroute, etc.) from within containers.

Key points:
- Use `docker exec` to run commands in router containers
- Parse and format output for readability
- Handle network unreachability gracefully (attacks may break connectivity)
- Log results for debugging purposes
