# Lichess puzzles: baseline vs CTM vs modified CTM

**Task:** predict the first correct move of a chess puzzle, then compare three
models on accuracy, accuracy by difficulty, calibration, and (CTMs only)
whether thinking time tracks puzzle rating.

## Plan

- [x] **1. Data** - 50,000 puzzles, 10,000 per rating band, 80/10/10 split
      stratified by band. `fetch_data.py` -> `data/puzzles.csv`
- [ ] **2. Shared setup** - board -> 12x8x8 planes (flipped so the side to move
      is always "white"); label = from-square x 64 + to-square (4,096 classes);
      illegal moves masked at evaluation for every model equally
      *Done when:* a batch loads and shapes are correct
- [ ] **3. Baseline** - a small CNN, the "normal neural network"
      *Done when:* trains, reports test accuracy overall and per band
- [ ] **4. CTM** - as in the paper: internal ticks, neuron-level models,
      synchronization representation, min-loss + max-certainty loss; square
      embeddings from a small conv as the attention keys/values
      *Done when:* trains, same metrics, plus ticks-to-certainty per band
- [ ] **5. Modified CTM** - one change, chosen with the user (see below)
      *Done when:* same metrics as step 4
- [ ] **6. Comparison** - one table + three plots (accuracy per band,
      calibration, ticks vs rating) and a short written explanation
      *Done when:* results are reproducible from one command

## Fairness rules

- Roughly matched parameter counts across all three models
- Same data, same splits, same epochs budget, same seed
- A worse result for the modified CTM is reported as-is

## Review

Steps 2-6 done in `ctm_lichess.py` / `ctm_lichess.ipynb`, run on Kaggle T4 (20 epochs, seed 42).
Modification chosen: compute penalty (lam 0.2, tau 0.8).

| Model | Params | Test acc | Mean ticks | Spearman(ticks, rating) |
|---|---|---|---|---|
| CNN | 1.79M | 35.2% | - | - |
| CTM | 1.76M | 30.2% | 21.0 | 0.22 |
| CTM + penalty | 1.76M | 30.8% | 19.4 | 0.24 |

- CNN wins on accuracy and trains 3x faster.
- Both CTMs think longer on harder puzzles; the penalty saves most ticks on easy ones
  (-2.3 easy vs -1.0 hard) and reaches peak per-tick accuracy earlier.
- Caveats: single seed; the +0.6% and +0.02 rho gaps are within noise (acc SE about 0.65 pts);
  all models overfit (CNN train loss about 0.0007) and are overconfident (ECE about 0.43).
