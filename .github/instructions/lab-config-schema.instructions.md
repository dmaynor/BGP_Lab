---
appliesTo:
  - lab_config.yaml
  - "**/lab_config.yaml"
---

# lab_config.yaml Schema and Configuration

## Purpose

`lab_config.yaml` is the single source of truth for the BGP attack lab. It defines the entire topology, routing policies, attack scenarios, and service configurations.

## Schema Version

Always start the file with:
```yaml
version: 1
```

This allows for future schema evolution with backwards compatibility checks.

## Top-Level Sections

### 1. metadata

General information about the lab:

```yaml
metadata:
  name: multi-as-lab
  description: >-
    Reference configuration describing routers, prefixes, and
    scenario metadata for the scalable BGP attack lab generator.
  maintainer: student-lab@example.edu
  asn_range:
    start: 65000  # Private ASN range start
    end: 65100    # Private ASN range end
```

**Validation rules**:
- `name`: Required, alphanumeric with hyphens
- `asn_range`: Must use private ASN ranges (64512-65534 or 4200000000-4294967294)

### 2. roles

Define policy templates for different router types:

```yaml
roles:
  core:
    local_pref: 200      # Prefer routes from core
    export_policy: advertise-all
  transit:
    local_pref: 150
    export_policy: customer-only  # Don't provide transit for peers
  edge:
    local_pref: 100
    export_policy: default
```

**Best practices**:
- Keep role definitions simple and reusable
- Use local_pref to control inbound preference
- Use export_policy to control outbound announcements

### 3. routers

List of all routers in the topology:

```yaml
routers:
  - name: r1                    # Required: Unique identifier
    asn: 65001                  # Required: BGP AS number
    role: edge                  # Required: References roles section
    router_id: 10.255.0.1       # Required: BGP router ID
    mgmt_ip: 10.255.0.11        # Required: Management network IP
    loopback: 10.0.1.1/32       # Optional: Loopback address
    networks:                   # Optional: Prefixes to advertise
      - 10.10.1.0/24
    peers:                      # Required: BGP neighbors
      - neighbor: r2            # Neighbor router name
        link: fabric-a          # Layer-2 fabric name
```

**Validation rules**:
- `name`: Must be unique, valid hostname (lowercase, alphanumeric, hyphens)
- `asn`: Must be within `metadata.asn_range` or standard private ASN ranges
- `role`: Must reference a defined role in `roles` section
- `router_id`: Must be valid IPv4 address (typically a management IP)
- `mgmt_ip`: Must be unique across all routers
- `loopback`: Must be valid CIDR notation
- `networks`: Each must be valid CIDR notation
- `peers.neighbor`: Must reference another router's `name`
- `peers.link`: Must reference a defined link in `links` section

**Common errors**:
```yaml
# BAD: ASN outside private range
asn: 65535  # This is reserved

# BAD: Duplicate router_id
router_id: 10.255.0.1  # Same as another router

# BAD: Peer reference to non-existent router
peers:
  - neighbor: r99  # No such router defined
    link: fabric-a

# GOOD: Properly defined router
- name: r1
  asn: 65001
  role: edge
  router_id: 10.255.0.1
  mgmt_ip: 10.255.0.11
  loopback: 10.0.1.1/32
  networks:
    - 10.10.1.0/24
  peers:
    - neighbor: r2
      link: fabric-a
```

### 4. links

Layer-2 network segments connecting routers:

```yaml
links:
  fabric-a:
    ipv4_subnet: 10.0.0.0/29  # Small subnet for point-to-point or small broadcast
  fabric-b:
    ipv4_subnet: 10.0.0.8/29
  fabric-c:
    ipv4_subnet: 10.0.0.16/29
```

**Validation rules**:
- Link names must be unique
- Subnets must not overlap
- Subnet must be large enough for all connected routers
  - /30 for point-to-point (2 hosts)
  - /29 for 3-6 hosts
  - /28 for 7-14 hosts
- Use private IP space (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)

**IP assignment logic**:
The generator assigns IPs from the subnet to routers deterministically:
- Sort router names alphabetically
- Assign host IPs in order (first usable, second usable, etc.)
- Skip network and broadcast addresses

### 5. prefix_owners

Define which router originates which prefixes and how they propagate:

```yaml
prefix_owners:
  - prefix: 10.10.1.0/24
    origin: r1                  # Router that owns/announces this prefix
    propagation_scope: full     # How far it should propagate
  - prefix: 10.20.3.0/24
    origin: r3
    propagation_scope: limited  # Only to direct neighbors
  - prefix: 10.50.5.0/24
    origin: r5
    propagation_scope: full
```

**Validation rules**:
- `prefix`: Valid CIDR notation
- `origin`: Must reference an existing router
- `propagation_scope`: Either `full`, `limited`, or `none`

**Usage**:
- Helps visualization show which AS "owns" which IP space
- Used by orchestrator to determine victim prefixes
- Can drive automatic prefix filtering policies

