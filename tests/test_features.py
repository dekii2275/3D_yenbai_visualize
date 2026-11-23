import numpy as np
import pytest
import shapely

from model.features import FEATURES, FORBIDDEN, Grid, cells_from_geoms, curvature, distance_m, tpi
from model.paths import SRC


def small_grid(n=3, cell=30.0):
    xs = cell * (np.arange(n) + 0.5)
    ys = cell * n - cell * (np.arange(n) + 0.5)
    return Grid(dem=np.zeros((n, n)), west=0.0, north=cell * n, cell=cell, xs=xs, ys=ys)


def test_distance_m():
    mask = np.zeros((5, 5), bool)
    mask[2, 2] = True
    d = distance_m(mask, 30)
    assert d[2, 4] == 60
    assert d[2, 2] == 0


def test_tpi_flat_zero():
    assert np.allclose(tpi(np.full((9, 9), 5.0), 3), 0)


def test_curvature_sign():
    dem = np.zeros((5, 5))
    dem[2, 2] = 10
    assert curvature(dem, 30)[2, 2] > 0


def test_cells_from_small_polygon():
    g = small_grid()
    poly = shapely.box(32, 33, 42, 43)  # 10 m square inside cell (1,1), away from its centre (45,45)
    m = cells_from_geoms(g, [poly])
    assert m[1, 1]
    assert m.sum() == 1


@pytest.mark.skipif(not SRC.exists(), reason='raw data not extracted')
def test_dataset_real():
    from model.build_dataset import build_dataset
    df = build_dataset(SRC)
    pos = int(df.nhan.sum())
    assert pos > 500
    assert (df.nhan == 0).sum() >= 3 * pos
    assert df[FEATURES].isna().sum().sum() == 0
    assert 'Yên Bái' in set(df.phuong)
    assert set(df.columns).isdisjoint(FORBIDDEN)
