import numpy as np
import pandas as pd
import pytest

from model.backtest import colour_hours, red_episodes, run_backtest
from model.paths import OUT, SRC

CFG = {
    "nguong": {"mua_24h_mm": [50, 100, 200], "mua_72h_mm": [100, 200, 400]},
    "ma_tran": {"R0": ["xanh"] * 4, "R1": ["xanh", "xanh", "vàng", "vàng"],
                "R2": ["xanh", "vàng", "cam", "cam"], "R3": ["vàng", "cam", "đỏ", "đỏ"]},
}


def _hours(n):
    return pd.date_range('2024-01-01', periods=n, freq='h')


def test_red_episode_merge():
    idx = _hours(72)
    col = pd.Series('xanh', index=idx)
    col.iloc[0:3] = 'đỏ'
    col.iloc[10:13] = 'đỏ'
    rain = pd.DataFrame({'mua_24h': 0.0, 'mua_72h': 500.0}, index=idx)
    assert len(red_episodes(col, rain)) == 1
    col.iloc[50] = 'đỏ'
    eps = red_episodes(col, rain)
    assert len(eps) == 2
    assert eps[0]['so_gio'] == 6


def test_missing_hours_grey():
    idx = _hours(10)
    rain = pd.DataFrame({'mua_24h': 0.0, 'mua_72h': 0.0}, index=idx)
    rain.iloc[2:5] = np.nan
    from model.backtest import hourly_levels
    out = colour_hours(hourly_levels(rain, CFG['nguong']), CFG)
    assert (out.iloc[2:5] == 'xám').all().all()
    assert (out.iloc[0] == 'xanh').all()


@pytest.mark.skipif(not (SRC.exists() and (OUT / 'flags.json').exists()), reason='model outputs missing')
def test_backtest_real():
    import json
    from model.rain_thresholds import load_rain
    from model.warning import load_config
    flags = json.loads((OUT / 'flags.json').read_text(encoding='utf-8'))
    r = run_backtest(load_rain(SRC), flags, load_config())
    assert r['yagi']['Rất cao'] == 'đỏ'
    assert r['so_ngay_co_mau']['Rất cao']['đỏ'] <= 10
