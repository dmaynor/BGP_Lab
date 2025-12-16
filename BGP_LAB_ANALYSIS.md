# BGP Attack Lab - Comprehensive Analysis

## Executive Summary

This BGP Attack Lab is a containerized educational environment designed to demonstrate common BGP attack vectors and their impacts on internet routing. The lab provides a safe, isolated environment for security researchers and students to understand how BGP vulnerabilities can be exploited and observed in real-time.

---

## Network Environment Architecture

### Topology Overview

The lab implements a multi-AS (Autonomous System) network topology with 5 routers representing different types of network participants:

```
┌─────────────────────────────────────────────────────────────┐
│                    BGP Lab Topology                          │
└─────────────────────────────────────────────────────────────┘

    R1 (AS 65001)          R3 (AS 65003)          R5 (AS 65005)
    Edge/Victim            Edge/Attacker          Edge
    10.10.1.0/24          10.20.3.0/24           10.50.5.0/24
         │                     │                      │
         │                     │                      │
    [fabric-a]            [fabric-b]            [fabric-d]
         │                     │                      │
         │                     │                      │
         └──────R2 (AS 65002)──┘                      │
                Transit         └─────R4 (AS 65004)───┘
                                      Core
```

### Router Details

| Router | ASN   | Role    | Prefixes       | Router ID   | MGMt IP      | Function        |
|--------|-------|---------|----------------|-------------|--------------|-----------------|
| R1     | 65001 | Edge    | 10.10.1.0/24   | 10.255.0.1  | 10.255.0.11  | **Victim**      |
| R2     | 65002 | Transit | None           | 10.255.0.2  | 10.255.0.12  | **Provider**    |
| R3     | 65003 | Edge    | 10.20.3.0/24   | 10.255.0.3  | 10.255.0.13  | **Attacker**    |
| R4     | 65004 | Core    | None           | 10.255.0.4  | 10.255.0.14  | **Core Transit**|
| R5     | 65005 | Edge    | 10.50.5.0/24   | 10.255.0.5  | 10.255.0.15  | **Observer Net**|

### Network Fabrics (Peering Links)

- **fabric-a** (10.0.0.0/29): Connects R1 ↔ R2
- **fabric-b** (10.0.0.8/29): Connects R2 ↔ R3
- **fabric-c** (10.0.0.16/29): Connects R2 ↔ R4
- **fabric-d** (10.0.0.24/29): Connects R4 ↔ R5
- **lab_mgmt** (10.255.0.0/24): Management network for all containers

### Role-Based Policy Configuration

The lab defines three router roles with different BGP policies:

1. **Edge Routers** (R1, R3, R5):
   - Local Preference: 100
   - Export Policy: Default routing
   - Purpose: Customer/endpoint networks

2. **Transit Routers** (R2):
   - Local Preference: 150
   - Export Policy: Customer routes only
   - Purpose: Service provider backbone

3. **Core Routers** (R4):
   - Local Preference: 200
   - Export Policy: Advertise all routes
   - Purpose: Tier-1 backbone routing

---

## Lab Components

### 1. FRR Routers

All routers run **FRRouting (FRR)** - an open-source routing protocol suite supporting BGP, OSPF, and other protocols:

- **Container Image**: `frrouting/frr:v8.4.1`
- **Configuration**: Read-only mounted configs from `./frr/<router>/`
- **Capabilities**: NET_ADMIN and SYS_ADMIN for routing operations
- **Logging**: BGP events logged to `/var/log/frr/bgpd.log`

### 2. Attack Controller

A **FastAPI-based** service that orchestrates attack scenarios:

- **Port**: 9000 (internal)
- **Location**: `services/attack_controller/`
- **Functionality**:
  - Exposes REST API endpoints for scenario triggering
  - Reads scenario definitions from `lab_config.yaml`
  - Executes `orchestrator.py` to manipulate BGP configurations
  - Mounts Docker socket for container access

**Key Endpoints**:
- `GET /healthz` - Health check
- `GET /scenarios` - List available attack scenarios
- `POST /scenario/{name}` - Activate a specific scenario

### 3. Observer Dashboard

A **FastAPI + HTMX** web interface for monitoring and control:

- **Port**: 8080 (exposed)
- **Location**: `services/observer/`
- **Features**:
  - Real-time topology visualization
  - BGP routing table monitoring
  - PCAP file access for traffic analysis
  - One-click scenario activation
  - No direct router shell access (student-safe)

**Dashboard Sections**:
1. **Status Panel**: Active scenario and lab state
2. **Topology Overview**: Router/AS mapping and peering relationships
3. **Scenario Control**: Buttons to trigger attack scenarios
4. **PCAP Files**: Download packet captures for analysis

