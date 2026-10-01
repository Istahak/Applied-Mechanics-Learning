# Data Dictionary - Lichess puzzle dataset

File: `data/puzzles.csv` (UTF-8, 50,000 rows, 13 columns, no missing values).
Moves are in UCI notation (`e2e4`: from-square then to-square).

| Column | Type | Meaning |
|---|---|---|
| `puzzle_id` | string | Lichess puzzle id, unique. Keep it as text: ids like `00008` lose their zeros as numbers. |
| `fen` | string | Board position the solver sees, i.e. **after** the opponent's setup move. |
| `side_to_move` | `white` / `black` | Who must find the solution. |
| `first_move` | string | **The prediction target:** the first correct move, in UCI. |
| `solution` | string | Full correct line from `first_move` onward, space-separated UCI moves (alternating solver / opponent). |
| `solution_length` | int | Number of moves in `solution` (1 to 23). |
| `rating` | int | Lichess puzzle rating, 400 to 3113. A difficulty measure; **do not use as a model input.** |
| `rating_deviation` | int | Uncertainty of the rating. Always 100 or less in this file. |
| `band` | string | `400-1000`, `1000-1500`, `1500-2000`, `2000-2500` or `2500-3400`. 10,000 puzzles each. |
| `popularity` | int | Lichess community score, 0 to 100. |
| `nb_plays` | int | Times the puzzle was played on Lichess. |
| `themes` | string | Space-separated Lichess tags (for example `fork endgame short`). |
| `split` | `train` / `val` / `test` | 40,000 / 5,000 / 5,000, stratified by `band`, seed 42. |

## Suggested label

`label = from_square * 64 + to_square` over the 64 squares gives 4,096 classes.
Most are illegal in any given position, so mask illegal moves before scoring.

## Known limits

- **Not a random sample of Lichess.** It is balanced across five rating bands, so
  band proportions do not match the real database.
- **One answer per puzzle.** Some positions have more than one good move; only the
  Lichess solution line counts as correct.
- **Ratings are crowd-sourced** from players solving the puzzle, not from an engine.
- **Puzzles share patterns.** Similar tactics repeat across puzzles, so a high score
  can partly reflect memorised motifs.

## Source and licence

Lichess puzzle database, https://database.lichess.org/#puzzles, published under
**CC0**. The MIT licence in [../LICENSE](../LICENSE) covers the repository code
only.
