"""Warning rule: (susceptibility class) x (rain level) -> flag colour and siren."""
import json
import math
from pathlib import Path

from model.paths import CONFIG

CAP = ["Thấp", "Trung bình", "Cao", "Rất cao"]
NOTE = "Thử nghiệm – ngưỡng nháp, cần cơ quan chuyên môn xác nhận"
GREY = {"mau": "xám", "coi": False, "muc_mua": None}


def load_config(path: Path = CONFIG) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _missing(v) -> bool:
    """None, any float/numpy NaN, pd.NA or non-numeric → missing."""
    if v is None:
        return True
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return True


def _level(value: float, cuts) -> int:
    return int(sum(float(value) >= c for c in cuts))


def rain_level(mua_24h, mua_72h, thresholds: dict):
    """Highest of the 24h and 72h levels (0-3, thresholds inclusive).

    Missing data never reads as safe: with only 24h known it is also scored against the 72h
    thresholds (72h rain ≥ 24h rain); with one value missing a level-0 result is unknown → None.
    """
    has24, has72 = not _missing(mua_24h), not _missing(mua_72h)
    if not (has24 or has72):
        return None
    level = 0
    if has24:
        level = max(level, _level(mua_24h, thresholds['mua_24h_mm']))
    if has72:
        level = max(level, _level(mua_72h, thresholds['mua_72h_mm']))
    elif has24:
        level = max(level, _level(mua_24h, thresholds['mua_72h_mm']))
    if not (has24 and has72) and level == 0:
        return None
    return level


def warning_level(cap, mua_24h, mua_72h, config: dict) -> dict:
    if cap is not None and cap not in CAP:
        raise ValueError(f'Cấp dễ trượt không hợp lệ: {cap!r}')
    level = rain_level(mua_24h, mua_72h, config['nguong'])
    if cap is None or level is None:
        return dict(GREY)
    colour = config['ma_tran'][f'R{level}'][CAP.index(cap)]
    return {"mau": colour, "coi": colour == "đỏ", "muc_mua": level}
