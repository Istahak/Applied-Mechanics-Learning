# %% [markdown]
# # Chess puzzles: CNN vs CTM vs CTM + compute penalty
#
# **Task:** given a Lichess puzzle position, predict the first correct move.
#
# Three models, same data, same training budget, roughly the same number of parameters:
#
# 1. **CNN** - a normal residual convolutional network. Looks once, answers once.
# 2. **CTM** - Continuous Thought Machine (Darlow et al., NeurIPS 2025): internal ticks,
#    neuron-level models, synchronization as the representation, min-loss + max-certainty loss.
# 3. **CTM + compute penalty** - the same CTM, plus a cost for every tick it spends before
#    becoming confident. Hypothesis: easy puzzles finish sooner, so thinking time follows
#    puzzle rating more closely. It may cost accuracy; that is reported as-is.
#
# **Before running:**
# - **Kaggle:** Settings -> Accelerator -> GPU T4 x2 (or P100), and Settings -> Internet -> On.
#   Add `puzzles.csv` with "+ Add Input" -> Upload.
# - **Colab:** Runtime -> Change runtime type -> T4 GPU. You will be asked to upload `puzzles.csv`.

# %%
import csv, glob, io, json, math, os, random, shutil, subprocess, sys, time

IN_COLAB = "google.colab" in sys.modules
IN_KAGGLE = os.path.exists("/kaggle/input")
if IN_COLAB or IN_KAGGLE:
    pip = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "chess", "zstandard"])
    if pip.returncode != 0:
        raise RuntimeError("pip install failed. On Kaggle, turn on Settings -> Internet, then run again.")

import chess, chess.svg
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import matplotlib
if "ipykernel" not in sys.modules:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
SMOKE = os.environ.get("SMOKE") == "1"   # tiny run used to test the code on a CPU
print("device:", DEVICE, "| Kaggle" if IN_KAGGLE else "| Colab" if IN_COLAB else "| local",
      "| smoke test" if SMOKE else "")
if DEVICE == "cpu" and not SMOKE:
    print("WARNING: no GPU found. Turn on the GPU accelerator, or this will take many hours.")

CFG = dict(
    epochs=20, batch_size=256, lr=5e-4, weight_decay=1e-4, warmup_frac=0.05, grad_clip=1.0, seed=42,
    cnn=dict(channels=128, blocks=6),
    ctm=dict(d_model=256, d_input=64, backbone_blocks=3, memory=16, nlm_hidden=16,
             ticks=24, out_pairs=256, action_pairs=128, heads=4),
    # tau matches the 0.8 certainty threshold the paper uses for adaptive compute.
    penalty=dict(lam=0.2, tau=0.8, temp=0.05),
)
if SMOKE:
    CFG.update(epochs=int(os.environ.get("SMOKE_EPOCHS", 1)), batch_size=128)
    CFG["cnn"].update(channels=32, blocks=2)
    CFG["ctm"].update(d_model=64, d_input=32, backbone_blocks=1, ticks=6, out_pairs=64, action_pairs=32)

DATA = "data/puzzles.csv"
RESULTS = "results"
os.makedirs(RESULTS, exist_ok=True)

# %% [markdown]
# ## 1. Get the data
#
# Uses `puzzles.csv` (the 50,000-puzzle sample made by `fetch_data.py`):
# on Kaggle it is found automatically under `/kaggle/input`, on Colab you are asked to upload it.
# If neither is available, a fresh balanced sample is streamed from database.lichess.org
# (needs internet, about a minute).

# %%
BANDS = [(400, 1000), (1000, 1500), (1500, 2000), (2000, 2500), (2500, 3400)]
BAND_NAMES = [f"{lo}-{hi}" for lo, hi in BANDS]


