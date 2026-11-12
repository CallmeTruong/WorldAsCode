"""Trusted, bounded CC0 material resolver. Never available to generated code."""
import base64
import hashlib
import json
import re
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
import httpx
from PIL import Image
from ..provider import write_json


def material_assets(run: Path):
    dest=run/'textures';dest.mkdir(exist_ok=True)
    # Physical surfaces, independent of artistic style; source can select a slot
    # per mesh via material.userData.textureRole. No whole-building override.
    specs=[('road','asphalt_02',6),('pavement','rectangular_paving',3),
           ('plaster','white_plaster_02',3),('roof_tile','clay_roof_tiles',2),('stone','granite_tile',2),('brick','red_brick_03',2)]
    requests=run/'surface-requests.json'
    if requests.exists():
        chosen={role:(asset,meters) for role,asset,meters in specs}
        for role,item in json.loads(requests.read_text(encoding='utf-8')).items():
            asset=item.get('asset_id');meters=item.get('physical_tile_m')
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,40}',role) or not isinstance(asset,str) or not re.fullmatch(r'[a-z0-9_]{1,80}',asset):raise ValueError('SURFACE_ASSET_ID')
            if not isinstance(meters,(int,float)) or not .1<=meters<=100:raise ValueError('SURFACE_METRIC_SCALE')
            chosen[role]=(asset,meters)
        specs=[(role,asset,meters) for role,(asset,meters) in chosen.items()]
    result={}
    with httpx.Client(timeout=45,headers={'User-Agent':'WorldAsCodeResearch/0.1'},follow_redirects=True) as client:
        for role,asset,meters in specs:
            metadata=client.get('https://api.polyhaven.com/files/'+asset);metadata.raise_for_status()
            info=metadata.json();entry={'id':asset,'license':'CC0','source':'https://polyhaven.com/a/'+asset,'physical_tile_m':meters,'maps':{},'selection':'per-run surface request' if requests.exists() else 'fallback registry; not location-specific'}
            for semantic,keys in [('color',['Diffuse','diff']),('normal',['nor_gl']),('roughness',['Rough','rough_ao','rough'])]:
                key=next((k for k in keys if k in info),None)
                if key is None:continue
                versions=info[key].get('1k',{});record=versions.get('jpg') or versions.get('png')
                if not record:continue
                url=record['url']
                if urlparse(url).hostname!='dl.polyhaven.org' or record.get('size',0)>12_000_000:
                    raise ValueError('UNTRUSTED_OR_LARGE_TEXTURE')
                path=dest/f'{role}-{asset}-{semantic}.jpg'
                if not path.exists():
                    response=client.get(url);response.raise_for_status()
                    if len(response.content)>12_000_000:raise ValueError('TEXTURE_BYTE_BUDGET')
                    source=response.content
                    if record.get('md5') and hashlib.md5(source).hexdigest()!=record['md5']:
                        raise ValueError('TEXTURE_CHECKSUM_MISMATCH')
                    with Image.open(BytesIO(source)) as im:
                        if im.width*im.height>4_000_000:raise ValueError('TEXTURE_PIXEL_BUDGET')
                        im.convert('RGB').save(path,quality=92)
                entry['maps'][semantic]={'file':str(path.relative_to(run)).replace('\\','/'),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'color_space':'srgb' if semantic=='color' else 'linear','format':'jpg','semantic':semantic}
            result[role]=entry
    write_json(run/'asset-manifest.json',result)
    return result


def browser_assets(run: Path,manifest):
    data={}
    for role,entry in manifest.items():
        data[role]={'physical_tile_m':entry['physical_tile_m'],'maps':{}}
        for semantic,item in entry['maps'].items():
            path=(run/item['file']).resolve()
            if not path.is_relative_to(run.resolve()):raise ValueError('ASSET_PATH_ESCAPE')
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('ASSET_CHANGED_AFTER_VALIDATION')
            data[role]['maps'][semantic]='data:image/jpeg;base64,'+base64.b64encode(raw).decode()
    return data
