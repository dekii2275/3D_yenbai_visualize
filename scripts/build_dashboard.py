#!/usr/bin/env python3
"""Explore the raw data in data/ and write dashboard.html (data report + 3D GIS tab).

Requires pandas, pyarrow, openpyxl, geopandas (pyogrio), shapely, numpy, Pillow.
Usage: python scripts/build_dashboard.py
The generated dashboard.html embeds only aggregated/derived data and loads
Plotly from a CDN, so it can be opened directly in a browser.
"""
import json, math, os, sys
from pathlib import Path

import warnings
import numpy as np
warnings.filterwarnings("ignore", category=RuntimeWarning)
import pandas as pd
import geopandas as gpd
import pyogrio
import shapely
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
SRC = DATA / 'du_lieu_phuong_Yen_Bai' / 'du_lieu'
EXCEL = DATA / 'Cac vi tri nguy co truot lo phuong Yen Bai.xlsx'
TEMPLATE = ROOT / 'scripts' / 'dashboard_template.html'
OUT = ROOT / 'dashboard.html'
UTM = 'EPSG:32648'


def r(v, n=2):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return None
    return round(float(v), n)


def counts(series, top=None):
    vc = series.fillna('(trống)').astype(str).str.replace('\n', ' ').value_counts()
    if top:
        vc = vc.head(top)
    return {'labels': vc.index.tolist(), 'values': [int(v) for v in vc.values]}


def hist(values, bins):
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    h, e = np.histogram(v, bins=bins)
    return {'edges': [r(x, 3) for x in e], 'counts': h.tolist()}


def read_tif(path):
    im = Image.open(path)
    t = im.tag_v2
    a = np.array(im, dtype=float)
    nd = t.get(42113)
    if nd is not None:
        a[a == float(nd)] = np.nan
    sx, sy, _ = t[33550]
    west, north = t[33922][3], t[33922][4]
    return a, dict(sx=sx, sy=sy, west=west, north=north, w=im.size[0], h=im.size[1])


def stats(a):
    v = a[np.isfinite(a)]
    return dict(n=int(v.size), min=r(v.min()), mean=r(v.mean()), median=r(np.median(v)),
                p95=r(np.percentile(v, 95)), max=r(v.max()), std=r(v.std()))


# ---------------------------------------------------------------- inventory
def inventory():
    files = []
    for p in sorted(DATA.rglob('*')):
        if p.is_dir():
            continue
        rel = p.relative_to(DATA).as_posix()
        item = dict(path=rel, size_kb=round(p.stat().st_size / 1024, 1), ext=p.suffix.lower(), detail='')
        try:
            if p.suffix == '.gpkg':
                parts = []
                for name, gtype in pyogrio.list_layers(p):
                    info = pyogrio.read_info(p, layer=name)
                    parts.append(f"{name}: {info['features']} {gtype or ''} · {len(info['fields'])} trường · {info['crs']}")
                item['detail'] = ' | '.join(parts)
            elif p.suffix == '.parquet':
                df = pd.read_parquet(p)
                item['detail'] = f"{len(df):,} dòng × {df.shape[1]} cột: " + ', '.join(map(str, df.columns))
            elif p.suffix == '.tif':
                a, m = read_tif(p)
                item['detail'] = f"{m['w']}×{m['h']} px, ô {r(m['sx'], 6)}, {np.isfinite(a).sum():,} ô hợp lệ"
            elif p.suffix == '.xlsx':
                df = pd.read_excel(p)
                item['detail'] = f"{len(df)} dòng × {df.shape[1]} cột"
            elif p.suffix == '.rar':
                item['detail'] = 'Kho nén gốc (đã giải nén vào du_lieu_phuong_Yen_Bai/)'
        except Exception as exc:  # keep the report going
            item['detail'] = f'Không đọc được: {exc}'
        files.append(item)
    return files


MODEL_OUT = ROOT / 'model' / 'outputs'


