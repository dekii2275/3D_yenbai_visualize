"""Feature rasters and masks on the 30 m UTM DEM grid."""
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
from PIL import Image
from scipy import ndimage

UTM = 'EPSG:32648'
NEN = 'nen_phuong_Yen_Bai.gpkg'
DEM_FILE = 'DEM_30m_phuong_Yen_Bai_UTM48N.tif'

FEATURES = ['cao_do', 'do_doc', 'sin_huong', 'cos_huong', 'bien_do_300m', 'do_cong', 'tpi_330m',
            'kc_duong_m', 'kc_nuoc_m', 'kc_dut_gay_m', 'mat_do_nha_150m',
            'da_bien_chat', 'da_tram_tich_de_tu', 'da_carbonat', 'da_khac']
# Attributes of the Yagi scars themselves: never usable as predictors (label leakage).
FORBIDDEN = ['max_24h_mm', 'max_72h_mm', 'rdNDVI', 'dBSI', 'dS1_dB', 'dcoh', 'coh_truoc', 'diem_tb',
             'so_pixel', 'cap_mua']
ROCK = {'Đá biến chất': 'da_bien_chat', 'Trầm tích bở rời Đệ Tứ': 'da_tram_tich_de_tu', 'Đá carbonat': 'da_carbonat'}


@dataclass
class Grid:
    dem: np.ndarray
    west: float
    north: float
    cell: float
    xs: np.ndarray  # cell-centre eastings
    ys: np.ndarray  # cell-centre northings (descending)

    @property
    def shape(self):
        return self.dem.shape


def read_raster(path: Path) -> np.ndarray:
    im = Image.open(path)
    a = np.array(im, dtype=float)
    nd = im.tag_v2.get(42113)
    if nd is not None:
        a[a == float(nd)] = np.nan
    return a


def load_grid(src: Path) -> Grid:
    im = Image.open(Path(src) / DEM_FILE)
    t = im.tag_v2
    cell = float(t[33550][0])
    west, north = float(t[33922][3]), float(t[33922][4])
    dem = read_raster(Path(src) / DEM_FILE)
    h, w = dem.shape
    return Grid(dem=dem, west=west, north=north, cell=cell,
                xs=west + cell * (np.arange(w) + 0.5), ys=north - cell * (np.arange(h) + 0.5))


def _mark_xy(grid: Grid, mask: np.ndarray, x, y) -> None:
    c = np.floor((np.asarray(x) - grid.west) / grid.cell).astype(int)
    r = np.floor((grid.north - np.asarray(y)) / grid.cell).astype(int)
    ok = (r >= 0) & (c >= 0) & (r < grid.shape[0]) & (c < grid.shape[1])
    mask[r[ok], c[ok]] = True


def cells_from_geoms(grid: Grid, geoms, step_m: float = 10) -> np.ndarray:
    """Cells touched by geometries: polygons by cell centre inside or centroid cell; lines by densified vertices."""
    mask = np.zeros(grid.shape, bool)
    for geom in geoms:
        if geom is None or geom.is_empty:
            continue
        if geom.geom_type in ('Polygon', 'MultiPolygon'):
            x0, y0, x1, y1 = geom.bounds
            cs = np.where((grid.xs >= x0) & (grid.xs <= x1))[0]
            rs = np.where((grid.ys >= y0) & (grid.ys <= y1))[0]
            if cs.size and rs.size:
                X, Y = np.meshgrid(grid.xs[cs], grid.ys[rs])
                inside = shapely.contains_xy(geom, X, Y)
                mask[np.ix_(rs, cs)] |= inside
            c = geom.centroid
            _mark_xy(grid, mask, [c.x], [c.y])
        else:
            try:
                dense = shapely.segmentize(geom, step_m)
            except shapely.errors.GEOSException:  # degenerate (single-point) line in OSM
                dense = geom
            xy = shapely.get_coordinates(dense)
            _mark_xy(grid, mask, xy[:, 0], xy[:, 1])
    return mask


def distance_m(mask: np.ndarray, cell: float) -> np.ndarray:
    if not mask.any():
        return np.full(mask.shape, np.inf)
    return ndimage.distance_transform_edt(~mask) * cell


def tpi(dem: np.ndarray, size: int) -> np.ndarray:
    ok = np.isfinite(dem)
    num = ndimage.uniform_filter(np.where(ok, dem, 0.0), size=size, mode='nearest')
    den = ndimage.uniform_filter(ok.astype(float), size=size, mode='nearest')
    with np.errstate(invalid='ignore', divide='ignore'):
        return dem - num / den


