# Session startup investigation — October 21, 2026

GitHub API metadata confirms delays before job creation:

| Date | Scheduled UTC | Created UTC | Trading step UTC |
|---|---|---|---|
| October 19 | 13:30 | 19:24:31 | 19:25:10 |
| October 20 | 13:30 | 18:03:33 | 18:04:19 |

Setup took seconds. The internal platform cause is unknown. The existing
150-minute entry cutoff correctly blocked late buys; removing it is not a fix.

Implemented changes:
- Read-only exchange-calendar preflight before GitHub cleanup. Only an open
  session within 15 minutes of opening passes. Missed starts fail visibly.
- Workflow concurrency prevents overlapping runs within GitHub, not across hosts.
- Cloud launcher uses exchange-calendar DST, holiday and early-close times,
  polls every 30 seconds, and retries failed report publication.
- Cloud launches beyond the opening tolerance are refused and marked missed.
  This also means late crash/redeploy recovery requires review; no automatic
  restart beyond that tolerance is promised. Existing brackets remain at broker.
- Logs identify execution source and revision. New order IDs identify gh/rc/local
  origin and include random suffixes. Earlier executions remain unattributed.
- Blocked entry display retains actual price, signal and confidence.

Validation: 38 offline tests passed; Python syntax and workflow ordering passed.
No trading or cleanup process was run. No hosting plan was purchased.

Deployment remains unresolved until one execution host is selected. The repo has
both GitHub and Render launchers. Render health responded, but its debug endpoint
had no debug log; health is not proof of timely trading or historical ownership.
Do not enable another runner before confirming the existing one is stopped.

GitHub scheduled events can be delayed, and hosted jobs are limited to six hours.
A normal exchange session lasts 6.5 hours, excluding setup and reporting. Raising
the configured timeout does not override that limit:
https://docs.github.com/en/actions/how-tos/troubleshoot-workflows
https://docs.github.com/en/actions/reference/limits

Render Free can sleep after 15 minutes without inbound traffic:
https://render.com/docs/free

The required next choice is an always-on cloud host, an awake online PC, or
accepting GitHub timing limitations. A single always-on host can use the calendar
launcher; competing trading/cleanup paths and mid-session redeploys must be
disabled as part of that deployment. These safeguards detect missed sessions;
they do not guarantee timely infrastructure. User hosting choice is pending.