def fetch_sample(path, per_band=10_000, max_rd=100, seed=42):
    """Same rules as fetch_data.py: balanced bands, reliable ratings, stratified split."""
    import urllib.request
    import zstandard
    url = "https://database.lichess.org/lichess_db_puzzle.csv.zst"
    resp = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "lichess-ctm-coursework/1.0"}))
    rows = csv.DictReader(io.TextIOWrapper(zstandard.ZstdDecompressor().stream_reader(resp), encoding="utf-8"))
    kept = {b: [] for b in BAND_NAMES}
    for row in rows:
        rating, moves = int(row["Rating"]), row["Moves"].split()
        band = next((f"{lo}-{hi}" for lo, hi in BANDS if lo <= rating < hi), None)
        if band is None or len(kept[band]) >= per_band or int(row["RatingDeviation"]) > max_rd or len(moves) < 2:
            continue
        board = chess.Board(row["FEN"])
        board.push_uci(moves[0])   # the opponent's move; the puzzle starts after it
        kept[band].append({"puzzle_id": row["PuzzleId"], "fen": board.fen(), "first_move": moves[1],
                           "solution": " ".join(moves[1:]), "solution_length": len(moves) - 1,
                           "rating": rating, "band": band, "themes": row["Themes"]})
        if all(len(v) >= per_band for v in kept.values()):
            break
    resp.close()
    rng, out = random.Random(seed), []
    for band in BAND_NAMES:
        rng.shuffle(kept[band])
        n = len(kept[band])
        for i, rec in enumerate(kept[band]):
            rec["split"] = "train" if i < 0.8 * n else "val" if i < 0.9 * n else "test"
        out += kept[band]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)


if not os.path.exists(DATA):
    os.makedirs("data", exist_ok=True)
    found = glob.glob("/kaggle/input/**/puzzles.csv", recursive=True) if IN_KAGGLE else []
    if found:
        shutil.copy(found[0], DATA)
        print("using", found[0])
    elif IN_COLAB:
        from google.colab import files
        print("Choose puzzles.csv from your computer (cancel to download a fresh sample instead).")
        for name, content in files.upload().items():
            if name.endswith(".csv"):
                open(DATA, "wb").write(content)
    if not os.path.exists(DATA):
        print("No puzzles.csv found. Streaming a fresh sample from Lichess (about a minute)...")
        fetch_sample(DATA)

with open(DATA, encoding="utf-8") as fh:
    ROWS = list(csv.DictReader(fh))
if SMOKE:
    ROWS = [r for s, n in (("train", 2000), ("val", 400), ("test", 400))
            for r in [x for x in ROWS if x["split"] == s][:n]]
print(f"{len(ROWS):,} puzzles:", {s: sum(r["split"] == s for r in ROWS) for s in ("train", "val", "test")})

# %% [markdown]
# ## 2. Turn boards into numbers
#
# - Each board becomes **12 layers of 8x8** (one per piece type and colour).
# - Boards are **flipped so the side to move is always "white"**, so the model only has to
#   learn one point of view.
# - A move is **from-square x 64 + to-square**, so there are 4,096 possible answers.
# - **Illegal moves are masked out** for every model, in training and testing, so each
#   model only chooses among legal moves (about 35 per position on average).

# %%
N_MOVES = 4096
NEG = -1e9


def encode(fen, uci):
    board = chess.Board(fen)
    move = chess.Move.from_uci(uci)
    if board.turn == chess.BLACK:
        board = board.mirror()
        move = chess.Move(chess.square_mirror(move.from_square), chess.square_mirror(move.to_square))
    planes = np.zeros((12, 8, 8), np.uint8)
    for sq, piece in board.piece_map().items():
        planes[(piece.piece_type - 1) + (0 if piece.color == chess.WHITE else 6),
               chess.square_rank(sq), chess.square_file(sq)] = 1
    legal = sorted({m.from_square * 64 + m.to_square for m in board.legal_moves})
    return planes, move.from_square * 64 + move.to_square, legal


t0 = time.time()
encoded = [encode(r["fen"], r["first_move"]) for r in ROWS]
max_legal = max(len(e[2]) for e in encoded)
X = torch.tensor(np.stack([e[0] for e in encoded]))
Y = torch.tensor([e[1] for e in encoded])
# Padded with index N_MOVES, a dummy column that is dropped when the mask is built.
LEGAL = torch.full((len(encoded), max_legal), N_MOVES, dtype=torch.long)
for i, e in enumerate(encoded):
    LEGAL[i, :len(e[2])] = torch.tensor(e[2])
