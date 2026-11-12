import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import psutil
from ..config import ROOT
from ..provider import write_json
from ..runtime import validate_source,kill_tree


def height_within_evidence(building,actual):
    envelope=building.get('height_envelope_m')
    if envelope is not None:
        if not isinstance(envelope,list) or len(envelope)!=2 or not 3<=envelope[0]<=envelope[1]<=500:raise ValueError('INVALID_HEIGHT_ENVELOPE')
        return envelope[0]-max(2,envelope[0]*.1)<=actual<=envelope[1]+max(2,envelope[1]*.1)
    return abs(actual-building['height'])<=max(5,building['height']*.15)


def capture_city(run:Path,timeout=240,memory_mb=3500):
    run=run.resolve();source=run/'building-generator.ts';validate_source(source.read_text(encoding='utf-8'))
    env={k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA','PLAYWRIGHT_BROWSERS_PATH','COMSPEC'}}
    env['PYTHONPATH']=str(ROOT/'src')
    with (run/'urban-runtime.log').open('w',encoding='utf-8') as log:
        child=subprocess.Popen([sys.executable,'-m','building_workflow.urban.runtime',str(run)],cwd=ROOT,env=env,stdout=log,stderr=log)
        started=time.monotonic();peak=0
        try:
            while child.poll() is None:
                if time.monotonic()-started>timeout:raise RuntimeError('URBAN_RUNTIME_TIMEOUT')
                try:
                    p=psutil.Process(child.pid);rss=sum(q.memory_info().rss for q in [p]+p.children(recursive=True) if q.is_running());peak=max(peak,rss)
                    if rss>memory_mb*1024**2:raise RuntimeError('URBAN_MEMORY_LIMIT')
                except (psutil.NoSuchProcess,psutil.AccessDenied):pass
                time.sleep(.15)
        finally:
            if child.poll() is None:kill_tree(child)
            child.wait()
        write_json(run/'urban-runtime-resources.json',{'seconds':time.monotonic()-started,'peak_process_tree_rss_mb':peak/1024**2,
            'memory_limit_mb':memory_mb,'timeout_seconds':timeout})
    output=run/'urban-runtime-result.json'
    if child.returncode or not output.exists():raise RuntimeError('URBAN_RUNTIME_FAILED_SEE_LOG')
    data=json.loads(output.read_text(encoding='utf-8'))
    if not data.get('ok'):raise RuntimeError(data.get('error','URBAN_RUNTIME_FAILED'))
    return data


def child(run:Path):
    from playwright.sync_api import sync_playwright
    from ..skills import geometry_gate
    from .assets import browser_assets
    from .style import NEUTRAL,canonical_hash
    try:
        source=run/'building-generator.ts'
        cmd=['node',str(ROOT/'node_modules/typescript/bin/tsc'),'--noEmit','--skipLibCheck','--moduleResolution','bundler','--module','esnext','--target','es2022',str(source)]
        check=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=25)
        (run/'urban-compile.log').write_text(check.stdout+check.stderr,encoding='utf-8')
        if check.returncode:raise RuntimeError('URBAN_TYPESCRIPT_FAILED')
        for mode in ['worker','viewer']:
            check=subprocess.run(['node',str(ROOT/'runtime/urban-bundle.mjs'),mode,str(source),str(run/f'urban-{mode}.js')],cwd=ROOT,capture_output=True,text=True,timeout=20)
            if check.returncode:
                (run/'urban-bundle.log').write_text(check.stdout+check.stderr,encoding='utf-8');raise RuntimeError('URBAN_BUNDLE_FAILED')
        city=json.loads((run/'city.json').read_text(encoding='utf-8'))
        streets_path=run/'streetscape.json'
        options={**(json.loads(streets_path.read_text()) if streets_path.exists() else {}),**city.get('streetscape',{})}
        if options:
            from .streetscape import decorate_streets
            context_path=run/'context-data/city.json'
            context=json.loads(context_path.read_text(encoding='utf-8')) if context_path.exists() else city
            city=decorate_streets(city,options,context)
            write_json(run/'streetscape-audit.json',city['streetscape_audit'])
        if (run/'scene-contract.json').exists():city['scene_mode']=True
        if (run/'mesh-height-evidence.json').exists():
            from .scene import apply_mesh_height_evidence
            evidence=json.loads((run/'mesh-height-evidence.json').read_text(encoding='utf-8'))
            write_json(run/'mesh-height-checks.json',apply_mesh_height_evidence(city,evidence))
            write_json(run/'city.json',city)
        ground_path=run/'ground-observation/ground-observations.json'
        if ground_path.exists():
            from .ground import apply_ground_observations
            observation=json.loads(ground_path.read_text(encoding='utf-8'))
            write_json(run/'ground-checks.json',apply_ground_observations(city,observation))
            write_json(run/'city.json',city)
        profile=json.loads((run/'style-profile.json').read_text(encoding='utf-8'))
        assets=browser_assets(run,json.loads((run/'asset-manifest.json').read_text(encoding='utf-8')))
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,chromium_sandbox=True)
            ctx=browser.new_context(viewport={'width':1440,'height':1080},service_workers='block',accept_downloads=False)
            denied=[]
            def deny(route):denied.append(route.request.url.split(':',1)[0]);route.abort()
            ctx.route('**/*',deny)
            page=ctx.new_page();page.set_default_timeout(90000)
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            csp="default-src 'none'; script-src 'unsafe-inline' blob:; worker-src blob:; connect-src 'none'; img-src data:; style-src 'unsafe-inline'"
            page.set_content(f'<meta http-equiv="Content-Security-Policy" content="{csp}"><body></body>')
            result=page.evaluate("""({code,city})=>new Promise((resolve,reject)=>{
                const worker=new Worker(URL.createObjectURL(new Blob([code],{type:'text/javascript'})));
                const timer=setTimeout(()=>{worker.terminate();reject(Error('CITY_WORKER_TIMEOUT'));},30000);
                worker.onmessage=e=>{clearTimeout(timer);worker.terminate();resolve(e.data)};
                worker.onerror=e=>{clearTimeout(timer);worker.terminate();reject(Error(e.message))};worker.postMessage(city);
            })""",{'code':(run/'urban-worker.js').read_text(encoding='utf-8'),'city':city})
            if not result.get('ok'):raise RuntimeError(result.get('error','GENERATOR_FAILURE'))
            if len(json.dumps(result))>60_000_000:raise RuntimeError('CITY_PAYLOAD_LIMIT')
            write_json(run/'buildings-scene.json',result['scene'])
            write_json(run/'urban-geometry-payload.json',result['geometry'])
            gate=geometry_gate(result['geometry']);write_json(run/'urban-geometry-checks.json',gate)
            if not gate['passed']:raise RuntimeError('URBAN_GEOMETRY_GATE_FAILED')
            if (run/'scene-contract.json').exists():
                from .scene import placement_checks
                contract=json.loads((run/'scene-contract.json').read_text())
                failures=placement_checks(city,result['metrics']['objects'],contract['max_bound_deviation_m'])
                write_json(run/'placement-checks.json',{'passed':not failures,'failures':failures})
                if failures:raise RuntimeError('SCENE_PLACEMENT_CONTRACT: '+json.dumps(failures)[:2500])
                bindings=[]
                for o in result['metrics']['objects']:
                    required=set(contract['objects'][o['id']]['required_texture_roles'])
                    declared={m['role'] for m in o['surfaces'] if m['role']}
                    missing=required-declared
                    missing_maps={r for r in declared if r not in assets or not assets[r].get('maps')}
                    bindings.append({'id':o['id'],'required':sorted(required),'declared':sorted(declared),'missing':sorted(missing|missing_maps),'surfaces':o['surfaces']})
                write_json(run/'material-binding-checks.json',{'passed':all(not b['missing'] for b in bindings),'objects':bindings})
                if any(b['missing'] for b in bindings):raise RuntimeError('SCENE_MATERIAL_BINDING_CONTRACT: '+json.dumps([{'id':b['id'],'missing':b['missing']} for b in bindings if b['missing']]))
            # Ground/height coverage checks use actual emitted building bounds.
            expected={b['id']:b for b in city['buildings']};bounds_failures=[]
            for o in result['metrics']['objects']:
                b=expected[o['id']];actual=o['max'][1]-o['min'][1]
                if not height_within_evidence(b,actual):bounds_failures.append({'id':o['id'],'actual_height':actual,'required':b.get('height_envelope_m') or b['height']})
            if bounds_failures:write_json(run/'urban-bounds-failures.json',bounds_failures);raise RuntimeError('BUILDING_HEIGHT_CONTRACT')
            payload={'data':city,'buildings':result['scene'],'assets':assets,'profile':profile,'neutral':NEUTRAL}
            settings=json.loads((run/'presentation-settings.json').read_text()) if (run/'presentation-settings.json').exists() else {}
            payload.update(presentation=settings.get('styled'),neutral_presentation=settings.get('neutral'))
            if (run/'render-probe.json').exists():payload['render_probe']=json.loads((run/'render-probe.json').read_text())
            write_json(run/'presentation.json',payload)
            page.add_script_tag(content=(run/'urban-viewer.js').read_text(encoding='utf-8'))
            page.evaluate('payload=>window.initCity(payload)',payload)
            renders=run/'renders';renders.mkdir(exist_ok=True)
            plan=json.loads((run/'capture-plan.json').read_text()) if (run/'capture-plan.json').exists() else {}
            requested_views=plan.get('views',['overview','north','grid','street','detail','seam','landmark'])
            if 'overview' not in requested_views or any(v not in ['overview','north','grid','street','detail','seam','landmark'] for v in requested_views):raise ValueError('CAPTURE_VIEW_PLAN')
            requested_objects=plan.get('objects',city.get('observed_objects',[]))
            if not set(requested_objects).issubset({b['id'] for b in city['buildings']}):raise ValueError('CAPTURE_OBJECT_PLAN')
            stats={};fingerprints={};material_fingerprints={}
            for name,style in [('neutral',NEUTRAL),('styled',profile)]:
                page.evaluate('p=>window.setCityStyle(p.style,p.inspection)',{'style':style,'inspection':name=='neutral'})
                fingerprints[name]=page.evaluate('window.cityGeometryFingerprint()')
                material_fingerprints[name]=hashlib.sha256(page.evaluate('window.cityMaterialFingerprint()').encode()).hexdigest()
                for view in requested_views:
                    page.evaluate('view=>window.setCityView(view)',view)
                    page.evaluate('value=>window.showCityGrid(value)',view in ['grid','seam'])
                    page.wait_for_timeout(180)
                    page.locator('canvas').screenshot(path=str(renders/f'{name}-{view}.png'),timeout=30000)
                page.evaluate("window.setCityView('overview');window.showCityGrid(false)")
                stats[name]=page.evaluate('frames=>window.benchmarkCity(frames)',plan.get('benchmark_frames',24))
            from .quality import object_view_name
            for identifier in requested_objects:
                page.evaluate('id=>window.selectCityObject(id,true)',identifier)
                page.wait_for_timeout(180)
                page.locator('canvas').screenshot(path=str(renders/f'styled-{object_view_name(identifier)}.png'),timeout=30000)
                page.evaluate("window.setCityView('grid')")
                page.locator('canvas').screenshot(path=str(renders/f'styled-{object_view_name(identifier)}-top.png'),timeout=30000)
            page.evaluate('window.resetCityObjects()')
            evidence_captures=[]
            for view in plan.get('evidence_views',[]):
                import re
                if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',view['id']):raise ValueError('EVIDENCE_VIEW_ID')
                page.evaluate('()=>window.resetCityObjects()')
                if view.get('object_id'):
                    if view['object_id'] not in expected:raise ValueError('EVIDENCE_OBJECT_ID')
                    page.evaluate('id=>{window.selectCityObject(id,true,false);window.toggleCityLayer("infrastructure",false)}',view['object_id'])
                page.evaluate('p=>window.setCityEvidenceCamera(p)',view['local_camera'])
                page.wait_for_timeout(180)
                page.locator('canvas').screenshot(path=str(renders/f'evidence-{view["id"]}.png'),timeout=30000)
                visible=page.evaluate('()=>window.cityVisibleObjectIds()')
                if view.get('object_id') and visible!=[view['object_id']]:raise ValueError('EVIDENCE_VISIBILITY_MISMATCH')
                evidence_captures.append({'id':view['id'],'object_id':view.get('object_id'),'mode':'isolated-object' if view.get('object_id') else 'whole-scene','camera':view['local_camera'],'visible_object_ids':visible,'sha256':hashlib.sha256((renders/f'evidence-{view["id"]}.png').read_bytes()).hexdigest()})
            page.evaluate('()=>window.resetCityObjects()')
            write_json(run/'evidence-captures.json',{'contract':'matching-source-visibility-v2','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'views':evidence_captures})
            write_json(run/'surface-bindings.json',page.evaluate('window.citySurfaceBindings()'))
            write_json(run/'render-performance.json',stats)
            for name in ['neutral','styled']:
                from PIL import Image,ImageStat
                im=Image.open(renders/f'{name}-overview.png')
                if max(ImageStat.Stat(im).stddev)<5:raise RuntimeError('BLANK_CITY_CAPTURE')
            if errors:write_json(run/'browser-errors.json',errors);raise RuntimeError('BROWSER_ERRORS')
            metrics=result['metrics'];metrics['geometry_input_hash']=city['geometry_input_hash']
            metrics['source_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
            metrics['scene_geometry_hash']=canonical_hash({'geometries':result['scene'].get('geometries'),
                'object':result['scene'].get('object')})
            metrics['style_only_fingerprints']=fingerprints
            metrics['style_only_same_geometry']=fingerprints['neutral']==fingerprints['styled']
            metrics['style_preserves_material_identity']=material_fingerprints['neutral']==material_fingerprints['styled']
            metrics['material_fingerprints']=material_fingerprints
            if not metrics['style_only_same_geometry']:raise RuntimeError('STYLE_CHANGED_GEOMETRY')
            if not metrics['style_preserves_material_identity']:raise RuntimeError('STYLE_CHANGED_MATERIAL_IDENTITY')
            output={'ok':True,'metrics':metrics,'network_requests_denied':denied,'performance':stats,
                'isolation':'Chromium OS sandbox + dedicated network-denied worker; trusted renderer binds vetted local texture data'}
            write_json(run/'urban-runtime-result.json',output);browser.close()
    except Exception as exc:
        write_json(run/'urban-runtime-result.json',{'ok':False,'error':str(exc)[:1200]})


if __name__=='__main__':child(Path(sys.argv[1]).resolve())
