# ADR-001: Use Causal-Lag And Topology-Aware RCA For Edge Cascades

## Status

Accepted for next iteration.

## Context

The reproduced edge-WAF regex outage showed that the pipeline detected the incident quickly but selected `api-gateway` as root with confidence 0.58. The better root candidate was `edge-waf` because edge CPU saturation started before API latency, and a WAF rule revision was inside the incident window. This is the same class of weakness seen in W3-D2 experiment 5 and 9: the loudest visible service can outrank an upstream or infrastructure dependency.

## Decision

Enhance RCA scoring with causal-lag and topology features. A candidate receives additional weight when its anomaly starts before downstream symptoms, sits upstream in the dependency graph, or has a recent deploy/config event inside the incident window. Alert count remains evidence, but it cannot outrank earlier upstream evidence by itself.

## Alternatives Considered

### Alternative 1: Count-based RCA

Pros:
- Simple to implement.
- Easy to explain from alert volume.

Cons:
- Picks noisy downstream services during retry storms or edge cascades.
- Failed in the reproduced outage by favoring `api-gateway` over earlier `edge-waf` evidence.

### Alternative 2: LLM-only RCA narrative

Pros:
- Produces readable explanations quickly.
- Can combine logs, deploy events, and metrics in natural language.

Cons:
- Risk of plausible but ungrounded root-cause claims.
- Confidence is hard to calibrate without explicit metric, topology, and timestamp evidence.

### Alternative 3: Topology-aware RCA without causal lag

Pros:
- Better than alert counting for upstream/downstream relationships.
- Cheap to implement using the existing service graph.

Cons:
- Still ambiguous when several upstream candidates exist.
- Does not distinguish a dependency that drifted first from a dependency that merely became noisy later.

## Consequences

Positive:
- RCA should rank `edge-waf` above `api-gateway` when edge saturation starts first.
- Retry-storm and backing-store incidents get a more defensible evidence chain.

Trade-off:
- Requires reliable timestamps and service topology. Missing or delayed telemetry can reduce confidence.
- The scoring model becomes less simple than alert counting and needs replay tests to prevent overfitting.

## Validation Plan

Replay the W3-D3 timeline and W3-D2 experiments 5, 9, and 10. The change passes only if `edge-waf`, `payment-db`, and `dns-resolver` rise above noisy application services while experiment 10 still avoids `checkout-svc`.
