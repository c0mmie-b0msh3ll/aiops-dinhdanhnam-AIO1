# W3-D1 Design Notes

## 1. Frontend SLI Choice

For frontend I chose `frontend_page_experience_ok`: `dom_ready_ms < 3000 AND js_error=false AND network_error=false` over all RUM page-load events. The baseline has 518,400 RUM events over 3 days, with DOM-ready p50 405ms, p95 959ms, and p99 1430ms. Pure page-load latency alone is not enough because JavaScript and network errors are direct user pain even when DOM-ready is fast. JS errors affected 4,682 events, or 0.903%, and network errors affected 2,433 events, or 0.469%. I rejected raw DOM-ready p50 because median hides regional CDN pain; I rejected JS error rate alone because it misses slow but technically successful pages; I rejected network error rate alone because it ignores frontend runtime failures. The combined SLI is measurable from `frontend_rum.jsonl`, user-side, and proportional to user experience.

## 2. API SLO Target

For API I chose a 99.0% availability SLO instead of 99.9% or 99.99%. The generated API baseline has 2,073,780 sampled requests over 3 days and 7,234 system failures, a fail rate of 0.3488%. Projected to 30 days, API has 20,737,800 events. A 99.0% target gives 207,378 allowed failures and about 432 minutes of equivalent monthly budget at the sampled request rate. A 99.9% target would allow only 20,738 failures, but the 3-day generated window already includes 7,234 failures during controlled incidents. A 99.99% target would allow only 2,074 failures per month, below the observed 3-day incident count, so it would create constant policy violations. 99.0% is a realistic first SLO for a lab stack while still forcing action on sustained incidents.

## 3. Latency Threshold

The API latency distribution supports a 500ms user-facing threshold for "good" request experience, while the burn-rate validation focuses on 5xx/429 availability failures. From `access_log.jsonl`, API latency was p50 45ms, p95 104ms, p99 156ms, and max 2553ms. A 200ms threshold would sit only slightly above p99 and would classify too much normal tail variation as bad during sampled traffic. A 1s threshold would be too loose because the generated incidents push latency sharply upward and users would already feel checkout/API pain before 1s. I kept 500ms as a practical threshold in `slo_spec.yaml`: high enough to avoid p99 noise under normal load, but low enough to catch meaningful degradation. For alerting, availability burn rate remains the page signal because the validator scores API failures from 5xx and 429.

## 4. 4xx Exclusion

I exclude 4xx responses from system failures except 429. In the generated API logs there were 41,712 non-429 4xx responses out of 2,073,780 requests, or 2.01%. By endpoint, every route had about 2% client-error traffic: `/api/cart` 2.04%, `/api/orders` 2.02%, `/api/checkout` 2.01%, `/api/products` 2.02%, and `/api/user` 1.98%. No endpoint had 4xx above 5%, and the distribution is flat enough to look like normal client/bot behavior rather than a service outage. Counting those as system failures would make the API SLO noisy and would burn budget when users send invalid requests. I count 429 as failure because system-side rate limiting rejects otherwise valid user work and is proportional to user pain.

## 5. MWMBR Tuning

I did not use the Google default 1h/5m at 14.4 for the API page tier because this small 3-day lab dataset has short 8-20 minute incidents. The default passed the validator but had 60s median MTTD regression versus the static baseline. I tuned page windows to 15m/2m at burn rate 3 for tier 1 and 1h/5m at burn rate 2 for tier 2. This kept the multi-window AND behavior but reacted faster to short API incidents. Validation produced 3 MWMBR fires, 3 true positives, 0 false positives, 0 false negatives, 86.4% noise reduction, and 0s MTTD delta. Tier 3 remains 3d/6h at burn rate 1 as a ticket, not a page, so long slow budget consumption is visible without waking on-call.
