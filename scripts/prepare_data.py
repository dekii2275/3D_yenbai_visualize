#!/usr/bin/env python3
"""Generate static browser data from the supplied GeoTIFF and GeoPackages.
Requires Pillow; generated JSON is included with the application.
"""
import json, math, sqlite3, struct
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = next((p for p in [ROOT / 'data/du_lieu_phuong_Yen_Bai/du_lieu', ROOT / 'data/du_lieu'] if p.exists()), ROOT / 'data/du_lieu')
image = Image.open(SOURCE / 'DEM_30m_phuong_Yen_Bai_WGS84.tif')
width, height = image.size
sx, sy, _ = image.tag_v2[33550]
_, _, _, west, north, _ = image.tag_v2[33922]
nodata = float(image.tag_v2.get(42113, '-32768'))
step = 2
xs = list(range(0, width, step)); ys = list(range(0, height, step))
if xs[-1] != width - 1: xs.append(width - 1)
if ys[-1] != height - 1: ys.append(height - 1)
pixels = image.load()
heights = [[round(float(pixels[x, y]), 2) if float(pixels[x, y]) != nodata else None for x in xs] for y in ys]
west += sx/2; north -= sy/2
east = west + sx*(width - 1); south = north - sy*(height - 1)

def height_at(lon, lat):
    x = round((lon-west)/sx); y = round((north-lat)/sy)
    if x < 0 or y < 0 or x >= width or y >= height: return None
    value = float(pixels[x, y])
    return None if value == nodata else round(value, 1)

def utm48_to_lonlat(x, y):
    # WGS84 / UTM zone 48N (EPSG:32648), inverse transverse Mercator.
    a=6378137.0; e2=0.0066943799901413165; k=0.9996
    e1=(1-math.sqrt(1-e2))/(1+math.sqrt(1-e2)); ep=e2/(1-e2)
    m=y/k; mu=m/(a*(1-e2/4-3*e2**2/64-5*e2**3/256))
    p=mu+(3*e1/2-27*e1**3/32)*math.sin(2*mu)+(21*e1**2/16-55*e1**4/32)*math.sin(4*mu)+(151*e1**3/96)*math.sin(6*mu)+(1097*e1**4/512)*math.sin(8*mu)
    n=a/math.sqrt(1-e2*math.sin(p)**2); r=a*(1-e2)/(1-e2*math.sin(p)**2)**1.5
    t=math.tan(p)**2; c=ep*math.cos(p)**2; d=(x-500000)/(n*k)
    lat=p-(n*math.tan(p)/r)*(d*d/2-(5+3*t+10*c-4*c*c-9*ep)*d**4/24+(61+90*t+298*c+45*t*t-252*ep-3*c*c)*d**6/720)
    lon=math.radians(105)+(d-(1+2*t+c)*d**3/6+(5-2*c+28*t-3*c*c+8*ep+24*t*t)*d**5/120)/math.cos(p)
    return round(math.degrees(lon),7), round(math.degrees(lat),7)

def wkb_geometry(blob):
    # GeoPackage binary header followed by standard WKB (2D geometries here).
    offset = 8 + {0:0,1:32,2:48,3:48,4:64}[(blob[3] >> 1) & 7]
    def parse(pos):
        endian = '<' if blob[pos] == 1 else '>'; pos += 1
        typ = struct.unpack_from(endian+'I',blob,pos)[0]; pos += 4
        def uint():
            nonlocal pos
            v=struct.unpack_from(endian+'I',blob,pos)[0]; pos+=4; return v
        def point():
            nonlocal pos
            p=struct.unpack_from(endian+'dd',blob,pos); pos+=16; return p
        if typ == 1: return point(),pos
        if typ == 2: return [point() for _ in range(uint())],pos
        if typ == 3: return [[point() for _ in range(uint())] for _ in range(uint())],pos
        if typ in (4,5,6,7):
            items=[]
            for _ in range(uint()):
                item,pos=parse(pos); items.append(item)
            return items,pos
        raise ValueError(f'Unsupported WKB type {typ}')
    return parse(offset)[0]

