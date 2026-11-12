"""Shared scene evidence, local component code and explicit acceptance contracts."""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw
from ..provider import write_json
from ..runtime import validate_source
from .style import canonical_hash
from .objects import footprint_sheet

ROLES = {'brick', 'plaster', 'stone', 'roof_tile', 'road', 'pavement'}


def scene_inputs(manifest_path):
    path = Path(manifest_path).resolve()
    manifest = json.loads(path.read_text(encoding='utf-8'))
    views = manifest.get('views', [])
    if not 2 <= len(views) <= 16:
        raise ValueError('SCENE_REQUIRES_2_TO_16_VIEWS')
    files = []
    ids = set()
    for view in views:
        if not isinstance(view.get('id'), str) or view['id'] in ids:
            raise ValueError('SCENE_VIEW_ID')
        ids.add(view['id'])
        image = (path.parent / view['image']).resolve()
        if not image.is_relative_to(path.parent) or not image.is_file():
            raise ValueError('SCENE_IMAGE_PATH')
        if image.stat().st_size > 15_000_000:
            raise ValueError('SCENE_IMAGE_BYTES')
        with Image.open(image) as im:
            if im.width * im.height > 30_000_000:
                raise ValueError('SCENE_IMAGE_PIXELS')
        files.append((view, image, hashlib.sha256(image.read_bytes()).hexdigest()))
    if not any(v.get('held_out') for v in views):
        raise ValueError('SCENE_REQUIRES_HELD_OUT_VIEW')
    return manifest, files, canonical_hash({'manifest': manifest, 'images': [(v['id'], h) for v, _, h in files]})


def validate_plan(plan, city, view_ids, available_roles=None):
    items = plan.get('buildings', [])
    expected = {b['id'] for b in city['buildings']}
    ids = [b.get('object_id') for b in items]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError('SCENE_PLAN_OBJECT_COVERAGE')
    for item in items:
        if not item.get('massing') or not item.get('roof') or not item.get('materials') or not item.get('uncertainty'):
            raise ValueError('SCENE_PLAN_INCOMPLETE')
        if not set(item.get('evidence_views', [])).issubset(view_ids):
            raise ValueError('SCENE_PLAN_UNKNOWN_VIEW')
        if not set(item.get('required_texture_roles', [])).issubset(ROLES if available_roles is None else available_roles):
            raise ValueError('SCENE_PLAN_TEXTURE_ROLE')
        if item.get('visibility') not in {'observed', 'partial', 'unobserved'}:
            raise ValueError('SCENE_PLAN_VISIBILITY')
    return plan


def scene_map(city, target):
    """Labeled plan associates source identities with locations; not aerial imagery."""
    im = Image.new('RGB', (1000, 1000), '#edf1ef'); draw = ImageDraw.Draw(im)
    x0,z0,x1,z1 = city['bounds']; scale = 880 / max(x1-x0,z1-z0)
    xy = lambda p:(60+(p[0]-x0)*scale,60+(p[1]-z0)*scale)
    for i,b in enumerate(city['buildings']):
        draw.polygon([xy(p) for p in b['outer']], fill='#b6c0c5', outline='#33434c', width=2)
        draw.text(xy(b['center']), str(i+1), fill='#09151e')
    draw.text((20,10), 'OSM ID PLAN, NOT A PHOTO. NORTH UP. ' + ' / '.join(str(i+1)+': '+b['id'] for i,b in enumerate(city['buildings'])), fill='#14212c')
    im.save(target)


def compose_scene(run, plan):
    fragments = []; calls = []
    for item in plan['buildings']:
        key = hashlib.sha256(item['object_id'].encode()).hexdigest()[:12]
        source = (run/'components'/key/'generator.ts').read_text(encoding='utf-8')
        fragments.append(source.replace('function buildComponent(', 'function component_'+key+'(', 1))
        calls.append(f"case {json.dumps(item['object_id'])}: g=component_{key}(local);break;")
    # Components cannot independently decide the world-space placement.
    wrapper = '''export function build(params:any={}) {
 const root=new THREE.Group();
 for(const b of params.city.buildings){
  const [x,z]=b.center;
  const local={...b,center:[0,0],outer:b.outer.map(([a,c]:number[])=>[a-x,c-z]),holes:(b.holes||[]).map((r:any)=>r.map(([a,c]:number[])=>[a-x,c-z]))};
  let g:any;switch(b.id){CASES default:throw Error('MISSING_COMPONENT:'+b.id);}
  const anchor=new THREE.Group();anchor.name=b.id;anchor.userData.objectId=b.id;
  anchor.position.set(x,0,z);g.traverse((o:any)=>{delete o.userData.objectId;});anchor.add(g);root.add(anchor);
 }return root;
}'''.replace('CASES','\n'.join(calls))
    source = "import * as THREE from 'three';\n"+'\n'.join(fragments)+'\n'+wrapper
    validate_source(source); (run/'building-generator.ts').write_text(source, encoding='utf-8')


