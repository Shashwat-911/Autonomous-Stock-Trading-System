# Project automation and decision audit — 2026-10-31

Reviewed revision: 14b9c77. Scope: source-level review of live orchestration,
strategy/risk, broker paths, ML training/prediction/optimization, research,
publication and GitHub/Render configuration. This is not an exhaustive security
assessment or confirmation of current Render dashboard settings, secrets or every
historical execution. No production behavior was changed by this audit.

## Priority findings

### P1 — Startup clears daily risk protections
Evidence: main.py startup calls sync_day_start_balance then reset_daily_state;
risk/manager.py both clear the breach latch and reset clears cooldowns.
A same-day restart reanchors the baseline at reduced equity and clears a previous
breach. Persist state by New York trading date, reset only for a new session,
and reconcile with durable broker/account history after ephemeral storage loss.
Test restart after a loss breach and restart during cooldown.

### P1 — Missing daily data is treated as bullish
Evidence: main.py initializes daily_trend_bullish=True, catches fetch exceptions
with pass, and also retains True if fewer than 20 daily bars exist. This can add
confidence despite missing evidence. Represent unknown explicitly and define
entry gating for missing/stale data. Audit broad-market regime fallback separately.
This finding establishes a bad fallback, not attribution of past losses to it.

### P1 — Claimed trailing protection is not implemented
Evidence: broker/alpaca.py _update_trailing_stop only adjusts memory and logs.
Original broker brackets are separate protection. Either implement confirmed
broker stop replacement with lifecycle tests, or remove claims of active trailing
protection. Never silently change exits merely to improve historical numbers.

### P1 — Historical simulator results remain provisional
research/simulator.py is long-only, OHLC-based and has no real volume-limited fills,
quote execution, shared portfolio cash allocation, or certified live scan replay.
Partial reductions are supported; that is not partial order-fill simulation.
research/strategies.py hourly adapter omits live entry cutoff/cooldown parity.
Do not describe it as a complete replacement for the live broker.

### P1 before any ML activation — Predictor failure permits entries
ml/predictor.py returns (True,1.0) for missing model/features or NaNs; model loading
does not enforce the research status, training interval or approval metadata.
The live ML filter is currently disabled, so this is a latent activation hazard.
Implement explicit unavailable status, schema/interval/model approval checks,
calibration and immutable model identity before it can influence orders.

### P2 — Weekly ML job computes artifacts without preserving them
.github/workflows/trading_bot.yml runs ml/run_pipeline.py weekly. The research
model, feature importance and training results have no dedicated upload step.
The account publisher stages account reports/logs, not research model artifacts.
Ephemeral runner results can disappear. Preserve candidate bundles and evaluation
reports in a private/durable artifact registry; never automatically promote them.

### P2 — Research failure can block account reporting
The weekly model step precedes account publication in the same job. Failed
optimization now correctly exits, but later reporting is skipped under default
success conditions. Separate ML into an independent job/workflow and preserve
failure evidence. Financial reporting must not depend on training success.

### P2 — New research automation is observation, not adaptation
research/cloud.py daily reads account execution history and emits aggregate
attribution; weekly re-downloads data and compares fixed 2023–2025 history.
It does not run the ETF candidate forward, train an hourly model, or change the
live strategy. Repeating the same historical comparison is a regression check,
not new evidence of edge. Implement an independently persisted shadow portfolio
with idempotent daily orders/fills and closed-bar timing before claiming forward
validation. No interaction with current broker positions is needed.

### P2 — Replay evidence remains missing
Version is emitted through logger (stderr); Render separates stderr into debug
logs, while the public archive preserves clean stdout. A run-level revision also
cannot explain each order. Capture protected structured events containing run,
code/config/model/data hashes, completed bar time, features, decision, risk gate,
client order ID and order lifecycle. Archive daily with explicit retention checks.
The prior 70 episodes cannot acquire missing historical evidence retroactively.

### P2 — Publication and deployment need isolation
research/ is not in render.yaml ignoredPaths. Research-only edits may trigger
trading-service redeployment if dashboard settings follow this blueprint.
Different publishing workflows use different concurrency groups; retries help but
there is no global publisher lock. Research-only paths should not redeploy trading;
use one publication owner or collision-safe publication branches.

### P2 — Research limits are declarations, not executable acceptance checks
protocol.json lists drawdown/exposure limits, but compare.py promotion is always
False and no structured per-condition acceptance evaluation exists. This is safe
against promotion but incomplete. Implement evidence-backed pass/fail/unknown
checks without removing unknown when future or replay evidence is absent.

### P2 — Data/reproducibility limits
Historical and research data is retrospectively adjusted. Generic data/fetcher.py
uses ffill/bfill; backward fill can inject future data into missing historical
values. Dependencies have broad minimum versions rather than a tested lockfile.
The daily research comparator checks alignment across tickers but does not itself
validate an exchange calendar; downloader does. Require provenance/calendar
manifest validation at comparison entry, interval validation and stale-data checks.
Timestamp semantics and bar-completion must be verified at live ingestion.

### P2 — Alerts and recovery lack a demonstrated end-to-end check
config.ALERTS.enabled is False. Workflow failures can appear in GitHub, but the
repo does not establish a tested user notification path for missing sessions,
unprotected positions, missing reports or failed research. Verify notification
preferences and delivery. Do not equate a scheduled workflow with a successful run.

## Automation inventory and recommended cadence

| Component | Current state | Recommendation |
|---|---|---|
| Live signal scans and risk checks | Render automated | Keep; repair restart/data gates first |
| Worker watchdog | GitHub scheduled | Verify stale scan, missing session and recovery alerts |
| Account reconciliation / chart / README | Render + GitHub automated | Keep daily; isolate from ML failure |
| Existing strategy attribution | Daily GitHub research | Add structured decision evidence and version segmentation |
| Daily ETF shadow candidate | Not implemented | Add daily after-close signals, next-open simulated execution, durable state |
| ML training | Weekly job, filter disabled | Independent weekly research job; retain artifacts and diagnostics |
| Model evaluation and promotion | Not complete | Weekly evaluation; promotion requires explicit evidence gates |
| Optimizer | Weekly pipeline, simplified model | Suspend use for decisions until live-parity simulator; research-only thereafter |
| Historical ETF comparison | Weekly fixed-period rerun | Treat as reproducibility regression; freeze inputs and log source changes |
| Hourly replay comparison | Adapter only, blocked | Run on archived events daily; aggregate weekly |
| Drift / calibration / costs | No complete pipeline | Daily data-quality monitoring; weekly statistical review |
| Risk-state and protection audit | No independent complete job | Before open, during session, after close; read-only checks |
| Dependency/security checks | No dedicated workflow identified | Weekly plus dependency changes |
| Web scraping / computer vision | No validated decision path | Do not automate until a specific testable feature justifies it |

## Implementation order

1. Restart-safe daily risk state, missing-data policy, truthful stop protection.
2. Durable structured execution evidence, publication isolation, independent alerts.
3. Independent weekly ML job with artifact retention, reproducible inputs and checks.
4. Daily shadow ETF portfolio and exact event-based hourly replay.
5. Version-specific attribution, benchmark/cost/drift evaluation and acceptance report.
6. Only then consider model/strategy promotion. Do not auto-tune the observed holdout.

Future observations cannot be accelerated into an already-completed holdout.
Automating a component does not establish that it improves decisions.
