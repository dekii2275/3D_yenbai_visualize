"""Replay the warning rule hour by hour over the 2021-2026 rainfall series."""
import json
import sys

import numpy as np
import pandas as pd

from model.paths import OUT, SRC
from model.rain_thresholds import load_rain
from model.warning import CAP, NOTE, load_config

ORDER = ['xám', 'xanh', 'vàng', 'cam', 'đỏ']
COLS = {'mua_24h': 'mua_24h_mm', 'mua_72h': 'mua_72h_mm'}


def hourly_levels(rain: pd.DataFrame, thresholds: dict) -> pd.Series:
    """Rain level 0-3 per hour (max of 24h and 72h, >= thresholds); NaN when both are missing."""
    levels = []
    for col, key in COLS.items():
        v = rain[col].values
        lv = np.searchsorted(np.asarray(thresholds[key], float), np.nan_to_num(v, nan=-1), side='right').astype(float)
        lv[np.isnan(v)] = np.nan
        levels.append(lv)
    return pd.Series(np.fmax(*levels), index=rain.index)


def colour_hours(levels: pd.Series, config: dict) -> pd.DataFrame:
    out = {}
    for i, cap in enumerate(CAP):
        lut = {lvl: config['ma_tran'][f'R{lvl}'][i] for lvl in range(4)}
        out[cap] = levels.map(lambda v: 'xám' if np.isnan(v) else lut[int(v)])
    return pd.DataFrame(out, index=levels.index)


def red_episodes(colours: pd.Series, rain: pd.DataFrame) -> list[dict]:
    """Contiguous red periods, merging red hours less than 24 h apart."""
    red = colours.index[colours.values == 'đỏ']
    episodes, cur = [], []
    for t in red:
        if cur and (t - cur[-1]) >= pd.Timedelta(hours=24):
            episodes.append(cur)
            cur = []
        cur.append(t)
    if cur:
        episodes.append(cur)
    return [{'bat_dau': str(e[0])[:16], 'ket_thuc': str(e[-1])[:16], 'so_gio': len(e),
             'mua_72h_max': round(float(rain.loc[e[0]:e[-1], 'mua_72h'].max()), 1)} for e in episodes]


def _peak(colours: pd.Series) -> str:
    return max(colours, key=ORDER.index) if len(colours) else 'xám'


def run_backtest(rain: pd.DataFrame, flags: list, config: dict) -> dict:
    colours = colour_hours(hourly_levels(rain, config['nguong']), config)
    day = colours.index.floor('D')
    daily = colours.groupby(day).agg(_peak)
    return {
        'tu': str(rain.index.min())[:16], 'den': str(rain.index.max())[:16],
        'so_gio': {c: {m: int((colours[c] == m).sum()) for m in ORDER} for c in CAP},
        'so_ngay_co_mau': {c: {m: int((daily[c] == m).sum()) for m in ORDER} for c in CAP},
        'dot_do': {c: red_episodes(colours[c], rain) for c in CAP},
        'yagi': {c: _peak(colours.loc['2024-09-08':'2024-09-10', c]) for c in CAP},
        'dot_2025_10_01': {c: _peak(colours.loc['2025-09-29':'2025-10-01', c]) for c in CAP},
        'gio_thieu_so_lieu': int((colours[CAP[0]] == 'xám').sum()),
        'so_co_theo_cap': {c: sum(f['cap'] == c for f in flags) for c in CAP},
        'dinh_nghia': 'so_ngay_co_mau: mỗi ngày tính theo màu cao nhất trong ngày; xám = cả ngày thiếu số liệu mưa.',
        'ghi_chu': NOTE,
    }


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    flags = json.loads((OUT / 'flags.json').read_text(encoding='utf-8'))
    r = run_backtest(load_rain(SRC), flags, load_config())
    (OUT / 'backtest.json').write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding='utf-8')
    print('Yagi:', r['yagi'])
    print('01/10/2025:', r['dot_2025_10_01'])
    print('Số ngày theo màu:', json.dumps(r['so_ngay_co_mau'], ensure_ascii=False))
    print('Giờ thiếu số liệu:', r['gio_thieu_so_lieu'])


if __name__ == '__main__':
    main()