def convert_line(line):
    out=[]
    for x,y in line:
        lon,lat=utm48_to_lonlat(x,y); h=height_at(lon,lat)
        out.append([lon,lat,h] if h is not None else None)
    return out

def convert_ring(line):
    # Like convert_line, but keeps lon/lat outside the DEM (height None) so water can be painted to the edge.
    out=[]
    for x,y in line:
        lon,lat=utm48_to_lonlat(x,y); out.append([lon,lat,height_at(lon,lat)])
    return out

with sqlite3.connect(SOURCE / 'truot_lo_phuong_Yen_Bai.gpkg') as db:
    db.row_factory = sqlite3.Row
    fields = ['ma_vi_tri', 'trang_thai', 'con_nguy_co', 'nhom_vi_tri', 'do_tin_cay_vi_tri', 'lon_wgs84', 'lat_wgs84', 'thon_ban', 'ten_diem', 'mo_ta', 'xa_cu', 'nguon', 'cao_do_m', 'do_doc_do', 'mua_tb_nam_mm', 'thoi_gian_xay_ra', 'kieu_truot', 'thiet_hai', 'nguy_co_truot_tiep', 'co_cap_trung_can_ra_soat']
    points = [dict(row) for row in db.execute('SELECT ' + ','.join('"'+f+'"' for f in fields) + ' FROM truot_lo_phuong_Yen_Bai')]

layers={'roads':[], 'waterways':[], 'water':[], 'buildings':[]}
with sqlite3.connect(SOURCE / 'nen_phuong_Yen_Bai.gpkg') as db:
    for key,table in [('roads','osm_roads'),('waterways','osm_waterways'),('water','osm_water_a'),('buildings','osm_buildings_a')]:
        for geom,kind,name in db.execute(f'SELECT geom,fclass,name FROM {table} WHERE geom IS NOT NULL'):
            shape=wkb_geometry(geom)
            if key=='waterways':
                coords=convert_ring(shape)
                if sum(p[2] is not None for p in coords)>=2: layers[key].append({'coords':coords,'kind':kind,'name':name})
            elif key=='roads':
                coords=convert_line(shape)
                if sum(p is not None for p in coords)>=2: layers[key].append({'coords':coords,'kind':kind,'name':name})
            elif key=='water':
                # Rivers and lakes often cross the ward boundary. Keep every polygon that touches the DEM,
                # storing lon/lat for all vertices (height null outside the DEM) plus any holes (islands).
                if not shape: continue
                polys=shape if isinstance(shape[0][0][0],(list,tuple)) else [shape]
                for poly in polys:
                    rings=[convert_ring(r) for r in poly]
                    if len(rings[0])>=4 and any(p[2] is not None for p in rings[0]):
                        layers[key].append({'coords':rings[0],'holes':rings[1:],'kind':kind,'name':name})
            else:
                if not shape: continue
                ring=convert_line(shape[0])
                # A building must have a complete footprint on the DEM; do not invent outside terrain.
                if len(ring)>=4 and all(p is not None for p in ring): layers[key].append({'coords':ring,'kind':kind,'name':name})
# ---- Extra context layers (lon/lat; heights only where on the DEM) ----
def r6(v): return round(v,6)
def ll(pt, utm=True):
    lon,lat = utm48_to_lonlat(*pt) if utm else pt
    return [r6(lon), r6(lat)]
def llh(pt, utm=True):
    lon,lat = ll(pt, utm); return [lon, lat, height_at(lon, lat)]
def as_polys(shape): return shape if isinstance(shape[0][0][0], (list, tuple)) else [shape]
def as_lines(shape): return shape if isinstance(shape[0][0], (list, tuple)) else [shape]
POI_GROUPS = {'hospital':'y_te','clinic':'y_te','doctors':'y_te','pharmacy':'y_te',
              'school':'giao_duc','college':'giao_duc','kindergarten':'giao_duc','university':'giao_duc',
              'police':'hanh_chinh','townhall':'hanh_chinh','community_centre':'hanh_chinh','fire_station':'hanh_chinh',
              'stadium':'cong_cong','museum':'cong_cong','library':'cong_cong','mall':'cong_cong','supermarket':'cong_cong','marketplace':'cong_cong'}
