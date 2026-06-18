# Ronki Closed-Loop Auto-Remediation

Run from the lab root:

```bash
cd w3/lab-closed-loop
bash data-pack/scripts/start_stack.sh
cd dinhdanhnam
uv run python closed_loop.py --config config.yaml
```

The orchestrator polls Alertmanager every 15 seconds, maps alerts to runbooks from `config.yaml`, performs dry-run, checks blast radius, executes the runbook, verifies with Prometheus for three passing samples in 60 seconds, and rolls back on verify failure. Use `--dry-run` to detect and decide without executing real actions.