def build_scene(city, manifest_path, run, provider):
    manifest, files, signature = scene_inputs(manifest_path)
    style = json.loads((run/'style-profile.json').read_text(encoding='utf-8'))
    training = [(v,p) for v,p,_ in files if not v.get('held_out')]
    registry=run/'asset-manifest.json'
    available_roles=set(json.loads(registry.read_text(encoding='utf-8'))) if registry.exists() else ROLES
    shared = [p for v,p in training if not v.get('object_id')]
    target = run/'scene-plan.json'; scene_map(city, run/'scene-id-map.png')
    if target.exists():
        plan = json.loads(target.read_text(encoding='utf-8'))
        if plan['input_hash'] != signature: raise ValueError('SCENE_INPUT_CHANGED_USE_NEW_RUN')
        validate_plan(plan, city, {v['id'] for v,_ in training},available_roles)
    else:
        brief = [{k:b.get(k) for k in ['id','name','outer','holes','center','height','height_evidence','floors','mesh_height_evidence']} for b in city['buildings']]
        prompt = '''Analyze the WHOLE urban scene jointly, not one isolated building. The final attachment is an OSM ID diagram, NOT photography. Map source photographs to ALL named footprint IDs. Camera/world: local X=east, Z=south, Y=up. Frames may show outside this smaller AOI. Distinguish partial, hidden and visible evidence; do not invent confirmation for occluded facades. Return JSON {buildings:[{object_id,visibility:"observed|partial|unobserved",evidence_views:[view IDs],massing:string,roof:string,openings:string,materials:string,identity_features:[strings],required_texture_roles:["brick|plaster|stone|roof_tile"],uncertainty:[strings],height_estimate_m:number|null}],ground:{road_observations:string,pavement_observations:string,vegetation_observations:string,uncertainty:[strings]},style_application:{form:string,surfaces:string,vegetation:string,composition:string},capture_gaps:[strings]}. Every footprint ID must occur once. Heights with actual OSM tags are authoritative unless clear conflicting evidence; inferred heights may be estimated with uncertainty. Preserve each identified object's evidenced silhouette, facade hierarchy and distinctive parts. Do not transfer architectural features from another object or city. Identify varied towers and local facade systems, not uniform building templates. Texture roles only where appropriate, never use clay tiles for dark metal/slate roofs. Preserve material identities and factual colors; style guides detail treatment without palette restrictions. No precise measurements from appearance alone.\nBuildings: '''+json.dumps(brief,ensure_ascii=False)+'\nViews: '+json.dumps([v for v,_ in training],ensure_ascii=False)+'\nStyle: '+json.dumps(style,ensure_ascii=False)
        prompt+='\nAvailable material registry roles (choose only appropriate roles from this list): '+json.dumps(sorted(available_roles))
        plan = provider.call('scene-observe', prompt, [p for _,p in training]+[run/'scene-id-map.png'], provider.settings.vision_model,6500)
        validate_plan(plan, city, {v['id'] for v,_ in training},available_roles);plan['input_hash']=signature
        write_json(target,plan)
    if (run/'scene-contract.json').exists() and (run/'building-generator.ts').exists():
        # Completed generation is immutable under identical run inputs. Retain reviewed
        # source and measured city refinements instead of regenerating every component.
        return city
    byid = {b['id']:b for b in city['buildings']}
    write_json(run/'scene-reference-provenance.json', {'manifest':manifest,'images':[{'id':v['id'],'sha256':h} for v,_,h in files], 'input_hash':signature})
    style_images = sorted((run/'style-inputs').glob('*.jpg'))
    for item in plan['buildings']:
        b = byid[item['object_id']]
        if b['height_evidence'] != 'OSM height tag':
            h = item.get('height_estimate_m')
            if isinstance(h,(int,float)) and 3<=h<=260:
                b.setdefault('source_height',b['height']);b['height']=h;b['height_evidence']='scene-estimated; not surveyed'
        b['scene_evidence'] = item['visibility'];b['reconstruction_level']='scene_informed_candidate'
        key=hashlib.sha256(b['id'].encode()).hexdigest()[:12];folder=run/'components'/key;folder.mkdir(parents=True,exist_ok=True)
        request_hash=canonical_hash({'input':signature,'plan':item,'building':b,'style':style,'contract':'local-scene-1'})
        cached=folder/'request.json'
        if (folder/'generator.ts').exists() and cached.exists() and json.loads(cached.read_text())['hash']==request_hash:continue
        footprint_sheet(b,folder/'footprint.png')
        prompt='''Build ONE architectural component, informed by the common scene plan and these actual photographs. Last attachment is its OSM footprint diagram; preceding STYLE images are explicitly listed below and are NOT factual geometry. Return JSON {source:"function buildComponent(b:any) { ... return group; }",notes:[],limitations:[]}.
THREE is in scope. No imports/exports, network, external textures, timers or randomness. The host passes LOCAL footprint coordinates around center [0,0] and places the group at its world anchor exactly once. X=east, Z=south, Y=up; never apply world coordinates or an arbitrary front rotation to the footprint. Preserve footprint edges, concavities and holes. Derive geometry from coordinates, not ring vertex indices that assume a six-point L. Keep emitted XZ bounds within footprint bounds plus 1.5 m. Ground=0, total height=b.height within 10%; use source ground-relative height, not absolute geodetic altitude. Return a local Group, do not assign objectId to children.
Stage the code in commented sections: 1 massing/exact plan, 2 roof/silhouette, 3 facade systems/opening recesses, 4 material binding/detail. Preserve each object's characteristic identity; plain context boxes are unacceptable. Shared helpers are permitted but adapt proportions/features from evidence. Keep unseen details simple and label them inferred. <=18000 triangles, <=1500 meshes, reuse geometry/materials and use InstancedMesh for repeats. CLOSED solids only: capped extrusions/cylinders/boxes. Every mesh must be individually manifold. Never split a closed roof into separate open material faces: use geometry groups on a single closed mesh or closed prisms. No zero-radius tips, negative transforms or coplanar overlapping faces. Concave extrusion can use exact triangulation into closed triangular prisms.
MATERIAL CONTRACT: distinct descriptive MeshStandardMaterials; all observed masonry/painted wall surfaces MUST have material.userData.textureRole from the required roles. Valid roles brick,plaster,stone,roof_tile. Brick/stone/roof tile use WHITE multiplier for scanned natural albedo; plaster retains evidenced paint tint and gets normal/roughness. Glass, metal roofs, trim can have intrinsic color without textureRole. Never use a generic wrong scan for slate/metal. Set meaningful roughness/metalness. Windows need visible recessed glazing and surrounds, not lines pasted over a solid flat wall. No invisible texture declarations. The renderer will reject missing required texture roles.
Use actual style images to guide fine readable architectural detailing, coherent surface frequency and convincing scale, without a fixed palette or toy exaggeration. Do not copy style-reference geography. Depth/recesses/roof proportions come from factual evidence, not style.\n'''
        prompt+='\nWorld footprint (subtract center for reasoning; HOST passes already local): '+json.dumps(b,ensure_ascii=False)+'\nComponent evidence plan: '+json.dumps(item,ensure_ascii=False)+'\nWhole scene ground/context: '+json.dumps(plan.get('ground',{}))+'\nStyle intent: '+json.dumps(style,ensure_ascii=False)
        prompt+='\nAdditional validated material roles may also be used from this registry: '+json.dumps(sorted(available_roles))
        details=[p for v,p in training if v.get('object_id')==b['id']]
        images=shared+details+style_images+[folder/'footprint.png']
        prompt+='\nAttachment order: '+str(len(shared))+' common FACTUAL scene images, '+str(len(details))+' target FACTUAL detail images, '+str(len(style_images))+' STYLE images, one FOOTPRINT diagram.'
        raw=provider.call('scene-component-'+key,prompt,images,provider.settings.code_model,11000)
        source=raw.get('source','')
        if source.count('function buildComponent(')!=1 or 'import ' in source or 'export ' in source:raise ValueError('SCENE_COMPONENT_CONTRACT')
        validate_source("import * as THREE from 'three';\n"+source+'\nexport function build(params:any={}) {return buildComponent(params);}')
        (folder/'generator.ts').write_text(source,encoding='utf-8');write_json(cached,{'hash':request_hash});write_json(folder/'notes.json',{k:v for k,v in raw.items() if k!='source'})
        provider.save_usage()
    city['scene_mode']=True
    city['observed_objects']=[b['id'] for b in city['buildings']]
    city['geometry_input_hash']=canonical_hash({k:v for k,v in city.items() if k!='geometry_input_hash'})
    write_json(run/'city.json',city);compose_scene(run,plan)
    write_json(run/'scene-contract.json',{'objects':{i['object_id']:{'required_texture_roles':i['required_texture_roles']} for i in plan['buildings']},'max_bound_deviation_m':3.0})
    return city


