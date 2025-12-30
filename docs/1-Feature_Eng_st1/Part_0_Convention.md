# Part 0: Conventions & Process

> **Navigation:** [README](README.md) | **Part 0** | [Part 1: Groups](Part_1_Groups.md) | [Part 2: Raw](Part_2_Raw.md) | [Part 3: Approved](Part_3_Approved.md) | [Part 3 (2)](Part_3_Approved2.md) | [Part 4: Suggestions](Part_4_Suggestions.md) | [Part 5: Disapproved](Part_5_Disapproved.md)

---

## Naming Convention

- **Raw features:** `RAW_[groups]_featureName_[form]_[norm]`
- **Engineered features:** `[groups]_featureName_[form]_[norm]`
- Group/category prefixes are alphabetically ordered
- Form suffix describes how the value is represented (see [Part 1: Form Suffixes](Part_1_Groups.md#form-suffixes-representation-type))
- Normalization suffix: `_N` (normalized/scale-invariant) or `_NN` (not normalized/scale-dependent)
- Example: `RAW_F_I_S_fundingRate_pct_N`, `D_F_N_S_premiumZscore_zsc_N`, `M_N_rsi_bnd_N`, `V_atr_abs_NN`

---

## Period Convention (8h bars)

Features marked with `{n}` accept period parameters. Standard period set for reference:

| Periods | Time Equivalent |
|---------|-----------------|
| 3 | 1 day |
| 6 | 2 days |
| 9 | 3 days |
| 12 | 4 days |
| 21 | 1 week |
| 42 | 2 weeks |
| 63 | 3 weeks |

*Periods are flexible — final selection will be optimized based on results.*

---

## Process

1. New feature ideas go to Part 4 as suggestions with proposed group/category assignments
2. We discuss usefulness, group/category assignments, and potential conflicts
3. **For each feature, document Pros and Cons** — preserves reasoning for implementation
4. Only after mutual agreement, feature moves to Part 3 (with Pros/Cons)
5. If not approved, feature moves to Part 5 with Pros (what we'd lose) and Cons (why rejected)
6. If transforming (fixing flaws), reject original → approve transformed version

**Why Pros/Cons matter:**
- Pros show what value the feature provides
- Cons show limitations and what other features cover them
- Together they ensure complete context for implementation

---

## Design Philosophy

- **Completeness over optimization** — Include all features with potential value
- **Better too many than missing** — We can prune later, but can't recover what we didn't track
- **Document everything** — This is step 1 of many; we will return here based on future results
- **Flexible periods** — Note which features use periods; exact values tuned later

---

## Cross-References

- **Groups/Categories defined in:** [Part_1_Groups.md](Part_1_Groups.md)
- **Form Suffixes defined in:** [Part_1_Groups.md](Part_1_Groups.md#form-suffixes-representation-type)
- **Available raw data:** [Part_2_Raw.md](Part_2_Raw.md)

---

*Last updated: 2025-12-20*
