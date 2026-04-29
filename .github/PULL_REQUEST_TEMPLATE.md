## Summary

Describe the change and why it is needed.

## Type Of Change

- [ ] Bug fix
- [ ] Feature or experiment
- [ ] Refactor
- [ ] Documentation
- [ ] Test/fixture
- [ ] Repository maintenance

## Affected Areas

- [ ] Data ingestion / raw data
- [ ] Feature engineering / helper cache
- [ ] Labels / targets
- [ ] Walk-forward backtest
- [ ] Stage-1 CatBoost / LightGBM
- [ ] Prediction analysis / ensembles
- [ ] Rust extension
- [ ] Documentation / governance

## Temporal And Leakage Review

- [ ] Prediction-time information availability is unchanged or explained.
- [ ] Train/validation/test chronology is unchanged or explained.
- [ ] Purge, embargo, tail exclusion, and batch alignment impacts are documented.
- [ ] Artifact schema or cache invalidation impacts are documented.
- [ ] Not applicable.

## Validation

Commands run:

```bash
# paste commands here
```

Results:

- [ ] Passed
- [ ] Failed, details below
- [ ] Not run, reason below

## Data And Artifact Impact

List any generated files, fixture files, parquet roots, model artifacts, or
metadata changed by this PR.

## Checklist

- [ ] I did not commit secrets, credentials, private CV files, or private data.
- [ ] I kept generated outputs out of the PR unless intentionally included.
- [ ] I updated docs when behavior or artifact contracts changed.
- [ ] I noted skipped checks and residual risks.
