"""Write single-band GeoTIFFs on the DEM grid by copying its georeferencing tags (Pillow only)."""
from pathlib import Path

import numpy as np
from PIL import Image, TiffImagePlugin, TiffTags

GEO_TAGS = (33550, 33922, 34735, 34736, 34737)


def write_geotiff(path: Path, arr: np.ndarray, template: Path, nodata: float) -> None:
    t = Image.open(template).tag_v2
    ifd = TiffImagePlugin.ImageFileDirectory_v2()
    for tag in GEO_TAGS:
        if tag in t:
            ifd[tag] = t[tag]
            ifd.tagtype[tag] = t.tagtype[tag]
    ifd[42113] = str(int(nodata)) if float(nodata).is_integer() else str(nodata)
    ifd.tagtype[42113] = TiffTags.ASCII
    im = Image.fromarray(arr.astype(np.uint8), mode='L') if arr.dtype == np.uint8 else \
        Image.fromarray(arr.astype(np.float32), mode='F')
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    im.save(path, tiffinfo=ifd)
