from __future__ import annotations


def is_worth_it(
    num_services: int,
    incidents_per_month: int,
    avg_incident_duration_hours: float,
    downtime_cost_per_hour: float,
    expected_mttr_reduction_pct: float = 0.4,
    aiops_monthly_cost: float = 15_000,
) -> dict:
    gross_monthly_incident_cost = incidents_per_month * avg_incident_duration_hours * downtime_cost_per_hour
    monthly_value = gross_monthly_incident_cost * expected_mttr_reduction_pct
    monthly_cost = aiops_monthly_cost
    roi = monthly_value / monthly_cost if monthly_cost else float("inf")
    payback_months = monthly_cost / monthly_value if monthly_value > 0 else float("inf")
    if roi > 1.5:
        verdict = "worth_it"
    elif roi > 1.0:
        verdict = "marginal"
    else:
        verdict = "not_worth_it"
    return {
        "monthly_value": round(monthly_value, 2),
        "monthly_cost": round(monthly_cost, 2),
        "roi": round(roi, 2),
        "payback_months": round(payback_months, 2) if payback_months != float("inf") else float("inf"),
        "verdict": verdict,
    }


if __name__ == "__main__":
    print(is_worth_it(num_services=20, incidents_per_month=2,
                      avg_incident_duration_hours=1, downtime_cost_per_hour=10_000,
                      aiops_monthly_cost=15_000))
    print(is_worth_it(num_services=100, incidents_per_month=5,
                      avg_incident_duration_hours=2, downtime_cost_per_hour=20_000,
                      aiops_monthly_cost=25_000))
    # E-commerce checkout scenario: $30k/hour approximates a mid-size store
    # where checkout degradation affects paid conversion but not all browsing.
    print(is_worth_it(num_services=35, incidents_per_month=4,
                      avg_incident_duration_hours=1.5, downtime_cost_per_hour=30_000,
                      expected_mttr_reduction_pct=0.35,
                      aiops_monthly_cost=18_000))