def placement_checks(city, objects, tolerance=3.0):
    expected={b['id']:b for b in city['buildings']}; failures=[]
    if len(objects)!=len(expected) or {o['id'] for o in objects}!=set(expected):return ['object coverage mismatch']
    for o in objects:
        b=expected[o['id']];xs=[p[0] for p in b['outer']];zs=[p[1] for p in b['outer']]
        deltas=[abs(o['min'][0]-min(xs)),abs(o['max'][0]-max(xs)),abs(o['min'][2]-min(zs)),abs(o['max'][2]-max(zs))]
        if max(deltas)>tolerance:failures.append({'id':b['id'],'bound_deltas_m':deltas})
        if abs(o['min'][1])>1:failures.append({'id':b['id'],'ground_y':o['min'][1]})
    return failures


def apply_mesh_height_evidence(city, evidence):
    """Update inferred heights only; retain tagged-height conflicts for explicit review."""
    ground=evidence.get('ground_height_m')
    if not isinstance(ground,(int,float)) or evidence.get('ground_samples',0)<3:
        raise ValueError('INSUFFICIENT_MESH_GROUND_EVIDENCE')
    origin=evidence.get('origin')
    if not origin or any(abs(origin[k]-city['origin'][k])>1e-6 for k in ['longitude','latitude']):
        raise ValueError('MESH_HEIGHT_ORIGIN_MISMATCH')
    byid={b['id']:b for b in city['buildings']};audit=[]
    for record in evidence.get('buildings',[]):
        b=byid.get(record.get('object_id'));height=record.get('estimated_height_m')
        if b is None or record.get('samples',0)<3 or not isinstance(height,(int,float)) or not 3<=height<=260:continue
        change=abs(height-b['height']);item={'object_id':b['id'],'original_height':b.get('source_height',b['height']),'sampled_height':height,'changed':False}
        if b['height_evidence']=='OSM height tag':
            item['tag_conflict']=change>max(5,b['height']*.2)
            item['note']='Tagged height preserved. A multilevel footprint needs part-level geometry, not a silent whole-building stretch.'
        else:
            b.setdefault('source_height',b['height']);b['height']=round(height,3)
            b['height_evidence']='sparse Google roof mesh relative to median road mesh; not surveyed'
            item['changed']=change>=.001
        b['mesh_height_evidence']=record;audit.append(item)
    city['geometry_input_hash']=canonical_hash({k:v for k,v in city.items() if k!='geometry_input_hash'})
    return {'source_hash':canonical_hash(evidence),'ground_height_m':ground,'objects':audit,'limitations':['Sparse maxima can include roof equipment. Ground median can contain canopy contamination. Tagged multilevel conflicts require explicit geometry interpretation.']}