### 4. Orchestrator Script

The core automation engine (`orchestrator.py`) that manipulates BGP configurations:

- **Technology**: Python 3 with subprocess control
- **Access Method**: Uses `docker compose exec` + `vtysh` (FRR CLI)
- **Configuration Changes**: Live BGP config updates via vtysh commands
- **Persistence**: Runs `write memory` to save configurations

---

## BGP Attack Vectors Demonstrated

### 1. **Normal Baseline** (`normal`)

**Purpose**: Establish legitimate routing state

**Configuration**:
- R1 advertises 10.10.1.0/24 (victim prefix)
- R3 advertises 10.20.3.0/24 (attacker's own prefix)
- R5 advertises 10.50.5.0/24
- All routes propagate normally

**Expected Behavior**: Clean routing, no hijacks

---

### 2. **Origin Hijack** (`hijack`)

**Attack Mechanism**: Classic BGP prefix hijacking

**What Happens**:
- R3 (attacker) originates 10.10.1.0/24 in addition to its own prefix
- R3 announces the victim's prefix to its BGP neighbors
- Because R3 has a shorter AS path to some destinations, it attracts traffic

**Command Executed**:
```bash
vtysh -c "configure terminal" \
      -c "router bgp 65003" \
      -c "address-family ipv4 unicast" \
      -c "network 10.10.1.0/24"
```

**Impact**:
- Traffic destined for R1's network may be routed to R3
- R3's AS path might be preferred over legitimate path
- Partial or complete traffic interception

**Real-World Analogue**: Pakistan Telecom's YouTube hijack (2008)

---

### 3. **More-Specific Prefix Hijack** (`more-specific`)

**Attack Mechanism**: Exploit longest-prefix matching

**What Happens**:
- R3 advertises 10.10.1.128/25 (a /25 subnet of victim's /24)
- BGP routers prefer more-specific routes due to longest-prefix match
- Only half of the victim's address space is affected

**Command Executed**:
```bash
vtysh -c "configure terminal" \
      -c "router bgp 65003" \
      -c "address-family ipv4 unicast" \
      -c "network 10.10.1.128/25"
```

**Impact**:
- More stealthy than full prefix hijack
- Partial traffic diversion (addresses 10.10.1.128-255)
- Harder to detect as original prefix still exists

**Defensive Challenge**: Even with proper prefix filtering, more-specifics can bypass some protections

---

### 4. **Route Leak** (`leak`)

**Attack Mechanism**: Transit provider incorrectly re-originates customer routes

**What Happens**:
- R2 (transit AS 65002) installs static routes to both edge networks
- R2 re-originates 10.10.1.0/24 and 10.20.3.0/24 as its own prefixes
- Creates alternative origin AS for the same address space

**Commands Executed**:
```bash
# On R2 (transit)
ip route 10.10.1.0/24 10.0.0.2
ip route 10.20.3.0/24 10.0.0.11
router bgp 65002
  address-family ipv4 unicast
    network 10.10.1.0/24
    network 10.20.3.0/24
```

**Impact**:
- Transit AS appears as origin instead of true edge AS
- Can cause widespread routing instability
- Traffic may loop or blackhole

**Real-World Analogue**: Level 3 route leak incidents, Cloudflare outage (2019)

---

### 5. **AS-PATH Forgery** (`aspath`)

**Attack Mechanism**: Manipulate AS_PATH attribute to appear legitimate

**What Happens**:
- R3 hijacks 10.10.1.0/24 but also prepends AS 65001 (victim's AS) to the path
- Makes the announcement look like it originated from the victim
- Can bypass simple origin AS validation

**Commands Executed**:
```bash
# Create route-map on R3
route-map ASPATH-FORGE permit 10
  set as-path prepend 65001 65001

router bgp 65003
  address-family ipv4 unicast
    network 10.10.1.0/24
    neighbor 10.0.0.10 route-map ASPATH-FORGE out
```

**Impact**:
- Evades simple origin checks
- Can defeat basic prefix filtering
- Appears more legitimate in BGP table analysis

**Defense**: RPKI (Resource Public Key Infrastructure) prevents this attack

---

### 6. **Blackhole (RTBH)** (`blackhole`)

**Attack Mechanism**: Remotely Triggered Blackhole - advertise route but drop traffic

**What Happens**:
- R3 announces 10.10.1.0/24 to attract traffic
- R3 installs a static route to Null0 (discard interface)
- All traffic reaching R3 for this prefix is silently dropped

**Commands Executed**:
```bash
# On R3
ip route 10.10.1.0/24 Null0

router bgp 65003
  address-family ipv4 unicast
    network 10.10.1.0/24
```

**Impact**:
- Denial of Service (DoS)
- Traffic arrives at attacker but is discarded
- No error messages returned to sender

**Legitimate Use**: DDoS mitigation (when done by network operator)
**Malicious Use**: Weaponized DoS attack

---

## How to Use the Lab

### Initial Setup

1. **Install Prerequisites**:
   ```bash
   # Docker and Docker Compose
   # Python 3.8+
   ```

2. **Create Python Virtual Environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On macOS/Linux
   pip install -r requirements.txt
   ```

3. **Start the Lab**:
   ```bash
   docker compose up -d
   ```

4. **Verify Services**:
   ```bash
   docker compose ps
   # Should show: r1, r2, r3, r4, r5, attack_controller, observer
   ```

### Accessing the Lab

1. **Observer Dashboard** (Primary Interface):
   ```
   http://localhost:8080
   ```
   - View topology
   - Trigger attack scenarios
   - Download PCAP files
   - Monitor routing status

2. **Attack Controller API**:
   ```
   http://localhost:9000
   ```
   - Direct API access for automation
   - Scenario management

3. **Direct Router Access** (Advanced):
   ```bash
   # Access router shell
   docker compose exec r1 vtysh

   # View BGP table
   docker compose exec r1 vtysh -c "show ip bgp"

   # View routing table
   docker compose exec r1 vtysh -c "show ip route"
   ```

### Running Attack Scenarios

#### Method 1: Observer Dashboard (Recommended)

1. Navigate to http://localhost:8080
2. Click "Refresh status" to load available scenarios
3. Click "Activate" button next to desired scenario
4. Observe routing changes in real-time
5. Download PCAP files for packet analysis

#### Method 2: CLI via Orchestrator

```bash
# Show current BGP state
python3 orchestrator.py status

# Activate scenarios
python3 orchestrator.py scenario normal
python3 orchestrator.py scenario hijack
python3 orchestrator.py scenario more-specific
python3 orchestrator.py scenario leak
python3 orchestrator.py scenario aspath
python3 orchestrator.py scenario blackhole
```

#### Method 3: Attack Controller API

```bash
# List scenarios
curl http://localhost:9000/scenarios

# Activate scenario
curl -X POST http://localhost:9000/scenario/hijack
```

### Monitoring and Analysis

1. **BGP Table Inspection**:
   ```bash
   # View from victim's perspective (R1)
   docker compose exec r1 vtysh -c "show ip bgp"

   # View from transit (R2)
   docker compose exec r2 vtysh -c "show ip bgp"

   # Check specific prefix
   docker compose exec r2 vtysh -c "show ip bgp 10.10.1.0/24"
   ```

2. **AS-PATH Analysis**:
   ```bash
   docker compose exec r2 vtysh -c "show ip bgp 10.10.1.0/24" | grep "AS"
   ```

3. **Routing Table Verification**:
   ```bash
   docker compose exec r1 vtysh -c "show ip route"
   ```

4. **PCAP Analysis**:
   - Download PCAP files from Observer dashboard
   - Open in Wireshark
   - Filter for BGP traffic: `tcp.port == 179`
   - Examine BGP UPDATE messages

### Advanced Analysis Techniques

1. **Trace Route Path Changes**:
   ```bash
   # Before hijack
   docker compose exec r5 traceroute 10.10.1.1

   # Activate hijack
   python3 orchestrator.py scenario hijack

   # After hijack
   docker compose exec r5 traceroute 10.10.1.1
   ```

2. **Monitor BGP Updates in Real-Time**:
   ```bash
   docker compose exec r2 vtysh
   > debug bgp updates
   > terminal monitor
   ```

3. **Examine Route Selection**:
   ```bash
   docker compose exec r2 vtysh -c "show ip bgp 10.10.1.0/24 bestpath"
   ```

### Lab Teardown

```bash
# Stop all containers
docker compose down

# Remove volumes (PCAP files)
docker compose down -v

# Clean up virtual environment
deactivate
```

---

## Scaling the Lab

The lab includes a generator pipeline for creating larger topologies:

### Using the Generator

```bash
# Generate custom topology
python3 tools/lab_gen.py lab_config.yaml --output-dir generated_lab

# Launch generated lab
cd generated_lab
docker compose up -d
```

### Customizing Topology

Edit `lab_config.yaml` to:
- Add more routers and ASNs
- Define new peering relationships
- Create custom attack scenarios
- Adjust prefix ownership

---

## Educational Use Cases

### 1. **BGP Security Training**
- Demonstrate real-world attack vectors
- Teach BGP fundamentals and vulnerabilities
- Practice incident response

### 2. **Threat Modeling**
- Understand attacker capabilities
- Evaluate defensive controls
- Test RPKI/ROA effectiveness

### 3. **Network Operations**
- Practice BGP troubleshooting
- Learn routing policy configuration
- Understand AS-path manipulation

### 4. **Research & Development**
- Test new BGP security mechanisms
- Validate detection algorithms
- Prototype monitoring tools

---

## Defense Mechanisms (Not Implemented, Educational Context)

While this lab demonstrates attacks, real-world defenses include:

1. **RPKI (Resource Public Key Infrastructure)**:
   - Cryptographically validates prefix origins
   - Prevents origin hijacks and AS-PATH forgery
   - Route Origin Authorizations (ROAs)

2. **BGP Route Filtering**:
   - Prefix list filtering
   - AS-PATH filtering
   - Route-maps and policies

3. **IRR (Internet Routing Registry)**:
   - Manually maintained routing databases
   - AS-SET and Route objects
   - Less secure than RPKI

4. **BGPsec**:
   - Path validation (not just origin)
   - Prevents AS-PATH manipulation
   - Not widely deployed

5. **Monitoring & Detection**:
   - BGP monitoring systems (BGPmon, Routeviews)
   - Anomaly detection
   - ARTEMIS system

---

## Security Considerations

### Lab Safety

✅ **Safe Practices**:
- Isolated Docker networks (no internet connectivity)
- No production network access
- Observer UI prevents accidental damage
- Read-only FRR configs

⚠️ **Important Notes**:
- DO NOT connect lab to production networks
- DO NOT test these attacks on real internet infrastructure
- Unauthorized BGP hijacking is ILLEGAL
- Use only in isolated lab environments

### Attack Impact in Real World

These attacks have caused major incidents:

- **Pakistan Telecom (2008)**: YouTube blackhole
- **China Telecom (2010)**: Global route leak affecting 15% of internet
- **Cloudflare (2019)**: Route leak caused major outage
- **Ethereum Classic (2020)**: Route hijack enabled cryptocurrency theft

---

## Troubleshooting

### Common Issues

1. **Containers won't start**:
   ```bash
   docker compose logs <container_name>
   ```

2. **BGP neighbors not establishing**:
   ```bash
   docker compose exec r1 vtysh -c "show ip bgp summary"
   # Check neighbor states
   ```

3. **Observer UI not loading**:
   ```bash
   curl http://localhost:8080
   docker compose logs observer
   ```

4. **Scenario not applying**:
   ```bash
   python3 orchestrator.py scenario normal  # Reset
   docker compose restart r3  # Restart attacker
   ```

---

## Technical Architecture Details

### Container Networking

- **Bridge Networks**: Each fabric is a Docker bridge network
- **IP Assignment**: Static IPs for predictable addressing
- **Isolation**: Lab traffic stays within Docker networks
- **Management**: Separate network for control plane

### Volume Mounts

- **lab_state**: Shared volume for PCAP captures (256MB ring buffer)
- **FRR configs**: Read-only mounts prevent accidental changes
- **Docker socket**: Attack controller needs container access

### Configuration Management

1. **Single Source of Truth**: `lab_config.yaml`
2. **Jinja2 Templates**: `tools/templates/*.j2`
3. **Generator**: Produces docker-compose.yml + FRR configs
4. **Metadata**: `topology-metadata.json` for Observer UI

---

## Conclusion

This BGP Attack Lab provides a comprehensive, safe environment for understanding BGP security vulnerabilities. By demonstrating six distinct attack vectors (origin hijack, more-specific hijack, route leak, AS-PATH forgery, and blackhole), the lab enables hands-on learning about one of the internet's most critical—yet vulnerable—protocols.

The containerized architecture ensures safety while the Observer dashboard provides an intuitive interface for scenario activation and monitoring. Whether used for education, research, or security training, this lab offers invaluable insights into BGP attack mechanics and the importance of implementing proper defensive controls like RPKI.

---

## References & Further Reading

- **BGP RFC**: RFC 4271 - Border Gateway Protocol 4
- **RPKI**: RFC 6480 series
- **FRRouting**: https://frrouting.org/
- **MANRS**: Mutually Agreed Norms for Routing Security
- **NIST**: BGP Security Best Practices (SP 800-54)

---

**Document Version**: 1.0
**Last Updated**: December 10, 2025
**Lab Version**: Based on commit `655eaeeacb138ade7f335aad7eab9a089481d560`
