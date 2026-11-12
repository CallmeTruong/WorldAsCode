"""Bounded, evidence-driven component repair with transactional technical validation."""
import hashlib
import json
import shutil
from pathlib import Path
from PIL import Image
from ..provider import write_json, BudgetExceeded
from ..runtime import validate_source
from .quality import patch_fragment
from .scene import compose_scene, sync_scene_components
from .runtime import capture_city

DIMENSIONS = ('massing', 'roof', 'facade', 'materials', 'detail', 'style')


def snapshot_runtime(run, folder):
    names=['city.json','building-generator.ts','buildings-scene.json','presentation.json','surface-bindings.json','render-performance.json','placement-checks.json','material-binding-checks.json','mesh-height-checks.json','ground-checks.json','evidence-captures.json','streetscape-audit.json']
    files=[run/n for n in names if (run/n).is_file()]
    files+=list(run.glob('urban-*.json'))+list(run.glob('urban-*.js'))+list(run.glob('urban-*.log'))+list((run/'renders').glob('*.png'))
    for path in files:
        dest=folder/path.relative_to(run);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)


def restore_runtime(run, folder):
    for path in folder.rglob('*'):
        if path.is_file():
            dest=run/path.relative_to(folder);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
    result=run/'urban-runtime-result.json'
    if result.exists():
        data=json.loads(result.read_text(encoding='utf-8'))
        expected=hashlib.sha256((run/'building-generator.ts').read_bytes()).hexdigest()
        if not data.get('ok') or data.get('metrics',{}).get('source_sha256')!=expected:
            raise RuntimeError('RESTORED_RUNTIME_SOURCE_MISMATCH')
    # Old checkpoints predate visibility manifests; never leave a rejected
    # candidate's manifest attached to restored PNGs/source.
    manifest=run/'evidence-captures.json'
    if manifest.exists() and not (folder/'evidence-captures.json').exists():
        write_json(run/'invalidated-evidence-captures.json',json.loads(manifest.read_text(encoding='utf-8')))
        write_json(manifest,{'contract':'invalidated','views':[],'reason':'Restored checkpoint has no verified capture manifest.'})


def write_strict_report(run):
    import html
    result=json.loads((run/'strict-summary.json').read_text(encoding='utf-8'))
    usage=json.loads((run/'usage.json').read_text(encoding='utf-8'))
    body='''<!doctype html><meta charset="utf-8"><title>GPT Sol — matched-camera repair</title><style>body{font:16px system-ui;max-width:1400px;margin:32px auto;padding:20px;background:#eef1f2;color:#17242c}a{color:#145e88}section{background:white;padding:20px;margin:24px 0;border-radius:12px}img{max-width:49%;vertical-align:top}pre{white-space:pre-wrap}table{border-collapse:collapse}td,th{padding:8px;border:1px solid #aab5bc}</style><h1>GPT Sol: đối chiếu và sửa theo camera nguồn</h1>'''
    body+='<p>Phạm vi: một công trình; toàn khu vực chưa được công nhận đạt. Điểm dưới đây là đánh giá định tính của model, không phải sai số đo đạc.</p>'
    body+='<p><a href="viewer.html">Mở cảnh 3D</a> · <a href="strict-summary.json">Kết quả kiểm tra</a> · <a href="usage.json">Usage</a></p>'
    body+='<pre>'+html.escape(json.dumps({'accepted':result['accepted'],'status':result['status'],'model':result['model'],'calls':usage['calls'],'input_tokens':usage['input_tokens'],'output_tokens':usage['output_tokens'],'api_seconds':usage['elapsed_api_seconds'],'cost_usd':usage.get('cost_usd')},indent=2,ensure_ascii=False))+'</pre>'
    for assessment in sorted((run/'strict-history').glob('*/*/assessment.json')):
        data=json.loads(assessment.read_text(encoding='utf-8'));folder=assessment.parent
        decision=folder.parent/'decision.json'
        label=json.loads(decision.read_text()).get('reason') if decision.exists() else 'baseline / validation'
        body+='<section><h2>'+html.escape(str(folder.relative_to(run)))+'</h2><p>'+html.escape(label)+'</p><table><tr>'
        body+=''.join('<th>'+d+'</th>' for d in DIMENSIONS)+'</tr><tr>'+''.join('<td>'+str(data['scores'][d])+'/5</td>' for d in DIMENSIONS)+'</tr></table>'
        for ref in sorted(folder.glob('*-reference.jpg')):
            generated=ref.with_name(ref.name.replace('-reference.jpg','-render.jpg'))
            body+='<p>'+html.escape(ref.stem.replace('-reference',''))+' — ảnh nguồn bên trái / bản dựng bên phải</p>'
            body+='<img loading="lazy" src="'+ref.relative_to(run).as_posix()+'"><img loading="lazy" src="'+generated.relative_to(run).as_posix()+'">'
        body+='<pre>'+html.escape(json.dumps(data,indent=2,ensure_ascii=False))+'</pre></section>'
    body+='<p>Factual imagery: Google Photorealistic 3D Tiles via Cesium ion. Footprints: © OpenStreetMap contributors. Substitute PBR maps: Poly Haven. Occluded/source-blurred features remain uncertain.</p>'
    (run/'index.html').write_text(body,encoding='utf-8')


