"""Joint AOI generation and visual refinement with optional, unconstrained materials."""
import hashlib
import html
import json
import shutil
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from ..config import ROOT,Settings
from ..provider import Provider,write_json
from ..runtime import validate_source
from .runtime import capture_city
from .strict_loop import snapshot_runtime,restore_runtime
from .quality import patch_fragment
from .scene import scene_map
from .report import viewer_files
from .style import canonical_hash

DIMENSIONS=('layout','identity','roofs','streetscape','materials','style','coherence')


def acceptable(review):
    scores=review.get('scores',{})
    if set(scores)!=set(DIMENSIONS) or any(type(v) not in (int,float) or not 0<=v<=5 for v in scores.values()):raise ValueError('SCENE_REVIEW_SCORES')
    if not isinstance(review.get('issues'),list):raise ValueError('SCENE_REVIEW_ISSUES')
    if any(i.get('severity') not in ('minor','major','critical') for i in review['issues']):raise ValueError('SCENE_REVIEW_SEVERITY')
    return min(scores.values())>=3 and sum(scores.values())/len(scores)>=3.5 and not any(i['severity'] in ('critical','major') for i in review['issues'])


def improved(old,new):
    critical=lambda r:sum(i['severity']=='critical' for i in r['issues'])
    major=lambda r:sum(i['severity']=='major' for i in r['issues'])
    return critical(new)<=critical(old) and major(new)<=major(old) and sum(new['scores'].values())>sum(old['scores'].values()) and all(new['scores'][k]>=min(old['scores'][k],3) for k in DIMENSIONS)


def apply_adjustments(city,data):
    """Shared material/vegetation controls, independent of a compulsory texture set."""
    recipes=data.get('material_recipes',{})
    valid={'road','pavement','grass','foliage','trunk','metal','ground','marking'}
    if not isinstance(recipes,dict) or not set(recipes).issubset(valid):raise ValueError('SCENE_MATERIAL_RECIPE_ROLES')
    for r in recipes.values():
        if not isinstance(r,dict):raise ValueError('SCENE_MATERIAL_RECIPE')
        if 'color' in r and (not isinstance(r['color'],str) or len(r['color'])!=7 or not r['color'].startswith('#') or any(c not in '0123456789abcdefABCDEF' for c in r['color'][1:])):raise ValueError('SCENE_MATERIAL_COLOR')
        for key in ('roughness','metalness'):
            if key in r and (type(r[key]) not in (int,float) or not 0<=r[key]<=1):raise ValueError('SCENE_PBR_RANGE')
        if r.get('pattern','none') not in ('none','asphalt','paving','brick','slate','grass'):raise ValueError('SCENE_PATTERN')
        if r.get('pattern','none')!='none' and (type(r.get('tile_m')) not in (int,float) or not .1<=r['tile_m']<=100):raise ValueError('SCENE_PATTERN_SCALE')
    city['material_recipes']={**city.get('material_recipes',{}),**recipes}
    detail=data.get('tree_cluster_detail',city.get('tree_cluster_detail',1))
    if type(detail) is not int or not 1<=detail<=3:raise ValueError('SCENE_TREE_DETAIL')
    city['tree_cluster_detail']=detail
    if 'streetscape' in data:
        if not isinstance(data['streetscape'],dict):raise ValueError('STREETSCAPE_RECIPE')
        city['streetscape']=data['streetscape']
    return city


def evidence_packet(city,views):
    keys=('id','name','center','outer','holes','height','floors','height_evidence','height_envelope_m','height_interpretation')
    return {'axes':'Metres: X east, Y up, Z south. Building centres and footprints share ONE world frame.',
            'buildings':[{k:b.get(k) for k in keys} for b in city['buildings']],
            'roads':[{'id':r.get('id'),'points':r['points'],'width':r.get('width')} for r in city['roads']],
            'trees':[{'id':t['id'],'position':t.get('position'),'height':t.get('height')} for t in city['trees']],
            'shared_streetscape_tools':city.get('streetscape',{}),
            'cameras':[{k:v.get(k) for k in ('id','local_camera','heading','pitch')} for v in views]}


def compact_image(source,target):
    with Image.open(source) as im:
        im=im.convert('RGB');im.thumbnail((1280,1280));im.save(target,quality=88)
    return target


