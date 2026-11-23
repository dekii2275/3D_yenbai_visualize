import pytest

from model.warning import NOTE, load_config, rain_level, warning_level

T = {"mua_24h_mm": [50, 100, 200], "mua_72h_mm": [100, 200, 400]}
CFG = {
    "nguong": T,
    "ma_tran": {
        "R0": ["xanh", "xanh", "xanh", "xanh"],
        "R1": ["xanh", "xanh", "vàng", "vàng"],
        "R2": ["xanh", "vàng", "cam", "cam"],
        "R3": ["vàng", "cam", "đỏ", "đỏ"],
    },
}


def test_rain_level_takes_max():
    assert rain_level(60, 50, T) == 1
    assert rain_level(10, 450, T) == 3


def test_rain_level_boundary_inclusive():
    assert rain_level(50, 0, T) == 1
    assert rain_level(49.9, 99.9, T) == 0


def test_rain_level_missing():
    assert rain_level(None, float("nan"), T) is None
    assert rain_level(float("nan"), 250, T) == 2


def test_matrix_cells():
    assert warning_level("Cao", 0, 250, CFG)["mau"] == "cam"
    assert warning_level("Thấp", 0, 450, CFG)["mau"] == "vàng"
    assert warning_level("Rất cao", 210, 0, CFG) == {"mau": "đỏ", "coi": True, "muc_mua": 3}


def test_missing_rain_grey():
    assert warning_level("Rất cao", None, None, CFG) == {"mau": "xám", "coi": False, "muc_mua": None}


def test_unknown_cap():
    assert warning_level(None, 300, 500, CFG)["mau"] == "xám"
    with pytest.raises(ValueError):
        warning_level("abc", 1, 1, CFG)


def test_config_file_matrix():
    cfg = load_config()
    assert cfg["ma_tran"]["R3"] == ["vàng", "cam", "đỏ", "đỏ"]
    assert cfg["ghi_chu"] == NOTE


def test_numpy_nan_is_missing():
    import numpy as np
    out = warning_level("Rất cao", np.float32("nan"), np.float32("nan"), CFG)
    assert out == {"mau": "xám", "coi": False, "muc_mua": None}
    lvl = warning_level("Rất cao", np.float64(500), np.float64(500), CFG)["muc_mua"]
    assert type(lvl) is int


def test_partial_rain_cannot_show_safe():
    # 72h missing: 24h is a lower bound of 72h; a level-0 result with partial data is unknown, not safe.
    assert rain_level(30, None, T) is None
    assert rain_level(None, 50, T) is None
    assert rain_level(170, None, T) == 2
    assert warning_level("Rất cao", 30, float("nan"), CFG)["mau"] == "xám"
