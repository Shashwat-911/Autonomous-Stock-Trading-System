# Session startup investigation — October 21, 2026

GitHub API metadata confirms delays before job creation:

| Date | Scheduled UTC | Created UTC | Trading step UTC |
|---|---|---|---|
| October 19 | 13:30 | 19:24:31 | 19:25:10 |
| October 20 | 13:30 | 18:03:33 | 18:04:19 |

Setup took seconds. The internal platform cause is unknown. The existing
150-minute entry cutoff correctly blocked late buys; removing it is not a fix.

Implemented and selected architecture (user selected free cloud only):
- Render Free is the sole scheduled trading runner. GitHub no longer runs
  main.py live or force_close_all; it publishes read-only reports after close.
- Calendar-based startup handles DST, holidays and early closes, checking every
  30 seconds. Entry thresholds are unchanged; the live gate uses broker time.
- The scan sleep wakes within the existing ten-minute liquidation window.
- /status exposes deployed revision, worker PID/running state, exit code,
  recent output, calendar phase and keepalive results. /health is liveness only.
- Self-ping runs every five minutes. A separate free GitHub watchdog wakes
  Render and checks actual worker status every five minutes (best effort).
  GitHub scheduling delays remain possible; this is not an uptime guarantee.
- Blueprint build filters exclude report/docs/test/workflow-only changes so daily
  artifact commits do not redeploy the trader. Code changes still redeploy.
- Source/revision logs and rc/gh/local client-order IDs identify future execution.
- Failed report publication retries; no incomplete artifacts are published.

Recovery limitations: the runner deliberately refuses launches later than 15
minutes after opening and attempts at most one trading process per process/day.
Automatic same-day crash restart is withheld because main currently resets daily
risk state at startup, and Render Free loses local state on restart. Broker
brackets remain at Alpaca, but continued position management is not guaranteed
when the process is absent. A watchdog failure is an incident requiring review,
not a successful trading session. Do not deploy code during market hours.

Render Free has a 750-hour monthly workspace allowance, may sleep after 15
minutes without inbound requests, and may restart at any time. Keepalive cannot
recover platform suspension or guarantee an uninterrupted session. No paid plan
was selected. Any existing independent uptime monitor can continue pinging
/health; /status plus the watchdog distinguishes service uptime from trading.
https://render.com/docs/free

GitHub delays on Oct19/20 were before job creation, not installation. Hosted
jobs have a six-hour limit, below the normal 6.5-hour exchange session:
https://docs.github.com/en/actions/how-tos/troubleshoot-workflows
https://docs.github.com/en/actions/reference/limits

Historical earlier fills remain unattributed. These operational fixes do not
establish strategy profitability or change the trading signal parameters.

## Deployment verification — October 21

Revision 71b941f deployed successfully to the existing Render Free service.
The dashboard confirms all five ignored build paths and /health were applied.
41 local tests passed; GitHub Python 3.11 regression run 39574082253 succeeded.
At 13:36 UTC, /status reported the worker running, launched at 13:30:26 UTC
(26 seconds after opening), with recent output and successful self-pings.
The first 20-symbol scan completed. Read-only Alpaca lookups confirmed both
first-scan Render-tagged paper orders filled (AMZN and AMD).
This verifies startup and initial execution, not completion of the full day.
The external watchdog was active but had no scheduled runs at verification;
its five-minute cron must not be interpreted as guaranteed five-minute coverage.
A manual read-only watchdog dispatch was accepted for workflow validation.
