from __future__ import annotations

import csv
import json
from pathlib import Path


OUTPUT_DIR = Path("outputs")


TIERS = [
    {"tier": "Small", "services": 10, "log_gb_day": 50, "metric_events_sec": 100_000},
    {"tier": "Medium", "services": 100, "log_gb_day": 500, "metric_events_sec": 1_000_000},
    {"tier": "Large", "services": 1000, "log_gb_day": 5_000, "metric_events_sec": 10_000_000},
]


ASSUMPTIONS = {
    "days_per_month": 30,
    "hot_log_retention_days": 7,
    "warm_cold_retention_days": 30,
    "hot_log_storage_usd_per_gb_month": 0.25,
    "s3_parquet_usd_per_gb_month": 0.023,
    "metric_storage_usd_per_million_events": 0.002,
    "kafka_compute_usd_per_service_month": 6.0,
    "flink_compute_usd_per_service_month": 4.0,
    "observability_backend_compute_usd_per_service_month": 10.0,
    "network_usd_per_gb": 0.02,
    "datadog_log_ingest_usd_per_gb": 1.25,
    "datadog_infra_host_usd_per_host_month": 15.0,
    "hosts_per_service": 1.5,
}


def estimate_tier(tier: dict) -> dict:
    days = ASSUMPTIONS["days_per_month"]
    services = tier["services"]
    log_gb_month = tier["log_gb_day"] * days
    metric_events_month = tier["metric_events_sec"] * 60 * 60 * 24 * days

    hot_log_gb_month_equivalent = tier["log_gb_day"] * ASSUMPTIONS["hot_log_retention_days"]
    cold_log_gb_month_equivalent = tier["log_gb_day"] * ASSUMPTIONS["warm_cold_retention_days"]

    storage = (
        hot_log_gb_month_equivalent * ASSUMPTIONS["hot_log_storage_usd_per_gb_month"]
        + cold_log_gb_month_equivalent * ASSUMPTIONS["s3_parquet_usd_per_gb_month"]
        + metric_events_month / 1_000_000 * ASSUMPTIONS["metric_storage_usd_per_million_events"]
    )
    compute = services * (
        ASSUMPTIONS["kafka_compute_usd_per_service_month"]
        + ASSUMPTIONS["flink_compute_usd_per_service_month"]
        + ASSUMPTIONS["observability_backend_compute_usd_per_service_month"]
    )
    network = log_gb_month * ASSUMPTIONS["network_usd_per_gb"]
    build_total = storage + compute + network

    datadog_hosts = services * ASSUMPTIONS["hosts_per_service"]
    datadog_total = (
        log_gb_month * ASSUMPTIONS["datadog_log_ingest_usd_per_gb"]
        + datadog_hosts * ASSUMPTIONS["datadog_infra_host_usd_per_host_month"]
    )

    return {
        "tier": tier["tier"],
        "services": services,
        "log_gb_day": tier["log_gb_day"],
        "metric_events_sec": tier["metric_events_sec"],
        "build_storage_usd": round(storage, 2),
        "build_compute_usd": round(compute, 2),
        "build_network_usd": round(network, 2),
        "build_total_usd": round(build_total, 2),
        "datadog_total_usd": round(datadog_total, 2),
        "build_vs_buy_delta_usd": round(datadog_total - build_total, 2),
        "recommendation": "Buy first" if tier["tier"] == "Small" else "Hybrid / build core pipeline",
    }


def as_markdown(rows: list[dict]) -> str:
    headers = [
        "tier",
        "services",
        "log_gb_day",
        "metric_events_sec",
        "build_storage_usd",
        "build_compute_usd",
        "build_network_usd",
        "build_total_usd",
        "datadog_total_usd",
        "build_vs_buy_delta_usd",
        "recommendation",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] + ["---:"] * 9 + ["---"]) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row[h]) for h in headers) + " |")
    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    rows = [estimate_tier(tier) for tier in TIERS]

    (OUTPUT_DIR / "cost_estimate.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    with (OUTPUT_DIR / "cost_estimate.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    markdown = as_markdown(rows)
    (OUTPUT_DIR / "cost_estimate.md").write_text(markdown + "\n", encoding="utf-8")

    print("Monthly cost estimate")
    print(markdown)
    print()
    print("Assumptions")
    for key, value in ASSUMPTIONS.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