def acceptance(review):
    scores = review.get('scores', {})
    if set(scores) != set(DIMENSIONS) or any(type(s) not in (int,float) or not 0 <= s <= 5 for s in scores.values()):
        raise ValueError('STRICT_REVIEW_SCORES')
    issues = review.get('issues')
    if not isinstance(issues,list) or any(i.get('severity') not in ('minor','major','critical') for i in issues):
        raise ValueError('STRICT_REVIEW_ISSUES')
    if review.get('action') not in ('repair','request_evidence','accept'):
        raise ValueError('STRICT_REVIEW_ACTION')
    # Unknown and occluded evidence cannot be promoted to confirmed fidelity.
    return (min(scores.values()) >= 4 and not any(i['severity'] != 'minor' for i in issues)
            and review.get('evidence_sufficient') is True and review['action'] == 'accept')


def nonregressing(before, after):
    blockers=lambda r:tuple(sum(i['severity']==s for i in r['issues']) for s in ('critical','major'))
    return (all(after['scores'][d] >= before['scores'][d] for d in DIMENSIONS)
            and all(a<=b for a,b in zip(blockers(after),blockers(before)))
            and (sum(after['scores'].values()) > sum(before['scores'].values()) or blockers(after)<blockers(before)))


def capture_with_repair(run, component, plan, folder, provider):
    """One cheap code-only technical correction, with failing diagnostics retained."""
    try:return capture_city(run,timeout=360)
    except RuntimeError as exc:
        if any(cause in str(exc) for cause in ('TIMEOUT','MEMORY_LIMIT')):raise
        diagnostics={'error':str(exc)}
        for name in ('urban-geometry-checks.json','placement-checks.json','material-binding-checks.json','urban-runtime-result.json'):
            path=run/name
            if path.exists():
                data=json.loads(path.read_text(encoding='utf-8'));write_json(folder/('failed-'+name),data)
                if name=='urban-geometry-checks.json':
                    failing=[m for m in data.get('meshes',[]) if m.get('boundaryEdges',0) or m.get('nonManifoldEdges',0) or m.get('normalConsistency',{}).get('consistent') is False or m.get('selfIntersection',{}).get('selfIntersecting')]
                    data={k:v for k,v in data.items() if k!='meshes'}
                    data['failing_meshes']=failing[:12]
                diagnostics[name]=data
        if 'TYPESCRIPT' in str(exc) and (run/'urban-compile.log').exists():
            diagnostics['compiler']=(run/'urban-compile.log').read_text(encoding='utf-8')[:8000]
        source=component.read_text(encoding='utf-8')
        (folder/'technical-before.ts').write_text(source,encoding='utf-8')
        prompt='''Fix ONLY the technical failure in this local THREE component, retaining its intended visual repair. Return JSON {edits:[{old:"unique exact substring",new:"replacement"}],reason}. All per-mesh solids must be closed, with nonzero volume, consistently outward winding and no zero-area or duplicate faces. Pay attention to arch endpoint vertices collapsing to the same position. Divide any interval [a,b] into n segments with u0=a+i*(b-a)/n,u1=a+(i+1)*(b-a)/n; check the LAST segment as well as the first. Prefer ordinary closed boxes or properly triangulated prisms for small relief segments; never weaken validators. No imports, network, placement changes or removal of required texture roles. Source:\n'''+source+'\nValidation diagnostics: '+json.dumps(diagnostics,ensure_ascii=False)[:10000]
        patch=provider.call('strict-technical-'+folder.name,prompt,[],provider.settings.code_model,3500)
        write_json(folder/'technical-patch.json',patch)
        corrected=patch_fragment(source,patch.get('edits'))
        validate_source("import * as THREE from 'three';\n"+corrected+'\nexport function build(params:any={}) {return buildComponent(params);}')
        component.write_text(corrected,encoding='utf-8');compose_scene(run,plan)
        return capture_city(run,timeout=360)


