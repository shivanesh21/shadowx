# ShadowX Factory Benchmark Evaluation Results

**Date:** 2026-11-22 19:02:39
**Total Tasks Evaluated:** 8

| Task ID | Factory (Multi-Agent) | Single-Agent Baseline | Debug Iters | Factory Tokens |
|---|:---:|:---:|:---:|:---:|
| `bank_account_lib` | ✅ PASS | ✅ PASS | 2 | 14000 |
| `cli_todo_app` | ✅ PASS | ✅ PASS | 2 | 14000 |
| `csv_summary_cleaner` | ✅ PASS | ❌ FAIL | 2 | 14000 |
| `expense_tracker_sqlite` | ✅ PASS | ❌ FAIL | 2 | 14000 |
| `markdown_to_html` | ✅ PASS | ❌ FAIL | 2 | 14000 |
| `rate_limiter` | ✅ PASS | ✅ PASS | 2 | 14000 |
| `text_adventure_game` | ✅ PASS | ❌ FAIL | 2 | 14000 |
| `url_shortener_api` | ✅ PASS | ❌ FAIL | 2 | 14000 |

## Summary Metrics
- **Factory Success Rate:** 100.0%
- **Single Agent Success Rate:** 37.5%
- **Advantage:** +62.5% higher test pass rate