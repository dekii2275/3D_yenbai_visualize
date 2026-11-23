"""Train and evaluate the susceptibility ("where") model, then map it and score the flag points."""
import json
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from model.build_dataset import build_dataset
from model.features import DEM_FILE, FEATURES, feature_stack, load_grid, masks
from model.geotiff import write_geotiff
from model.paths import OUT, SRC, WORK
from model.warning import CAP

HOLDOUT = 'Yên Bái'
SLOPE_DOMAIN = 5.0  # min mean slope of any Yagi scar polygon (detector filter)


def spatial_blocks(x: np.ndarray, y: np.ndarray, size_m: float = 1000) -> np.ndarray:
    bx = np.floor(np.asarray(x) / size_m).astype(np.int64)
    by = np.floor(np.asarray(y) / size_m).astype(np.int64)
    return bx * 100000 + by


def make_models() -> dict:
    return {
        'logistic': Pipeline([('scale', StandardScaler()),
                              ('lr', LogisticRegression(class_weight='balanced', max_iter=2000))]),
        'random_forest': RandomForestClassifier(n_estimators=400, min_samples_leaf=5,
                                                class_weight='balanced_subsample', n_jobs=-1, random_state=42),
    }


def _scores(y, p) -> tuple[float, float]:
    return float(roc_auc_score(y, p)), float(average_precision_score(y, p))


def evaluate(model, df: pd.DataFrame) -> dict:
    X, y = df[FEATURES].values, df.nhan.values
    test = (df.phuong == HOLDOUT).values
    model.fit(X[~test], y[~test])
    p_test = model.predict_proba(X[test])[:, 1]
    roc, pr = _scores(y[test], p_test)
    hold = {'auc_roc': round(roc, 4), 'auc_pr': round(pr, 4), 'n_pos': int(y[test].sum()),
            'n_neg': int((y[test] == 0).sum())}
    # The scar detector never flags polygons with mean slope < 5°; scoring only inside that domain shows how
    # much of the AUC is just "flat vs not flat".
    steep = df.do_doc.values[test] >= SLOPE_DOMAIN
    roc5, pr5 = _scores(y[test][steep], p_test[steep])
    hold5 = {'auc_roc': round(roc5, 4), 'auc_pr': round(pr5, 4), 'n_pos': int(y[test][steep].sum()),
             'n_neg': int((y[test][steep] == 0).sum())}
    rocs, prs = [], []
    for tr, te in GroupKFold(n_splits=5).split(X, y, spatial_blocks(df.x, df.y)):
        model.fit(X[tr], y[tr])
        r, p = _scores(y[te], model.predict_proba(X[te])[:, 1])
        rocs.append(r)
        prs.append(p)
    return {'holdout_yen_bai': hold, 'holdout_yen_bai_doc_ge5': hold5,
            'block_cv': {'auc_roc_mean': round(float(np.mean(rocs)), 4), 'auc_roc_std': round(float(np.std(rocs)), 4),
                         'auc_pr_mean': round(float(np.mean(prs)), 4)}}


def choose(results: dict) -> str:
    rf = results['random_forest']['holdout_yen_bai']['auc_roc']
    lr = results['logistic']['holdout_yen_bai']['auc_roc']
    return 'random_forest' if rf - lr > 0.02 else 'logistic'


def classify(prob: np.ndarray, valid: np.ndarray) -> tuple[np.ndarray, list[float]]:
    cuts = [float(c) for c in np.percentile(prob[valid], [60, 85, 95])]
    classes = np.full(prob.shape, 255, np.uint8)
    classes[valid] = np.searchsorted(cuts, prob[valid], side='right').astype(np.uint8)
    return classes, cuts


def _importance(model, name: str) -> dict:
    if name == 'random_forest':
        v = model.feature_importances_
    else:
        v = np.abs(model.named_steps['lr'].coef_[0])
    v = v / v.sum()
    order = np.argsort(v)[::-1]
    return {FEATURES[i]: round(float(v[i]), 4) for i in order}