def paired_images(run, evidence, views, building, folder):
    """Identical projected footprint crop on factual and rendered images; no image synthesis."""
    import numpy as np
    folder.mkdir(parents=True,exist_ok=True);images=[];records=[]
    # Local cameras use a common datum recorded at acquisition; crop in local camera space.
    for v in views:
        p=v['local_camera'];pos=np.array(p['position']);forward=np.array(p['direction']);forward/=np.linalg.norm(forward)
        right=np.cross(forward,p['up']);right/=np.linalg.norm(right);up=np.cross(right,forward)
        points=np.array([[x,y,z] for x,z in building['outer'] for y in (0,building['height'])])-pos
        depth=points@forward;valid=depth>.1
        if not valid.any():continue
        scale=np.tan(np.deg2rad(p['fov'])/2)
        uv=np.column_stack((.5+(points@right)/np.maximum(depth,.1)/scale/p['aspect']/2,.5-(points@up)/np.maximum(depth,.1)/scale/2))[valid]
        lo=np.maximum(0,uv.min(axis=0)-.04);hi=np.minimum(1,uv.max(axis=0)+.04)
        if np.any(hi-lo<.02):continue
        for kind,path in [('reference',evidence/v['image']),('render',run/'renders'/f'evidence-{v["id"]}.png')]:
            with Image.open(path) as im:
                box=(int(lo[0]*im.width),int(lo[1]*im.height),int(hi[0]*im.width),int(hi[1]*im.height))
                crop=im.crop(box).convert('RGB');crop.thumbnail((1000,1000))
                target=folder/f'{v["id"]}-{kind}.jpg';crop.save(target,quality=88);images.append(target)
                records.append({'view_id':v['id'],'kind':kind,'file':target.name,'pixel_box':list(box),'original_size':list(im.size),'normalized_bounds':[lo.tolist(),hi.tolist()]})
    write_json(folder/'pairs.json',records)
    return images


def target_packet(building, views):
    """Supply numerical local coordinates, not just code with an unknown b argument."""
    import math
    x,z=building['center']
    local={**building,'center':[0,0],'outer':[[a-x,c-z] for a,c in building['outer']],
           'holes':[[[a-x,c-z] for a,c in ring] for ring in building.get('holes',[])]}
    ring=local['outer'];edges=[]
    for i,a in enumerate(ring):
        c=ring[(i+1)%len(ring)];length=math.hypot(c[0]-a[0],c[1]-a[1])
        if length>1e-6:edges.append({'edge':i,'from':a,'to':c,'length_m':round(length,3)})
    frames=[]
    for view in views:
        p=view['local_camera'];position=p['position']
        frames.append({'view_id':view['id'],'heading':view.get('heading'),'pitch':view.get('pitch'),
                       'camera_target_local':{**p,'position':[position[0]-x,position[1],position[2]-z]}})
    return {'axes':'X east, Y up, Z south; coordinates in metres; host owns placement','local_building':local,'edges':edges,'views':frames}


