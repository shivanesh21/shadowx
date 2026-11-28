# ShadowX Factory Benchmark Evaluation Results

**Date:** 2026-11-28 20:00:54
**Total Tasks Evaluated:** 8

| Task ID | Factory (Multi-Agent) | Single-Agent Baseline | Debug Iters | Factory Tokens | Baseline Tokens |
|---|:---:|:---:|:---:|:---:|:---:|
| `bank_account_lib` | ✅ PASS | ✅ PASS | 0 | 24000 | 3000 |
| `cli_todo_app` | ✅ PASS | ✅ PASS | 0 | 24000 | 3000 |
| `csv_summary_cleaner` | ❌ FAIL | ❌ FAIL | 0 | 12000 | 3000 |
| `expense_tracker_sqlite` | ❌ FAIL | ❌ FAIL | 0 | 12000 | 3000 |
| `markdown_to_html` | ❌ FAIL | ❌ FAIL | 0 | 12000 | 3000 |
| `rate_limiter` | ✅ PASS | ✅ PASS | 0 | 24000 | 3000 |
| `text_adventure_game` | ❌ FAIL | ❌ FAIL | 0 | 12000 | 3000 |
| `url_shortener_api` | ❌ FAIL | ❌ FAIL | 0 | 12000 | 3000 |

## Summary Metrics
- **Factory Success Rate:** 37.5% (3/8)
- **Single Agent Success Rate:** 37.5% (3/8)
- **Advantage:** +0.0% higher test pass rate
- **Factory Avg Tokens:** 16,500
- **Baseline Avg Tokens:** 3,000