RATING = np.array([int(r["rating"]) for r in ROWS])
BAND = np.array([BAND_NAMES.index(r["band"]) for r in ROWS])
SPLIT = {s: torch.tensor([i for i, r in enumerate(ROWS) if r["split"] == s]) for s in ("train", "val", "test")}
X, Y, LEGAL = X.to(DEVICE), Y.to(DEVICE), LEGAL.to(DEVICE)
print(f"encoded in {time.time() - t0:.0f}s | legal moves per position: "
      f"mean {np.mean([len(e[2]) for e in encoded]):.1f}, max {max_legal}")


def legal_mask(idx):
    mask = torch.zeros(len(idx), N_MOVES + 1, dtype=torch.bool, device=DEVICE)
    mask.scatter_(1, LEGAL[idx], True)
    return mask[:, :N_MOVES]


def batches(split, batch_size, shuffle):
    idx = SPLIT[split]
    if shuffle:
        idx = idx[torch.randperm(len(idx))]
    for i in range(0, len(idx), batch_size):
        b = idx[i:i + batch_size].to(DEVICE)
        yield b, X[b].float(), Y[b], legal_mask(b)

# %% [markdown]
# ## 3. The models
#
# **CNN (baseline).** Residual conv layers, then a 1x1 conv with 64 output channels: at each
# from-square, channel *k* scores moving that piece to square *k*.
#
# **CTM.** A small conv network turns the board into 64 square tokens. The CTM then thinks
# for a fixed number of internal ticks. On every tick it:
# 1. builds an attention query from **how pairs of neurons are synchronised**, and looks at the board,
# 2. passes what it saw through the **synapse** network to get new pre-activations,
# 3. lets **each neuron's private little MLP** read its last *M* pre-activations and decide its next value,
# 4. updates the synchronisation between neuron pairs, and **predicts a move from that synchronisation**.
#
# One deliberate difference from the paper: square tokens get a **learned position
# embedding**. The paper leaves positions out for mazes because a maze route is made of
# relative steps (up, down, left, right); a chess move names absolute squares, so without
# positions the CTM could not say *which* square a piece is on.
#
# The synapse is a plain 2-layer GLU MLP rather than the paper's U-Net-style MLP, to keep it short.

# %%
class ResBlock(nn.Module):
    def __init__(self, c):
        super().__init__()
        self.c1, self.b1 = nn.Conv2d(c, c, 3, padding=1, bias=False), nn.BatchNorm2d(c)
        self.c2, self.b2 = nn.Conv2d(c, c, 3, padding=1, bias=False), nn.BatchNorm2d(c)

    def forward(self, x):
        return F.relu(x + self.b2(self.c2(F.relu(self.b1(self.c1(x))))))


def conv_trunk(c, blocks):
    return nn.Sequential(nn.Conv2d(12, c, 3, padding=1, bias=False), nn.BatchNorm2d(c), nn.ReLU(),
                         *[ResBlock(c) for _ in range(blocks)])


class CNNPolicy(nn.Module):
    def __init__(self, channels, blocks):
        super().__init__()
        self.trunk = conv_trunk(channels, blocks)
        self.head = nn.Conv2d(channels, 64, 1)

    def forward(self, x):
        h = self.head(self.trunk(x))                       # B, to-square, 8, 8 (from-square)
        return h.flatten(2).transpose(1, 2).reshape(len(x), N_MOVES)


