# BGP Attack Lab

This repository provides a self-contained BGP attack playground built
with Docker and FRRouting (FRR). It spins up three routers:

- **R1** (Victim, AS 65001) – legitimately owns `10.10.1.0/24`.
- **R2** (Transit, AS 65002) – passes routes between R1 and R3.
- **R3** (Attacker, AS 65003) – legitimately owns `10.20.3.0/24` but can
  hijack the victim's prefix via the provided orchestrator.

The `orchestrator.py` script toggles between clean, hijack, and
more-specific hijack scenarios so you can observe the resulting BGP
state from the victim and transit perspectives.

## Requirements

- Linux or macOS host with Docker and the Docker Compose plugin
- Python 3.8+ for the orchestrator script

All networks are private Docker bridges; nothing is exposed to the
public Internet.

## Repository layout

```
.
├── docker-compose.yml
├── orchestrator.py
└── frr/
    ├── r1/
    │   ├── daemons
    │   └── frr.conf
    ├── r2/
    │   ├── daemons
    │   └── frr.conf
    └── r3/
        ├── daemons
        └── frr.conf
```

## Usage

1. **Start the lab**

   ```bash
   docker compose up -d
   ```

2. **Check baseline status**

   ```bash
   python3 orchestrator.py status
   ```

   R1 should originate `10.10.1.0/24` and learn `10.20.3.0/24` via R2 → R3.

3. **Run scenarios**

   - Classic prefix hijack:

     ```bash
     python3 orchestrator.py scenario hijack
     python3 orchestrator.py status
     ```

   - More-specific hijack:

     ```bash
     python3 orchestrator.py scenario more-specific
     python3 orchestrator.py status
     ```

   - Reset to the clean state:

     ```bash
     python3 orchestrator.py scenario normal
     ```

4. **Tear down the lab**

   ```bash
   docker compose down
   ```

## Extending the lab

The setup intentionally mirrors a simple three-AS topology so you can
easily add more routers or experiments such as RPKI validation,
AS-path prepending, or packet captures (`docker compose exec r2 tcpdump -i any port 179`).
