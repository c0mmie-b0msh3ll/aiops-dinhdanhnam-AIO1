# Ronki Closed-Loop Auto-Remediation

Run from the lab root on Windows PowerShell:

```powershell
cd w3/lab-closed-loop
powershell -NoProfile -ExecutionPolicy Bypass -File dinhdanhnam/scripts/Start-Stack.ps1
cd dinhdanhnam
python closed_loop.py --config config.yaml
```

The orchestrator polls Alertmanager every 15 seconds, maps alerts to runbooks from `config.yaml`, performs dry-run, checks blast radius, executes the runbook, verifies with Prometheus for three passing samples, and rolls back on verify failure. The Windows config uses a 120-second verify timeout because Docker Desktop can take longer than Linux to recreate a container and expose `/health`. Use `--dry-run` to detect and decide without executing real actions.

See `../../WINDOWS_STEP_BY_STEP.md` for the full Windows walkthrough and test commands.