class CTM(nn.Module):
    def __init__(self, d_model, d_input, backbone_blocks, memory, nlm_hidden, ticks,
                 out_pairs, action_pairs, heads, seed=0):
        super().__init__()
        D, M, H = d_model, memory, nlm_hidden
        self.ticks = ticks
        self.backbone = conv_trunk(d_input, backbone_blocks)
        self.pos = nn.Parameter(torch.randn(64, d_input) * 0.02)
        self.kv_norm = nn.LayerNorm(d_input)
        self.attn = nn.MultiheadAttention(d_input, heads, batch_first=True)
        self.q_proj = nn.Linear(action_pairs, d_input)
        self.synapse = nn.Sequential(nn.Linear(D + d_input, 2 * D), nn.GLU(), nn.LayerNorm(D),
                                     nn.Linear(D, 2 * D), nn.GLU(), nn.LayerNorm(D))
        # Neuron-level models: every neuron has its own weights over its own history.
        self.nlm_w1 = nn.Parameter(torch.empty(D, M, 2 * H).uniform_(-1 / math.sqrt(M), 1 / math.sqrt(M)))
        self.nlm_b1 = nn.Parameter(torch.zeros(D, 2 * H))
        self.nlm_w2 = nn.Parameter(torch.empty(D, H).uniform_(-1 / math.sqrt(H), 1 / math.sqrt(H)))
        self.nlm_b2 = nn.Parameter(torch.zeros(D))
        self.start_z = nn.Parameter(torch.randn(D) * 0.1)
        self.start_hist = nn.Parameter(torch.randn(D, M) * 0.1)
        # Neuron pairs are sampled once and fixed, as in the paper.
        g = torch.Generator().manual_seed(seed)
        for name, n in (("out", out_pairs), ("act", action_pairs)):
            self.register_buffer(f"{name}_i", torch.randint(0, D, (n,), generator=g))
            self.register_buffer(f"{name}_j", torch.randint(0, D, (n,), generator=g))
        self.decay_out = nn.Parameter(torch.zeros(out_pairs))
        self.decay_act = nn.Parameter(torch.zeros(action_pairs))
        self.out = nn.Linear(out_pairs, N_MOVES)

    def forward(self, x, return_attn=False):
        B = len(x)
        kv = self.kv_norm(self.backbone(x).flatten(2).transpose(1, 2) + self.pos)   # B, 64, d_input
        z = self.start_z.expand(B, -1)
        hist = self.start_hist.expand(B, -1, -1)
        r_out = torch.exp(-self.decay_out.clamp(0, 15))
        r_act = torch.exp(-self.decay_act.clamp(0, 15))
        # Running sums for synchronization (the paper's Appendix H recursion):
        # S = alpha / sqrt(beta), with alpha and beta decayed by r every tick.
        a_act = z[:, self.act_i] * z[:, self.act_j]
        b_act = torch.ones_like(a_act)
        a_out = b_out = None
        logits, attns = [], []
        for _ in range(self.ticks):
            q = self.q_proj(a_act / b_act.sqrt()).unsqueeze(1)
            o, w = self.attn(q, kv, kv, need_weights=return_attn)
            if return_attn:
                attns.append(w[:, 0])
            pre = self.synapse(torch.cat([z, o[:, 0]], -1))
            hist = torch.cat([hist[:, :, 1:], pre.unsqueeze(-1)], -1)
            h = F.glu(torch.einsum("bdm,dmh->bdh", hist, self.nlm_w1) + self.nlm_b1, -1)
            z = torch.einsum("bdh,dh->bd", h, self.nlm_w2) + self.nlm_b2

            a_act, b_act = r_act * a_act + z[:, self.act_i] * z[:, self.act_j], r_act * b_act + 1
            p_out = z[:, self.out_i] * z[:, self.out_j]
            if a_out is None:
                a_out, b_out = p_out, torch.ones_like(p_out)
            else:
                a_out, b_out = r_out * a_out + p_out, r_out * b_out + 1
            logits.append(self.out(a_out / b_out.sqrt()))
        logits = torch.stack(logits, 1)                      # B, ticks, 4096
        return (logits, torch.stack(attns, 1)) if return_attn else logits


def n_params(model):
    return sum(p.numel() for p in model.parameters())

# %% [markdown]
# ## 4. Loss functions
#
# **CTM loss (from the paper).** The CTM predicts a move on every tick. For each puzzle we
# take two ticks: the one with the **lowest loss** and the one where it was **most certain**,
# and average their losses. Certainty = 1 - (entropy / max possible entropy over the legal moves).
#
# **Compute penalty (our modification).** Treat "certainty passed 0.8" as a soft decision to
# stop thinking. From that we get the **expected number of ticks** the model would use, and add
# `lam x expected_ticks / total_ticks` to the loss. The model is now rewarded for becoming
# confident early, so it should learn to stop early on easy puzzles and keep thinking on hard ones.

