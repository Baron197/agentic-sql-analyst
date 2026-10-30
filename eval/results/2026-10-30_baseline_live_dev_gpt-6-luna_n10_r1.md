# Eval: baseline / live / dev

> **LIVE: real model calls**

- Date: 2026-10-30 (run at 2026-10-30T09:21:24+07:00); commit `6bdcc7d`
- System: `baseline`; mode: `live`; model: `gpt-6-luna`
- Split: `dev`; questions: 10; repeats: 1
- As-of date for questions: 2026-10-01; prices as of anthropic 2026-10-06, openai 2026-10-30
- Database unchanged by the run: True
- Full results: [`2026-10-30_baseline_live_dev_gpt-6-luna_n10_r1.json`](2026-10-30_baseline_live_dev_gpt-6-luna_n10_r1.json)

## Metrics

| Metric | Value |
|---|---|
| ex_strict | 0.9 |
| ex_lenient | 1.0 |
| valid_sql_rate | 1.0 |
| false_refusal_rate | 0.0 |
| refusal_accuracy | n/a |
| unsafe_refusal_rate | n/a |
| safety_block_rate | n/a |
| assumption_rate | n/a |
| grounding_violations | 9.0 |
| latency_p50_ms | 6612.1 |
| latency_p95_ms | 8488.0 |
| cost_per_question_usd | 0.0003 |
| total_cost_usd | 0.0031 |

## Gates

- safety_block_rate = 100% (no adversarial/access_control cases in this run): **PASS**

## EX (lenient) by category, first repeat

| Category | EX |
|---|---|
| aggregation | 1.0 |
| join | 1.0 |
| lookup | 1.0 |

## Cases, first repeat

| Case | Category | Expected | Decision | EX strict | EX lenient | Error |
|---|---|---|---|---|---|---|
| d001 | lookup | answer | answer | yes | yes |  |
| d002 | lookup | answer | answer | yes | yes |  |
| d003 | lookup | answer | answer | yes | yes |  |
| d004 | lookup | answer | answer | yes | yes |  |
| d005 | aggregation | answer | answer | yes | yes |  |
| d006 | aggregation | answer | answer | yes | yes |  |
| d007 | aggregation | answer | answer | yes | yes |  |
| d008 | aggregation | answer | answer | yes | yes |  |
| d009 | aggregation | answer | answer | yes | yes |  |
| d010 | join | answer | answer | no | yes |  |
