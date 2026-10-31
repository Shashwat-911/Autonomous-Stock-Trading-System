# Research repair checkpoint — October 31, 2026

No profitable replacement has been validated. Zero losing trades is not a deployment guarantee.

Implemented:
- Failed optimizer evaluations raise errors; all-invalid studies refuse publication.
- Legacy -999 parameter artifact explicitly invalidated.
- Labels use the complete requested future horizon; incomplete tails are excluded.
- If a future candle touches both barriers, assume the stop first.
- Cross-validation groups identical dates and leaves 12 unique dates between folds.
- Training saves a research model separately; weekly workflow no longer stages the deployed model.
- Pipeline guidance requires independent evaluation before deployment.

Validation: 49 offline tests passed at this checkpoint, including label ambiguity
and horizon tests. Python compilation passed for modified research modules.
This does not validate profitability, production fills, or the model's probabilities.

Remaining required work before strategy comparison:
1. Replace simplified backtests with next-bar execution, explicit costs, portfolio
   accounting, and matching live exit semantics.
2. Attribute 70 October 19–30 episodes using private fills and order metadata;
   public daily aggregates alone cannot establish entry versions or exit causes.
3. Build daily ETF trend candidate and cash/passive benchmarks under the same engine.
4. Reserve an untouched holdout, record every experiment and test cost sensitivity.
5. Validate label end times per symbol (12 unique dates is not a substitute for
   exact event-end purging when individual symbols have missing sessions).
6. Fix misleading trailing-stop logging separately from deciding new exit rules.

Live strategy settings and broker positions were not modified in this checkpoint.
