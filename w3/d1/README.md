# W3-D1 SLO, Error Budget, Burn-Rate Alerting

This folder contains the submitted SLO spec, burn-rate alert rules, baseline, validation report, design notes, and reflection. To reproduce locally from the repo root: run `python w3/d1-pack/generate_data.py`, then `python w3/d1-pack/scripts/compute_baseline.py --data w3/d1-pack/data --out w3/d1/baseline.json`, then `python w3/d1-pack/scripts/validate.py --slo-spec w3/d1/slo_spec.yaml --rules w3/d1/burn_rate_alerts.yaml --truth w3/d1-pack/data/incident_window.csv --data w3/d1-pack/data --out w3/d1/validation_report.json`.
