# Applied ML

Datasets and coursework for an Applied Machine Learning class.

| Folder | What it is | Size |
|---|---|---|
| [`ghush-dataset/`](ghush-dataset) | ~19,000 public, unverified reports from ghush.site, collected and cleaned by `scraper.py` and `clean.py` | 19,016 rows |
| [`chess-puzzle-dataset/`](chess-puzzle-dataset) | Difficulty-balanced Lichess puzzles for first-move prediction (CC0 source), plus the CNN vs CTM experiment code and results | 50,000 rows |

Each folder has its own `README.md` and `DATA_DICTIONARY.md`. Read the data
dictionary before analysing anything.

## Licence

The MIT licence in [LICENSE](LICENSE) covers **the code only** (`scraper.py`,
`clean.py`, `fetch_data.py`, `ctm_lichess.py`) and the documentation. It does **not** cover the data: the ghush
records belong to their source site, and the Lichess puzzles are CC0 as published
by Lichess.
