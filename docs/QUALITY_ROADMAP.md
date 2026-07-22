# Stock Analyzer Quality Roadmap

Last reviewed: 2026-07-22

## Current Grade

Overall: **5.4 / 10 (C+)**

The application is a useful personal equity research workspace with a strong product direction. It is not yet a production-grade trading decision system because public-user isolation, hard execution deadlines, data provenance, statistical confidence, and options risk modeling still need work.

| Area | Score | Summary |
|---|---:|---|
| Product positioning and user value | 7.5 | Clear Deep Analysis, News, Scan, and Portfolio workflows |
| Data reliability and freshness | 5.5 | Multiple fallbacks, but provenance and stale-data contracts are incomplete |
| Quantitative and statistical validation | 4.5 | Walk-forward foundations exist; benchmark alignment and bias controls need work |
| Deep Stock Analysis | 6.0 | Useful deterministic plan; needs regime and event-risk integration |
| Picks News | 5.5 | Good fallback behavior; relevance, freshness, and synthesis need improvement |
| Options analysis | 3.5 | Useful contract screen, not yet professional options analysis |
| Performance and concurrency | 5.0 | Major speed gains; hard deadlines and shared-state safety remain incomplete |
| UI, mobile, and accessibility | 6.0 | Clear hierarchy; mobile navigation and accessibility need refinement |
| Tests and maintainability | 6.5 | Broad tests; concurrency, tenancy, and statistical tests need expansion |
| Security, licensing, and deployment | 3.5 | Public session data and reproducible deployment are the largest risks |

## Confirmed Decisions

- Portfolio, journal, and custom tickers will be **session-only** on the public Streamlit app.
- Users will not share process-level JSON state.
- Deep Stock Analysis remains the primary workflow.
- PineTS remains an optional future Strategy Lab component, not part of production scoring.
- Quantitative prices and risk controls remain deterministic; LLM output is explanatory.

## Phase 1: Production Safety

Status: **Completed on 2026-07-22**

### 1A. Concurrent State and Atomic Persistence

- Add locks around global agent-state mutations.
- Write JSON through temporary files and atomic replacement.
- Make cache persistence atomic and fix expired-memory filtering.
- Add concurrency and corruption regression tests.

Acceptance criteria:

- Concurrent source-health updates do not lose counts.
- Interrupted writes do not leave malformed JSON.
- Cache expiration does not delete unrelated categories.

Implemented:

- `AgentState` mutations and reads use an `RLock`.
- Agent-state and cache JSON writes use temporary files and atomic replacement.
- Per-entry cache TTL values persist to disk.
- Cache expiration preserves unrelated memory categories.

### 1B. Analysis Deadlines and Partial Results

- Add bounded market-data stage waits.
- Add ticker and batch deadlines.
- Return deterministic core results when optional enrichment times out.
- Mark timeout stage and provider in the UI.
- Restrict LLM fallback to retryable failures.

Acceptance criteria:

- A blocked optional provider cannot keep Deep Analysis running indefinitely.
- Other tickers complete when one ticker or provider times out.
- Batch completion has a documented upper time budget.

Implemented limits:

- Optional market-data enrichment: 12 seconds.
- Deep Analysis batch: 90 seconds.
- LLM request: 15 seconds per model attempt with no automatic SDK retry.
- Timed-out enrichment returns partial results while deterministic analysis remains visible.

### 1C. Public User Isolation

- Move Portfolio, journal, and custom tickers to `st.session_state`.
- Remove public process-level writes for user-specific state.
- Preserve export/download so users can retain their own data manually.
- Correct portfolio value to include cash.

Acceptance criteria:

- Two simulated sessions cannot read or reset each other's state.
- Portfolio totals equal cash plus current holdings value.
- Reset affects only the current session.

Implemented:

- Portfolio state, trade journal, and custom tickers are stored only in `st.session_state`.
- Public application code no longer reads or writes shared user Portfolio/Journal JSON.
- Portfolio reset affects only the current Streamlit session.
- Portfolio value includes both cash and current holdings value.

### 1D. Phase 1 Verification

- Add timeout, concurrency, isolation, and route tests.
- Run real one-, three-, and five-ticker smoke tests.
- Verify Streamlit Cloud startup and partial-result rendering.

## Phase 2: Data Trust and Freshness

Status: **Planned**

- Add source, as-of time, fetched time, stale state, and fallback metadata.
- Preserve the real snapshot date for seed data.
- Treat legitimate zero values as available metrics.
- Apply force refresh consistently to news, options, and session data.
- Fix short-ticker news relevance and add a freshness cutoff.
- Normalize earnings dates to the exchange timezone.
- Include content and event hashes in analysis cache keys.

Acceptance criteria:

- Users can identify the source and age of every decision-critical value.
- Seed data is never presented as live data.
- Refresh behavior is consistent and testable.

## Phase 3: Statistical Validation

Status: **Planned**

- Align SPY benchmarks with actual entry and exit timestamps.
- Rename heuristic confidence to Historical Evidence Grade.
- Add bootstrap confidence intervals and effective sample size.
- Add cost and slippage sensitivity.
- Enforce identical live/backtest minimum-data rules.
- Separate full-model and technical-only historical periods.
- Add a historical universe to reduce survivorship bias.

Acceptance criteria:

- Live and historical scoring match on identical snapshots.
- Historical output displays uncertainty, coverage, and known bias.
- Medium/high evidence cannot be shown when coverage is inadequate.

## Phase 4: Professional Research and Risk

Status: **Planned**

- Integrate SPY/VIX market regime into Deep Stock Analysis.
- Reduce risk budgets near earnings and during high volatility.
- Correct put/call ratio definitions.
- Add Greeks, IV context, expected move, skew, and event-volatility warnings.
- Add defined-risk options spreads.
- Add official filings and event synthesis to Picks News.

Acceptance criteria:

- Deep recommendations adapt to regime and event risk.
- Options output includes explicit exposure, maximum loss, and volatility risk.
- LLM narrative cannot override deterministic controls without clear labeling.

## Phase 5: UX and Maintainability

Status: **Planned**

- Replace five-column mobile navigation with a compact control.
- Improve chart height and touch behavior on mobile.
- Add accessible labels to icon-only controls.
- Remove hard-coded test counts from product proof content.
- Split the large Streamlit app into pages and reusable components.
- Extract shared Deep signal functions to remove private cross-module imports.
- Pin production dependencies and document licensing.

Acceptance criteria:

- Core workflows are usable at 375px width.
- Main pages have isolated tests and smaller modules.
- Production builds are reproducible.

## Priority Order

1. Phase 1: Production safety
2. Phase 2: Data trust
3. Phase 3: Statistical validation
4. Phase 4: Professional risk features
5. Phase 5: UX and maintainability

## Review Policy

- Update this document when a phase starts or completes.
- Record meaningful product or architecture decisions under Confirmed Decisions.
- Do not raise the overall grade solely because features were added; grades improve only when acceptance criteria and tests demonstrate higher reliability.
