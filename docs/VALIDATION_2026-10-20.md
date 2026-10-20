# October 20 validation and corrective changes

## Scope and result

35 offline unittest tests pass, including the private verified snapshot replay.
All 52 tracked Python files compile. Both GitHub workflow YAML files parse.
Chart generation and README regeneration completed in the prior change, and the
dark chart was visually inspected. Diff whitespace and targeted privacy checks
passed: no raw private audit exports or .env files are tracked, and no recognized
GitHub token/private-key patterns were found in changed text files.

This is a bounded source review and offline test pass, not exhaustive proof of
correctness. No live or paper orders were submitted, canceled or closed for tests.
No optimizer, retraining pipeline, cleanup script or live trading loop was run.
Tests use mocked broker responses, temporary SQLite storage and patched risk
state persistence. The private historical replay skips when its snapshot is absent
in fresh clones; synthetic coverage remains active in CI.

## Verified defects repaired

1. A failed position query was treated as flat. Only a broker 404 now means no
   position; other failures propagate. Full-inventory failures no longer become
   an empty portfolio.
2. Pending-order lookup failures previously permitted new entries. They now
   block the affected tick instead of defeating duplicate-order protection.
3. Account retrieval failures previously invented a $100,000 valuation. The
   tick now skips orders; nonfinite/invalid price or valuation is also rejected.
4. Failed buy submissions previously counted as successful BUY actions and
   pending scan exposure. Only a response with an order identifier updates those
   fields and the last-buy timestamp. Acknowledgement is not proof of execution.
5. The post-session publication script continued after report/chart/README
   failure. It now stops before Git publication and checks commit/rebase success.
6. That script persisted an HTTPS token in the remote URL. It now passes auth in
   child-process Git configuration via environment and uses a token-free URL.
   No actual authentication or push is performed by its tests.
7. Explicit Bash in the trading workflow enables pipefail for the trader/tee
   pipeline. Failed Git synchronization is no longer ignored.
8. A separate CI workflow runs the offline regression suite without broker
   credentials, trading commands or strategy parameter changes.

Added coverage includes actual extracted broker methods with mocked clients,
404-versus-network-error handling, failed and accepted order acknowledgements,
publication failure exits, ephemeral authentication, indicator prefix invariance,
position-size limits, circuit-breaker latching and local paper cash conservation.

## Remaining limitations and red flags

- October 19 scheduled run arrived almost six hours late. The external scheduling
  cause is unresolved; changing a cron minute is not a demonstrated fix.
- Fills before that saved run have not been attributed to a specific execution
  process/version. Do not count that date as a clean current-strategy baseline.
- Broker daily history remains missing October 19 in the fresh capture; retain
  the blank and distinguish it from the current account snapshot.
- Trailing-stop tracking remains advisory; broker bracket stops are not trailed
  by that tracking method. Enabling a new trailing execution policy would change
  the strategy and needs a separately specified implementation.
- Session startup resets the daily risk baseline, and EOD checks share the scan
  loop. Restarts and timing deserve dedicated lifecycle tests; this review does
  not certify restart-safe daily drawdown enforcement or guaranteed liquidation.
- The legacy multi-ticker broker entry point and historical research scripts are
  syntax-checked, not comprehensively behavior-tested. Backtests are not evidence
  that current live-paper execution behaves identically.
- Shared environment pip check reports datasets 4.8.5 vs fsspec 2026.4.0 and
  grpcio-tools 1.80.0 vs protobuf 5.29.6 conflicts. These packages are not direct
  requirements of this project. No shared packages were changed; CI installs the
  project requirements in a fresh runner.

Strategy thresholds, sizing parameters, ticker universe and schedule remain
unchanged. Failure handling intentionally differs: uncertain broker state cannot
be treated as permission to open a position. Record this commit boundary when
segmenting future observation results.
