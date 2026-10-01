# Results

| Model | Params | Accuracy | Top-3 | ECE | Mean ticks | Spearman(ticks, rating) | Acc. if stop at 0.8 | Train min |
|---|---|---|---|---|---|---|---|---|
| CNN | 42,752 | 0.068 | 0.195 | 0.022 | nan | nan | nan | 0.0 |
| CTM | 353,792 | 0.037 | 0.155 | 0.026 | 6.0 | 0.00 | 0.033 | 0.1 |
| CTM + penalty | 353,792 | 0.037 | 0.155 | 0.026 | 6.0 | 0.00 | 0.033 | 0.1 |

**Accuracy by rating band**

| Model | 400-1000 | 1000-1500 | 1500-2000 | 2000-2500 | 2500-3400 |
|---|---|---|---|---|---|
| CNN | 0.065 | 0.058 | 0.061 | 0.095 | 0.111 |
| CTM | 0.000 | 0.044 | 0.044 | 0.032 | 0.222 |
| CTM + penalty | 0.000 | 0.044 | 0.044 | 0.032 | 0.222 |

## Summary

- **Best accuracy:** CNN (6.8%). CNN 6.8%, CTM 3.8%, CTM + penalty 3.8%.
- **Difficulty:** from the easiest to the hardest band, accuracy falls from 6.5% to 11.1% (CNN), 0.0% to 22.2% (CTM), 0.0% to 22.2% (CTM + penalty).
- **Calibration:** lowest ECE is CNN (CNN 0.022, CTM 0.026, CTM + penalty 0.026).
- **Thinking time:** the CTM uses 6.0 ticks on average, the penalised CTM 6.0 (+0.0).
- **Does thinking time follow difficulty?** Spearman(ticks, rating) is 0.00 for the CTM and 0.00 with the penalty. The penalty did **not** make the link stronger, so the hypothesis is not supported here.
- **Cost of the penalty:** accuracy changed by +0.0% versus the plain CTM.
