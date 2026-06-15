# W3-D3 Submission — dinhdanhnam

## Outage chosen

- ID: 3
- Name: Cloudflare Regex 2019-style edge outage
- Why this one: I chose this because it shows how a small config/rule change can create a large reliability event. It also tests whether RCA can look past the loud API gateway symptom and identify an earlier edge/WAF cause.
- Failure mode: regex + cascading edge latency

## 3 thứ tôi học từ outage này

1. A fast detector is not enough. The pipeline detected the incident quickly, but RCA still chose `api-gateway` instead of the better `edge-waf` root.
2. Deployment/config events should be first-class RCA evidence. In this reproduction, the WAF rule revision happened before the CPU and latency symptoms.
3. Regex and rule systems need performance tests, not only syntax validation. A valid rule can still create catastrophic runtime behavior.

## 1 thứ pipeline của tôi sẽ vẫn miss nếu outage này xảy ra real

- Pattern: edge middleware CPU saturation caused by a WAF rule with bad regex behavior.
- Why miss: the current RCA weights high-volume API alerts more heavily than lower-volume edge deploy and CPU evidence.
- Mitigation idea: add causal-lag scoring and promote deploy events into the RCA feature set, as described in `ADR.md`.

## 1 quyết định trong ADR mà tôi không hoàn toàn chắc

I am not fully sure about how much weight to give causal-lag evidence. If the weight is too low, RCA keeps choosing noisy downstream services. If it is too high, delayed telemetry from an infrastructure node could make the platform blame the wrong upstream service. I would validate the weight through replay tests before production rollout.

## Cost model verdict cho stack của tôi

- ROI: 3.5
- Payback: 0.29 tháng
- Verdict: worth_it
