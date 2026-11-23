import numpy as np
import pandas as pd
import pytest

from model.paths import SRC
from model.rain_thresholds import draft_thresholds, load_rain
from model.warning import NOTE


def test_draft_rounding():
    v = np.arange(0, 10000, dtype=float)
    rain = pd.DataFrame({'mua_24h': v, 'mua_72h': v},
                        index=pd.date_range('2021-01-01', periods=len(v), freq='h'))
    t = draft_thresholds(rain)
    assert t['mua_24h_mm'] == [9890, 9980, 9990]
    assert t['mua_72h_mm'] == [9890, 9980, 9990]


@pytest.mark.skipif(not SRC.exists(), reason='raw data not extracted')
def test_thresholds_real():
    t = draft_thresholds(load_rain(SRC))
    for k in ('mua_24h_mm', 'mua_72h_mm'):
        assert t[k][0] < t[k][1] < t[k][2]
    assert t['yagi_dinh']['mua_72h'] >= t['mua_72h_mm'][2]
    assert t['ghi_chu'] == NOTE


@pytest.mark.skipif(not SRC.exists(), reason='raw data not extracted')
def test_r3_reached_by_scar_date():
    rain = load_rain(SRC)
    t = draft_thresholds(rain)
    before = rain.loc['2024-09-06':'2024-09-09 23:59']
    assert before.mua_24h.max() >= t['mua_24h_mm'][2] or before.mua_72h.max() >= t['mua_72h_mm'][2]
