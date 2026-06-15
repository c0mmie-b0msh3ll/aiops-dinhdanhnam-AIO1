# Blameless Postmortem — Edge WAF Regex Saturation

## Summary

On 2026-06-15, a WAF regex rule revision caused high CPU usage in the edge middleware. The edge tier became slow, which raised API gateway latency and created downstream timeout symptoms in checkout and payment. The reproduced incident lasted about 10 minutes from initial rollout to stable recovery. Customer-facing impact was elevated latency and intermittent 5xx responses for requests passing through the affected edge path.

## Impact

- User-facing API p99 latency rose from 180ms to about 2400ms.
- Edge CPU rose from 35% to 92%.
- Checkout saw downstream timeout rate around 18%.
- Payment queue depth rose to 920 while upstream requests slowed.
- Estimated customer-visible degradation window: 2026-06-15T02:01:35Z to 2026-06-15T02:07:30Z.

## Detection

The pipeline detected the outage in under 30 seconds after the API latency page fired. The correlator grouped edge, API gateway, checkout, and payment symptoms into one incident. RCA returned `api-gateway` with confidence 0.58, but the better root candidate was `edge-waf`: edge CPU saturation started before API latency, and a WAF rule revision had just reached canary.

Detection gaps:

1. RCA selected the loudest gateway symptom instead of the earlier edge middleware signal.
2. The evidence block treated the deployment event as secondary context rather than a first-class causal clue.

## Root Cause

The immediate technical cause was catastrophic regex behavior in the edge WAF middleware. A rule pattern consumed excessive CPU for a subset of request paths, slowing edge request processing and causing API gateway latency to rise. Downstream services were healthy but appeared degraded because upstream calls arrived slowly or timed out.

## Contributing Factors

- Regex rule validation checked syntax but not worst-case runtime.
- The canary window was short relative to traffic diversity.
- RCA ranked high-volume API alerts above lower-volume edge middleware saturation.
- Deployment event correlation had lower weight than metric alert count.

## Timeline

| Time UTC | Source | Event |
|---|---|---|
| 2026-06-15T02:00:00Z | deploy | WAF regex rule revision promoted to edge middleware canary |
| 2026-06-15T02:01:12Z | metrics | edge CPU utilization rises from 35% to 92% |
| 2026-06-15T02:01:35Z | metrics | api_gateway p99 latency rises from 180ms to 2400ms |
| 2026-06-15T02:02:05Z | alerts | tier1 API latency and edge 5xx alerts fire |
| 2026-06-15T02:02:20Z | aiops | correlator groups edge, gateway, checkout, and payment symptoms |
| 2026-06-15T02:02:45Z | aiops | RCA selects api-gateway with confidence 0.58 |
| 2026-06-15T02:04:10Z | operator | WAF rule rollback command issued |
| 2026-06-15T02:05:00Z | metrics | edge CPU drops below 50%; latency begins recovery |
| 2026-06-15T02:07:30Z | metrics | api_gateway p99 latency returns below 250ms |
| 2026-06-15T02:10:00Z | incident | incident moved to monitoring |

## What Went Well

- Multi-service symptoms were grouped into one incident.
- Page fired quickly enough for a target under 30 seconds after the gateway symptom.
- Rollback path was simple and recovery started within one minute of rollback.

## What Could Improve

- RCA needs stronger causal-lag scoring so earlier edge saturation outranks later API symptoms.
- WAF changes need performance tests with adversarial request samples before canary.
- Deployment events should be weighted as evidence when they occur inside the incident window.

## Action Items

| Action | Owner | Due | Success measure |
|---|---|---|---|
| Add regex worst-case runtime test for WAF rule changes | Platform | 2026-06-22 | CI blocks patterns exceeding 50ms/test corpus |
| Add causal-lag feature to RCA scoring | AIOps | 2026-06-29 | RCA ranks edge-waf above api-gateway in replay |
| Promote deploy events to first-class correlation evidence | AIOps | 2026-06-29 | Evidence block includes deploy event with timestamp and service |
| Extend WAF canary to include synthetic adversarial paths | Edge team | 2026-07-01 | Canary catches CPU saturation before broader rollout |