# %%
def certainty(logp, mask):
    """1 - normalised entropy over the legal moves; logp is (B, T, 4096)."""
    entropy = -(logp.exp() * logp).sum(-1)
    max_entropy = torch.log(mask.sum(-1).clamp(min=2).float()).unsqueeze(1)
    return 1 - entropy / max_entropy


def ctm_loss(logits, y, mask, penalty=None):
    logp = F.log_softmax(logits.masked_fill(~mask.unsqueeze(1), NEG), -1)
    ce = -logp.gather(-1, y[:, None, None].expand(-1, logits.size(1), 1)).squeeze(-1)   # B, T
    cert = certainty(logp, mask)
    t_best, t_sure = ce.argmin(1, keepdim=True), cert.argmax(1, keepdim=True)
    loss = 0.5 * (ce.gather(1, t_best) + ce.gather(1, t_sure)).mean()
    if penalty:
        p_stop = torch.sigmoid((cert - penalty["tau"]) / penalty["temp"])
        still_thinking = torch.cumprod(1 - p_stop, 1)
        expected_ticks = 1 + still_thinking[:, :-1].sum(1)
        loss = loss + penalty["lam"] * (expected_ticks / logits.size(1)).mean()
    return loss

# %% [markdown]
# ## 5. Training and evaluation
#
# Every model gets the same optimiser (AdamW, warm-up then cosine decay, gradient clipping),
# the same number of epochs, and keeps the checkpoint with the best validation accuracy.
#
# **How a CTM answers at test time:** it uses the move from its most certain tick.
# We also record **ticks-to-certainty**: the first tick where certainty reaches 0.8
# (or the last tick if it never does). That is the "thinking time" we compare with puzzle rating.

# %%
TAU = CFG["penalty"]["tau"]


@torch.no_grad()
def evaluate(model, split, is_ctm):
    model.eval()
    out = {k: [] for k in ("idx", "correct", "top3", "conf", "ticks", "halt_correct", "tick_correct")}
    for idx, x, y, mask in batches(split, 512, shuffle=False):
        logits = model(x)
        if is_ctm:
            logp = F.log_softmax(logits.masked_fill(~mask.unsqueeze(1), NEG), -1)
            cert = certainty(logp, mask)
            rows = torch.arange(len(x), device=x.device)
            sure = logp[rows, cert.argmax(1)]
            reached = cert >= TAU
            first = torch.where(reached.any(1), reached.float().argmax(1), torch.full_like(y, cert.size(1) - 1))
            out["ticks"].append((first + 1).cpu())
            out["halt_correct"].append((logp[rows, first].argmax(-1) == y).cpu())
            out["tick_correct"].append((logp.argmax(-1) == y[:, None]).float().cpu())
        else:
            sure = F.log_softmax(logits.masked_fill(~mask, NEG), -1)
        out["idx"].append(idx.cpu())
        out["correct"].append((sure.argmax(-1) == y).cpu())
        out["top3"].append((sure.topk(3, -1).indices == y[:, None]).any(-1).cpu())
        out["conf"].append(sure.max(-1).values.exp().cpu())
    return {k: torch.cat(v).numpy() for k, v in out.items() if v}


