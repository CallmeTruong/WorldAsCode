import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import time
import subprocess
import sys
from urllib.parse import urlparse
from typing import TypedDict
from langgraph.graph import StateGraph,START,END
from langgraph.checkpoint.sqlite import SqliteSaver
from ..config import ROOT,Settings,SKILL_COMMIT
from ..provider import Provider,write_json
from .style import extract_style,canonical_hash,presentation_settings
from .data import build_city
from .assets import material_assets
from .generate import generate_buildings,repair_source
from .runtime import capture_city
from .report import make_report,paired_images
from .objects import observed_objects,reference_signature,sync_object_sources
from .reuse import cell_artifacts
from .quality import inspect_objects,refine_objects
from .vegetation import apply_tree_observations
from .scene import scene_inputs,build_scene,inspect_scene,refine_scene,sync_scene_components


class UrbanState(TypedDict,total=False):
    city_hash:str
    style_hash:str
    source_hash:str
    render_ok:bool
    review:dict
    finalized:bool


def update_run_config(run,config,resume_code_update=False):
    path=run/'urban-config.json'
    if path.exists():
        previous=json.loads(path.read_text(encoding='utf-8'))
        if previous!=config:
            strip=lambda c:{k:v for k,v in c.items() if k!='implementation_hash'}
            if not resume_code_update or strip(previous)!=strip(config):raise ValueError('URBAN_RUN_ID_CONFIG_MISMATCH')
            write_json(run/'config-history'/f'before-code-update-{time.time_ns()}.json',previous)
    write_json(path,config)


