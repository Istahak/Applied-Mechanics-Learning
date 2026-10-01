"""Turn ctm_lichess.py (cells marked with '# %%') into ctm_lichess.ipynb for Kaggle / Colab."""
import json
import re

src = open("ctm_lichess.py", encoding="utf-8").read()
cells = []
for chunk in re.split(r"^# %%", src, flags=re.M)[1:]:
    is_md = chunk.startswith(" [markdown]")
    body = chunk.split("\n", 1)[1].strip("\n") if "\n" in chunk else ""
    if is_md:
        body = "\n".join(line[2:] if line.startswith("# ") else line.lstrip("#") for line in body.splitlines())
        cells.append({"cell_type": "markdown", "metadata": {}, "source": body.splitlines(keepends=True)})
    else:
        cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
                      "source": body.splitlines(keepends=True)})

nb = {
    "nbformat": 4, "nbformat_minor": 5, "cells": cells,
    "metadata": {
        "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
        "language_info": {"name": "python"},
        "accelerator": "GPU",
        "colab": {"gpuType": "T4", "provenance": []},
        "kaggle": {"accelerator": "gpu", "isInternetEnabled": True},
    },
}
json.dump(nb, open("ctm_lichess.ipynb", "w", encoding="utf-8"), indent=1)
print(f"wrote ctm_lichess.ipynb with {len(cells)} cells")
