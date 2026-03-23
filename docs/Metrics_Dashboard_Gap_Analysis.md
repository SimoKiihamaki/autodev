# Metrics Dashboard Gap Analysis

**Date:** 2026-03-23  
**Implementation:** `src/dashboard/metrics_dashboard.py` (327 lines)  
**Spec:** `~/Documents/Obsidian/Hermes/Knowledge/AutoDev/Metrics_Dashboard_Spec.md`

---

## Summary

The foundation implementation is solid with a 3-panel Rich TUI layout, callback-based integration with TrainingOrchestrator, and basic metrics display. However, several features from the spec are missing and there is one syntax error.

---

## Critical Issues (P0)

| Issue | Location | Description | Effort |
|-------|----------|-------------|--------|
| Syntax Error | Line 278 | `self.metrics.tokens_used=***` is incomplete code - will cause runtime error | **5 min** |

---

## Missing Features vs Spec

### 1. ComparisonResult Integration (P1)

**Spec Reference:** Section 3 - Data Sources mentions `ComparisonResult` with `tasks_improved/regressed`

**Current State:** Dashboard has no integration with `ComparisonResult` from `swebench_runner.py`

**Missing:**
- `update_comparison()` method to accept `ComparisonResult`
- Display fields: `tasks_improved`, `tasks_regressed`, `improvement_percent`

**Effort:** 1-2 hours

### 2. Average Execution Time Display (P1)

**Spec Reference:** Mock layout shows "Avg: 847s" in evaluation panel

**Current State:** `EvaluationResults.avg_execution_time` exists in swebench_runner.py but dashboard doesn't display it

**Effort:** 15 minutes

### 3. Timeout Tracking (P2)

**Spec Reference:** Section 1 - Core Metrics lists `failed/timeouts` separately

**Current State:** Only `failed_tasks` displayed; `EvaluationResults.timeouts` not shown

**Effort:** 30 minutes

---

## Future Enhancements (from Spec Section 5.6)

These are explicitly marked as future work in the spec:

| Feature | Status | Effort |
|---------|--------|--------|
| Color-coded status indicators | ❌ Not implemented | 2-3 hours |
| Multi-run comparison view | ❌ Not implemented | 4-6 hours |
| Export metrics to JSON | ❌ Not implemented | 1-2 hours |
| WebSocket streaming | ❌ Not implemented | 6-8 hours |

---

## Detailed Gap Breakdown

### Core Metrics Comparison

| Metric | Spec Required | Implemented | Notes |
|--------|--------------|-------------|-------|
| `stage` | ✅ | ✅ | Working |
| `stage_progress` | ✅ | ✅ | Working |
| `traces_collected` | ✅ | ✅ | Working |
| `completed_steps/total_steps` | ✅ | ✅ | Working |
| `best_resolution_rate` | ✅ | ✅ | Working |
| `elapsed_time` | ✅ | ✅ | Working |
| `resolved/total_tasks` | ✅ | ✅ | Working |
| `failed_tasks` | ✅ | ✅ | Working |
| `timeouts` | ✅ | ❌ | Missing from display |
| `total_cost` | ✅ | ✅ | Working |
| `total_tokens_used` | ✅ | ⚠️ | Bug on line 278 |
| `tasks_improved` | ✅ | ❌ | ComparisonResult not integrated |
| `tasks_regressed` | ✅ | ❌ | ComparisonResult not integrated |
| `avg_execution_time` | ✅ | ❌ | Not displayed |

### Layout Comparison

| Layout Element | Spec | Implemented |
|----------------|------|-------------|
| Header with stage + progress | ✅ | ✅ |
| Training panel | ✅ | ✅ |
| Evaluation panel | ✅ | ✅ |
| Progress bar with timing | ✅ | ✅ |
| Summary footer (Elapsed/ETA/Tokens) | ✅ | ⚠️ Tokens in eval panel |

---

## Recommended Priority Order

1. **Fix syntax error** (Line 278) - 5 min
2. **Add avg_execution_time display** - 15 min
3. **Add timeout count display** - 30 min
4. **Implement ComparisonResult integration** - 1-2 hours
5. **Color-coded status indicators** - 2-3 hours (future enhancement)
6. **Export to JSON** - 1-2 hours (future enhancement)
7. **Multi-run comparison view** - 4-6 hours (future enhancement)
8. **WebSocket streaming** - 6-8 hours (future enhancement)

---

## Total Estimated Effort

- **Critical fixes:** 5 min
- **Missing spec features (P1-P2):** 2-3.5 hours
- **Future enhancements:** 13-19 hours

---

## Files Referenced

- Implementation: `src/dashboard/metrics_dashboard.py`
- Spec: `~/Documents/Obsidian/Hermes/Knowledge/AutoDev/Metrics_Dashboard_Spec.md`
- Related: `src/evaluation/swebench_runner.py` (EvaluationResults, ComparisonResult classes)