def label_scene(path,city,view):
    """Projected identity annotations, not recovered geometry or inferred source detail."""
    import numpy as np
    p=view['local_camera'];position=np.array(p['position']);forward=np.array(p['direction']);forward/=np.linalg.norm(forward)
    right=np.cross(forward,p['up']);right/=np.linalg.norm(right);up=np.cross(right,forward)
    scale=np.tan(np.deg2rad(p['fov'])/2)
    with Image.open(path) as source:
        im=source.convert('RGB');draw=ImageDraw.Draw(im)
        try:font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',15)
        except OSError:font=ImageFont.load_default()
        for index,b in enumerate(city['buildings']):
            height=b.get('height_envelope_m',[b['height']])[-1]
            point=np.array([b['center'][0],height,b['center'][1]])-position;depth=float(point@forward)
            if depth<=.1:continue
            u=.5+float(point@right)/depth/scale/p['aspect']/2;v=.5-float(point@up)/depth/scale/2
            if not 0<=u<=1 or not 0<=v<=1:continue
            x,y=int(u*im.width),int(v*im.height);label=str(index+1)+': '+b['id']
            box=draw.textbbox((x,y),label,font=font);draw.rectangle((box[0]-3,box[1]-2,box[2]+3,box[3]+2),fill='#f4d67e');draw.text((x,y),label,font=font,fill='#172630')
        im.save(path,quality=89)


def make_report(run):
    viewer_files(run)
    summary=json.loads((run/'scene-first-result.json').read_text(encoding='utf-8'))
    body='''<!doctype html><meta charset="utf-8"><title>Scene-first GPT Sol</title><style>body{font:16px system-ui;background:#eef1f2;color:#1a2b34;max-width:1400px;padding:28px;margin:auto}section{background:white;padding:24px;margin:24px 0;border-radius:12px}img{width:49%;vertical-align:top}pre{white-space:pre-wrap}a{color:#12628d}</style><h1>Dựng chung toàn cảnh — GPT Sol</h1><p>Vật liệu được chọn theo quan sát; không bắt buộc texture mẫu hoặc độ khớp 100%. Điểm đánh giá là nhận xét định tính của model.</p><a href="viewer.html">Mở cảnh 3D tương tác</a> · <a href="scene-first-result.json">Kết quả và usage</a>'''
    body+='<pre>'+html.escape(json.dumps(summary,indent=2,ensure_ascii=False))+'</pre>'
    for folder in sorted((run/'iterations').glob('*')):
        review=folder/'review.json'
        if not review.exists():continue
        body+='<section><h2>Lượt '+folder.name+'</h2>'
        for ref in sorted(folder.glob('source-*.jpg')):
            rendered=folder/ref.name.replace('source-','render-')
            if rendered.exists():body+='<p>'+html.escape(ref.stem)+'</p><img loading="lazy" src="'+ref.relative_to(run).as_posix()+'"><img loading="lazy" src="'+rendered.relative_to(run).as_posix()+'">'
        body+='<pre>'+html.escape(review.read_text(encoding='utf-8'))+'</pre></section>'
    body+='<p>Source imagery: Google Photorealistic 3D Tiles via Cesium ion. Map data: © OpenStreetMap contributors. Hidden surfaces, planting positions and approximate materials retain uncertainty.</p>'
    (run/'index.html').write_text(body,encoding='utf-8')