def run_urban(style_dir:Path|None,run_id='district1-pilot',max_calls=12,max_tokens=180000,max_seconds=2400,rerender=False,reuse_run_id=None,object_refs:Path|None=None,
              size=400.,longitude=106.702,latitude=10.775,grid=2,max_visual_refinements=1,resume_code_update=False,osm_snapshot=None,tree_observations=None,scene_refs=None,reference_url=None):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,80}',run_id):raise ValueError('INVALID_RUN_ID')
    run=ROOT/'runs/urban'/run_id;run.mkdir(parents=True,exist_ok=True)
    if reuse_run_id:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,80}',reuse_run_id):raise ValueError('INVALID_REUSE_RUN_ID')
        parent=ROOT/'runs/urban'/reuse_run_id
        if parent==run:raise ValueError('REUSE_REQUIRES_DIFFERENT_RUN_ID')
        for path in parent.glob('osm-relation-*.osm'):
            if not (run/path.name).exists():shutil.copy2(path,run/path.name)
        if not (run/'building-generator.ts').exists():
            shutil.copy2(parent/'building-generator.ts',run/'building-generator.ts')
            write_json(run/'reuse-manifest.json',{'parent_run':reuse_run_id,'source_sha256':hashlib.sha256((run/'building-generator.ts').read_bytes()).hexdigest(),
                'scope':'Reuse API-authored parameterized building source; normalized city/roads rebuilt from original snapshot. No claim of new per-building inference.'})
    styles=sorted(style_dir.resolve().iterdir()) if style_dir else []
    refs=[{'name':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in styles if p.is_file() and p.suffix.lower() in ['.png','.jpg','.jpeg','.webp']]
    snapshot=Path(osm_snapshot).resolve() if osm_snapshot else ROOT.parent/'docs/research/2026-11-12-district1-osm.osm'
    config={'run_id':run_id,'style_reference_set':refs,'max_calls':max_calls,'max_tokens':max_tokens,'max_active_seconds':max_seconds,
        'source_snapshot_sha256':hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        'scope':{'size_m':size,'longitude':longitude,'latitude':latitude,'grid':grid},'max_visual_refinements':max_visual_refinements,
        'skill_commit':SKILL_COMMIT,'workflow_version':'urban-0.2',
        'implementation_hash':canonical_hash({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [*Path(__file__).parent.glob('*.py'),* (ROOT/'runtime').glob('urban-*.mjs')]})}
    if reuse_run_id:config['reuse_run_id']=reuse_run_id
    if reference_url:
        url=urlparse(reference_url)
        if url.scheme!='http' or url.hostname not in ['127.0.0.1','localhost'] or url.username or url.password or url.query:raise ValueError('REFERENCE_URL_MUST_BE_LOCAL_SERVICE')
        config['reference_url']=reference_url
    if scene_refs:config['scene_reference_hash']=scene_inputs(scene_refs)[2]
    if object_refs:config['object_reference_set_hash']=reference_signature(object_refs)
    if tree_observations:config['tree_observations_sha256']=hashlib.sha256(Path(tree_observations).read_bytes()).hexdigest()
    update_run_config(run,config,resume_code_update)
    api=Provider(Settings.load(),run,max_calls,max_tokens,max_seconds)
    def node(name,fn):
        def wrapped(state):
            if api.elapsed()>=max_seconds:raise RuntimeError('URBAN_ACTIVE_TIME_BUDGET')
            t=time.monotonic();api.trace('urban_stage_start',stage=name)
            result=fn(state);api.save_usage();api.trace('urban_stage_complete',stage=name,seconds=time.monotonic()-t)
            print(json.dumps({'stage':name,'seconds':round(time.monotonic()-t,2)},ensure_ascii=True),flush=True)
            return result
        return wrapped
    def prepare(state):
        if not (run/'city.json').exists():city=build_city(run,snapshot=snapshot,size=size,longitude=longitude,latitude=latitude,grid=grid)
        else:city=json.loads((run/'city.json').read_text(encoding='utf-8'))
        if tree_observations:
            city=apply_tree_observations(city,tree_observations);write_json(run/'city.json',city)
        boundary=json.loads((run/'boundary-checks.json').read_text())
        if boundary['symmetric_difference_area_m2']>1e-6 or not boundary['one_owner_per_building'] or not boundary['object_ids_unique']:
            raise RuntimeError('CITY_BOUNDARY_CONTRACT_FAILED')
        return {'city_hash':city['geometry_input_hash']}
    def style(state):
        profile=extract_style(style_dir,run,api)
        write_json(run/'presentation-settings.json',{'styled':presentation_settings(profile,api if style_dir else None),'neutral':presentation_settings(profile)})
        return {'style_hash':profile.get('profile_hash',canonical_hash(profile))}
    def evidence(state):
        if not scene_refs or not reference_url:return {}
        from .scene import apply_mesh_height_evidence
        from .ground import apply_ground_observations
        city=json.loads((run/'city.json').read_text(encoding='utf-8'))
        height_path=run/'mesh-height-evidence.json'
        ground_path=run/'ground-observation/ground-observations.json'
        if not height_path.exists():
            subprocess.run([sys.executable,str(ROOT/'scripts/measure_google_block.py'),'--city',str(run/'city.json'),'--output',str(height_path),'--url',reference_url],cwd=ROOT,check=True,timeout=240)
        if not ground_path.exists():
            subprocess.run([sys.executable,str(ROOT/'scripts/observe_google_ground.py'),'--output',str(ground_path.parent),'--longitude',str(longitude),'--latitude',str(latitude),'--url',reference_url,'--style-image',str(run/'style-contact-sheet.jpg'),'--ground-height',str(json.loads(height_path.read_text())['ground_height_m']),'--range',str(max(150,size*2.5))],cwd=ROOT,check=True,timeout=400)
        write_json(run/'mesh-height-checks.json',apply_mesh_height_evidence(city,json.loads(height_path.read_text(encoding='utf-8'))))
        write_json(run/'ground-checks.json',apply_ground_observations(city,json.loads(ground_path.read_text(encoding='utf-8'))))
        write_json(run/'city.json',city)
        return {'city_hash':city['geometry_input_hash']}
    def assets(state):
        material_assets(run);return {}
    def generate(state):
        source=generate_buildings(json.loads((run/'city.json').read_text(encoding='utf-8')),run,api)
        return {'source_hash':hashlib.sha256(source.read_bytes()).hexdigest()}
    def render(state):
        old=run/'renders'
        if old.exists():
            archive=run/'experiments'/f'before-render-{time.time_ns()}'
            archive.mkdir(parents=True,exist_ok=True)
            for p in old.glob('*.png'):shutil.copy2(p,archive/p.name)
            for name in ['urban-runtime-result.json','urban-geometry-checks.json']:
                if (run/name).exists():shutil.copy2(run/name,archive/name)
        for attempt in range(3):
            try:
                capture_city(run,timeout=min(240,max(10,max_seconds-api.elapsed())))
                return {'render_ok':True,'source_hash':hashlib.sha256((run/'building-generator.ts').read_bytes()).hexdigest()}
            except RuntimeError as error:
                api.trace('urban_render_failure',attempt=attempt+1,error=str(error))
                evidence=run/'experiments'/f'failed-attempt-{attempt+1}-{time.time_ns()}'
                evidence.mkdir(parents=True,exist_ok=True)
                for name in ['urban-runtime-result.json','urban-geometry-checks.json','urban-compile.log','building-generator.ts']:
                    if (run/name).exists():shutil.copy2(run/name,evidence/name)
                if attempt>=2 or any(v in str(error) for v in ['TIMEOUT','MEMORY','BROWSER_ERRORS']):raise
                repair_source(run,api,error)
        raise RuntimeError('URBAN_RENDER_RETRIES_EXHAUSTED')
    def review(state):
        if scene_refs:
            result=inspect_scene(run,scene_refs,api)
            for iteration in range(max_visual_refinements):
                if result['visual_accepted'] or not refine_scene(run,scene_refs,api,result):break
                render(state);result=inspect_scene(run,scene_refs,api,iteration+1)
            result=inspect_scene(run,scene_refs,api,2)
            return {'review':result}
        if (run/'object-observations.json').exists():
            result=inspect_objects(run,api,0)
            for iteration in range(max_visual_refinements):
                if result['visual_accepted'] or not refine_objects(run,api,result):break
                render(state)
                result=inspect_objects(run,api,iteration+1)
            write_json(run/'visual-review.json',result)
            return {'review':result}
        paired_images(run)
        images=[run/'comparison-overview.jpg',run/'renders/styled-street.png']
        if (run/'style-contact-sheet.jpg').exists():images.append(run/'style-contact-sheet.jpg')
        prompt="""Review this actual procedural urban pilot. Attachment 1: neutral vs styled SAME geometry and camera; attachment 2 street view; attachment 3 if present the user's STYLE reference contact sheet. The reference is NOT Ho Chi Minh City geometry and must not be used as a factual comparison. City geometry is derived from OSM footprints; heights without tags and all facades are inferred. Evaluate visual defects, style correspondence, texture scaling, readability and consistency. Do not claim real facade fidelity or infer exact real measurements. Return JSON {"style_score":0..1,"visual_coherence":0..1,"confidence":0..1,"factual_facade_accuracy":null,"matched_style_features":[strings],"issues":[{"severity":"critical|major|minor","component":"...","cause":"geometry|material|camera|data","fix":"..."}],"limitations":[strings],"recommended_next_experiment":"..."}. Acknowledge that palette/shading cannot reproduce full detail from the style reference alone. Be specific about actual images, not generic praise. Profile:
"""+(run/'style-profile.json').read_text(encoding='utf-8')
        if (run/'object-observations.json').exists():
            observed=json.loads((run/'object-observations.json').read_text(encoding='utf-8'))
            item=observed['objects'][0];images.extend([run/item['folder']/'reference-00.jpg',run/'renders/styled-landmark.png'])
            prompt+='\nAdditional last TWO images are a licensed FACTUAL reference of the selected observed building, then its actual generated close-up (camera not calibrated). Compare observed identity separately: add object_review {matched_features:[],missing_features:[],confidence:0..1}. Factual reference is not the style reference. Only '+str(observed['coverage']['observed'])+' of '+str(observed['coverage']['total_buildings'])+' buildings have per-object photo evidence; all others are inferred facades. Do not claim whole-area facade accuracy. Object observations: '+json.dumps(item['observation'])
        result=api.call('urban-visual-review',prompt,images,api.settings.review_model,3500)
        if not isinstance(result.get('issues'),list):raise ValueError('INVALID_URBAN_REVIEW')
        write_json(run/'visual-review.json',result);return {'review':result}
    def finalize(state):
        if scene_refs:sync_scene_components(run)
        sync_object_sources(run)
        cell_artifacts(json.loads((run/'city.json').read_text(encoding='utf-8')),json.loads((run/'style-profile.json').read_text(encoding='utf-8')),run)
        make_report(run,state.get('review'));return {'finalized':True}
    def objects(state):
        current=json.loads((run/'city.json').read_text(encoding='utf-8'))
        city=build_scene(current,scene_refs,run,api) if scene_refs else observed_objects(current,object_refs,run,api)
        return {'city_hash':city['geometry_input_hash'],'source_hash':hashlib.sha256((run/'building-generator.ts').read_bytes()).hexdigest()}
    graph=StateGraph(UrbanState)
    stages=[('prepare',prepare),('style',style),('evidence',evidence),('assets',assets),('generate',generate),('objects',objects),('render',render),('review',review),('finalize',finalize)]
    last=START
    for name,fn in stages:graph.add_node(name,node(name,fn));graph.add_edge(last,name);last=name
    graph.add_edge(last,END)
    with sqlite3.connect(run/'urban-checkpoint.sqlite',check_same_thread=False) as connection:
        app=graph.compile(checkpointer=SqliteSaver(connection));settings={'configurable':{'thread_id':run_id}}
        current=app.get_state(settings)
        if current.values and not current.next and not rerender:return run
        initial={} if rerender or not current.values else None
        try:app.invoke(initial,settings)
        except Exception as exc:
            write_json(run/'urban-failure.json',{'error':type(exc).__name__+': '+str(exc)[:500],
                'recovery':'Inspect checkpoint, compile/geometry/runtime evidence. Resume unchanged config or use a new ID for changed inputs.'})
            raise
    return run
