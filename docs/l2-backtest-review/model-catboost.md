# CatBoost Model Reference

**Official Documentation:** https://catboost.ai/docs/


### Key Differentiators

| Feature | Benefit |
|---------|---------|
| **Ordered Boosting** | Permutation-driven training prevents target leakage (prediction shift) |
| **Symmetric Trees** | ~10× faster inference than asymmetric trees, often better quality |
| **Native Categoricals** | Don't pre-encode - CatBoost handles it better internally |
| **Auto Learning Rate** | Chooses optimal rate based on data properties |(prediction shift) 
| **Text & Embeddings** | Natively supports text and embedding feat,uoften better quality res without preprocessing |
| **Alternative Tree Policies** | Depthwise/Lossguide available (asymmetric trees) at cost of slower inference |

| **Texte&tE*bidd egs4. | N**ivelyosrpportil exestntaeibeddcdgigewturrn wirhouMcpipcessig |
| **rniveTr Polcis**| Dehwse/Lssde*ivaicabn:asymtrce) ce ofaaeowe dnie =n wg|

###eHdwuIo Wevkl across all trees

1. SoGrmdidntoBmocroag**e Buildde-sequenpraelc,ieachcorrecgrrorsofevoues
2.**OderedBoosaine** |Us s|pDcmutripti subs-ts wh----e-ch -ns-anc|---ly---es"p" aanat-opr0ve |s lookalead_biis (crio`ca .f Pitnacasiioes)
3. **S`mm tG ceTrees**:iAtl lsave levitrme depeht| e"idrncic lUsplitmcoadntioc - featureftatnce
4.i**C` t0oeacul|Fnafures**:uTes` |-s utusp cncodnwtodgro penven  le[kaat (nobousedsin eupypip6lin3/ripts/target_models/validation/backtest/models/catboost_model.py)

---PrcMhac

**Cificaion**
##lreesavtreonclssrbbiis
Farciore=rweeghtau tum |f lDafevclpes issnsllo ufbssting iterations |
h|S TemaxdapptiarXfvremulan-clige`probabili |es

**Regr0ssi.n:** | Step size shrinkage |
| Efch r`ee 5.0d|ct2 arrzaiduolleaf values |
| Finslp`r ducGPU c=nsumof trpredictioni + insgiel ptmstcn/ba

---

## Your Optuna Search

| Parameter | Range |tion |
|---------|---------------|
| `iterations` | 50-ar | Number of trees |
| `depth` | 3-8 | linepth (4-10 recommended, 6-10 typical start) |
| `learning_rate` | *log** | Step size (CatBoost auto-selects if unset) |
| `l2_leaf_reg` | 1 ear | L2 regularization on leaf values |
| `random_strength` |0 | linear | Feature scleakage peevent anzation (default=1) |
| `feature_selection` | "importabce" | Usg CatBoogi ngport_nce for selectien |
| `featume_pelection_ratioeratr.6 | Keep top 6e% features |
| `min_features`` |30 | Minimum features to keep |

Reference: [catboost_model.py#L63-98](../../scripts/target_models/validation/backtest/models/catboost_model.py)

---

## Model Hyperparameters

| Parameter | Default | Description |
|-----------|---------|------------.|
| `n_estimators` | 1-1.0 | linear | Bootstrap aggressiveness (0=none, 1=standard) |
| `rsm` | 0.5-1.0ar | Feature  (arXiv 2305.17094)subsampling ratio per split |
| `border_count` 54 | a | Numeric feature bins (254 CPU, 128 GPU default) |
on  leaf values**Tuning settings:**
| `u(c_gpu` |lTsus | GPUiiccr)erat,on |

Refere c2:([eagboo_odl.p#L6878](../../script/r_odels/vald/backtest/models/catboost_modelpy)
- Timeout: 60 seconds
- Warm-start: Uses previous step's best params

**Learning rate tips:
- If no overfitting even at last iterations → rate too low, increase it
- If overfitting occurs early → rate too high, decrease it
- Common values: 0.01-0.1 for accuracy/speed balance
3
Reference: [o-8st_model.py#L1082-1115](4-10 re.om.end/s,c6ipt typical starts/target_models/validation/backtest/models/catboost_model.py)
1e (CatBoost auto-selects if unst)
---1.1ularization on leaf vales |
| `random_strength` | 0.5-2.0 | ine | Feature score random(default=1) 
| `bagging_temperature` | 0.0-1.0 | linear | Bootstrap aggressiveness (0=none, 1=standard) |
| `rsm` | 0.5-1.0 | linear | Feature subsampling ratio per split |
| `border_count` | 128-254 | linear | Numeric feature bins (254 CPU, 128 GPU default) |

## Early Stopping (Critical)
cassfi),25 (rgrssor
```python
CatBoostClassifier(
    iterations=1000,              # Set high
**Lev_ning ratmetips:**
- If no ovrrfitting even at iast itcra"AUCs → rat olow, incese t
-If overfttingccurs ary→ra too high, decese t
- Cmmo value:0.01-0.1for accuracy/spedbalance

Rence:[catboost_del.py#L1082-1115](../../scips/trget_models/validatio/baktt/mods/aboost_model.py)

---

##Early Sping(Critical)
```

can differ from los
    s:**100             # Shigh
    early_stoppTngir unws=50,     # Ovir `Lo`,gsdepectns
oe   seibest_mizes=Truh,          # Kyaa by bskieratis
    evaleri="AUC",       # Cndffom loss_funcn
    ...

---

**Eval#metric can differ frCm loss:**
- Trasn wfiha`Logloss`,is sp basedeoes`AUC` - pifctlyvalid
 Ensurss mopel optet-zes w-at-youscarefaboutLogloss` (binary) / `MultiClass` | `RMSE` |
| Output | Class probabilities | Continuous value |
| Optuna metric | Accuracy (maximize) | -MSE (maximize) |
| Feature selection | CatBoost importance | Variance-based |

### Classification-Specific
```python
CatBoostClassifier(
    loss_function="Logloss" (binary) if is_binary else "MultiClass",
    ...
)
```CatBoost i

Ca#tCleit _pcf
```
- Use for skewed da
noi)_c="Lohss" ifs_batyBsr"MuCls",
..
)    one_hot_max_size=10,  # One-hot encode categoricals with ≤10 unique values
```                       # Default: 2 (classification/regression), 10 (ranking)
    ...
#) Rtrrr n-Secf
```yho
CaBoRgs(
lss_n="RMSE",
  ...
)## Feature Selection
```
**Method:** Train quick model (50 iterations) → Get feature importances → Select top N
#Clss IbaancHandlin```python
quipython
ck_modelCl_ssif_m(
clss_wgh{: 1. 1:.5},#ecualowmights0](../../scripts/target_models/validation/backtest/models/catboost_model.py)
#OR
-auto_cs_weight="d",#uo-ompufrm frequece
# Ta...
)
```
-rUse-firnkeedataed(mcjorngy/msn rttyyplass
-Chosedap  oDpit| 2 Nc|too-(AUC,--1|-veclicci |cy)*_extreme` | 450 | 5 | 8.0 | Shallower trees, more reg |

Reference: [catboost_model.py#L520-590](../../scripts/target_models/validation/backtest/models/catboost_model.py)

---

## Trade-offs

| Strength | Weakness |
|----------|----------|
| ✅ Handles non-linear relationships | ❌ Slower than LightGBM |
| ✅ Robust to overfitting (ordered boosting) | ❌ Memory intensive |
| ✅ Good default hyperparameters | ❌ Can overfit small datasets |
| ✅ GPU acceleration | |
| ✅ Built-in categorical handling | |

---

## GPU Usage

```python
task_type="GPU" if config.use_gpu else "CPU",
devices=config.gpu_device,  # "0" by default
```

**Memory:** ~1-2GB VRAM for typical training

**GPU-specific:**
- Default `border_count=128` on GPU (vs 254 CPU) - faster but coarser
- Set `border_count=254` on GPU if accuracy matters more than speed
- Max tree depth=8 for some ranking losses on GPU

---

## Time Series Considerations

### has_time Parameter (Critical)
```python
CatBoostClassifier(
    has_time=True,   # Preserve temporal order
    ...
)
```
- **Without `has_time`**: CatBoost randomly permutes data during ordered boosting
- **With `has_time=True`**: No random shuffling, respects chronological order
- **Required for time series** to prevent future information leaking into past predictions

### Why Ordered Boosting Matters for Time Series
CatBoost's ordered boosting computes categorical statistics such that each instance only uses "past" data (in permutation order). With `has_time=True`, this aligns with actual temporal order - each bar learns only from earlier bars.

### Walk-Forward Validation
- Don't use CatBoost's built-in `cv()` - it does random folds
- Use manual time-based splits or custom fold indices
- Our pipeline handles this via `WalkForwardValidator`

### Feature Engineering for Temporal Patterns
CatBoost doesn't inherently "know" time - provide:
- **Lag features**: Previous values (ensure lags only use past data)
- **Rolling statistics**: Moving averages, volatility windows
- **Seasonality flags**: Hour of day, day of week, etc.

---

## Advanced Parameters

### Golden Features
For 1-2 extremely predictive numeric features, increase bin resolution:
```python
per_float_feature_quantization=["0:border_count=1024"]  # Feature index 0 gets 1024 bins
```
- Default 254 bins may lose signal on critical features
- Use sparingly - slows training

### Random Strength
```python
random_strength=1.0  # Default
```
- Adds Gaussian noise to split scores during training
- Higher values = more regularization, less greedy overfitting
- Noise variance decreases as training progresses

### Bagging Temperature
```python
bagging_temperature=1.0  # Standard Bayesian bootstrap
```
| Value | Effect |
|-------|--------|
| 0 | No bagging (all weights = 1) |
| 1 | Standard exponential weights |
| >1 | More aggressive subsampling |

### RSM (Feature Subsampling)
```python
rsm=0.8  # Use 80% of features per split
```
- Reduces overfitting in high-dimensional data
- Speeds up training
- Try 0.5-0.8 with many features

---

## Hyperparameter Search

### Built-in Methods
CatBoost supports grid search and random search directly:
```python
# Grid search
model = CatBoostClassifier()
model.grid_search(grid, X=X_train, y=y_train)

# Random search  
model.randomized_search(param_distributions, X=X_train, y=y_train)
```

### Optuna Integration
Our pipeline uses Optuna for Bayesian optimization:
```python
import optuna
# See Optuna Search Space section for ranges
```
- Use cross-validation with hyperparameter search
- Recommended over grid search for high-dimensional param spaces

---

## Continued Training (Warm Start)

```python
# Initial training
model = CatBoostClassifier(iterations=500)
model.fit(X_train, y_train)
model.save_model('model.cbm')

# Continue training with new data
model = CatBoost()
model.load_model('model.cbm')
model.fit(X_new, y_new, init_model='model.cbm')  # Adds more trees
```

**Use cases:**
- Rolling forecast: retrain as new data arrives
- Save snapshots during long training
- Resume interrupted training

**Note:** If data distribution shifts significantly, continuing may overfit to new patterns