def prepare_scene_run(parent,evidence,run,expanded_context=False):
    if run.exists():raise ValueError('SCENE_FIRST_NEW_RUN_REQUIRED')
    run.mkdir(parents=True)
    for n in ('city.json','style-profile.json','style-references.json','boundary-checks.json','mesh-height-evidence.json','presentation-settings.json','render-probe.json'):
        if (parent/n).exists():shutil.copy2(parent/n,run/n)
    shutil.copytree(parent/'style-inputs',run/'style-inputs')
    # Do not inherit generic scans, obligatory roles, inferred colour multipliers or old component code.
    city=json.loads((run/'city.json').read_text(encoding='utf-8'));city['surface_settings']={};city['scene_mode']=True
    if expanded_context:
        from .data import build_city
        raw=Path(city['source_audit']['source']);context=run/'context-data';context.mkdir()
        for cached in (parent/'context-data').glob('*.osm'):shutil.copy2(cached,context/cached.name)
        points=[p for b in city['buildings'] for p in b['outer']]
        size=min(1000,max(200,max(abs(c) for p in points for c in p)*2+40))
        expanded=build_city(context,snapshot=raw,size=size,longitude=city['origin']['longitude'],latitude=city['origin']['latitude'])
        city.setdefault('core_bounds',city['bounds']);city['context_extent_note']='Shared OSM streets/pavement buffer; only the original reference-backed buildings are reconstructed.'
        for k in ('bounds','roads','surfaces','parks','cells'):city[k]=expanded[k]
        for cell in city['cells']:
            cell['owned']=[b['id'] for b in city['buildings'] if cell['bounds'][0]<=b['center'][0]<cell['bounds'][2] and cell['bounds'][1]<=b['center'][1]<cell['bounds'][3]]
            cell['references']=[i for i in cell.get('references',[]) if i in {b['id'] for b in city['buildings']}]
        city['context_data_audit']=expanded['source_audit']
        city['streetscape']={'curbs':True,'extend_tree_rows':True,'tree_spacing_m':14,'add_lamps':True,'inferred_lane_dashes':True,'include_core':False}
        write_json(run/'streetscape.json',city['streetscape'])
        boundary=json.loads((context/'boundary-checks.json').read_text())
        boundary['one_owner_per_building']=all(sum(b['id'] in cell['owned'] for cell in city['cells'])==1 for b in city['buildings'])
        boundary['object_ids_unique']=len({b['id'] for b in city['buildings']})==len(city['buildings'])
        boundary['scope']='Buffered shared infrastructure with original reference-backed building ownership.'
        write_json(run/'boundary-checks.json',boundary)
        measurements=json.loads((run/'mesh-height-evidence.json').read_text())
        by_id={b['id']:b for b in city['buildings']}
        for sample in measurements.get('buildings',[]):
            b=by_id.get(sample.get('object_id'));height=sample.get('estimated_height_m')
            if b and type(height) in (int,float) and 3<=height<=500 and abs(height-b['height'])>max(5,b['height']*.2):
                b['height_envelope_m']=[min(b['height'],height),max(b['height'],height)]
                b['height_interpretation']='Conflicting tag and sparse roof measurement: interpret multi-level parts using views; envelope is not permission to uniformly stretch the whole footprint.'
        city['geometry_input_hash']=canonical_hash({k:v for k,v in city.items() if k!='geometry_input_hash'})
    write_json(run/'city.json',city);write_json(run/'asset-manifest.json',{})
    write_json(run/'scene-contract.json',{'objects':{b['id']:{'required_texture_roles':[]} for b in city['buildings']},'max_bound_deviation_m':3})
    views=json.loads((evidence/'source-views.json').read_text())['views']
    training=[v for v in views if not v.get('held_out') and v['id'] in ('overhead','south','west','north','east')]
    held=[v for v in views if v.get('held_out')]
    if not held:raise ValueError('SCENE_HELDOUT_REQUIRED')
    write_json(run/'capture-plan.json',{'views':['overview','north','grid'],'objects':[],'evidence_views':training+held,'benchmark_frames':6})
    points=[p for b in city['buildings'] for p in b['outer']]
    scene_map({**city,'bounds':[min(p[0] for p in points)-10,min(p[1] for p in points)-10,max(p[0] for p in points)+10,max(p[1] for p in points)+10]},run/'scene-map.png')
    refs=run/'references';refs.mkdir();images=[compact_image(evidence/v['image'],refs/(v['id']+'.jpg')) for v in training]
    styles=sorted((run/'style-inputs').glob('*.jpg'))
    packet=evidence_packet(city,training)
    return {'city':city,'views':views,'training':training,'held':held,'styles':styles,'images':images,'packet':packet}


