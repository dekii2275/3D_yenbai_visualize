"""Build the cell-level training table: Yagi scar cells (1) vs sampled non-scar cells (0)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from model.features import FEATURES, distance_m, feature_stack, load_grid, masks
from model.paths import SRC, WORK


def build_dataset(src: Path = SRC, seed: int = 42, neg_ratio: int = 4, buffer_m: float = 60) -> pd.DataFrame:
    grid = load_grid(src)
    feats = feature_stack(src, grid)
    m = masks(src, grid, feats)
    pos = m['positive'] & m['valid']
    cand = m['valid'] & ~m['positive'] & (distance_m(m['positive'], grid.cell) >= buffer_m)
    pr, pc = np.nonzero(pos)
    cr, cc = np.nonzero(cand)
    rng = np.random.default_rng(seed)
    n_neg = min(len(cr), neg_ratio * len(pr))
    pick = rng.choice(len(cr), size=n_neg, replace=False)
    rows = np.concatenate([pr, cr[pick]])
    cols = np.concatenate([pc, cc[pick]])
    df = pd.DataFrame({'row': rows, 'col': cols, 'x': grid.xs[cols], 'y': grid.ys[rows],
                       'nhan': np.r_[np.ones(len(pr), int), np.zeros(n_neg, int)],
                       'phuong': m['ward'][rows, cols]})
    for k in FEATURES:
        df[k] = feats[k][rows, cols]
    return df


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    df = build_dataset()
    WORK.mkdir(parents=True, exist_ok=True)
    df.to_parquet(WORK / 'dataset.parquet')
    print(df.groupby(['phuong', 'nhan']).size().unstack(fill_value=0).to_string())
    print(f'Tổng: {int(df.nhan.sum())} dương, {int((df.nhan == 0).sum())} âm → {WORK / "dataset.parquet"}')


if __name__ == '__main__':
    main()