extra = {'geology':[], 'faults':[], 'railways':[], 'places':[], 'pois':[], 'yagi':[], 'ward':None}
with sqlite3.connect(SOURCE / 'nen_phuong_Yen_Bai.gpkg') as db:
    for geom, unit, group, litho in db.execute('SELECT geom, ten_don_vi, nhom_da, thach_hoc FROM dia_chat'):
        for poly in as_polys(wkb_geometry(geom)):
            extra['geology'].append({'rings':[[ll(p) for p in r] for r in poly], 'unit':unit, 'group':group, 'litho':litho})
    for geom, kind in db.execute('SELECT geom, kieu_dut_gay FROM dut_gay'):
        for line in as_lines(wkb_geometry(geom)):
            extra['faults'].append({'coords':[ll(p) for p in line], 'kind':kind})
    for geom, name in db.execute('SELECT geom, name FROM osm_railways'):
        for line in as_lines(wkb_geometry(geom)):
            c=[llh(p) for p in line]
            if any(q[2] is not None for q in c): extra['railways'].append({'coords':c, 'name':name})
    for geom, kind, name in db.execute('SELECT geom, fclass, name FROM osm_places'):
        lon,lat = ll(wkb_geometry(geom)); extra['places'].append({'lon':lon,'lat':lat,'h':height_at(lon,lat),'kind':kind,'name':name})
    for table in ('osm_pois','osm_pois_a'):
        for geom, kind, name in db.execute(f'SELECT geom, fclass, name FROM {table}'):
            if kind not in POI_GROUPS: continue
            shape = wkb_geometry(geom)
            if table == 'osm_pois': lon,lat = ll(shape)
            else:
                ring = as_polys(shape)[0][0]; pts=[ll(p) for p in ring]
                lon = r6(sum(p[0] for p in pts)/len(pts)); lat = r6(sum(p[1] for p in pts)/len(pts))
            h = height_at(lon,lat)
            if h is not None: extra['pois'].append({'lon':lon,'lat':lat,'h':h,'kind':kind,'group':POI_GROUPS[kind],'name':name})
with sqlite3.connect(SOURCE / 'vet_truot_ve_tinh_Yagi_trong_phuong.gpkg') as db:
    q = 'SELECT geom, ma_vi_tri, dien_tich_m2, do_doc, muc_tin_cay, max_24h_mm, max_72h_mm, ngay_phat_sinh, lon, lat FROM vet_truot_ve_tinh_Yagi_trong_phuong'
    for geom, code, area, slope, conf, r24, r72, day, lon, lat in db.execute(q):
        poly = as_polys(wkb_geometry(geom))[0]
        extra['yagi'].append({'rings':[[ll(p) for p in r] for r in poly], 'code':code, 'area':area, 'slope':round(slope,1) if slope is not None else None,
                              'conf':conf, 'r24':r24, 'r72':r72, 'day':day, 'lon':r6(lon), 'lat':r6(lat)})
with sqlite3.connect(SOURCE / 'ranh_gioi_phuong_Yen_Bai.gpkg') as db:
    geom, name, merged, kind, area, pop, dens, prov = db.execute('SELECT geom, ten_xa, sap_nhap, loai, dtich_km2, dan_so, matdo_km2, ten_tinh FROM ranh_gioi_phuong_Yen_Bai').fetchone()
    poly = as_polys(wkb_geometry(geom))[0]
    extra['ward'] = {'name':name, 'merged':merged, 'kind':kind, 'area_km2':area, 'population':pop, 'density':dens, 'province':prov,
                     'outline':[ll(p, utm=False) for p in poly[0]]}
layers.update(extra)
result = {'terrain': {'width': len(xs), 'height': len(ys), 'west': west, 'north': north, 'east': east, 'south': south, 'heights': heights}, 'points': points, 'layers':layers}
out = ROOT / 'web/assets/data.json'
out.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
print(f'Wrote {len(points)} points, terrain {len(xs)} x {len(ys)}, layers:', {k:len(v) for k,v in layers.items()})
