# Results

| Model | Params | Accuracy | Top-3 | ECE | Mean ticks | Spearman(ticks, rating) | Acc. if stop at 0.8 | Train min |
|---|---|---|---|---|---|---|---|---|
| CNN | 1,794,880 | 0.352 | 0.578 | 0.424 | nan | nan | nan | 2.2 |
| CTM | 1,756,096 | 0.302 | 0.537 | 0.439 | 21.0 | 0.22 | 0.284 | 7.0 |
| CTM + penalty | 1,756,096 | 0.308 | 0.540 | 0.456 | 19.4 | 0.24 | 0.292 | 7.3 |

**Accuracy by rating band**

| Model | 400-1000 | 1000-1500 | 1500-2000 | 2000-2500 | 2500-3400 |
|---|---|---|---|---|---|
| CNN | 0.605 | 0.411 | 0.282 | 0.245 | 0.219 |
| CTM | 0.559 | 0.355 | 0.228 | 0.190 | 0.176 |
| CTM + penalty | 0.572 | 0.369 | 0.219 | 0.201 | 0.177 |

## Summary

- **Best accuracy:** CNN (35.2%). CNN 35.2%, CTM 30.2%, CTM + penalty 30.8%.
- **Difficulty:** from the easiest to the hardest band, accuracy falls from 60.5% to 21.9% (CNN), 55.9% to 17.6% (CTM), 57.2% to 17.7% (CTM + penalty).
- **Calibration:** lowest ECE is CNN (CNN 0.424, CTM 0.439, CTM + penalty 0.456).
- **Thinking time:** the CTM uses 21.0 ticks on average, the penalised CTM 19.4 (-1.5).
- **Does thinking time follow difficulty?** Spearman(ticks, rating) is 0.22 for the CTM and 0.24 with the penalty. The penalty made the link **stronger**, as hypothesised.
- **Cost of the penalty:** accuracy changed by +0.6% versus the plain CTM.
