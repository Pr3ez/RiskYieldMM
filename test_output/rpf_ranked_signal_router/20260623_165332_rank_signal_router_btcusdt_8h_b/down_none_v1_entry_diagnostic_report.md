# down_none_v1 Entry Diagnostic

Source run:
`test_output/rpf_ranked_signal_router/20260623_165332_rank_signal_router_btcusdt_8h_b/`

Candidate inspected: `down_none_v1`.

## Finding

The candidate has useful sparse shadow performance in aggregate, but normal router selection fired it on the wrong live window.

Aggregate shadow evidence:

```text
signals:   23
TP / FP:   13 / 10
precision: 0.565
lift:      1.35
active:    8 / 120 windows
```

The useful active windows were mostly cases where validation was quiet under the candidate threshold, then the prediction batch produced a sparse breakout.

## Active Shadow Windows

```text
batch 5624: 2 TP / 0 FP, validation signals 0
batch 5628: 0 TP / 3 FP, validation signals 9
batch 5669: 3 TP / 0 FP, validation signals 0
batch 5671: 3 TP / 0 FP, validation signals 0
batch 5686: 3 TP / 0 FP, validation signals 0
batch 5696: 0 TP / 3 FP, validation signals 3
batch 5706: 0 TP / 3 FP, validation signals 6
batch 5719: 2 TP / 1 FP, validation signals 12
```

## Diagnostic Rule

Rule tested post-hoc, using only prediction-time-safe validation state plus the candidate's own live row decisions:

```text
candidate = down_none_v1
validation candidate signal count == 0
batch-state gate passed
```

On this block, among active candidate windows this selects:

```text
batches:   5624, 5669, 5671, 5686
signals:   11
TP / FP:   11 / 0
precision: 1.0
```

A stricter prefix condition also worked, but lost one good batch:

```text
validation signals == 0
prefix rows above threshold == 0
batches: 5669, 5671, 5686
signals: 9
TP / FP: 9 / 0
```

## Interpretation

The current router incorrectly treats quiet validation as a failure. For this sparse specialist, quiet validation appears to mean the threshold is conservative. The candidate becomes interesting only when the future batch produces a sparse breakout above that quiet threshold.

This should not be promoted from one block. The next implementation should add an explicit experimental entry mode for `down_none_v1` quiet-validation specialist routing, then replay older and latest blocks.
