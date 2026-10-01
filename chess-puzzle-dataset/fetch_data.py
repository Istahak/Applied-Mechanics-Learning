"""Stream a difficulty-balanced sample of Lichess puzzles.

    python fetch_data.py

Reads the public puzzle database (CC0) straight from database.lichess.org and
stops as soon as every rating band is full, so only a small part of the
~300 MB file is downloaded.

Writes data/puzzles.csv and a few SVG boards under data/examples/.
"""

import csv
import io
import os
import random
import sys
import time
import urllib.request

import chess
import chess.svg
import zstandard

URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"
OUT_CSV = os.path.join("data", "puzzles.csv")
EXAMPLES_DIR = os.path.join("data", "examples")

BANDS = [(400, 1000), (1000, 1500), (1500, 2000), (2000, 2500), (2500, 3400)]
PER_BAND = 10_000
# Ratings with a high deviation have been played too few times to trust as a
# difficulty label.
MAX_RATING_DEVIATION = 100
MAX_ROWS_SCANNED = 3_000_000
SPLIT = (0.8, 0.1, 0.1)
SEED = 42


def band_of(rating):
    for low, high in BANDS:
        if low <= rating < high:
            return f"{low}-{high}"
    return None


def parse(row):
    """Return a cleaned record, or None if the row is unusable."""
    if int(row["RatingDeviation"]) > MAX_RATING_DEVIATION:
        return None
    rating = int(row["Rating"])
    band = band_of(rating)
    if band is None:
        return None

    moves = row["Moves"].split()
    if len(moves) < 2:
        return None

    # The stored FEN is the position before the opponent's move; the puzzle
    # the solver faces starts after moves[0].
    board = chess.Board(row["FEN"])
    board.push_uci(moves[0])
    first_move = chess.Move.from_uci(moves[1])
    if first_move not in board.legal_moves:
        return None

    return {
        "puzzle_id": row["PuzzleId"],
        "fen": board.fen(),
        "side_to_move": "white" if board.turn == chess.WHITE else "black",
        "first_move": moves[1],
        "solution": " ".join(moves[1:]),
        "solution_length": len(moves) - 1,
        "rating": rating,
        "rating_deviation": int(row["RatingDeviation"]),
        "band": band,
        "popularity": int(row["Popularity"]),
        "nb_plays": int(row["NbPlays"]),
        "themes": row["Themes"],
    }


def stream_rows():
    req = urllib.request.Request(URL, headers={"User-Agent": "lichess-ctm-coursework/1.0"})
    resp = urllib.request.urlopen(req, timeout=60)
    reader = zstandard.ZstdDecompressor().stream_reader(resp)
    return resp, csv.DictReader(io.TextIOWrapper(reader, encoding="utf-8"))


def save_examples(records):
    """Two boards per band, with the answer drawn as an arrow, for slides."""
    os.makedirs(EXAMPLES_DIR, exist_ok=True)
    for low, high in BANDS:
        band = f"{low}-{high}"
        for rec in [r for r in records if r["band"] == band][:2]:
            board = chess.Board(rec["fen"])
            move = chess.Move.from_uci(rec["first_move"])
            svg = chess.svg.board(
                board,
                flipped=board.turn == chess.BLACK,
                arrows=[chess.svg.Arrow(move.from_square, move.to_square, color="#2e7d32")],
                size=360,
            )
            name = f"{band}_rating{rec['rating']}_{rec['puzzle_id']}.svg"
            with open(os.path.join(EXAMPLES_DIR, name), "w", encoding="utf-8") as fh:
                fh.write(svg)


def assign_splits(records):
    """Stratified by band so every split has the same difficulty mix."""
    rng = random.Random(SEED)
    for low, high in BANDS:
        band = [r for r in records if r["band"] == f"{low}-{high}"]
        rng.shuffle(band)
        n_train = int(len(band) * SPLIT[0])
        n_val = int(len(band) * SPLIT[1])
        for i, rec in enumerate(band):
            rec["split"] = "train" if i < n_train else "val" if i < n_train + n_val else "test"


def main():
    os.makedirs("data", exist_ok=True)
    counts = {f"{lo}-{hi}": 0 for lo, hi in BANDS}
    records, scanned, started = [], 0, time.time()

    resp, rows = stream_rows()
    try:
        for row in rows:
            scanned += 1
            rec = parse(row)
            if rec and counts[rec["band"]] < PER_BAND:
                counts[rec["band"]] += 1
                records.append(rec)

            if scanned % 100_000 == 0:
                print(f"scanned {scanned:,} | kept {len(records):,} | {counts}", flush=True)
            if all(c >= PER_BAND for c in counts.values()) or scanned >= MAX_ROWS_SCANNED:
                break
    finally:
        resp.close()

    assign_splits(records)
    fields = list(records[0].keys())
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    save_examples(records)

    print(f"\ndone in {time.time() - started:.0f}s: scanned {scanned:,} rows, kept {len(records):,}")
    print("per band:", counts)
    if any(c < PER_BAND for c in counts.values()):
        print("warning: some bands are short of", PER_BAND, file=sys.stderr)


if __name__ == "__main__":
    main()