def run_scene_first(parent,evidence,run,max_repairs=2,seed_scene=False,expanded_context=False):
    prepared=prepare_scene_run(parent,evidence,run,expanded_context)
    city,views,training,held,styles,images,packet=[prepared[k] for k in ('city','views','training','held','styles','images','packet')]
    settings=Settings.load();settings.model=settings.code_model=settings.review_model=settings.vision_model='gpt-6-sol'
    api=Provider(settings,run,max_calls=10,max_tokens=300000,max_seconds=2100,max_attempts=1,request_timeout=240)
    source_path=run/'building-generator.ts';history=[]
    contract='''Build a coherent entire urban scene from the shared area observations, not independent generic buildings. Factual images first, then STYLE references, then the OSM ID diagram (not photography). Preserve shared spatial relations, varied roof topology, courtyard ownership and skyline. STYLE controls finish/detail/composition, never a mandatory palette. Approximate materials are sufficient if convincing and consistent; do NOT chase exact pixels or photogrammetry artifacts. No fixed texture library, no mandatory textureRole. Use MeshStandardMaterial with freely chosen observed approximate colors/roughness/metalness. Optional material.userData.surfaceRecipe={pattern:"brick|slate|asphalt|paving|grass|none",tile_m:number,rows?:number,columns?:number,seed?:number} creates a trusted procedural surface at metric scale; optional, not required. Plain/painted materials, glazing, metal and geometry detail are equally valid. No textures/canvas/network/imports except import * as THREE from 'three'. No lights, randomness or external capabilities.
Output one complete TypeScript module: import * as THREE from 'three'; export function build(params:any={}) {...return root;}. Host calls build({city}). Every city.buildings ID must have exactly one anchor Group with userData.objectId=b.id; all shapes under that anchor have no objectId. Anchor placement at [b.center[0],0,b.center[1]]; subtract center from footprint coordinates exactly once for local geometry. Keep each object's XZ bounds within its complete OSM bounds +1.5m, ground=0 and total height within 10% of b.height. Root is ONE scene, with shared helpers and object-specific designs informed by WHOLE-scene context. Distinctive towers, recessed roof wells, planted roof, connected pitched roofs and glazed circular feature must have correct ownership; if uncertain, simplify and disclose. Roof ridges and roof planes before decorative repetition. Roof equipment and facade trim should be proportionate, not giant spikes or uniform grids. Do not add a passage solely because a photogrammetry mesh has a black hole.
The host supplies shared OSM roads, pavement, crosswalks, parks and seeded trees at approximate anchors. Improve their shared appearance through scene_adjustments, do not duplicate roads inside buildings. Optional shared ground recipes use roles road,pavement,grass,foliage,trunk,metal,ground,marking and {color:"#RRGGBB",roughness:0..1,metalness:0..1,pattern,tile_m,rows,columns,seed}. tree_cluster_detail=1..3. Shared courtyard features can be attached to the verified owning building group within its bounds. Keep unknown details conservative. Never copy baked shadows into material colors.
Use CLOSED, nondegenerate solids: capped boxes/extrusions/prisms/cylinders. Avoid zero-radius tips, negative scales and unclosed roof planes. For concave footprints, triangulate ShapeUtils.triangulateShape and extrude each triangle into a closed prism. For convex roof prisms, orient all triangles outward, including caps. Reuse materials/geometries, use instancing where helpful. Aim <180000 scene triangles, <4500 source meshes. Return JSON {scene_plan:{spatial_relations:[],roof_systems:[],surface_approach:[],uncertainties:[]},source:string,scene_adjustments:{material_recipes:{},tree_cluster_detail:integer},limitations:[]}.
'''
    try:
        if seed_scene:
            generated=json.loads((parent/'generation.json').read_text(encoding='utf-8'));generated['source']=(parent/'building-generator.ts').read_text(encoding='utf-8')
            generated['seed_provenance']={'parent':parent.name,'source_sha256':hashlib.sha256(generated['source'].encode()).hexdigest(),'scope':'Reuse previously jointly generated AOI program, then reassess with expanded evidence/context.'}
        else:generated=api.call('scene-first-generate',contract+'\nActual scene/cameras: '+json.dumps(packet,ensure_ascii=False),images+styles+[run/'scene-map.png'],settings.code_model,13000)
        validate_source(generated['source']);source_path.write_text(generated['source'],encoding='utf-8');write_json(run/'generation.json',{k:v for k,v in generated.items() if k!='source'})
        city=apply_adjustments(city,generated.get('scene_adjustments',{}));write_json(run/'city.json',city)
        def render_with_fix(folder):
            try:return capture_city(run,timeout=420)
            except RuntimeError as exc:
                if 'TIMEOUT' in str(exc) or 'MEMORY' in str(exc):raise
                folder.mkdir(parents=True,exist_ok=True)
                diagnostics={'error':str(exc)}
                for name in ('urban-geometry-checks.json','urban-compile.log','placement-checks.json','urban-runtime-result.json'):
                    f=run/name
                    if f.exists():
                        shutil.copy2(f,folder/('failed-'+name))
                        if f.suffix=='.json':
                            d=json.loads(f.read_text(encoding='utf-8'))
                            if name=='urban-geometry-checks.json':
                                d={k:v for k,v in d.items() if k not in ('meshes','architectural_id_mapping')}
                            diagnostics[name]=d
                        else:diagnostics[name]=f.read_text(encoding='utf-8')[:6000]
                source=source_path.read_text(encoding='utf-8');(folder/'before-technical.ts').write_text(source,encoding='utf-8')
                fix=api.call('scene-technical-'+folder.name,'Fix only these technical errors in the whole scene source; preserve visible design. Return JSON {edits:[{old:unique exact substring,new:replacement}],reason}. Closed solids, positive volume/scales, outward normals; avoid collapsed vertices and zero-area faces. Do not relax validators.\n'+json.dumps(diagnostics)+'\nSOURCE:\n'+source,[],settings.code_model,6000)
                write_json(folder/'technical-patch.json',fix);corrected=patch_fragment(source,fix.get('edits'));validate_source(corrected);source_path.write_text(corrected,encoding='utf-8')
                return capture_city(run,timeout=420)
        render_with_fix(run/'technical-initial')
        def assess(index,validation=False):
            selected=held if validation else [v for v in training if v['id'] in ('overhead','south','west')]
            folder=run/'iterations'/f'{index:02d}'
            if validation:folder=run/'heldout'
            folder.mkdir(parents=True,exist_ok=True);pairs=[]
            for v in selected:
                pairs+=[compact_image(evidence/v['image'],folder/('source-'+v['id']+'.jpg')),compact_image(run/'renders'/('evidence-'+v['id']+'.png'),folder/('render-'+v['id']+'.jpg'))]
                label_scene(pairs[-2],city,v);label_scene(pairs[-1],city,v)
            prompt='''Evaluate the WHOLE reconstructed area at matching source cameras. Images alternate source/render, followed by STYLE reference. Target is a convincing, recognizable and coherent small urban scene, not exact survey reconstruction or identical textures. Approximate colors/materials are acceptable; plain surfaces can be good if architectural hierarchy is convincing. Judge layout, identities/silhouettes, roof systems, streets/sidewalks/vegetation, material readability, style and coherence. Do not force a palette or library scan. Prioritize major visible faults over microscopic detail. Black source holes, clipping and baked shadows are not physical openings/material colors. An uncertain hidden detail is not a major defect by itself. Identify the owning object ID or shared-ground subsystem for each issue; do not transfer neighbors' features. 0..5 scores: 3=usable/recognizable with simplifications, 4=good with minor issues, 5=excellent. Return JSON {scores:{layout,identity,roofs,streetscape,materials,style,coherence},issues:[{severity:"critical|major|minor",owner,part,evidence,repair}],strengths:[],uncertainties:[],next_actions:[]}. Major means visibly damages usability/identity; do not demand 100% texture correspondence. Scene information: '''+json.dumps(evidence_packet(city,selected),ensure_ascii=False)
            prompt+='\nYellow labels are projected OSM identity annotations from the shared coordinate frame, NOT measured roof geometry. ONLY these five labelled buildings are reconstruction targets. Do not assign unlabelled background towers to low labelled buildings or demand modeling every background structure outside the AOI. The final ID diagram helps ownership. Trust corroborated roof measurements over an unsupported apparent-height guess. Street context has its own declared extent. Conflicting height envelopes, when present, supersede the +/-10% original height requirement and allow multi-level interpretation, not uniform stretching.'
            raw=api.call('scene-first-'+('heldout' if validation else 'review-'+str(index)),prompt,pairs+styles+[run/'scene-map.png'],settings.review_model,3500)
            raw['accepted']=acceptable(raw);write_json(folder/'review.json',raw);return raw,pairs
        current,pairs=assess(0);history.append(current);status='needs_improvement'
        contract+='\nShared streetscape tools are optional scene_adjustments.streetscape={curbs:boolean,extend_tree_rows:boolean,tree_spacing_m:8..40,add_lamps:boolean,inferred_lane_dashes:boolean,include_core:boolean}. These create seeded approximate sidewalk trees/lights, curb edging and illustrative centreline dashes on host OSM roads. They are not exact surveyed placements and do not require hand-coding road duplicates. Agent choices override defaults. When a height_envelope_m is present, it supersedes the earlier +/-10% b.height limit: use multilevel source-supported parts within that envelope.'
        for index in range(1,max_repairs+1):
            if current['accepted']:break
            folder=run/'iterations'/f'{index:02d}';folder.mkdir(parents=True,exist_ok=True);snapshot_runtime(run,folder/'accepted-runtime')
            old_source=source_path.read_text(encoding='utf-8');old_city=json.loads((run/'city.json').read_text(encoding='utf-8'))
            detail_views=[]
            owners={i.get('owner') for i in current['issues'] if i.get('severity') in ('major','critical')}
            for identifier in sorted(o for o in owners if o):
                candidates=[v for v in views if v.get('object_id')==identifier and not v.get('held_out')]
                if candidates:detail_views.append(candidates[0])
            detail_views=detail_views[:3]
            details=[compact_image(evidence/v['image'],folder/('detail-'+v['id']+'.jpg')) for v in detail_views]
            prompt=contract+'\nImprove the WHOLE scene jointly using the actual pairs and critique. Keep correct parts; coordinate roof, courtyard, facade and shared street surfaces. Height envelopes, when supplied, resolve known conflicting tags/roof samples: interpret parts from views within that envelope rather than enforcing a contradicted low tag on all parts. Appendices after paired images are factual detail views of the named targets; use them for facade/roof architecture, not as separate scenes. Return JSON {edits:[{old:unique exact substring,new:replacement}],scene_adjustments:{material_recipes:{},tree_cluster_detail:integer},reason,remaining_uncertainties:[]}. SOURCE:\n'+old_source+'\nCritique: '+json.dumps(current,ensure_ascii=False)+'\nNumerical scene: '+json.dumps(packet,ensure_ascii=False)+'\nAdditional detailed views: '+json.dumps([{k:v.get(k) for k in ('id','object_id','local_camera','heading','pitch')} for v in detail_views])
            patch=api.call('scene-first-refine-'+str(index),prompt,pairs+details+styles,settings.code_model,10000);write_json(folder/'patch.json',patch)
            try:
                corrected=patch_fragment(old_source,patch.get('edits'));validate_source(corrected);source_path.write_text(corrected,encoding='utf-8')
                city=apply_adjustments(json.loads(json.dumps(old_city)),patch.get('scene_adjustments',{}));write_json(run/'city.json',city)
                render_with_fix(folder)
                candidate,new_pairs=assess(index);history.append(candidate)
                keep=improved(current,candidate) or candidate['accepted'];write_json(folder/'decision.json',{'kept':keep})
                if keep:current,pairs=candidate,new_pairs
                else:
                    restore_runtime(run,folder/'accepted-runtime');city=old_city;status='stagnated';break
            except Exception as exc:
                write_json(folder/'rejection.json',{'error':str(exc)});restore_runtime(run,folder/'accepted-runtime');city=old_city;status='technical_rejection';break
        final,_=assess(max_repairs+1,validation=True)
        accepted=current['accepted'] and final['accepted']
        api.save_usage();result={'model':settings.model,'scope':'whole AOI; joint generation and refinement','mandatory_texture_roles':[],'exact_texture_match_required':False,'accepted':accepted,'status':'accepted' if accepted else status,'training':current,'heldout':final,'usage':api.usage,'limitations':generated.get('limitations',[])}
        write_json(run/'scene-first-result.json',result);make_report(run);return result
    finally:api.save_usage();api.client.close()