def _flags(grid, valid, prob, classes) -> list[dict]:
    pts = gpd.read_file(SRC / 'truot_lo_phuong_Yen_Bai.gpkg')
    pu = pts.to_crs('EPSG:32648')
    out = []
    for p, g in zip(pts.itertuples(), pu.geometry):
        r = int((grid.north - g.y) // grid.cell)
        c = int((g.x - grid.west) // grid.cell)
        best = None
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                rr, cc = r + dr, c + dc
                if 0 <= rr < valid.shape[0] and 0 <= cc < valid.shape[1] and valid[rr, cc]:
                    d = (grid.xs[cc] - g.x) ** 2 + (grid.ys[rr] - g.y) ** 2
                    if best is None or d < best[0]:
                        best = (d, rr, cc)
        prob_v = cap = None
        if best:
            prob_v = round(float(prob[best[1], best[2]]), 4)
            cap = CAP[int(classes[best[1], best[2]])]
        out.append({'ma_vi_tri': p.ma_vi_tri, 'ten_diem': p.ten_diem, 'trang_thai': p.trang_thai,
                    'lon': round(float(p.lon_wgs84), 6), 'lat': round(float(p.lat_wgs84), 6),
                    'x': round(float(g.x), 1), 'y': round(float(g.y), 1), 'xac_suat': prob_v, 'cap': cap})
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    path = WORK / 'dataset.parquet'
    df = pd.read_parquet(path) if path.exists() else build_dataset(SRC)
    results = {name: evaluate(model, df) for name, model in make_models().items()}
    chosen = choose(results)
    model = make_models()[chosen].fit(df[FEATURES].values, df.nhan.values)

    grid = load_grid(SRC)
    feats = feature_stack(SRC, grid)
    m = masks(SRC, grid, feats)
    valid = m['valid']
    X = np.column_stack([feats[k][valid] for k in FEATURES])
    prob = np.full(grid.shape, np.nan)
    prob[valid] = model.predict_proba(X)[:, 1]
    classes, cuts = classify(prob, valid)

    OUT.mkdir(parents=True, exist_ok=True)
    write_geotiff(OUT / 'susceptibility_prob.tif', np.where(valid, prob, -9999).astype(np.float32),
                  SRC / DEM_FILE, -9999)
    write_geotiff(OUT / 'susceptibility_class.tif', classes, SRC / DEM_FILE, 255)

    flags = _flags(grid, valid, prob, classes)
    pd.DataFrame(flags).to_csv(OUT / 'flags.csv', index=False, encoding='utf-8-sig')
    (OUT / 'flags.json').write_text(json.dumps(flags, ensure_ascii=False, indent=1), encoding='utf-8')

    yb_scar = m['positive'] & valid & (m['ward'] == HOLDOUT)
    # Out-of-sample view: model trained without Yên Bái, mapped everywhere, classed with its own cut-offs.
    out_df = df[df.phuong != HOLDOUT]
    hold_model = make_models()[chosen].fit(out_df[FEATURES].values, out_df.nhan.values)
    hold_prob = np.full(grid.shape, np.nan)
    hold_prob[valid] = hold_model.predict_proba(X)[:, 1]
    hold_classes, _ = classify(hold_prob, valid)
    metrics = {
        'models': results, 'chosen': chosen, 'cutoffs': [round(c, 4) for c in cuts],
        'cutoff_rule': 'Thấp < P60 ≤ Trung bình < P85 ≤ Cao < P95 ≤ Rất cao (xác suất trên ô hợp lệ)',
        'importance': _importance(model, chosen), 'features': FEATURES,
        'n_samples': {'positive': int(df.nhan.sum()), 'negative': int((df.nhan == 0).sum())},
        'area_share_by_class': {CAP[i]: round(float((classes[valid] == i).mean()), 4) for i in range(4)},
        'yen_bai_scar_cells_by_class': {CAP[i]: int((classes[yb_scar] == i).sum()) for i in range(4)},
        'yen_bai_scar_cells_by_class_holdout': {CAP[i]: int((hold_classes[yb_scar] == i).sum()) for i in range(4)},
        'scar_class_note': 'yen_bai_scar_cells_by_class dùng mô hình cuối (đã học cả Yên Bái – trong mẫu); '
                           'bản _holdout dùng mô hình không học Yên Bái – đây là con số kiểm định.',
        'flags_by_class': {c: sum(f['cap'] == c for f in flags) for c in CAP + [None]},
        'note': '87 điểm cờ không độc lập với vết Yagi (64/87 điểm cách vết < 100 m) – chỉ là kiểm tra phụ.',
    }
    metrics['flags_by_class']['Không xác định'] = metrics['flags_by_class'].pop(None)
    (OUT / 'metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding='utf-8')
    for name, r in results.items():
        print(f"{name:14s} holdout Yên Bái AUC-ROC {r['holdout_yen_bai']['auc_roc']:.3f} (dốc≥5°: {r['holdout_yen_bai_doc_ge5']['auc_roc']:.3f}) AUC-PR "
              f"{r['holdout_yen_bai']['auc_pr']:.3f} | block-CV AUC-ROC {r['block_cv']['auc_roc_mean']:.3f}"
              f"±{r['block_cv']['auc_roc_std']:.3f}")
    print('Chọn:', chosen, '| Vết Yên Bái theo cấp (holdout):', metrics['yen_bai_scar_cells_by_class_holdout'])
    print('Cờ theo cấp:', metrics['flags_by_class'])


if __name__ == '__main__':
    main()
