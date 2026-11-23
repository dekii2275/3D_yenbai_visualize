import json

import numpy as np
import pytest

from model.features import FEATURES, FORBIDDEN, read_raster
from model.paths import OUT, SRC
from model.train_susceptibility import choose, classify, spatial_blocks
from model.warning import CAP


def test_no_leakage():
    assert set(FEATURES).isdisjoint(FORBIDDEN)


def test_classify_proportions():
    prob = np.linspace(0, 1, 10000).reshape(100, 100)
    valid = np.ones_like(prob, bool)
    valid[0] = False
    classes, cuts = classify(prob, valid)
    v = classes[valid]
    assert abs((v == 3).mean() - 0.05) <= 0.01
    assert abs((v == 2).mean() - 0.10) <= 0.01
    assert abs((v == 1).mean() - 0.25) <= 0.01
    assert classes[0].max() == 255
    assert len(cuts) == 3


def test_spatial_blocks():
    b = spatial_blocks(np.array([0, 999, 1000]), np.array([0, 0, 0]))
    assert b[0] == b[1]
    assert b[2] != b[0]


def test_choose():
    lr = {"holdout_yen_bai": {"auc_roc": .80}}
    assert choose({"logistic": lr, "random_forest": {"holdout_yen_bai": {"auc_roc": .81}}}) == "logistic"
    assert choose({"logistic": lr, "random_forest": {"holdout_yen_bai": {"auc_roc": .83}}}) == "random_forest"


@pytest.mark.skipif(not (SRC.exists() and (OUT / 'metrics.json').exists()), reason='model not trained')
def test_outputs_real():
    from model.features import load_grid, masks
    m = json.loads((OUT / 'metrics.json').read_text(encoding='utf-8'))
    assert m['chosen'] in ('logistic', 'random_forest')
    auc = m['models'][m['chosen']]['holdout_yen_bai']['auc_roc']
    assert 0.5 < auc <= 1
    hold = m['yen_bai_scar_cells_by_class_holdout']
    assert sum(hold.values()) == sum(m['yen_bai_scar_cells_by_class'].values()) > 0
    cls = read_raster(OUT / 'susceptibility_class.tif')  # 255 read back as NaN (nodata)
    assert cls.shape == (224, 289)
    assert set(np.unique(cls[np.isfinite(cls)])) <= {0, 1, 2, 3}
    grid = load_grid(SRC)
    water = masks(SRC, grid)['water']
    assert np.isnan(cls[water]).all()
    flags = json.loads((OUT / 'flags.json').read_text(encoding='utf-8'))
    assert len(flags) == 87
    assert all(f['cap'] in CAP or f['cap'] is None for f in flags)