def inspect_scene(run, manifest_path, provider, iteration=0):
    _,files,_=scene_inputs(manifest_path)
    style_images=sorted((run/'style-inputs').glob('*.jpg'))
    factual=[p for v,p,_ in files if not v.get('object_id') and (iteration>=2 or not v.get('held_out'))]
    images=factual+[run/'renders'/('styled-'+v+'.png') for v in ['overview','north','grid']]+style_images
    prompt='''Review the actual reconstructed small block. Attachment order: FACTUAL source views (the final validation iteration additionally includes the held-out angle), then THREE generated overview/north/top views, then STYLE references. Source covers a larger extent; judge only listed AOI. Generated viewpoints are not calibrated to source; do not confuse camera mismatch with geometry. Analyze all visible buildings, roofs, road/pavement surface treatment, vegetation, texture visibility and coherent scale. Distinguish inferred hidden surfaces. Return JSON {factual_accepted:boolean,style_accepted:boolean,issues:[{severity:"critical|major|minor",object_id:string,part:string,cause:"geometry|material|style|camera|data",evidence:string,action:string}],matched_features:[strings],missing_evidence:[strings],confidence:0..1}. Major/critical factual problems mean factual_accepted=false; style problems mean style_accepted=false. Do not accept plain block towers just for having windows. Do not give credit for maps that are not visible. Style is surface/detail/vegetation/composition, not copying palette or geography.\nAttachment counts: '''+str(len(factual))+' factual, 3 generated, '+str(len(style_images))+' style.\nScene plan: '+(run/'scene-plan.json').read_text(encoding='utf-8')
    raw=provider.call('scene-review-'+str(iteration),prompt,images,provider.settings.review_model,4500)
    if not isinstance(raw.get('factual_accepted'),bool) or not isinstance(raw.get('style_accepted'),bool) or not isinstance(raw.get('issues'),list):raise ValueError('SCENE_REVIEW_CONTRACT')
    if any(i.get('severity') in ['critical','major'] and i.get('cause')!='style' for i in raw['issues']):raw['factual_accepted']=False
    if any(i.get('severity') in ['critical','major'] and i.get('cause')=='style' for i in raw['issues']):raw['style_accepted']=False
    raw['held_out_included']=iteration>=2
    raw['visual_accepted']=raw['factual_accepted'] and raw['style_accepted'];raw['iteration']=iteration
    write_json(run/f'scene-review-{iteration:02d}.json',raw);write_json(run/'visual-review.json',raw)
    return raw


