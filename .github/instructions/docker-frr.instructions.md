---
appliesTo:
  - docker-compose.yml
  - frr/**
  - "**/Dockerfile"
---

# Docker and FRR Configuration

## Docker Compose

### Network Architecture

The lab uses Docker networks to simulate BGP topologies:

- **Fabric networks** (`fabric-a`, `fabric-b`, etc.): Point-to-point or shared segments between routers
- **Management network** (`lab_mgmt`): Out-of-band access for orchestration
- **Shared volumes** (`lab_state`): For packet captures and persistent data

### Router Service Pattern

```yaml
r1:
  image: frrouting/frr:stable  # Use stable, not latest
  container_name: r1
  hostname: r1
  volumes:
    - ./frr/r1/frr.conf:/etc/frr/frr.conf:ro  # Read-only!
    - ./frr/r1/daemons:/etc/frr/daemons:ro
    - lab_state:/captures
  networks:
    fabric-a:
      ipv4_address: 192.0.2.2  # Static IP for deterministic peering
    lab_mgmt:
      ipv4_address: 172.30.0.11
  cap_add:
    - NET_ADMIN  # Required for FRR to manage routes
    - SYS_ADMIN  # Required for network namespaces
  # Optional: limit resources
  # mem_limit: 512m
  # cpus: 0.5
```

### Key Principles

1. **Read-only configs**: Mount FRR configs with `:ro` to prevent accidental modification
2. **Static IPs**: Use `ipv4_address` to ensure deterministic BGP peering
3. **Capabilities**: Only grant necessary Linux capabilities (`NET_ADMIN`, `SYS_ADMIN`)
4. **No host networking**: Keep containers isolated for safety
5. **Version pinning**: Use `frrouting/frr:stable` or specific version tags, not `latest`

### Network Definitions

```yaml
networks:
  fabric-a:
    driver: bridge
    ipam:
      config:
        - subnet: 192.0.2.0/29  # Small subnet, typically /29 or /30
  
  lab_mgmt:
    driver: bridge
    ipam:
      config:
        - subnet: 172.30.0.0/24  # Management subnet

volumes:
  lab_state:
    driver: local
```

### Service Dependencies

```yaml
services:
  observer:
    depends_on:
      - attack_controller
    # Wait for API to be ready
```

Use `depends_on` for startup ordering, but remember it doesn't wait for "ready" - use health checks if needed:

```yaml
attack_controller:
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:9000/healthz"]
    interval: 10s
    timeout: 5s
    retries: 3
```

## FRR Configuration

### File Structure

Each router needs two files:

1. **`daemons`**: Enables FRR routing protocols
2. **`frr.conf`**: Router-specific BGP and interface configuration

### daemons File

```
# Standard daemons file for BGP routers
zebra=yes
bgpd=yes
ospfd=no
ospf6d=no
ripd=no
ripngd=no
isisd=no
pimd=no
ldpd=no
nhrpd=no
eigrpd=no
babeld=no
sharpd=no
pbrd=no
bfdd=no
fabricd=no

# Logging
zebra_options="  -A 127.0.0.1 -s 90000000"
bgpd_options="   -A 127.0.0.1"
```

Only enable protocols you need. For BGP-only routers, only `zebra` and `bgpd` should be `yes`.

### frr.conf Structure

```
!
! FRR configuration for r1 (AS 65001)
!
frr version 8.5
frr defaults traditional
hostname r1
log syslog informational
no ipv6 forwarding
service integrated-vtysh-config
!

! Interface configurations
interface eth0
 description Link to r2 (fabric-a)
 ip address 192.0.2.2/29
!

interface lo
 description Loopback
 ip address 10.0.1.1/32
!

! BGP configuration
router bgp 65001
 bgp router-id 10.255.0.1
 no bgp ebgp-requires-policy
 no bgp network import-check
 
 ! Advertise local networks
 network 10.10.1.0/24
 network 10.0.1.1/32
 
 ! BGP neighbors
 neighbor 192.0.2.1 remote-as 65002
 neighbor 192.0.2.1 description r2-transit
 
 ! Address family configuration
 address-family ipv4 unicast
  neighbor 192.0.2.1 activate
 exit-address-family
!

! Static routes (if needed)
ip route 10.10.1.0/24 Null0
!

line vty
!
end
```

### BGP Configuration Best Practices

#### Router ID

```
router bgp 65001
 bgp router-id 10.255.0.1  ! Use unique, stable IP
```

Always set explicitly - don't rely on automatic selection.