### 6. scenarios

BGP attack scenarios that can be triggered:

```yaml
scenarios:
  normal:
    description: Baseline clean routing state.
    orchestrator_entrypoint: normal
  origin_hijack:
    description: Classic origin hijack by AS 65003.
    orchestrator_entrypoint: hijack
  subprefix:
    description: More specific prefix hijack for partial traffic attraction.
    orchestrator_entrypoint: more-specific
  leak:
    description: Transit AS incorrectly re-advertises full feed.
    orchestrator_entrypoint: leak
```

**Fields**:
- **Key** (e.g., `origin_hijack`): Scenario identifier used in API calls
- `description`: Human-readable explanation shown in UI
- `orchestrator_entrypoint`: Function name in orchestrator.py (without `_scenario_` prefix)

**Adding new scenarios**:
1. Add entry here with unique key
2. Implement `_scenario_<entrypoint>()` in orchestrator.py
3. Update Attack Controller to recognize it
4. Add UI elements in Observer if needed

### 7. services

Configuration for the Attack Controller and Observer services:

```yaml
services:
  observer:
    image: bgp-lab/observer:dev
    listen_port: 8080
  attack_controller:
    image: bgp-lab/attack-ctl:dev
    listen_port: 9000
```

**Used by**:
- `docker-compose.yml.j2` template to generate service definitions
- Services themselves to read configuration

### 8. pcap_pipeline

Packet capture configuration:

```yaml
pcap_pipeline:
  enabled: true
  ring_buffer_size_mb: 256  # Size of rotating capture buffer
  shared_volume: lab_state  # Docker volume name
```

**Future expansion**:
- Per-link capture configuration
- Filtering rules
- Automatic PCAP rotation

## Validation Best Practices

When modifying lab_config.yaml or writing validation code:

### Required Validations

1. **Schema version check**
   ```python
   if config.get("version") != 1:
       raise ValueError("Unsupported config version")
   ```

2. **Referential integrity**
   - All `peers.neighbor` must reference existing routers
   - All `peers.link` must reference existing links
   - All `prefix_owners.origin` must reference existing routers
   - All router `role` must reference existing roles

3. **Network validation**
   - No subnet overlaps in `links`
   - All IP addresses are valid
   - Management IPs are unique
   - Router IDs are valid IPv4 addresses

4. **ASN validation**
   - Within declared `asn_range` or standard private ranges
   - Unique per router (unless intentionally multi-router AS)

5. **Link capacity**
   - Each link subnet has enough IPs for all connected routers
   ```python
   subnet = ipaddress.ip_network(link["ipv4_subnet"])
   num_routers = count_routers_on_link(link_name)
   if subnet.num_addresses - 2 < num_routers:  # -2 for network/broadcast
       raise ValueError(f"Link {link_name} subnet too small")
   ```

### Recommended Validations

- Check for isolated routers (no peers)
- Warn if no router advertises a prefix from `prefix_owners`
- Verify scenario entrypoints exist in orchestrator.py
- Check service port uniqueness

### Error Messages

```python
# Good error message
f"Router 'r5' peer 'r99' on link 'fabric-d' does not exist. Available routers: {list(router_names)}"

# Bad error message
"Invalid peer"
```

## Common Configuration Patterns

### Linear Topology (3 routers)

```yaml
routers:
  - name: r1
    peers: [{neighbor: r2, link: fabric-a}]
  - name: r2
    peers: [{neighbor: r1, link: fabric-a}, {neighbor: r3, link: fabric-b}]
  - name: r3
    peers: [{neighbor: r2, link: fabric-b}]
```

### Star Topology (central hub)

```yaml
routers:
  - name: hub
    peers:
      - {neighbor: r1, link: fabric-a}
      - {neighbor: r2, link: fabric-b}
      - {neighbor: r3, link: fabric-c}
  - name: r1
    peers: [{neighbor: hub, link: fabric-a}]
  # ... etc
```

### Ring Topology

```yaml
routers:
  - name: r1
    peers: [{neighbor: r2, link: fabric-a}, {neighbor: r4, link: fabric-d}]
  - name: r2
    peers: [{neighbor: r1, link: fabric-a}, {neighbor: r3, link: fabric-b}]
  # ... continues around the ring
```

## DO NOT

- Don't use ASNs outside private ranges without good reason
- Don't create overlapping subnets
- Don't reference non-existent routers or links
- Don't use IP addresses that conflict with host networking
- Don't create circular dependencies in validation logic
- Don't put secrets in this file (it's configuration, not credentials)
- Don't make the file too large - break into includes if needed (future feature)

## Future Schema Evolution

Planned additions:
- Route filtering policies per router
- RPKI cache configuration
- Telemetry backend configuration
- Multi-vendor support (not just FRR)
- Scenario parameters (currently hardcoded in orchestrator)

When making breaking changes:
1. Increment `version` number
2. Implement migration logic in generator
3. Update all examples and documentation