def sync_scene_components(run):
    """Persist actual validated/technically repaired source, not pre-repair caches."""
    source=(run/'building-generator.ts').read_text(encoding='utf-8')
    plan=json.loads((run/'scene-plan.json').read_text(encoding='utf-8'))
    for item in plan['buildings']:
        key=hashlib.sha256(item['object_id'].encode()).hexdigest()[:12]
        name='component_'+key
        start=source.index('function '+name+'(')
        ends=[p for token in ['\nfunction component_','\nexport function build('] if (p:=source.find(token,start+1))>=0]
        fragment=source[start:min(ends)].replace('function '+name+'(', 'function buildComponent(',1)
        path=run/'components'/key/'generator.ts'
        if path.read_text(encoding='utf-8')!=fragment:
            old=hashlib.sha256(path.read_bytes()).hexdigest()[:12]
            (path.parent/('before-'+old+'.ts')).write_bytes(path.read_bytes())
        path.write_text(fragment,encoding='utf-8')


def refine_scene(run, manifest_path, provider, review):
    """Target failing components, preserving host placement and the other modules."""
    from .quality import patch_fragment
    sync_scene_components(run)
    plan=json.loads((run/'scene-plan.json').read_text(encoding='utf-8'))
    _,files,_=scene_inputs(manifest_path)
    known={i['object_id'] for i in plan['buildings']};changed=False
    failing={i['object_id'] for i in review['issues'] if i.get('severity') in ['critical','major'] and i.get('object_id') in known and i.get('cause') in ['geometry','material','style']}
    for identifier in sorted(failing)[:2]:
        key=hashlib.sha256(identifier.encode()).hexdigest()[:12];path=run/'components'/key/'generator.ts'
        source=path.read_text(encoding='utf-8')
        issues=[i for i in review['issues'] if i.get('object_id')==identifier]
        images=[p for v,p,_ in files if not v.get('held_out') and (not v.get('object_id') or v['object_id']==identifier)]
        images.extend([run/'renders'/('styled-object-'+key+'.png'),*sorted((run/'style-inputs').glob('*.jpg'))])
        prompt='''Repair only this local architectural component using the factual shared/detail views, actual generated object render and final style reference. Return JSON {edits:[{old:"unique exact substring",new:"replacement"}],reason:string}. Host places the LOCAL group once; do not add world coordinates. Preserve footprint, required material roles and other components. Fix massing/roof/openings before ornaments. All meshes individually closed and manifold; never create separate open roof faces for color variation. Material identity must remain factual; style has no fixed palette. Source: '''+source+'\nIssues: '+json.dumps(issues,ensure_ascii=False)
        raw=provider.call('scene-refine-'+key,prompt,images,provider.settings.code_model,7000)
        write_json(run/'source-history'/('scene-refine-'+key+'.json'),raw)
        try:corrected=patch_fragment(source,raw.get('edits'))
        except ValueError as error:
            write_json(run/'source-history'/('scene-refine-rejected-'+key+'.json'),{'error':str(error)});continue
        validate_source("import * as THREE from 'three';\n"+corrected+'\nexport function build(params:any={}) {return buildComponent(params);}')
        (path.parent/'before-visual-refine.ts').write_text(source,encoding='utf-8');path.write_text(corrected,encoding='utf-8');changed=True
    if changed:compose_scene(run,plan)
    return changed
