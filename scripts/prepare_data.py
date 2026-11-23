#!/usr/bin/env python3
"""Generate static browser data from the supplied GeoTIFF and GeoPackages.
Requires Pillow; generated JSON is included with the application.
"""
import json, math, sqlite3, struct
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/du_lieu_phuong_Yen_Bai/du_lieu'
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

with sqlite3.connect(SOURCE / 'truot_lo_phuong_Yen_Bai.gpkg') as db:
    db.row_factory = sqlite3.Row
    fields = ['ma_vi_tri', 'trang_thai', 'con_nguy_co', 'nhom_vi_tri', 'do_tin_cay_vi_tri', 'lon_wgs84', 'lat_wgs84', 'thon_ban', 'ten_diem', 'mo_ta', 'xa_cu', 'nguon', 'cao_do_m', 'do_doc_do', 'mua_tb_nam_mm', 'thoi_gian_xay_ra', 'kieu_truot', 'thiet_hai', 'nguy_co_truot_tiep', 'co_cap_trung_can_ra_soat']
    points = [dict(row) for row in db.execute('SELECT ' + ','.join('"'+f+'"' for f in fields) + ' FROM truot_lo_phuong_Yen_Bai')]

layers={'roads':[], 'waterways':[], 'water':[], 'buildings':[]}
with sqlite3.connect(SOURCE / 'nen_phuong_Yen_Bai.gpkg') as db:
    for key,table in [('roads','osm_roads'),('waterways','osm_waterways'),('water','osm_water_a'),('buildings','osm_buildings_a')]:
        for geom,kind,name in db.execute(f'SELECT geom,fclass,name FROM {table} WHERE geom IS NOT NULL'):
            shape=wkb_geometry(geom)
            if key in ('roads','waterways'):
                coords=convert_line(shape)
                if sum(p is not None for p in coords)>=2: layers[key].append({'coords':coords,'kind':kind,'name':name})
            else:
                if not shape: continue
                ring=convert_line(shape[0])
                # A polygon must have a complete footprint on the DEM; do not invent outside terrain.
                if len(ring)>=4 and all(p is not None for p in ring): layers[key].append({'coords':ring,'kind':kind,'name':name})
result = {'terrain': {'width': len(xs), 'height': len(ys), 'west': west, 'north': north, 'east': east, 'south': south, 'heights': heights}, 'points': points, 'layers':layers}
out = ROOT / 'web/assets/data.json'
out.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
print(f'Wrote {len(points)} points, terrain {len(xs)} x {len(ys)}, layers:', {k:len(v) for k,v in layers.items()})