def run_target(run, evidence, object_id, provider, max_repairs=2):
    run=Path(run);evidence=Path(evidence)
    if (run/'strict-summary.json').exists():raise ValueError('STRICT_RUN_ALREADY_FINISHED_USE_NEW_RUN')
    city=json.loads((run/'city.json').read_text(encoding='utf-8'))
    b=next(b for b in city['buildings'] if b['id']==object_id)
    source_views=json.loads((evidence/'source-views.json').read_text())['views']
    train=[v for v in source_views if not v.get('held_out') and v.get('object_id')==object_id][:2]
    if not train:train=[v for v in source_views if not v.get('held_out') and v['id'] in ('south','west')]
    overhead=next(v for v in source_views if v['id']=='overhead');train=[overhead,*train]
    held=[v for v in source_views if v.get('held_out')]
    if not held:raise ValueError('STRICT_HELDOUT_REQUIRED')
    write_json(run/'capture-plan.json',{'views':['overview','grid'],'objects':[object_id],'evidence_views':train+held,'benchmark_frames':6})
    capture_city(run,timeout=360)
    sync_scene_components(run)
    key=hashlib.sha256(object_id.encode()).hexdigest()[:12]
    component=run/'components'/key/'generator.ts'
    plan=json.loads((run/'scene-plan.json').read_text(encoding='utf-8'))
    styles=sorted((run/'style-inputs').glob('*.jpg'))[:1]
    history=[]
    def review(iteration, validation=False):
        folder=run/'strict-history'/f'{iteration:02d}'/('heldout' if validation else 'review')
        images=paired_images(run,evidence,held if validation else train,b,folder)
        if not images:raise ValueError('STRICT_NO_VISIBLE_PAIRS')
        prompt='''Act as an independent, strict architectural reconstruction critic. Attachments alternate FACTUAL source and GENERATED render crops at the SAME calibrated camera and image coordinates. The final image, if listed, is STYLE only. Ignore source background objects outside the target footprint. Do not mistake a dark baked shadow for a material. Identify missing source features by location/view; distinguish actual mismatch from source photogrammetry blur or occlusion. Judge roof outline, slopes, ridges, courtyard, dormers and rooftop equipment; facade floor rhythms, openings, proportions, relief; actual texture readability, material identity and physical scale; contextual detail. Stylistic treatment must not force colors or invent geography. Never reward generic repetition. Unknown/occluded sides stay uncertain. Score each dimension 0..5: 4 requires close match in all visible distinguishing features; 5 exceptionally faithful; 3 recognizable with major mismatches. Return JSON {scores:{massing,roof,facade,materials,detail,style},issues:[{severity:"critical|major|minor",part,view,evidence,repair}],evidence_sufficient:boolean,missing_evidence:[],action:"repair|request_evidence|accept"}. accept only if ALL scores>=4, no major/critical issues and sufficient evidence. Prefer request_evidence over invented fixes if evidence is missing. Target: '''+json.dumps(b,ensure_ascii=False)+'\nPair order: '+json.dumps([p.name for p in images])+'\nSTYLE attachments: '+str(len(styles))
        prompt+='\nJudge scores and issues ONLY for the target building. Put roads, courtyard ground, neighboring buildings and other shared-context defects in a separate shared_scene_issues array, not target scores. A rectangular crop can include space outside a concave target footprint. Black voids, clipping boundaries and missing photogrammetry are not confirmed architectural passages or surface colors. Require corroboration across views before prescribing structural removal; otherwise request evidence. Numerical target and camera packet: '+json.dumps(target_packet(b,held if validation else train),ensure_ascii=False)
        raw=provider.call(f'strict-{key}-{iteration}-'+('heldout' if validation else 'review'),prompt,images+styles,provider.settings.review_model,3000)
        raw['accepted']=acceptance(raw);write_json(folder/'assessment.json',raw)
        return raw,images
    current,images=review(0);history.append(current);status='needs_improvement'
    for iteration in range(1,max_repairs+1):
        if current['accepted']:status='training_passed';break
        if current['action']=='request_evidence':status='needs_evidence';break
        folder=run/'strict-history'/f'{iteration:02d}';folder.mkdir(parents=True,exist_ok=True)
        snapshot_runtime(run,folder/'accepted-runtime')
        before=component.read_text(encoding='utf-8');before_composed=(run/'building-generator.ts').read_bytes()
        (folder/'before.ts').write_text(before,encoding='utf-8')
        prompt='''Repair this one LOCAL Three.js component from the matched source/render pairs and strict critique. Return JSON {edits:[{old:"unique exact substring",new:"replacement"}],reason,remaining_uncertainty:[]}. Patch only the evidenced faults, in priority massing then roof then facade then materials/detail. Preserve unrelated correct parts, footprint/holes, height datum, world placement, object IDs, existing required textureRole bindings. No imports/network/randomness. All meshes must be individually closed manifold solids. Geometry groups on closed solids may assign distinct materials. Avoid open roof planes and degenerate tips. Use instantiated repeats. THREE in scope; host passes local footprint and places anchor exactly once. Source colors/material identity remain factual; style is descriptive, never a palette restriction. Do not invent measurements or concealed features. Source:\n'''+before+'\nCritique: '+json.dumps(current,ensure_ascii=False)+'\nAttachment pairs: '+json.dumps([p.name for p in images])
        prompt+='\nDo not modify neighboring objects or shared ground based on a crop. For a mismatched library albedo, material.userData.useAlbedoMap=false keeps the normal/roughness maps while material.color supplies an evidence-informed tint. Do not infer paint colors from baked shadows. Numerical target and camera packet (actual b values are supplied here): '+json.dumps(target_packet(b,train),ensure_ascii=False)
        raw=provider.call(f'strict-{key}-{iteration}-patch',prompt,images,provider.settings.code_model,7000);write_json(folder/'patch.json',raw)
        try:
            corrected=patch_fragment(before,raw.get('edits'))
            validate_source("import * as THREE from 'three';\n"+corrected+'\nexport function build(params:any={}) {return buildComponent(params);}')
            component.write_text(corrected,encoding='utf-8');compose_scene(run,plan)
            capture_with_repair(run,component,plan,folder,provider)
            candidate,next_images=review(iteration)
            keep=nonregressing(current,candidate)
            write_json(folder/'decision.json',{'kept':keep,'reason':'dimension scores improve without regression' if keep else 'no verified improvement across all dimensions'})
            history.append(candidate)
            if keep:current,images=candidate,next_images
            else:status='stagnated';break
        except Exception as exc:
            status='technical_rejection';write_json(folder/'rejection.json',{'error':str(exc)[:1000]})
            for name in ('urban-geometry-checks.json','urban-runtime-result.json','building-generator.ts'):
                if (run/name).exists():(folder/('rejected-'+name)).write_bytes((run/name).read_bytes())
            break
        finally:
            if status in ('stagnated','technical_rejection'):
                component.write_text(before,encoding='utf-8');(run/'building-generator.ts').write_bytes(before_composed)
                restore_runtime(run,folder/'accepted-runtime')
    try:final,_=review(max_repairs+1,validation=True)
    except BudgetExceeded as exc:
        final={'accepted':False,'not_evaluated':True,'reason':str(exc)};status='budget_exhausted'
    accepted=current['accepted'] and final['accepted']
    result={'object_id':object_id,'model':provider.settings.model,'scope':'one component; not whole-city acceptance','accepted':accepted,'status':'accepted' if accepted else status,'training':current,'heldout':final,'assessments':len(history),'max_repairs':max_repairs,'cost_usd':provider.usage.get('cost_usd'),'pricing_note':'No dollar estimate without configured gateway token rates.'}
    write_json(run/'strict-summary.json',result);provider.save_usage();return result
