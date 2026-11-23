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
    return v is None or (isinstance(v, float) and math.isnan(v))


def _level(value: float, cuts) -> int:
    return sum(value >= c for c in cuts)


def rain_level(mua_24h, mua_72h, thresholds: dict):
    """Highest of the 24h and 72h levels (0-3); None when both values are missing."""
    levels = [_level(v, thresholds[k]) for v, k in ((mua_24h, 'mua_24h_mm'), (mua_72h, 'mua_72h_mm'))
              if not _missing(v)]
    return max(levels) if levels else None


def warning_level(cap, mua_24h, mua_72h, config: dict) -> dict:
    if cap is not None and cap not in CAP:
        raise ValueError(f'Cấp dễ trượt không hợp lệ: {cap!r}')
    level = rain_level(mua_24h, mua_72h, config['nguong'])
    if cap is None or level is None:
        return dict(GREY)
    colour = config['ma_tran'][f'R{level}'][CAP.index(cap)]
    return {"mau": colour, "coi": colour == "đỏ", "muc_mua": level}