def train(name, model, is_ctm, penalty=None):
    torch.manual_seed(CFG["seed"])
    model.to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=CFG["lr"], weight_decay=CFG["weight_decay"])
    steps = CFG["epochs"] * math.ceil(len(SPLIT["train"]) / CFG["batch_size"])
    warm = max(1, int(CFG["warmup_frac"] * steps))
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1, (s + 1) / warm) * 0.5 * (1 + math.cos(math.pi * min(1, s / steps))))
    history, best_acc, best_state, started = [], -1, None, time.time()
    print(f"\n=== {name}: {n_params(model):,} parameters ===")
    for epoch in range(1, CFG["epochs"] + 1):
        model.train()
        losses = []
        for _, x, y, mask in batches("train", CFG["batch_size"], shuffle=True):
            logits = model(x)
            if is_ctm:
                loss = ctm_loss(logits, y, mask, penalty)
            else:
                loss = F.cross_entropy(logits.masked_fill(~mask, NEG), y)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), CFG["grad_clip"])
            opt.step()
            sched.step()
            losses.append(loss.item())
        val_acc = evaluate(model, "val", is_ctm)["correct"].mean()
        history.append({"epoch": epoch, "train_loss": float(np.mean(losses)), "val_acc": float(val_acc)})
        print(f"epoch {epoch:2d} | loss {np.mean(losses):.3f} | val acc {val_acc:.3f} | {time.time() - started:.0f}s")
        if val_acc > best_acc:
            best_acc, best_state = val_acc, {k: v.detach().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    return {"name": name, "model": model, "is_ctm": is_ctm, "history": history,
            "train_seconds": time.time() - started, "params": n_params(model)}

# %% [markdown]
# ## 6. Train the three models
#
# On a T4 GPU this takes roughly 15-30 minutes in total. The CTMs are slower because they
# think for 24 ticks per puzzle.

# %%
runs = [
    train("CNN", CNNPolicy(**CFG["cnn"]), is_ctm=False),
    train("CTM", CTM(**CFG["ctm"], seed=CFG["seed"]), is_ctm=True),
    train("CTM + penalty", CTM(**CFG["ctm"], seed=CFG["seed"]), is_ctm=True, penalty=CFG["penalty"]),
]
for run in runs:
    run["test"] = evaluate(run["model"], "test", run["is_ctm"])

# %% [markdown]
# ## 7. Results
#
# - **Accuracy / top-3:** how often the correct first move is the model's best guess / in its top 3.
# - **ECE (calibration error):** when the model says "70% sure", is it right 70% of the time? Lower is better.
# - **Ticks-to-certainty (CTMs only):** how long it thinks before reaching 0.8 certainty.
# - **Spearman(ticks, rating):** does it think longer on harder puzzles? +1 = perfectly, 0 = no link.
# - **Accuracy if it stops at 0.8 certainty:** what adaptive compute costs, or saves.

# %%
def ece(conf, correct, bins=10):
    edges, total = np.linspace(0, 1, bins + 1), 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (conf > lo) & (conf <= hi)
        if sel.any():
            total += sel.mean() * abs(correct[sel].mean() - conf[sel].mean())
    return float(total)


def spearman(a, b):
    def avg_rank(v):
        order = np.argsort(v, kind="mergesort")
        ranks = np.empty(len(v))
        ranks[order] = np.arange(len(v))
        _, inv, counts = np.unique(v, return_inverse=True, return_counts=True)
        return (np.bincount(inv, weights=ranks) / counts)[inv]
    ra, rb = avg_rank(a), avg_rank(b)
    if ra.std() == 0 or rb.std() == 0:
        return 0.0   # e.g. every puzzle took the same number of ticks
    return float(np.corrcoef(ra, rb)[0, 1])


summary = []
for run in runs:
    t = run["test"]
    band = BAND[t["idx"]]
    row = {"model": run["name"], "params": run["params"], "train_min": round(run["train_seconds"] / 60, 1),
           "accuracy": float(t["correct"].mean()), "top3": float(t["top3"].mean()),
           "ece": ece(t["conf"], t["correct"]),
           "acc_by_band": [float(t["correct"][band == b].mean()) for b in range(len(BANDS))]}
    if run["is_ctm"]:
        row.update(mean_ticks=float(t["ticks"].mean()),
                   ticks_by_band=[float(t["ticks"][band == b].mean()) for b in range(len(BANDS))],
                   spearman_ticks_rating=spearman(t["ticks"], RATING[t["idx"]]),
                   halt_accuracy=float(t["halt_correct"].mean()))
    summary.append(row)

lines = ["| Model | Params | Accuracy | Top-3 | ECE | Mean ticks | Spearman(ticks, rating) | Acc. if stop at 0.8 | Train min |",
         "|" + "---|" * 9]
for r in summary:
    lines.append(f"| {r['model']} | {r['params']:,} | {r['accuracy']:.3f} | {r['top3']:.3f} | {r['ece']:.3f} | "
                 f"{r.get('mean_ticks', float('nan')):.1f} | {r.get('spearman_ticks_rating', float('nan')):.2f} | "
                 f"{r.get('halt_accuracy', float('nan')):.3f} | {r['train_min']} |")
lines += ["", "**Accuracy by rating band**", "",
          "| Model | " + " | ".join(BAND_NAMES) + " |", "|" + "---|" * (len(BANDS) + 1)]
lines += [f"| {r['model']} | " + " | ".join(f"{a:.3f}" for a in r["acc_by_band"]) + " |" for r in summary]
table = "\n".join(lines)
print(table)

# %% [markdown]
# ## 8. Plots

# %%
colors = ["#607d8b", "#1976d2", "#e65100"]
fig, ax = plt.subplots(1, 3, figsize=(17, 4.5))

w = 0.27
for k, r in enumerate(summary):
    ax[0].bar(np.arange(len(BANDS)) + (k - 1) * w, r["acc_by_band"], w, label=r["model"], color=colors[k])
ax[0].set_xticks(range(len(BANDS)), BAND_NAMES)
ax[0].set(title="Accuracy by puzzle rating", xlabel="rating band", ylabel="accuracy")
ax[0].legend()

for k, run in enumerate(runs):
    t, edges = run["test"], np.linspace(0, 1, 11)
    mids, accs = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (t["conf"] > lo) & (t["conf"] <= hi)
        if sel.sum() >= 20:
            mids.append(t["conf"][sel].mean())
            accs.append(t["correct"][sel].mean())
    ax[1].plot(mids, accs, "o-", label=run["name"], color=colors[k])
ax[1].plot([0, 1], [0, 1], "k--", lw=1, label="perfect calibration")
ax[1].set(title="Calibration", xlabel="confidence", ylabel="actual accuracy")
ax[1].legend()

for k, r in enumerate(summary):
    if "ticks_by_band" in r:
        ax[2].plot(BAND_NAMES, r["ticks_by_band"], "o-", color=colors[k],
                   label=f"{r['model']} (rho={r['spearman_ticks_rating']:.2f})")
ax[2].set(title="Thinking time vs difficulty", xlabel="rating band", ylabel="ticks to reach 0.8 certainty")
ax[2].legend()
plt.tight_layout()
plt.savefig(f"{RESULTS}/comparison.png", dpi=150)
plt.show()

fig, ax = plt.subplots(1, 2, figsize=(12, 4))
for k, run in enumerate(runs):
    ax[0].plot(range(1, len(run["history"]) + 1), [h["val_acc"] for h in run["history"]],
               "o-", label=run["name"], color=colors[k])
    if run["is_ctm"]:
        ax[1].plot(range(1, CFG["ctm"]["ticks"] + 1), run["test"]["tick_correct"].mean(0),
                   label=run["name"], color=colors[k])
ax[0].set(title="Validation accuracy during training", xlabel="epoch", ylabel="accuracy")
ax[1].set(title="CTM accuracy at each internal tick", xlabel="tick", ylabel="test accuracy")
ax[0].legend()
ax[1].legend()
plt.tight_layout()
plt.savefig(f"{RESULTS}/training_and_ticks.png", dpi=150)
plt.show()

# %% [markdown]
# ## 9. Where does the CTM look while it thinks?
#
# Attention over the 64 squares at four moments, for one hard test puzzle. The green square is
# the piece that should move, the red square is where it should go. The board is shown from the
# side to move (flipped if Black is to move), exactly as the model sees it.

# %%
ctm_run = runs[1]
t = ctm_run["test"]
hard = [i for i, ok in zip(t["idx"], t["correct"]) if ok and BAND[i] == len(BANDS) - 1]
pick = int(hard[0]) if hard else int(t["idx"][0])
ctm_run["model"].eval()
with torch.no_grad():
    _, attn = ctm_run["model"](X[pick:pick + 1].float(), return_attn=True)
attn = attn[0].cpu().numpy()
frm, to = divmod(int(Y[pick]), 64)
T = attn.shape[0]
ticks = sorted({0, T // 3, (2 * T) // 3, T - 1})
fig, ax = plt.subplots(1, len(ticks), figsize=(4 * len(ticks), 4))
for a, tk in zip(np.atleast_1d(ax), ticks):
    a.imshow(attn[tk].reshape(8, 8), origin="lower", cmap="magma")
    for sq, c in ((frm, "lime"), (to, "red")):
        a.add_patch(plt.Rectangle((sq % 8 - 0.5, sq // 8 - 0.5), 1, 1, fill=False, ec=c, lw=3))
    a.set(title=f"tick {tk + 1}", xticks=range(8), xticklabels=list("abcdefgh"),
          yticks=range(8), yticklabels=range(1, 9))
plt.suptitle(f"Puzzle {ROWS[pick]['puzzle_id']}, rating {ROWS[pick]['rating']}")
plt.tight_layout()
plt.savefig(f"{RESULTS}/attention.png", dpi=150)
plt.show()

board = chess.Board(ROWS[pick]["fen"])
board = board.mirror() if board.turn == chess.BLACK else board
svg = chess.svg.board(board, arrows=[chess.svg.Arrow(frm, to, color="#2e7d32")], size=320)
open(f"{RESULTS}/attention_board.svg", "w").write(svg)
if "ipykernel" in sys.modules:
    from IPython.display import SVG, display
    display(SVG(svg))

# %% [markdown]
# ## 10. What the numbers say
#
# Generated from the results above, as a starting point for your write-up.

# %%
cnn, ctm, pen = summary
best = max(summary, key=lambda r: r["accuracy"])
notes = [
    f"- **Best accuracy:** {best['model']} ({best['accuracy']:.1%}). "
    f"CNN {cnn['accuracy']:.1%}, CTM {ctm['accuracy']:.1%}, CTM + penalty {pen['accuracy']:.1%}.",
    "- **Difficulty:** accuracy on the easiest band vs the hardest band: "
    + ", ".join(f"{r['acc_by_band'][0]:.1%} vs {r['acc_by_band'][-1]:.1%} ({r['model']})" for r in summary) + ".",
    f"- **Calibration:** lowest ECE is {min(summary, key=lambda r: r['ece'])['model']} "
    f"(CNN {cnn['ece']:.3f}, CTM {ctm['ece']:.3f}, CTM + penalty {pen['ece']:.3f}).",
    f"- **Thinking time:** the CTM uses {ctm['mean_ticks']:.1f} ticks on average, the penalised CTM "
    f"{pen['mean_ticks']:.1f} ({pen['mean_ticks'] - ctm['mean_ticks']:+.1f}).",
    f"- **Does thinking time follow difficulty?** Spearman(ticks, rating) is {ctm['spearman_ticks_rating']:.2f} "
    f"for the CTM and {pen['spearman_ticks_rating']:.2f} with the penalty. "
    + ("The penalty made the link **stronger**, as hypothesised."
       if pen["spearman_ticks_rating"] > ctm["spearman_ticks_rating"]
       else "The penalty did **not** make the link stronger, so the hypothesis is not supported here."),
    f"- **Cost of the penalty:** accuracy changed by {pen['accuracy'] - ctm['accuracy']:+.1%} versus the plain CTM.",
]
report = "# Results\n\n" + table + "\n\n## Summary\n\n" + "\n".join(notes) + "\n"
print(report)
open(f"{RESULTS}/summary.md", "w", encoding="utf-8").write(report)
json.dump({"config": CFG, "summary": summary, "history": {r["name"]: r["history"] for r in runs}},
          open(f"{RESULTS}/results.json", "w"), indent=2)

shutil.make_archive("results", "zip", RESULTS)
if IN_COLAB:
    from google.colab import files
    files.download("results.zip")
elif IN_KAGGLE:
    print("Saved results.zip. Download it from the Output panel on the right (or the Output tab after saving).")