def curvature(dem: np.ndarray, cell: float) -> np.ndarray:
    """Negative Laplacian (1/m): positive on convex crests, negative in hollows."""
    p = np.pad(dem, 1, mode='edge')
    lap = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:] - 4 * dem) / cell ** 2
    return -lap


def _layer(src: Path, name: str, file: str = NEN) -> gpd.GeoDataFrame:
    g = gpd.read_file(Path(src) / file, layer=name)
    return g.to_crs(UTM) if g.crs and g.crs.to_epsg() != 32648 else g


def feature_stack(src: Path, grid: Grid) -> dict:
    src = Path(src)
    slope = read_raster(src / 'do_doc_do_UTM48N.tif')
    aspect = read_raster(src / 'huong_doc_do_UTM48N.tif')
    relief = read_raster(src / 'bien_do_dia_hinh_300m_UTM48N.tif')
    flat = ~np.isfinite(aspect) | (aspect < 0)
    rad = np.radians(np.where(flat, 0, aspect))
    roads = cells_from_geoms(grid, _layer(src, 'osm_roads').geometry)
    water = (cells_from_geoms(grid, _layer(src, 'osm_waterways').geometry)
             | cells_from_geoms(grid, _layer(src, 'osm_water_a').geometry))
    faults = cells_from_geoms(grid, _layer(src, 'dut_gay').geometry)
    counts = np.zeros(grid.shape)
    cen = _layer(src, 'osm_buildings_a').geometry.centroid
    c = np.floor((cen.x.values - grid.west) / grid.cell).astype(int)
    r = np.floor((grid.north - cen.y.values) / grid.cell).astype(int)
    ok = (r >= 0) & (c >= 0) & (r < grid.shape[0]) & (c < grid.shape[1])
    np.add.at(counts, (r[ok], c[ok]), 1)
    k = int(round(150 / grid.cell))
    yy, xx = np.mgrid[-k:k + 1, -k:k + 1]
    disk = (xx ** 2 + yy ** 2 <= k ** 2).astype(float)
    density = ndimage.convolve(counts, disk, mode='constant')
    feats = {
        'cao_do': grid.dem, 'do_doc': slope,
        'sin_huong': np.where(flat, 0.0, np.sin(rad)), 'cos_huong': np.where(flat, 0.0, np.cos(rad)),
        'bien_do_300m': relief, 'do_cong': curvature(grid.dem, grid.cell) * 1000, 'tpi_330m': tpi(grid.dem, 11),
        'kc_duong_m': distance_m(roads, grid.cell), 'kc_nuoc_m': distance_m(water, grid.cell),
        'kc_dut_gay_m': distance_m(faults, grid.cell), 'mat_do_nha_150m': density,
    }
    geo = _layer(src, 'dia_chat')
    rock = {v: np.zeros(grid.shape) for v in ROCK.values()}
    covered = np.zeros(grid.shape, bool)
    for nhom, gdf in geo.groupby('nhom_da'):
        m = cells_from_geoms(grid, gdf.geometry) & ~covered
        covered |= m
        if nhom in ROCK:
            rock[ROCK[nhom]][m] = 1.0
    other = np.ones(grid.shape)
    for v in rock.values():
        other -= v
    feats.update(rock)
    feats['da_khac'] = np.clip(other, 0, 1)
    return {k: feats[k] for k in FEATURES}


def masks(src: Path, grid: Grid, feats: dict | None = None) -> dict:
    src = Path(src)
    scars = _layer(src, 'vet_truot_ve_tinh_Yagi')
    positive = cells_from_geoms(grid, scars.geometry)
    wa = _layer(src, 'osm_water_a')
    water = cells_from_geoms(grid, wa[wa.fclass.isin(['riverbank', 'water'])].geometry)
    valid = np.isfinite(grid.dem) & ~water
    if feats is not None:
        for a in feats.values():
            valid &= np.isfinite(a)
    wards = gpd.read_file(src / 'xa_Lao_Cai.gpkg').to_crs(UTM)
    box = shapely.box(grid.xs[0], grid.ys[-1], grid.xs[-1], grid.ys[0])
    ward = np.full(grid.shape, '', dtype=object)
    X, Y = np.meshgrid(grid.xs, grid.ys)
    for w in wards[wards.intersects(box)].itertuples():
        ward[shapely.contains_xy(w.geometry, X, Y)] = w.ten_xa
    return {'positive': positive, 'water': water, 'valid': valid, 'ward': ward}
