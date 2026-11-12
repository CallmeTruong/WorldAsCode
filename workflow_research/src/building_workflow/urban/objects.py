"""Evidence-backed object modules; descriptive style never replaces appearance."""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw
from ..provider import write_json
from ..runtime import validate_source
from .style import canonical_hash


def reference_signature(manifest_path):
    manifest_path=Path(manifest_path).resolve();root=manifest_path.parent
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'));files=[]
    for record in manifest.get('objects',[]):
        for name in record['images']:
            p=(root/name).resolve()
            if not p.is_relative_to(root) or not p.is_file():raise ValueError('OBJECT_REFERENCE_PATH')
            if p.stat().st_size>15_000_000:raise ValueError('OBJECT_IMAGE_BYTE_LIMIT')
            with Image.open(p) as im:
                if im.width*im.height>30_000_000:raise ValueError('OBJECT_IMAGE_PIXEL_LIMIT')
            files.append({'path':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    return canonical_hash({'manifest':manifest,'images':files,'object_contract':'parts-0.2'})


def compose_sources(run,objects):
    base=(run/'base-building-generator.ts').read_text(encoding='utf-8')
    generic=base.replace('export function build(','function buildGeneric(',1)
    ids=[o['object_id'] for o in objects]
    wrapper='\nexport function build(params:any={}) {\n const all=params.city.buildings;\n const targets='+json.dumps(ids)+';\n const root=buildGeneric({...params,city:{...params.city,buildings:all.filter((b:any)=>!targets.includes(b.id))}});\n'
    fragments=[]
    for item in objects:
        name=item['function'];fragments.append((run/item['folder']/'generator.ts').read_text(encoding='utf-8'))
        wrapper+=f' const b_{name}=all.find((b:any)=>b.id==={json.dumps(item["object_id"])}); if(b_{name})root.add({name}(b_{name}));\n'
    source=generic+'\n'+'\n'.join(fragments)+wrapper+' return root;\n}\n'
    validate_source(source);(run/'building-generator.ts').write_text(source,encoding='utf-8')


def sync_object_sources(run):
    """Cache reusable modules from the validated final source, retaining originals."""
    manifest=run/'object-observations.json'
    if not manifest.exists():return
    source=(run/'building-generator.ts').read_text(encoding='utf-8')
    for item in json.loads(manifest.read_text(encoding='utf-8'))['objects']:
        name=item.get('function')
        if not name:continue
        start=source.index('function '+name+'(')
        ends=[p for token in ['\nfunction buildObserved_','\nexport function build('] if (p:=source.find(token,start+1))>=0]
        fragment=source[start:min(ends) if ends else len(source)].strip()+'\n'
        path=run/item['folder']/'generator.ts'
        if path.exists() and path.read_text(encoding='utf-8')!=fragment:
            digest=hashlib.sha256(path.read_bytes()).hexdigest()[:12]
            history=path.parent/'source-history';history.mkdir(exist_ok=True)
            (history/(digest+'.ts')).write_bytes(path.read_bytes())
        path.write_text(fragment,encoding='utf-8')


def footprint_sheet(building,path):
    """Map diagram, explicitly NOT aerial photography."""
    im=Image.new('RGB',(800,650),'#f5f5f0');draw=ImageDraw.Draw(im)
    xs=[p[0] for p in building['outer']];zs=[p[1] for p in building['outer']]
    scale=min(650/max(max(xs)-min(xs),1),490/max(max(zs)-min(zs),1))
    xy=lambda p:(75+(p[0]-min(xs))*scale,85+(p[1]-min(zs))*scale)
    draw.polygon([xy(p) for p in building['outer']],fill='#b7c2c8',outline='#213443',width=3)
    for h in building['holes']:draw.polygon([xy(p) for p in h],fill='#f5f5f0',outline='#213443',width=2)
    draw.text((20,15),'OSM FOOTPRINT DIAGRAM - NOT aerial/photo evidence. North is UP.',fill='#15232e')
    draw.text((20,610),'Metres: footprint only; roof partitions and facade proportions require photo evidence.',fill='#15232e')
    im.save(path)


def observed_objects(city,manifest_path:Path|None,run:Path,provider):
    if manifest_path is None:return city
    manifest_path=manifest_path.resolve();manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    root=manifest_path.parent;records=manifest.get('objects',[])
    if not 1<=len(records)<=4:raise ValueError('OBJECT_REFERENCE_PILOT_LIMIT_1_TO_4')
    signature=reference_signature(manifest_path)
    saved=run/'object-observations.json'
    if saved.exists():
        if json.loads(saved.read_text(encoding='utf-8'))['manifest_hash']!=signature:raise ValueError('OBJECT_REFERENCE_CHANGED_USE_NEW_RUN')
        return city
    source_path=run/'building-generator.ts'
    if not (run/'base-building-generator.ts').exists():
        (run/'base-building-generator.ts').write_text(source_path.read_text(encoding='utf-8'),encoding='utf-8')
    observations=[];byid={b['id']:b for b in city['buildings']}
    intent=json.loads((run/'style-profile.json').read_text(encoding='utf-8'))
    for record in records:
        identifier=record['object_id']
        if identifier not in byid:raise ValueError('OBJECT_REFERENCE_ID_NOT_IN_AOI')
        b=byid[identifier];paths=[]
        folder=run/'objects'/hashlib.sha256(identifier.encode()).hexdigest()[:12];folder.mkdir(parents=True,exist_ok=True)
        for i,name in enumerate(record['images']):
            with Image.open(root/name) as im:
                im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((1600,1600));copied=folder/f'reference-{i:02d}.jpg';im.save(copied,quality=94);paths.append(copied)
        diagram=folder/'footprint.png';footprint_sheet(b,diagram)
        context='\nBuilding: '+json.dumps(b,ensure_ascii=False)+'\nReference notes: '+json.dumps(record.get('image_notes',[]))+'\nFront hint (inferred): '+json.dumps(record.get('camera_hint',{}))
        prompt='''Analyze ONLY the named target building in these factual photos. Last image is an OSM FOOTPRINT DIAGRAM, not an aerial image. Segment identity into parts BEFORE code. Return JSON {name,observed_floors,main_masses:[],roof_structure,facade:{symmetry,columns,openings,distinctive_features:[]},materials:[],critical_identity_features:[],uncertainty:[],confidence,part_plan:[{name,visible_evidence,normalized_proportions,geometry_approach,material_identity}],height_assessment:{conflict:boolean,reason,suggested_height_m:number|null},camera_plan:{front_normal_xz:[x,z],evidence},missing_views:[]}.
Do not mistake background towers for the target. Separate night lighting from intrinsic color. Identify roof silhouette, raised stairs, recessed openings, railings, moldings and material boundaries. Use ratios/part relationships, not invented exact dimensions. Estimate hidden sides cautiously. If OSM height contradicts clear storey counts, flag conflict and suggest approximate metric height with uncertainty instead of flattening the tower to a wrong height. No top-down photo means roof depth/partitions uncertain. Camera plan is approximate, never calibrated.'''+context
        obs=provider.call('object-parts-observe',prompt,[*paths,diagram],provider.settings.vision_model,4500)
        if not obs.get('part_plan') or not obs.get('critical_identity_features') or not obs.get('uncertainty'):raise ValueError('INVALID_OBJECT_PART_PLAN')
        write_json(folder/'observation.json',obs);write_json(folder/'reference-provenance.json',record)
        b['front_normal_hint']=obs.get('camera_plan',{}).get('front_normal_xz') or record.get('camera_hint',{}).get('front_normal_xz',[0,1])
        h=obs.get('height_assessment',{});suggested=h.get('suggested_height_m')
        if h.get('conflict') and isinstance(suggested,(int,float)) and 3<=suggested<=260:
            b['source_height']=b['height'];b['height']=suggested;b['height_evidence']='inferred photo storey estimate; conflict with OSM: '+str(h.get('reason',''))
        if isinstance(obs.get('observed_floors'),int) and 1<=obs['observed_floors']<=70:
            b['floors']=obs['observed_floors'];b['floor_evidence']='photo estimate; not calibrated'
        prompt='''Reconstruct this ONE building from factual photos and its PART PLAN. Return JSON {source:"function buildObservedObject(b:any) { ... return group; }",notes:[],limitations:[]}.
THREE is in scope; no imports/exports except the single function, no network, host APIs, timers or randomness. Local helper functions allowed. group.name=b.id;group.userData.objectId=b.id. Geometry closed solids, positive transforms, <=35000 triangles and <=1200 meshes per object; use InstancedMesh for repeated windows/balusters. All details must be geometrically visible at object inspection distance.
FIRST shape masses/ROOF SILHOUETTE from the photo; THEN openings with reveal depth, cornices, balcony/rails, base/stairs, columns and identity ornaments. Do not place an unbroken box behind openings/arches that should be recessed. Roof slopes run in the actual intended axis; avoid giant vertical gable walls. Project stairs in front of the facade where visible. Preserve footprint anchor: place the local object group at (b.center[0],0,b.center[1]) exactly once. Fit each subdivision to projected ring bounds. Build local x=right,z=front with normal=b.front_normal_hint; rotationY=atan2(normal.x,normal.z). Normalize plan dimensions to footprint extents; do not copy dimensions from another building. Facades need multiple distinct surfaces, never a grid over a single slab. Shape roof sections rather than extrude the entire footprint to max height. Height tolerance is a technical bound, not a requirement to put every roof at the same elevation.
MATERIAL IDENTITY: create distinct MeshStandardMaterials with descriptive per-part names (any safe name), intrinsic photo-based color, appropriate roughness/metalness. Renderer PRESERVES them; no global palette. Explicit material.userData.textureRole may be plaster,roof_tile,stone,brick,road,pavement; only select maps appropriate to that surface, omit for clean painted trim/glass. Natural tile/brick retain scanned albedo; use a WHITE color multiplier with naturally colored maps to avoid dark double tint. Do not use stone texture as a facade/window substitute. Glass may use physical roughness and metalness, opaque approximation acceptable. No generated images/textures/URLs. Material color must not include cast shadows or night illumination. Semantic roles are not limited to five. No open PlaneGeometry or uncapped TubeGeometry. Use nonzero cylinder radii to avoid degenerate tips; smooth analytic surfaces need valid normals.
Style intent is soft guidance for detail readability and form treatment; it must never override factual colors/materials or identity. Unseen geometry must be disclosed. Factual images and last footprint diagram follow.
'''+context+'\nUpdated target: '+json.dumps(b,ensure_ascii=False)+'\nPart plan: '+json.dumps(obs,ensure_ascii=False)+'\nArtistic intent: '+json.dumps(intent,ensure_ascii=False)
        raw=provider.call('object-parts-codegen',prompt,[*paths,diagram],provider.settings.code_model,11000)
        fragment=raw['source'];safe_name='buildObserved_'+hashlib.sha256(identifier.encode()).hexdigest()[:10]
        if fragment.count('function buildObservedObject(')!=1 or 'import ' in fragment or 'export ' in fragment:raise ValueError('OBJECT_GENERATOR_FRAGMENT_CONTRACT')
        fragment=fragment.replace('function buildObservedObject(',f'function {safe_name}(',1)
        (folder/'generator.ts').write_text(fragment,encoding='utf-8');write_json(folder/'generation-notes.json',{k:v for k,v in raw.items() if k!='source'})
        b['facade_evidence']='per-object photo part plan; reconstruction not calibrated';b['reconstruction_level']='photo_reconstruction_candidate'
        observations.append({'object_id':identifier,'function':safe_name,'folder':folder.relative_to(run).as_posix(),'observation':obs,'reference':record,'image_count':len(paths)})
        # Save each finished module so a failed later call resumes from API cache.
        compose_sources(run,observations)
    city['observed_objects']=[r['object_id'] for r in observations]
    city['geometry_input_hash']=canonical_hash({k:v for k,v in city.items() if k!='geometry_input_hash'})
    write_json(run/'city.json',city);write_json(saved,{'manifest_hash':signature,'objects':observations,'coverage':{'observed':len(observations),'total_buildings':len(city['buildings']),'unobserved':len(city['buildings'])-len(observations)}})
    return city
