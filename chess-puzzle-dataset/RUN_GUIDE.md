# How to run the experiment on a free GPU

**You need two files:** `ctm_lichess.ipynb` (the notebook) and `data/puzzles.csv` (the 50,000 puzzles).
**The same notebook works on Kaggle and Colab** without any edits; it detects where it is running.
**A full run takes roughly 20-40 minutes on a T4 GPU.**

---

## Option A: Kaggle (recommended)

**Kaggle is recommended** because the free GPU session lasts longer, it does not disconnect when
your browser tab sleeps, and "Save Version" can run the whole notebook in the background.

**One-time setup:** your Kaggle account must be **phone-verified** to use GPUs and internet
(Settings -> Phone verification). The free quota is about 30 GPU hours per week.

1. Go to <https://www.kaggle.com/code> -> **New Notebook**.
2. **File -> Import Notebook** -> upload `ctm_lichess.ipynb`.
3. Right panel -> **Session options**:
   - **Accelerator -> GPU T4 x2** (or GPU P100). The code uses one GPU, which is fine.
   - **Internet -> On** (needed for `pip install chess`).
4. Right panel -> **+ Add Input** -> **Upload** -> choose `data/puzzles.csv`, name the dataset
   e.g. `lichess-puzzles-50k`, then **Create**. The notebook finds it automatically under `/kaggle/input/`.
   (If you skip this step, the notebook downloads a fresh sample from Lichess instead.)
5. Run it one of two ways:
   - **Interactive:** **Run All** and watch the output. Keep the tab open.
   - **Background (safer):** **Save Version -> Save & Run All (Commit)**. You can close the browser;
     the run finishes on Kaggle's side and the results appear under the version's **Output** tab.
6. **Download the results:** `results.zip` (and the `results/` folder) appear in the **Output** section
   in the right panel under `/kaggle/working`. Click the file, then the download icon.

## Option B: Google Colab

1. Go to <https://colab.research.google.com> -> **File -> Upload notebook** -> choose `ctm_lichess.ipynb`.
2. **Runtime -> Change runtime type -> T4 GPU** -> Save.
3. **Runtime -> Run all**.
4. In cell 2 a **"Choose files"** button appears: upload `data/puzzles.csv`.
   (Press Cancel instead and it downloads a fresh sample from Lichess.)
5. **Keep the tab open and active**; free Colab can disconnect an idle session.
6. At the end, `results.zip` downloads to your computer automatically.

---

## What you get in `results.zip`

| File | What it shows |
|---|---|
| `summary.md` | **The comparison table plus an auto-written summary**; start your report from this |
| `comparison.png` | Accuracy by rating band, calibration curve, thinking time vs difficulty |
| `training_and_ticks.png` | Validation accuracy per epoch, CTM accuracy at every internal tick |
| `attention.png` | Where the CTM looks on the board at 4 moments while solving one hard puzzle |
| `attention_board.svg` | That puzzle's board with the correct move drawn |
| `results.json` | All numbers and the config, for your own charts |

## If something goes wrong

| Problem | Fix |
|---|---|
| Prints `WARNING: no GPU found` | The accelerator is off. Turn on the GPU (step 3 / step 2) and restart. |
| `pip install failed` on Kaggle | Internet is off, or the account is not phone-verified. |
| `CUDA out of memory` | In the `CFG` cell, change `batch_size=256` to `128`. |
| Too slow / quota running low | In the `CFG` cell, change `epochs=20` to `10`. Keep it the same for all three models. |
| Colab disconnected mid-run | Use Kaggle's "Save & Run All" instead; it keeps running without your browser. |

**Fairness rule:** if you change anything in `CFG`, it applies to all three models at once. Do not
tune one model more than the others, and **report the penalty result even if it is worse**.
