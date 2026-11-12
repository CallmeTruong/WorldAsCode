"""Measured rendering probe for replicas of one actual generated asset."""

import json
import time
from pathlib import Path

from .artifacts import file_hash, write_json
from .browser import bundle, capture, serve
from .config import ROOT


def probe(source_run, out, count=9, batched=True):
    source_run,out=Path(source_run).resolve(),Path(out).resolve()
    if out.exists():
        raise ValueError('USE_NEW_PROBE_DIRECTORY')
    out.mkdir(parents=True)
    result=json.loads((source_run/'result.json').read_text(encoding='utf-8'))
    attempt=source_run/f"attempt-{result['best_attempt']}"
    kit=source_run/'kit-versions/base/kit.mjs'
    site=json.loads((source_run/'site.json').read_text(encoding='utf-8'))
    style=json.loads((source_run/'style.json').read_text(encoding='utf-8'))
    script=out/'factory.ts'
    imports={'kit':kit,'design':attempt/'design.mjs','batch':ROOT/'runtime/batching.mjs'}
    code='import * as THREE from "three";\n'+f"import {{buildDesign}} from {json.dumps(imports['kit'].as_posix())};\nimport {{design}} from {json.dumps(imports['design'].as_posix())};\nimport {{batchStaticAssets}} from {json.dumps(imports['batch'].as_posix())};\n"
    code+='export function createProbe(options: ProceduralModelOptions = {}) {\n'
    code+=f'const prototype=buildDesign(design,{json.dumps(site)},{json.dumps(style)});\n'
    code+=f'const count={count},batched={str(batched).lower()};\n'
    code+='const size=new THREE.Box3().setFromObject(prototype).getSize(new THREE.Vector3()),columns=Math.ceil(Math.sqrt(count));\n'
    code+='const placements=Array.from({length:count},(_,i)=>({id:"asset-"+i,position:[(i%columns)*(size.x+12),0,Math.floor(i/columns)*(size.z+12)]}));\n'
    code+='if(batched)return batchStaticAssets(prototype,placements);\n'
    code+='const root=new THREE.Group(),metadata=prototype.userData;root.userData.look={...(metadata.look??{})};prototype.userData={};for(const p of placements){const instance=prototype.clone(true);instance.name=p.id;instance.position.set(...p.position);root.add(instance);}prototype.userData=metadata;return root;\n}'
    script.write_text(code,encoding='utf-8')
    write_json(out/'input-manifest.json',{'source_run':str(source_run),'design_sha256':file_hash(attempt/'design.mjs'),
        'kit_sha256':file_hash(kit),'count':count,'batched':batched,
        'scope':'Replicated static asset on software WebGL; not distinct real buildings, FPS or urban streaming benchmark.'})
    started=time.monotonic()
    bundle(out,native=script)
    report=capture(out,review_only=True,export_geometry=False)
    metrics={'passed':report['passed'],'count':count,'batched':batched,'elapsed_seconds':round(time.monotonic()-started,2),
             'performance':report.get('manifest',{}).get('performance'),
             'triangles':report.get('manifest',{}).get('triangles'),'bounds':report.get('manifest',{}).get('bounds'),
             'state_preserves_geometry':report.get('state_preserves_geometry'),'runtime_error':report.get('runtime_error')}
    write_json(out/'result.json',metrics)
    return metrics


def frame_probe(folder):
    """Synchronous warmed frames on software WebGL, excluding startup/export."""
    from playwright.sync_api import sync_playwright

    folder=Path(folder)
    with serve(folder) as url,sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--use-angle=swiftshader','--enable-webgl'])
        page=browser.new_page(viewport={'width':1100,'height':900})
        page.goto(url)
        page.wait_for_function('() => window.worldscaleReady === true',timeout=60000)
        report=page.evaluate('''() => {
          worldscale.renderer.setAnimationLoop(null);
          const gl=worldscale.renderer.getContext(),samples=[];
          for(let i=0;i<11;i++){const start=performance.now();worldscale.view(215+i*.2,32);gl.finish();if(i>=3)samples.push(performance.now()-start);}
          return {milliseconds:samples,drawCalls:worldscale.renderer.info.render.calls,
            contextLost:gl.isContextLost(),glError:gl.getError(),triangles:worldscale.renderer.info.render.triangles,
            renderer:gl.getParameter(gl.RENDERER),scope:'Eight warmed synchronized software-WebGL frames, not end-user hardware FPS.'};
        }''')
        browser.close()
    report['mean_ms']=round(sum(report['milliseconds'])/len(report['milliseconds']),2)
    report['valid']=not report['contextLost'] and report['glError']==0 and report['triangles']>0
    write_json(folder/'frame-times.json',report)
    return report


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-run',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--count',type=int,default=9)
    parser.add_argument('--unbatched',action='store_true')
    args=parser.parse_args()
    if not 1<=args.count<=25:
        parser.error('count must be 1..25')
    print(json.dumps(probe(args.source_run,args.out,args.count,not args.unbatched)))