def model_section(x0, y0):
    """Trial model results from model/outputs (None when the model has not been run)."""
    if not (MODEL_OUT / 'metrics.json').exists():
        return None
    load = lambda n: json.loads((MODEL_OUT / n).read_text(encoding='utf-8'))
    cls = np.array(Image.open(MODEL_OUT / 'susceptibility_class.tif'), dtype=float)
    cls[cls == 255] = np.nan
    flags = load('flags.json')
    for f in flags:
        f['kx'] = round((f['x'] - x0) / 1000, 4)
        f['ky'] = round((f['y'] - y0) / 1000, 4)
    return dict(metrics=load('metrics.json'), thresholds=load('thresholds.json'), backtest=load('backtest.json'),
                config=json.loads((ROOT / 'model' / 'config.json').read_text(encoding='utf-8')), flags=flags,
                classes=[[None if not np.isfinite(v) else int(v) for v in row] for row in cls])


def main():
    out = {}
    out['inventory'] = inventory()

    ward = gpd.read_file(SRC / 'ranh_gioi_phuong_Yen_Bai.gpkg')
    ward_u = ward.to_crs(UTM)
    ward_poly = ward_u.geometry.iloc[0]
    w0 = ward.iloc[0]
    out['ward'] = dict(name=w0.ten_xa, area_km2=r(w0.dtich_km2), pop=int(w0.dan_so), density=r(w0.matdo_km2),
                       merged=w0.sap_nhap, province=w0.ten_tinh, area_calc_km2=r(ward_poly.area / 1e6))

    # ------------------------------------------------------------ landslide points
    pts = gpd.read_file(SRC / 'truot_lo_phuong_Yen_Bai.gpkg')
    pts_u = pts.to_crs(UTM)
    pts['xa_cu_norm'] = pts.xa_cu.str.replace(r'^P\.\s*', '', regex=True).str.strip()
    nonnull = pts.drop(columns='geometry').notna().mean()
    out['points'] = dict(
        n=len(pts),
        status=counts(pts.trang_thai),
        group=counts(pts.nhom_vi_tri),
        conf=counts(pts.do_tin_cay_vi_tri),
        source=counts(pts.nguon),
        xa_cu_raw=counts(pts.xa_cu),
        xa_cu=counts(pts.xa_cu_norm),
        aspect=counts(pts.huong_doc_8),
        rock=counts(pts.dc_nhom_da),
        geo_unit=counts(pts.dc_ten_don_vi),
        road_class=counts(pts.cap_duong_gan_nhat),
        road_pos=counts(pts.vi_tri_so_voi_tuyen.dropna()),
        fault_type=counts(pts.kieu_dut_gay_gan_nhat),
        n_cols=int(pts.shape[1] - 1),
        empty_cols=[c for c, v in nonnull.items() if v == 0],
        sparse_cols=[[c, r(v * 100, 1)] for c, v in nonnull.items() if 0 < v < 0.5],
        numeric={},
        occurred=pts.loc[pts.trang_thai == 'Đã xảy ra', ['ma_vi_tri', 'ten_diem', 'xa_cu', 'the_tich_m3', 'cao_do_m',
                                                        'do_doc_do', 'mo_ta']].fillna('').to_dict('records'),
    )
    numeric = {
        'cao_do_m': ('Cao độ (m)', 10), 'do_doc_do': ('Độ dốc (°)', 2), 'kc_duong_m': ('K/c tới đường gần nhất (m)', 20),
        'so_nha_500m': ('Số nhà trong 500 m', 20), 'twi': ('Chỉ số ẩm địa hình TWI', 0.5),
        'kc_dut_gay_m': ('K/c tới đứt gãy (m)', 200), 'tpi_300m': ('TPI 300 m', 4),
        'bien_do_dia_hinh_500m': ('Biên độ địa hình 500 m (m)', 10), 'kc_song_suoi_dem_m': ('K/c sông suối DEM (m)', 30),
        'mua_tb_nam_mm': ('Mưa TB năm 2021–2026 (mm)', 10),
    }
    for col, (label, width) in numeric.items():
        v = pd.to_numeric(pts[col], errors='coerce').dropna()
        lo = math.floor(v.min() / width) * width
        hi = math.ceil(v.max() / width) * width + width
        out['points']['numeric'][col] = dict(label=label, stats=dict(n=int(v.size), min=r(v.min()), mean=r(v.mean()),
                                             median=r(v.median()), max=r(v.max())),
                                             hist=hist(v, np.arange(lo, hi + 1e-9, width)))
    out['points']['by_status_slope'] = {s: pd.to_numeric(g.do_doc_do).round(1).tolist()
                                        for s, g in pts.groupby('trang_thai')}
    out['points']['table'] = pts[['ma_vi_tri', 'ten_diem', 'xa_cu', 'trang_thai', 'do_tin_cay_vi_tri', 'cao_do_m',
                                  'do_doc_do', 'huong_doc_8', 'dc_nhom_da', 'kc_duong_m', 'so_nha_100m',
                                  'lon_wgs84', 'lat_wgs84']].round(5).fillna('').to_dict('records')

    # ------------------------------------------------------------ excel vs gpkg
    xl = pd.read_excel(EXCEL)
    coslat = math.cos(math.radians(21.72))
    dx = (pts.lon_wgs84.values[None, :] - xl.Long.values[:, None]) * 111320 * coslat
    dy = (pts.lat_wgs84.values[None, :] - xl.Lat.values[:, None]) * 110574
    d = np.hypot(dx, dy)
    dmin, imin = d.min(1), d.argmin(1)
    exact = dmin < 1
    gp_matched = set(imin[exact])
    xl_un = xl.loc[~exact].assign(kc_m=dmin[~exact].round(1), gpkg_gan_nhat=pts.ma_vi_tri.values[imin[~exact]])
    gp_un = pts.loc[~pts.index.isin(gp_matched)]
    out['excel'] = dict(
        n=len(xl), n_cols=int(xl.shape[1]), cols=list(xl.columns),
        xa_cu=counts(xl.Ten_Xa_cu), he_so=counts(xl.He_so),
        dup_coords=int(xl.duplicated(['Long', 'Lat']).sum()),
        dup_coord_rows=xl[xl.duplicated(['Long', 'Lat'], keep=False)][['id_diem_truot', 'ten_diem_truot', 'Long', 'Lat']].to_dict('records'),
        n_exact=int(exact.sum()), n_gpkg_matched=len(gp_matched),
        dist_hist=hist(np.clip(dmin, 0, 300), [0, 1, 10, 50, 100, 200, 300.01]),
        excel_unmatched=xl_un[['id_diem_truot', 'ten_diem_truot', 'Ten_Xa_cu', 'Long', 'Lat', 'kc_m', 'gpkg_gan_nhat']].round(6).to_dict('records'),
        gpkg_unmatched=gp_un[['ma_vi_tri', 'ten_diem', 'xa_cu', 'trang_thai', 'nguon']].fillna('').to_dict('records'),
    )
    xl_g = gpd.GeoDataFrame(xl, geometry=gpd.points_from_xy(xl.Long, xl.Lat), crs='EPSG:4326').to_crs(UTM)
    xl_g['in_ward'] = xl_g.within(ward_poly.buffer(1))
    out['excel']['in_ward'] = int(xl_g.in_ward.sum())
    out['points']['in_ward'] = int(pts_u.within(ward_poly.buffer(1)).sum())

    # ------------------------------------------------------------ Yagi scars
    yg = gpd.read_file(SRC / 'vet_truot_ve_tinh_Yagi_trong_phuong.gpkg')
    yg_all = gpd.read_file(SRC / 'nen_phuong_Yen_Bai.gpkg', layer='vet_truot_ve_tinh_Yagi')
    out['yagi'] = dict(
        n=len(yg), n_all=len(yg_all), area_total_m2=r(yg.dien_tich_m2.sum(), 0),
        area_total_all_m2=r(yg_all.dien_tich_m2.sum(), 0),
        area=hist(yg.dien_tich_m2, [0, 500, 1000, 2000, 3000, 5000, 10000, max(10001, yg.dien_tich_m2.max() + 1)]),
        area_stats=dict(min=r(yg.dien_tich_m2.min()), median=r(yg.dien_tich_m2.median()), max=r(yg.dien_tich_m2.max())),
        conf=counts(yg.muc_tin_cay), dot=counts(yg['dot']), date=counts(yg.ngay_phat_sinh.astype(str)),
        xa=counts(yg_all.ten_xa), track=counts(yg.track_insar),
        slope=hist(yg.do_doc, np.arange(0, 40, 2.5)),
        score=hist(yg.diem_tb, np.arange(1, 3.01, 0.25)),
        rain24=counts(yg.max_24h_mm.round(0).astype(int).astype(str) + ' mm (' + yg.id_tram + ')'),
        ndvi=hist(yg.rdNDVI, np.arange(-1, 0.01, 0.1)),
        cols=[c for c in yg.columns if c != 'geometry'],
    )

    # ------------------------------------------------------------ rasters
    dem, dm = read_tif(SRC / 'DEM_30m_phuong_Yen_Bai_UTM48N.tif')
    slope, _ = read_tif(SRC / 'do_doc_do_UTM48N.tif')
    aspect, _ = read_tif(SRC / 'huong_doc_do_UTM48N.tif')
    relief, _ = read_tif(SRC / 'bien_do_dia_hinh_300m_UTM48N.tif')
    xs = dm['west'] + dm['sx'] * (np.arange(dm['w']) + 0.5)
    ys = dm['north'] - dm['sy'] * (np.arange(dm['h']) + 0.5)
    XX, YY = np.meshgrid(xs, ys)
    inward = shapely.contains_xy(ward_poly, XX, YY)
    rasters = {}
    for name, label, arr in [('dem', 'Cao độ (m)', dem), ('slope', 'Độ dốc (°)', slope),
                             ('relief', 'Biên độ địa hình 300 m (m)', relief)]:
        rasters[name] = dict(label=label, all=stats(arr), ward=stats(np.where(inward, arr, np.nan)))
    rasters['dem']['hist_ward'] = hist(dem[inward], np.arange(0, 170, 10))
    sw = slope[inward & np.isfinite(slope)]
    bins = [0, 5, 10, 15, 20, 25, 30, 40]
    hw, _ = np.histogram(sw, bins)
    hp, _ = np.histogram(pd.to_numeric(pts.do_doc_do), bins)
    yslope = yg.do_doc.values
    hy, _ = np.histogram(yslope, bins)
    rasters['slope_compare'] = dict(bins=[f'{a}–{b}°' for a, b in zip(bins[:-1], bins[1:])],
                                    ward=[r(v * 100 / hw.sum(), 1) for v in hw],
                                    points=[r(v * 100 / hp.sum(), 1) for v in hp],
                                    yagi=[r(v * 100 / hy.sum(), 1) for v in hy])
    a8 = ['Bắc', 'Đông Bắc', 'Đông', 'Đông Nam', 'Nam', 'Tây Nam', 'Tây', 'Tây Bắc']
    aw = aspect[inward & np.isfinite(aspect) & (aspect >= 0)]
    idx = (((aw + 22.5) % 360) // 45).astype(int)
    ward_aspect = np.bincount(idx, minlength=8)
    pa = pts.huong_doc_8.value_counts()
    rasters['aspect_compare'] = dict(labels=a8, ward=[r(v * 100 / ward_aspect.sum(), 1) for v in ward_aspect],
                                     points=[r(pa.get(k, 0) * 100 / pa.sum(), 1) for k in a8])
    rasters['meta'] = dict(w=dm['w'], h=dm['h'], cell=dm['sx'], cells_ward=int(inward.sum()),
                           cells_valid=int(np.isfinite(dem).sum()))
    out['rasters'] = rasters

    # ------------------------------------------------------------ geology & OSM
    geo = gpd.read_file(SRC / 'nen_phuong_Yen_Bai.gpkg', layer='dia_chat')
    gc = gpd.clip(geo, ward_poly)
    gc['a'] = gc.area / 1e6
    ga = gc.groupby('nhom_da').a.sum().sort_values(ascending=False)
    gu = gc.groupby('ten_don_vi').a.sum().sort_values(ascending=False)
    faults = gpd.read_file(SRC / 'nen_phuong_Yen_Bai.gpkg', layer='dut_gay')
    fc = gpd.clip(faults, ward_poly)
    out['geology'] = dict(rock_area={'labels': ga.index.tolist(), 'values': [r(v, 3) for v in ga.values]},
                          unit_area={'labels': gu.index.tolist(), 'values': [r(v, 3) for v in gu.values]},
                          fault_len_km=r(fc.length.sum() / 1000, 2), fault_n=len(fc),
                          fault_types=counts(faults.kieu_dut_gay))
    osm = {}
    for name, _ in pyogrio.list_layers(SRC / 'nen_phuong_Yen_Bai.gpkg'):
        if name.startswith('osm_'):
            osm[name] = pyogrio.read_info(SRC / 'nen_phuong_Yen_Bai.gpkg', layer=name)['features']
    roads = gpd.read_file(SRC / 'nen_phuong_Yen_Bai.gpkg', layer='osm_roads')
    rc = gpd.clip(roads, ward_poly)
    rl = (rc.assign(km=rc.length / 1000).groupby('fclass').km.sum().sort_values(ascending=False))
    out['osm'] = dict(layers=osm, road_km={'labels': rl.index.tolist(), 'values': [r(v, 2) for v in rl.values]},
                      buildings_in_ward=int(gpd.read_file(SRC / 'nen_phuong_Yen_Bai.gpkg', layer='osm_buildings_a')
                                            .centroid.within(ward_poly).sum()))

    # ------------------------------------------------------------ rainfall
    daily = pd.read_parquet(SRC / 'mua_ngay_tram_Yen_Bai_2011_2024.parquet')
    ann = daily.groupby(['station_id', 'nam']).agg(tot=('mua_mm', 'sum'), n=('mua_mm', 'size')).reset_index()
    daily['thang'] = daily.ngay.dt.month
    mon = daily.groupby(['station_id', 'nam', 'thang']).mua_mm.sum().groupby(['station_id', 'thang']).mean().reset_index()
    top = daily.sort_values('mua_mm', ascending=False).head(12)
    out['rain_daily'] = dict(
        stations={s: dict(years=g.nam.tolist(), tot=[r(v, 1) for v in g.tot], days=g.n.tolist())
                  for s, g in ann.groupby('station_id')},
        monthly={s: [r(v, 1) for v in g.sort_values('thang').mua_mm] for s, g in mon.groupby('station_id')},
        sources=counts(daily.nguon),
        coverage={s: dict(start=str(g.ngay.min().date()), end=str(g.ngay.max().date()), n=int(len(g)),
                          expected=int((g.ngay.max() - g.ngay.min()).days + 1), na=int(g.mua_mm.isna().sum()))
                  for s, g in daily.groupby('station_id')},
        top=[dict(station=t.station_id, date=str(t.ngay.date()), mm=r(t.mua_mm, 1)) for t in top.itertuples()],
        n=len(daily),
    )
    hourly = pd.read_parquet(SRC / 'mua_gio_tram_quanh_phuong_2021_2026.parquet')
    hourly['ngay'] = hourly.gio.dt.tz_localize(None).dt.floor('D')
    st = {}
    for s, g in hourly.groupby('id_tram'):
        exp = int((g.gio.max() - g.gio.min()).total_seconds() // 3600) + 1
        st[s] = dict(start=str(g.gio.min())[:16], end=str(g.gio.max())[:16], n=int(len(g)), expected=exp,
                     total=r(g.mua_mm.sum(), 1), max1h=r(g.mua_mm.max(), 1),
                     max1h_at=str(g.loc[g.mua_mm.idxmax(), 'gio'])[:16], wet_hours=int((g.mua_mm > 0).sum()),
                     tre_gt1=int((g.tre > 1).sum()))
    yagi_win = hourly[(hourly.ngay >= '2024-09-01') & (hourly.ngay <= '2024-09-15')]
    yd = yagi_win.groupby(['id_tram', 'ngay']).mua_mm.sum().reset_index()
    monthly_h = hourly.groupby(['id_tram', hourly.gio.dt.tz_localize(None).dt.to_period('M')]).mua_mm.sum().reset_index()
    monthly_h['gio'] = monthly_h.gio.astype(str)
    out['rain_hourly'] = dict(
        n=len(hourly), stations=st,
        yagi={s: dict(days=[str(d.date()) for d in g.ngay], mm=[r(v, 1) for v in g.mua_mm]) for s, g in yd.groupby('id_tram')},
        monthly={s: dict(m=g.gio.tolist(), mm=[r(v, 1) for v in g.mua_mm]) for s, g in monthly_h.groupby('id_tram')},
    )
    cum = pd.read_parquet(SRC / 'mua_tich_luy_truot.parquet')
    cd = cum.resample('D').max()
    peaks = cum['3 ngày'].resample('D').max().sort_values(ascending=False)
    ev, used = [], []
    for day, v in peaks.items():
        if any(abs((day - u).days) < 7 for u in used):
            continue
        used.append(day)
        ev.append(dict(date=str(day.date()), mm3d=r(v, 1), mm1d=r(cd.loc[day, '1 ngày'], 1), mm7d=r(cd.loc[day, '7 ngày'], 1)))
        if len(ev) == 10:
            break
    out['rain_cum'] = dict(
        n=len(cum), start=str(cum.index.min())[:16], end=str(cum.index.max())[:16], cols=list(cum.columns),
        na={c: int(cum[c].isna().sum()) for c in cum.columns},
        max={c: r(cum[c].max(), 1) for c in cum.columns},
        p99={c: r(cum[c].quantile(0.99), 1) for c in cum.columns},
        daily=dict(d=[str(x.date()) for x in cd.index], d1=[r(v, 1) for v in cd['1 ngày']],
                   d3=[r(v, 1) for v in cd['3 ngày']], d7=[r(v, 1) for v in cd['7 ngày']]),
        events=ev,
    )

    # ------------------------------------------------------------ 3D scene
    step = 1
    z = dem[::step, ::step]
    x0, y0 = xs[0], ys[-1]  # local origin (SW corner)
    sx_km = ((xs[::step] - x0) / 1000).round(4)
    sy_km = ((ys[::step] - y0) / 1000).round(4)

    def sample(xu, yu, arr=dem):
        c = np.clip(((np.asarray(xu) - xs[0]) / dm['sx']), 0, dm['w'] - 1)
        rr = np.clip(((ys[0] - np.asarray(yu)) / dm['sy']), 0, dm['h'] - 1)
        c0, r0 = np.floor(c).astype(int), np.floor(rr).astype(int)
        c1, r1 = np.minimum(c0 + 1, dm['w'] - 1), np.minimum(r0 + 1, dm['h'] - 1)
        fc, fr = c - c0, rr - r0
        q = [arr[r0, c0], arr[r0, c1], arr[r1, c0], arr[r1, c1]]
        val = (q[0] * (1 - fc) * (1 - fr) + q[1] * fc * (1 - fr) + q[2] * (1 - fc) * fr + q[3] * fc * fr)
        near = np.nanmean(np.stack(q), axis=0)
        return np.where(np.isfinite(val), val, near)

    def lines(gdf, offset=2.0, densify=15):
        X, Y, Z = [], [], []
        geoms = gdf.geometry.boundary if gdf.geom_type.str.contains('Polygon').any() else gdf.geometry
        for geom in geoms:
            if geom is None or geom.is_empty:
                continue
            geom = shapely.segmentize(geom, densify)
            parts = geom.geoms if hasattr(geom, 'geoms') else [geom]
            for part in parts:
                cx, cy = np.asarray(part.coords.xy)
                zz = sample(cx, cy) + offset
                X += ((cx - x0) / 1000).round(4).tolist() + [None]
                Y += ((cy - y0) / 1000).round(4).tolist() + [None]
                Z += [r(v, 1) for v in zz] + [None]
        return dict(x=X, y=Y, z=Z)

    bbox = shapely.box(xs[0], ys[-1], xs[-1], ys[0])
    main_roads = roads[roads.fclass.isin(['trunk', 'primary', 'secondary', 'tertiary', 'trunk_link', 'primary_link'])]
    minor_roads = roads[roads.fclass.isin(['residential', 'unclassified'])]
    water = gpd.read_file(SRC / 'nen_phuong_Yen_Bai.gpkg', layer='osm_water_a')
    rail = gpd.read_file(SRC / 'nen_phuong_Yen_Bai.gpkg', layer='osm_railways')
    pz = sample(pts_u.geometry.x, pts_u.geometry.y)
    xz = sample(xl_g.geometry.x, xl_g.geometry.y)
    yc = yg.geometry.centroid
    out['scene'] = dict(
        x=sx_km.tolist(), y=sy_km.tolist(),
        z=[[r(v, 1) for v in row] for row in z],
        slope=[[r(v, 1) for v in row] for row in slope[::step, ::step]],
        ward=lines(ward_u, 3),
        roads_main=lines(gpd.clip(main_roads, bbox), 2),
        roads_minor=lines(gpd.clip(minor_roads, bbox), 1.5, 30),
        rail=lines(gpd.clip(rail, bbox), 2),
        water=lines(gpd.clip(water, bbox), 1),
        faults=lines(gpd.clip(faults, bbox), 4),
        yagi=lines(yg, 1.5, 10),
        yagi_pts=dict(x=((yc.x - x0) / 1000).round(4).tolist(), y=((yc.y - y0) / 1000).round(4).tolist(),
                      z=[r(v + 3, 1) for v in sample(yc.x, yc.y)],
                      text=[f"{a.ma_vi_tri}<br>Diện tích: {a.dien_tich_m2:.0f} m²<br>Độ dốc TB: {a.do_doc:.1f}°<br>"
                            f"Tin cậy: {a.muc_tin_cay}<br>Ngày: {a.ngay_phat_sinh}<br>Mưa max 24h: {a.max_24h_mm} mm"
                            for a in yg.itertuples()],
                      area=yg.dien_tich_m2.tolist()),
        points=dict(x=((pts_u.geometry.x - x0) / 1000).round(4).tolist(), y=((pts_u.geometry.y - y0) / 1000).round(4).tolist(),
                    z=[r(v, 1) for v in pz], status=pts.trang_thai.tolist(),
                    text=[f"<b>{a.ma_vi_tri}</b> · {a.ten_diem}<br>{a.trang_thai} · {a.xa_cu}<br>Cao độ {a.cao_do_m} m · dốc {a.do_doc_do}°"
                          f"<br>Hướng dốc: {a.huong_doc_8} · {a.dc_nhom_da}<br>Số nhà 100 m: {a.so_nha_100m}"
                          + (f"<br>Thể tích: {a.the_tich_m3:.0f} m³" if pd.notna(a.the_tich_m3) else '')
                          for a in pts.itertuples()]),
        excel=dict(x=((xl_g.geometry.x - x0) / 1000).round(4).tolist(), y=((xl_g.geometry.y - y0) / 1000).round(4).tolist(),
                   z=[r(v, 1) for v in xz], matched=exact.tolist(),
                   text=[f"Excel id {a.id_diem_truot} · {a.ten_diem_truot}<br>{a.Ten_Xa_cu}"
                         + ('<br>Trùng toạ độ GPKG' if m else f'<br>Không trùng GPKG (cách {dd:.0f} m)')
                         for a, m, dd in zip(xl.itertuples(), exact, dmin)]),
        origin=[r(x0, 1), r(y0, 1)], zrange=[r(np.nanmin(dem)), r(np.nanmax(dem))],
        extent_km=[r(sx_km.max()), r(sy_km.max())],
    )

    out['model'] = model_section(x0, y0)

    payload = json.dumps(out, ensure_ascii=False, separators=(',', ':')).replace('NaN', 'null').replace('</', '<\\/')
    html = TEMPLATE.read_text(encoding='utf-8').replace('/*__DATA__*/null', payload)
    OUT.write_text(html, encoding='utf-8')
    print(f'Wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
