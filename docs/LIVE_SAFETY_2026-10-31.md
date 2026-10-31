# Live safety changes — October 31, 2026

The preceding research commits (4c55db2 through 14b9c77) changed research,
training validation and automation, not the live signal thresholds or sizing.
This safety change DOES change live entry eligibility; future baseline reports
must identify its deployed revision and actual first session.

- Live startup uses broker clock NY date and last_equity rather than current equity.
- Valid same-day persisted baseline, breach latch and cooldown survive startup.
- Missing/corrupt/legacy state blocks NEW entries for that date; exits remain active.
  A later NY date can initialize from known prior state. An ephemeral disk loss
  can therefore cost a session; it must not silently grant a fresh risk budget.
- State writes use atomic replacement; write errors disable entries in memory.
- Unknown/short/nonfinite daily trend data blocks new entries, not exit handling.
- Trailing messages explicitly say hypothetical and NOT BROKER ENFORCED.
  Existing bracket stops remain separate; no new trailing execution was added.

66 offline tests passed including shared real-startup initialization, breach
restart, cooldown restart, missing/corrupt state, date rollover, persistence
failure and unknown daily trend evidence. This is not a claim of zero errors.

Limits: raw data freshness and broad-market regime fallback require separate
review. Durable recovery across lost containers needs an external state store or
full risk-event reconstruction; this patch chooses blocked entries when unknown.
Render deployment/dashboard settings and notification delivery were not verified.