#### Disable Policy Enforcement (Lab Only!)

```
no bgp ebgp-requires-policy
```

This allows BGP peering without explicit route-maps. **NEVER use in production**, but acceptable for educational labs.

#### Network Statements

```
network 10.10.1.0/24  ! Advertise prefix
network 10.0.1.1/32   ! Advertise loopback
```

Use `network` statements for static prefixes. For dynamic origination during attacks, use vtysh commands from orchestrator.

#### Neighbor Configuration

```
neighbor 192.0.2.1 remote-as 65002
neighbor 192.0.2.1 description r2-transit
neighbor 192.0.2.1 activate  ! In address-family section
```

Always include:
- Remote ASN
- Description (helps debugging)
- Explicit activation in address-family

#### Route Filtering (Advanced)

```
! Prefix lists
ip prefix-list ALLOW_VICTIM permit 10.10.1.0/24

! Route maps
route-map HIJACK_FILTER permit 10
 match ip address prefix-list ALLOW_VICTIM
 set as-path prepend 65001 65001

! Apply to neighbor
router bgp 65003
 neighbor 192.0.2.1 route-map HIJACK_FILTER out
```

Use for implementing defensive controls or complex attack scenarios.

### Common FRR Commands (for orchestrator)

```bash
# Enter configuration mode
vtysh -c 'conf t'

# Advertise a new prefix (origin hijack)
vtysh -c 'conf t' -c 'router bgp 65003' -c 'network 10.10.1.0/24'

# AS path manipulation
vtysh -c 'conf t' -c 'router bgp 65003' \
      -c 'neighbor 192.0.2.1 route-map PREPEND out'

# Withdraw prefix
vtysh -c 'conf t' -c 'router bgp 65003' -c 'no network 10.10.1.0/24'

# Clear BGP session (force update)
vtysh -c 'clear ip bgp *'

# Check status
vtysh -c 'show ip bgp summary'
vtysh -c 'show ip bgp'
vtysh -c 'show ip route'
```

## Dockerfile Best Practices

### Service Images

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Non-root user (security)
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:9000/healthz || exit 1

EXPOSE 9000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
```

### Multi-stage Builds (if needed)

```dockerfile
# Build stage
FROM python:3.11 as builder
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# Runtime stage
FROM python:3.11-slim
COPY --from=builder /wheels /wheels
RUN pip install --no-cache /wheels/*
# ... rest of Dockerfile
```

## Testing Changes

### Validate Compose File

```bash
docker compose config  # Check syntax
docker compose config --quiet  # Exit code only
```

### Test FRR Config Syntax

```bash
docker run --rm \
  -v $(pwd)/frr/r1:/etc/frr:ro \
  frrouting/frr:stable \
  vtysh -C -f /etc/frr/frr.conf
```

### Network Connectivity

```bash
# Start lab
docker compose up -d

# Check BGP sessions
docker exec r1 vtysh -c 'show ip bgp summary'

# Verify routes
docker exec r1 vtysh -c 'show ip route bgp'

# Test connectivity
docker exec r1 ping -c 3 192.0.2.1
```

## Common Pitfalls

### FRR Config Errors

- **Typo in command**: FRR silently ignores invalid commands in config files - validate!
- **Wrong indentation**: FRR config is whitespace-sensitive in some sections
- **Missing `!` delimiter**: Separate sections with `!`
- **Interface name mismatch**: eth0, eth1 vs. what Docker actually creates

### Docker Compose Issues

- **Port conflicts**: Check that no services conflict on exposed ports
- **Volume permissions**: FRR may need specific ownership on mounted configs
- **Network conflicts**: Subnet overlaps with host or other compose projects
- **Missing dependencies**: Service starts before required service is ready

## DO NOT

- Don't use `network_mode: host` - breaks isolation
- Don't run FRR containers as privileged - use specific capabilities
- Don't mount the Docker socket in student-facing containers
- Don't use weak BGP passwords (if implementing MD5 auth)
- Don't advertise private IPs to "the Internet" (even simulated)
- Don't modify configs inside running containers - changes are ephemeral
- Don't use `latest` tag - pin to specific FRR versions for reproducibility

## FRR Version Compatibility

- Minimum FRR 7.5 for stable BGP
- FRR 8.x recommended for modern features
- Test configs against target version before deploying
- Check FRR release notes when upgrading

## Debugging

```bash
# FRR logs
docker logs r1

# Interactive FRR shell
docker exec -it r1 vtysh

# Inside vtysh:
show running-config
show ip bgp neighbors
debug bgp updates
```
