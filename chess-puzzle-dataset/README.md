# Lichess puzzle dataset (50,000 puzzles)

Part of [Applied ML](../README.md). A difficulty-balanced sample of the public
[Lichess puzzle database](https://database.lichess.org/#puzzles), prepared for
one task: **predict the first correct move of a chess puzzle from the board
position alone.** The folder also holds the experiment that uses it: a plain CNN
against the Continuous Thought Machine (CTM) and a CTM with a compute penalty.

## At a glance

| | |
|---|---|
| Puzzles | **50,000**, all with a unique `puzzle_id` |
| Source | https://database.lichess.org/lichess_db_puzzle.csv.zst |
| Source licence | **CC0** (public domain), as published by Lichess |
| Difficulty bands | 5 bands x 10,000 puzzles |
| Split | 80 / 10 / 10 train / val / test, stratified by band, seed 42 |
| Rating filter | only puzzles with `rating_deviation <= 100` (trustworthy ratings) |
| Missing values | none |

| Band (rating) | Train | Val | Test |
|---|---|---|---|
| 400-1000 | 8,000 | 1,000 | 1,000 |
| 1000-1500 | 8,000 | 1,000 | 1,000 |
| 1500-2000 | 8,000 | 1,000 | 1,000 |
| 2000-2500 | 8,000 | 1,000 | 1,000 |
| 2500-3400 | 8,000 | 1,000 | 1,000 |
| **Total** | **40,000** | **5,000** | **5,000** |

Ratings run from 400 to 3113 (median 1726). White moves first in 26,035 puzzles
and Black in 23,965. Solutions are 1 to 23 moves long.

## How it was built

1. Stream the Lichess puzzle CSV and keep rows whose `RatingDeviation` is 100 or less.
2. Fill five rating bands with 10,000 puzzles each, drawn at random.
3. Shuffle with seed 42 and assign each band 80 / 10 / 10 to train / val / test.
4. Keep the original FEN and moves, and add `side_to_move`, `first_move`,
   `solution_length` and `band`.

`fetch_data.py` does all of this and rebuilds `data/puzzles.csv`.

## The one trap: which move to predict

In the raw Lichess data the FEN is the position **before the opponent's move**, and
the first listed move is that opponent move. The puzzle the player actually solves
starts after it. **This file has that already applied:** `fen` is the position the
solver sees, and `first_move` is the first move the solver must find (the raw
second move). `solution` is `first_move` plus everything after it.

## Files

```
data/puzzles.csv        all 50,000 rows, 13 columns
data/examples/*.svg     10 rendered boards, 2 per band
DATA_DICTIONARY.md      column-by-column description
fetch_data.py           builds the dataset from the Lichess database
ctm_lichess.py          the experiment: CNN, CTM, CTM + compute penalty
ctm_lichess.ipynb       same code as a notebook (built by build_notebook.py)
RUN_GUIDE.md            how to run it on Kaggle or Colab GPU
PLAN_AND_REVIEW.md      plan, fairness rules and review notes
results/                outputs of the full GPU run (see below)
```

## The experiment

Three models, same data, splits, epochs and seed, about 1.8 million parameters each:

1. **CNN**, a normal convolutional network (baseline).
2. **CTM**, the Continuous Thought Machine, which thinks for 24 internal ticks.
3. **CTM + compute penalty**, our change: every tick spent before the model is
   80% certain adds a small cost to the loss, so it learns to stop early.

Run it with `RUN_GUIDE.md` (Kaggle GPU recommended, about the same on Colab).
`SMOKE=1 python ctm_lichess.py` runs a tiny CPU test.

### Results (test set, 5,000 puzzles, single seed)

| Model | Accuracy |
|---|---|
| CNN | **35.2%** |
| CTM | 30.2% |
| CTM + penalty | 30.8% |

- **The CNN is most accurate** and trains about 3 times faster.
- **The CTM thinks longer on harder puzzles** (19.2 ticks on the easiest band,
  22.1 on the hardest) although it never sees the rating.
- **The penalty saves about 1.5 ticks** on average, mostly on easy puzzles, with no
  loss in accuracy. The 0.6 point gain over the plain CTM is within noise for a
  single seed.

Full details, plots and numbers are in `results/` (`summary.md`, `results.json`,
`comparison.png`, `training_and_ticks.png`, `attention.png`).

## Intended use

Classification over the 4,096 (from-square x to-square) moves. Puzzle `rating` is a
**difficulty ruler for analysis only**; it is never a model input.

## Licence

The puzzles come from Lichess and are **CC0**. The MIT licence in
[../LICENSE](../LICENSE) covers the code in this repository only.
