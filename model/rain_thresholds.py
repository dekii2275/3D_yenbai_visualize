"""Draft 4-level rainfall thresholds (R0-R3) from the ward's cumulative rainfall series."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from model.paths import CONFIG, OUT, SRC
from model.warning import NOTE, load_config

COLS = {'mua_24h': 'mua_24h_mm', 'mua_72h': 'mua_72h_mm'}
PCTS = [99, 99.9, 99.99]
YAGI = ('2024-09-06', '2024-09-14')
ANCHOR_END = '2024-09-09 23:59'  # 593/904 Yagi scars are dated 09/09/2024

# Filled in from a check of Decision 18/2021/QĐ-TTg; see doi_chieu in thresholds.json.
DOI_CHIEU = ('chưa đối chiếu – cấp độ rủi ro do lũ quét, sạt lở đất nằm ở Phụ lục XII (Bảng 5–6) của '
             'Quyết định 18/2021/QĐ-TTg (hiệu lực 01/7/2021, thay QĐ 44/2014); chưa xác minh được giá trị ngưỡng mưa. '
             'Nguồn: https://thuvienphapluat.vn/documents/law.aspx?id=E%3DRjeE56RTTk ; '
             'https://vupc.mae.gov.vn/Data/files/18_2021_QD-TTg.doc')


def load_rain(src: Path = SRC) -> pd.DataFrame:
    cum = pd.read_parquet(Path(src) / 'mua_tich_luy_truot.parquet')
    return pd.DataFrame({'mua_24h': cum['1 ngày'], 'mua_72h': cum['3 ngày']})


def _floor10(v: float) -> int:
    return int(np.floor(v / 10) * 10)


def draft_thresholds(rain: pd.DataFrame) -> dict:
    out = {}
    exceed = {}
    days = rain.index.floor('D')
    before = rain.loc[YAGI[0]:ANCHOR_END]
    for col, key in COLS.items():
        v = rain[col].dropna().values
        cuts = [_floor10(np.percentile(v, p)) for p in PCTS]
        # Anchor to Yagi: R3 must already be reached by the date most scars appeared (09/09/2024).
        if len(before) and before[col].notna().any():
            cuts[2] = min(cuts[2], _floor10(before[col].max()))
            if cuts[1] >= cuts[2]:
                cuts[1] = _floor10((cuts[0] + cuts[2]) / 2)
        out[key] = cuts
        exceed[key] = [int(days[(rain[col] >= c).values].nunique()) for c in cuts]
    yagi = rain.loc[YAGI[0]:YAGI[1]]
    out.update({
        'cach_tinh': 'R1/R2/R3 = phân vị P99/P99.9/P99.99 của các giờ có số liệu (2021–2026), làm tròn xuống bội 10 mm; '
                     'R3 neo với Yagi: không vượt lượng mưa đã đạt đến hết 09/09/2024 (ngày phát sinh của đa số vết trượt), '
                     'nếu R2 ≥ R3 thì R2 = trung bình R1 và R3; mức mưa = mức cao nhất của mưa 24h và 72h (so sánh ≥).',
        'ghi_chu': NOTE,
        'so_ngay_vuot': exceed,
        'yagi_den_09_09': {'mua_24h': round(float(before.mua_24h.max()), 1), 'mua_72h': round(float(before.mua_72h.max()), 1)} if len(before) else None,
        'yagi_dinh': {'mua_24h': round(float(yagi.mua_24h.max()), 1), 'mua_72h': round(float(yagi.mua_72h.max()), 1)},
        'so_gio_co_so_lieu': {k: int(rain[c].notna().sum()) for c, k in COLS.items()},
        'doi_chieu': DOI_CHIEU,
    })
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    t = draft_thresholds(load_rain(SRC))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'thresholds.json').write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding='utf-8')
    cfg = load_config()
    cfg['nguong'] = {k: t[k] for k in COLS.values()}
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: t[k] for k in ('mua_24h_mm', 'mua_72h_mm', 'so_ngay_vuot', 'yagi_dinh')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
