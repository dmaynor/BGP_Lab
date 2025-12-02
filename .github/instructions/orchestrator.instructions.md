---
appliesTo:
  - orchestrator.py
  - network_*.py
  - start_lab.py
  - stop_lab.py
  - show_lab_status.py
---

# Orchestrator and Network Management Scripts

## Purpose

These scripts manage the BGP lab lifecycle and implement attack scenarios. They interact directly with Docker containers running FRR routers.

## Key Principles

### Direct Container Interaction

- Use `subprocess` to execute `docker exec` commands
- Always specify container name explicitly (e.g., `r1`, `r2`, `r3`)
- Use `vtysh -c` for FRR commands from outside the container
- Handle subprocess errors gracefully with proper error messages

### Scenario Implementation

When adding or modifying scenarios in `orchestrator.py`:

1. Add the scenario function following the naming pattern: `_scenario_<name>()`
2. Use the scenario registry decorator or mapping
3. Include clear docstrings explaining what BGP manipulation occurs
4. Return meaningful status/output that can be surfaced in the Observer UI
5. Make changes idempotent - running a scenario twice should be safe

### FRR Command Best Practices

```python
# Good: Clear, specific FRR command
subprocess.run(
    ["docker", "exec", "r3", "vtysh", "-c", "conf t", "-c", 
     "router bgp 65003", "-c", "network 10.10.1.0/24"],
    check=True,
    capture_output=True,
    text=True
)

# Bad: Shell=True (security risk)
subprocess.run(
    f"docker exec r3 vtysh -c 'conf t' -c 'router bgp 65003'",
    shell=True  # AVOID
)
```

### Network Status Checking

- Parse `docker ps` output to verify container state
- Use `docker exec <router> vtysh -c 'show bgp summary'` to check BGP sessions
- Parse routing tables with `show ip bgp` or `show ip route`
- Present output in a user-friendly format (tabular when appropriate)

## Code Patterns

### Error Handling

```python
try:
    result = subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True
    )
    return result.stdout
except subprocess.CalledProcessError as e:
    print(f"Command failed: {e.stderr}", file=sys.stderr)
    return None
```

### Configuration Changes

- Always use `conf t` to enter configuration mode
- Combine related commands in a single `vtysh` invocation for atomicity
- Use `write memory` or equivalent to persist changes if needed (though in this lab configs are ephemeral)

### Verification Steps

After making routing changes:
1. Verify BGP session state
2. Check that expected prefixes appear in the routing table
3. Optionally verify from the victim/observer perspective

## Testing Changes

```bash
# Start the lab
docker compose up -d

# Run your scenario
python3 orchestrator.py scenario your_scenario_name

# Verify BGP state
python3 orchestrator.py status

# Check from inside a router
docker exec r1 vtysh -c 'show ip bgp'

# Clean up
docker compose down
```

## Common Tasks

### Adding a New Attack Scenario

1. Define the scenario in `lab_config.yaml` under `scenarios:`
2. Implement `_scenario_<name>()` in orchestrator.py
3. Register it in the scenario dispatcher (SCENARIOS dict or similar)
4. Test thoroughly before exposing via Attack Controller

### Parsing BGP Output

FRR's `show` commands produce text output. Parse carefully:
- Split on newlines and whitespace
- Skip header lines
- Handle cases where tables might be empty
- Use regex for complex patterns but keep it readable

### Debugging

- Use `docker logs <container>` to see FRR logs
- Add verbose output with `-v` or `--verbose` flags
- Log intermediate steps when troubleshooting complex scenarios

## DO NOT

- Don't modify container filesystems directly - use vtysh
- Don't assume containers are always running - check first
- Don't hardcode the 3-router topology (code should scale)
- Don't leave containers in inconsistent state - always have a "normal" scenario to reset
- Don't expose dangerous commands to untrusted users via the API
