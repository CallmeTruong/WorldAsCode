"""Observer -> critic -> work order -> coder -> validator -> critic, with persisted feedback."""
import hashlib
import json
import shutil
import time
from pathlib import Path
from ..config import Settings
from ..provider import Provider,write_json,BudgetExceeded
from ..runtime import validate_source
from .scene_first import prepare_scene_run,compact_image,label_scene,evidence_packet,apply_adjustments,acceptable,make_report
from .strict_loop import paired_images,snapshot_runtime,restore_runtime
from .quality import patch_fragment
from .runtime import capture_city
from .geometry_evidence import load_geometry_evidence,label_source_heights

TOOLS = '''The trusted worker passes params.tools with optional tested geometry tools:
params.tools.gableRoof({length,width,eave,rise,center:[localX,localZ],rotation:radians,material}) returns one CLOSED triangular-prism roof, ridge along local X before Y rotation. Eave is absolute local Y, peak=eave+rise. Split an L into appropriate rectangular wings and join their ridges; do not put a roof strip on every perimeter edge leaving an exposed wall-material cap.
params.tools.hipRoof({length,width,eave,rise,inset,center:[x,z],rotation,material}) returns a CLOSED truncated hip roof, inset < min(length,width)/2.
params.tools.extrudeFootprint({outer:[[x,z],...],holes:[],base,height,material}) returns a CLOSED extruded polygon with holes. Use roof wells, setbacks and properly sized parts rather than shrinking the entire footprint into a pyramid. Tools are optional; arbitrary Three geometry remains available.
'''


def validate_observations(raw,city):
    expected={b['id'] for b in city['buildings']}
    if not isinstance(raw.get('objects'),list) or {o.get('owner') for o in raw['objects']}!=expected or len(raw['objects'])!=len(expected):raise ValueError('OBSERVER_OBJECT_COVERAGE')
    feature_ids=[]
    for obj in raw['objects']:
        if not obj.get('features'):raise ValueError('OBSERVER_EMPTY_FEATURES')
        for f in obj['features']:
            if not f.get('id') or not f.get('observation') or not f.get('evidence_views') or f.get('confidence') not in ('high','medium','low'):raise ValueError('OBSERVER_FEATURE_SCHEMA')
            feature_ids.append(f['id'])
    if len(feature_ids)!=len(set(feature_ids)) or not raw.get('style_contract'):raise ValueError('OBSERVER_FEATURE_IDS_OR_STYLE')
    return raw


def validate_review(raw,observations):
    acceptable(raw)  # validate scores, severities and finite values
    expected={o['owner'] for o in observations['objects']}
    all_checks=raw.get('object_checks',[])
    shared_ids={f['id'] for f in observations.get('shared_scene_features',[])}
    shared=[];checks=[]
    for obj in all_checks:
        if obj.get('owner') in expected:checks.append(obj)
        elif obj.get('features') and {f.get('id') for f in obj['features']}.issubset(shared_ids):shared.append(obj)
        else:raise ValueError('CRITIC_UNKNOWN_OWNER_OR_SHARED_FEATURE')
    raw['object_checks']=checks
    if shared:raw['shared_checks']=shared
    if len(checks)!=len(expected) or {o.get('owner') for o in checks}!=expected:raise ValueError('CRITIC_OBJECT_COVERAGE')
    known={f['id'] for o in observations['objects'] for f in o['features']}
    owners={f['id']:o['owner'] for o in observations['objects'] for f in o['features']}
    tested=[]
    for obj in checks:
        for check in obj.get('features',[]):
            if check.get('id') not in known or check.get('status') not in ('matched','partial','missing','uncertain'):raise ValueError('CRITIC_UNKNOWN_FEATURE')
            if owners[check['id']]!=obj['owner']:raise ValueError('CRITIC_FEATURE_OWNER')
            tested.append(check['id'])
    if set(tested)!=known or len(tested)!=len(known):raise ValueError('CRITIC_FEATURE_COVERAGE')
    style_ids={s['id'] for s in observations['style_contract']}
    style_checks=raw.get('style_checks',[])
    if len(style_checks)!=len(style_ids) or {s.get('id') for s in style_checks}!=style_ids:raise ValueError('CRITIC_STYLE_COVERAGE')
    for s in style_checks:
        if s.get('status') not in ('matched','partial','missing'):raise ValueError('CRITIC_STYLE_STATUS')
    for issue in raw['issues']:
        if not issue.get('id') or not issue.get('owner') or not issue.get('evidence') or not issue.get('repair'):raise ValueError('CRITIC_UNACTIONABLE_ISSUE')
    existing={i['id'] for i in raw['issues']}
    inventory={f['id']:(o['owner'],f) for o in observations['objects'] for f in o['features']}
    for obj in checks:
        for check in obj['features']:
            owner,feature=inventory[check['id']]
            if check['status']=='missing' and feature.get('importance')=='identity' and feature['confidence']=='high' and check['id'] not in existing:
                raw['issues'].append({'id':check['id'],'owner':owner,'severity':'major','part':feature['part'],'evidence':check.get('evidence','Missing confirmed identity feature.'),'repair':'Restore the observed feature: '+feature['observation'],'impact':5,'gate_added':True})
    for check in style_checks:
        if check['status']=='missing' and check['id'] not in existing:
            raw['issues'].append({'id':check['id'],'owner':'scene-style','severity':'major','part':'style correspondence','evidence':check.get('evidence','Missing style feature.'),'repair':check.get('repair') or next(s['application'] for s in observations['style_contract'] if s['id']==check['id']),'impact':4,'gate_added':True})
    raw['accepted']=acceptable(raw)
    return raw


def work_order(review,observations,iteration):
    rank={'critical':0,'major':1,'minor':2}
    tasks=sorted(review['issues'],key=lambda i:(rank[i['severity']],-i.get('impact',1),i['id']))[:4]
    return {'iteration':iteration,'tasks':tasks,'style_contract':observations['style_contract'],
            'verification':'Critic rechecks all observed features on real renders; coder completion claims never establish success.',
            'geometry_tools':TOOLS,'preserve':'Shared coordinates, target IDs, verified heights/footprints, correct sibling details; no forced texture list.'}


def review_better(old,new):
    # Qualitative scores may fluctuate; also track stable feature defects.
    blockers=lambda r:{i['id'] for i in r['issues'] if i['severity'] in ('critical','major')}
    critical=lambda r:sum(i['severity']=='critical' for i in r['issues'])
    return critical(new)<=critical(old) and all(new['scores'][k]>=min(old['scores'][k],3) for k in old['scores']) and (
        sum(new['scores'].values())>sum(old['scores'].values()) or blockers(new)<blockers(old))


def validate_evidence_captures(run,views):
    path=run/'evidence-captures.json'
    if not path.exists():raise ValueError('EVIDENCE_CAPTURE_MANIFEST_MISSING')
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('contract')!='matching-source-visibility-v2':raise ValueError('EVIDENCE_CAPTURE_CONTRACT')
    if data.get('source_sha256')!=hashlib.sha256((run/'building-generator.ts').read_bytes()).hexdigest():raise ValueError('EVIDENCE_CAPTURE_SOURCE_CHANGED')
    records={r['id']:r for r in data['views']}
    for view in views:
        item=records.get(view['id']);expected='isolated-object' if view.get('object_id') else 'whole-scene'
        if not item or item.get('mode')!=expected or item.get('object_id')!=view.get('object_id') or item.get('camera')!=view['local_camera']:raise ValueError('EVIDENCE_CAMERA_OR_VISIBILITY_MISMATCH')
        if view.get('object_id') and item.get('visible_object_ids')!=[view['object_id']]:raise ValueError('EVIDENCE_VISIBLE_OBJECTS')
        image=run/'renders'/f'evidence-{view["id"]}.png'
        if not image.exists() or hashlib.sha256(image.read_bytes()).hexdigest()!=item.get('sha256'):raise ValueError('EVIDENCE_CAPTURE_IMAGE_CHANGED')
    return data


class SceneWorkflow:
    def __init__(self,parent,evidence,run,max_repairs=3,resume=False):
        self.parent,self.evidence,self.run=Path(parent),Path(evidence),Path(run)
        self.max_repairs=max_repairs
        self.resume=resume
        if resume:
            city=json.loads((self.run/'city.json').read_text(encoding='utf-8'));views=json.loads((self.evidence/'source-views.json').read_text())['views']
            prepared={'city':city,'views':views,'styles':sorted((self.run/'style-inputs').glob('*.jpg')),
                      'training':[v for v in views if not v.get('held_out') and v['id'] in ('overhead','south','west','north','east')],
                      'held':[v for v in views if v.get('held_out')]}
            if any((self.run/'iterations').glob('*/work-order.json')):raise ValueError('RESUME_REQUIRES_OBSERVATION_OR_INITIAL_REVIEW_STAGE')
        else:prepared=prepare_scene_run(self.parent,self.evidence,self.run,expanded_context=True)
        self.city=prepared['city'];self.views=prepared['views'];self.styles=prepared['styles']
        self.training=prepared['training'];self.held=prepared['held']
        self.details=[]
        for b in self.city['buildings']:
            available=[v for v in self.views if not v.get('held_out') and v.get('object_id')==b['id']]
            if available:self.details.append(available[0])
        selected=self.training+self.details+self.held
        plan={'views':['overview','north','grid'],'objects':[],'evidence_views':selected,'benchmark_frames':6}
        if resume and json.loads((self.run/'capture-plan.json').read_text())!=plan:raise ValueError('RESUME_CAMERA_PLAN_CHANGED')
        write_json(self.run/'capture-plan.json',plan)
        s=Settings.load();s.model=s.code_model=s.vision_model=s.review_model='gpt-6-sol'
        self.api=Provider(s,self.run,max_calls=14,max_tokens=600000,max_seconds=2700,max_attempts=1,request_timeout=240)
        self.source=self.run/'building-generator.ts'
        self.events=json.loads((self.run/'workflow-state.json').read_text()).get('events',[]) if resume else []
        self.geometry_evidence=load_geometry_evidence(self.city,self.evidence)
        write_json(self.run/'source-geometry-evidence.json',self.geometry_evidence)

    def node(self,name,fn):
        started=time.monotonic();write_json(self.run/'workflow-state.json',{'node':name,'status':'running','events':self.events})
        self.api.trace('node_start',node=name)
        status='interrupted'
        try:
            result=fn();status='complete';return result
        except Exception:
            status='failed';raise
        finally:
            event={'node':name,'status':status,'seconds':round(time.monotonic()-started,3)};self.events.append(event)
            write_json(self.run/'workflow-state.json',{'node':name,'status':status,'events':self.events});self.api.trace('node_end',**event);self.api.save_usage()

    def observer(self):
        root=self.run/'observer';root.mkdir(exist_ok=True)
        if (root/'observations.json').exists():shutil.copy2(root/'observations.json',root/('previous-'+str(len(self.events))+'.json'))
        folder=root/f'pass-{len(self.events):02d}';folder.mkdir(exist_ok=True)
        common=[v for v in self.training if v['id'] in ('overhead','west')]
        factual=[]
        for v in common+self.details:
            image=compact_image(self.evidence/v['image'],folder/(v['id']+'.jpg'));label_scene(image,self.city,v);label_source_heights(image,self.city,v,self.geometry_evidence);factual.append(image)
        prompt='''You are the EVIDENCE OBSERVER node, not the coder or output judge. Inspect the whole area and the provided building details, then make a compact feature inventory that other nodes can verify. First images are factual, followed by STYLE reference images, then OSM ID diagram. Yellow tags are projected identity annotations, not source geometry. Only the target IDs are buildings to reconstruct; unlabelled background towers are not low target buildings. Black clipped backgrounds/photogrammetry holes are not actual walls, passages or paint. For each target identify 3-5 decisive observable features: silhouette/roof topology, facade hierarchy, material/color family, distinctive parts. Give their view IDs and confidence. Approximate physical colors are observations per object, never a STYLE palette. Ground/style are shared scene responsibilities. Describe STYLE through form, detail scale, surface readability, natural/graphic treatment and lighting, without requiring RGB values, copying geography or uniformizing materials. Distinguish hidden details from observable mismatches. Return JSON {objects:[{owner:exactID,features:[{id:globally_unique_stable_string,part,observation,evidence_views:[],confidence:"high|medium|low",importance:"identity|supporting"}]}],shared_scene_features:[],style_contract:[{id,observation,application,reference_images:[]}],data_conflicts:[],uncertainties:[]}. Retain feature IDs across later reviews. Do not repeat vague demands like "more detail". Scene/camera data: '''+json.dumps(evidence_packet(self.city,common+self.details),ensure_ascii=False)+'\nFactual attachment order: '+json.dumps([{'id':v['id'],'owner':v.get('object_id'),'image':v['image']} for v in common+self.details])+'\nStyle intent: '+(self.run/'style-profile.json').read_text(encoding='utf-8')
        prompt+='\nBlue source anchors label source-mesh height above local ground, not target geometry. Ground/tower-roof levels can look misleading in photographs; resolve them from spatial anchors and multiview evidence. Do not invent a low podium or move rooftop features to ground if source anchors place them at the upper roof. Numerical source levels: '+json.dumps(self.geometry_evidence)
        raw=self.api.call('node-observer',prompt,factual+self.styles+[self.run/'scene-map.png'],self.api.settings.vision_model,5500)
        validate_observations(raw,self.city);write_json(folder/'observations.json',raw);write_json(root/'observations.json',raw);return raw

    def render(self,stage):
        try:return capture_city(self.run,timeout=480)
        except RuntimeError as exc:
            if any(t in str(exc) for t in ('TIMEOUT','MEMORY')):raise
            folder=self.run/'technical'/stage;folder.mkdir(parents=True)
            diagnostics={'error':str(exc)}
            for name in ('urban-runtime-result.json','urban-compile.log','urban-geometry-checks.json','placement-checks.json','urban-bounds-failures.json'):
                path=self.run/name
                if path.exists():
                    shutil.copy2(path,folder/name)
                    if path.suffix=='.json':
                        value=json.loads(path.read_text(encoding='utf-8'))
                        if name=='urban-geometry-checks.json':
                            failed=[m for m in value.get('meshes',[]) if m.get('boundaryEdges',0) or m.get('nonManifoldEdges',0) or m.get('normalConsistency',{}).get('consistent') is False]
                            value={k:v for k,v in value.items() if k not in ('meshes','architectural_id_mapping')};value['failing_meshes']=failed[:8]
                        diagnostics[name]=value
                    else:diagnostics[name]=path.read_text(encoding='utf-8')[:6000]
            source=self.source.read_text(encoding='utf-8');(folder/'before.ts').write_text(source,encoding='utf-8')
            prompt='You are the TECHNICAL REPAIR node. Fix the actual compiler/topology/placement errors without removing the intended architectural correction. Return JSON {edits:[{old:unique exact substring,new:replacement}],reason}. Do not weaken validators. Use tested geometry helpers where appropriate. '+TOOLS+'\nDiagnostics: '+json.dumps(diagnostics)+'\nSOURCE:\n'+source
            fix=self.api.call('node-technical-'+stage,prompt,[],self.api.settings.code_model,7000)
            write_json(folder/'patch.json',fix);corrected=patch_fragment(source,fix.get('edits'));validate_source(corrected);self.source.write_text(corrected,encoding='utf-8')
            return capture_city(self.run,timeout=480)

    def critic(self,index,observations,previous=None,tasks=None,validation=False):
        needed=self.held if validation else [v for v in self.training if v['id'] in ('overhead','west')]+self.details
        try:capture_metadata=validate_evidence_captures(self.run,needed)
        except ValueError as exc:
            self.api.trace('capture_evidence_rejected',error=str(exc),iteration=index)
            self.node('recapture-'+str(index),lambda:self.render('capture-'+str(index)))
            capture_metadata=validate_evidence_captures(self.run,needed)
        self.city=json.loads((self.run/'city.json').read_text(encoding='utf-8'))
        folder=self.run/('heldout' if validation else f'iterations/{index:02d}');folder.mkdir(parents=True,exist_ok=True)
        common=self.held if validation else [v for v in self.training if v['id'] in ('overhead','west')]
        images=[];manifest=[]
        for v in common:
            for kind,path in [('source',self.evidence/v['image']),('render',self.run/'renders'/f'evidence-{v["id"]}.png')]:
                image=compact_image(path,folder/f'{kind}-{v["id"]}.jpg');label_scene(image,self.city,v);images.append(image)
                manifest.append({'image':image.name,'view':v['id'],'kind':kind,'scope':'whole scene'})
        if not validation:
            for v in self.details:
                b=next(b for b in self.city['buildings'] if b['id']==v['object_id']);bounded={**b,'height':b.get('height_envelope_m',[b['height']])[-1]}
                pair=paired_images(self.run,self.evidence,[v],bounded,folder/v['id']);images.extend(pair)
                manifest.extend({'image':p.relative_to(folder).as_posix(),'owner':b['id'],'view':v['id'],'kind':'source' if n%2==0 else 'render','scope':'matched region'} for n,p in enumerate(pair))
        write_json(folder/'image-manifest.json',manifest)
        prompt='''You are the independent VISUAL CRITIC node. You judge actual source/render pairs, not code or coder completion claims. Whole scene and matched detail pairs come first, then STYLE references, then OSM identity diagram. Assess every inventory feature and style feature. Explain visible expected-versus-actual differences with view IDs and owning object. The style reference is a real input: compare readable architectural detail, form treatment, surface variation, planting and daylight/composition; a flat generic CAD box does not match a richly articulated reference merely by being isometric. Do not impose a palette. Approximate textures/colors are acceptable if material identity and coherent appearance remain convincing; don't request exact texels or invent hidden ornaments. Ignore unlabeled background buildings outside targets and source clipping/mesh holes. 0..5: 3=usable with simplification,4=good,5=excellent. Return JSON {scores:{layout,identity,roofs,streetscape,materials,style,coherence},object_checks:[{owner,features:[{id:inventory_featureID,status:"matched|partial|missing|uncertain",evidence,views:[]}]}],style_checks:[{id:style_contract_id,status:"matched|partial|missing",evidence,repair}],issues:[{id:stable_featureID_or_scene_issueID,severity:"critical|major|minor",owner,part,evidence,repair,impact:1..5}],resolved_task_ids:[],strengths:[],uncertainties:[],next_actions:[]}. Every known feature appears exactly once. Any missing/poor defining visible roof or facade must appear as a major issue; don't let a global average hide it. A major issue damages usability/identity/style. Verify requested repairs in rendered images; do not trust claimed changes. Use consistent issue IDs across reviews. If a comparison is occluded, say uncertain instead of guessing.\nInventory: '''+json.dumps(observations,ensure_ascii=False)+'\nImage order: '+json.dumps(manifest)+'\nScene geometry and camera context: '+json.dumps(evidence_packet(self.city,common+self.details if not validation else common),ensure_ascii=False)
        prompt+='\nSource mesh level evidence (upper-surface samples, not survey): '+json.dumps(self.geometry_evidence)
        if previous:prompt+='\nPrevious assessment: '+json.dumps(previous,ensure_ascii=False)
        if tasks:prompt+='\nRequested work order: '+json.dumps(tasks,ensure_ascii=False)
        raw=self.api.call('node-critic-'+('heldout' if validation else str(index)),prompt,images+self.styles+[self.run/'scene-map.png'],self.api.settings.review_model,6500)
        raw['capture_contract']=capture_metadata['contract']
        write_json(folder/'raw-review.json',raw);validate_review(raw,observations);write_json(folder/'review.json',raw)
        return raw,images

    def coder(self,index,order,observations,images):
        source=self.source.read_text(encoding='utf-8')
        prompt='''You are the SCENE CODING node. Follow the critic's evidence-based work order while preserving whole-scene coherence. Attachments contain factual/render pairs, then STYLE references. Make substantive structural changes when a defining roof or facade is wrong; do not merely tint faulty geometry or add ornaments to a wrong mass. Remove/replace superseded wrong roof meshes and exposed wall-material roof caps, not stack a second correct-looking shell on top. Work in the shared source, retaining stable object IDs and host-owned streets. Use exact provided footprint coordinates and observed roof/facade hierarchy. Distinguish glass from masonry, trim and roof surfaces. Do not enforce palette restrictions. Texture lookup is not compulsory; freely choose approximate material properties and optional surface recipes. Explicitly address the observed style's level of articulation and natural-looking material readability. Source import only three, no network/timers/randomness. Closed positive-volume meshes or the tested tools; keep footprint bounds and ground datum. Height envelopes override contradictory original tags for source-supported multi-level parts, not uniform stretching. Every target has exactly one anchor Group userData.objectId; no child objectId. Host passes build({city,tools}).\n'''+TOOLS+'''
Return JSON {edits:[{old:unique exact substring,new:replacement}],scene_adjustments:{material_recipes:{},tree_cluster_detail:1..3,streetscape:{curbs:boolean,extend_tree_rows:boolean,tree_spacing_m:8..40,add_lamps:boolean,inferred_lane_dashes:boolean,include_core:boolean}},completed_task_ids:[],unresolved_task_ids:[],reason}. If edits would be fragile, return a complete source string instead of edits. Shared appearance roles road,pavement,grass,foliage,trunk,metal,ground,marking accept {color:"#RRGGBB",roughness,metalness,pattern?:"none|asphalt|paving|brick|slate|grass",tile_m,rows,columns,seed}. Optional building material.userData.surfaceRecipe uses the same pattern tools, not mandatory. Shared street tools create approximate seeded rows, lamps, curb edging and illustrative markings; do not duplicate roads in building code.\nWork order: '''+json.dumps(order,ensure_ascii=False)+'\nObservation inventory: '+json.dumps(observations,ensure_ascii=False)+'\nNumerical scene: '+json.dumps(evidence_packet(self.city,self.training+self.details),ensure_ascii=False)+'\nSOURCE:\n'+source
        prompt+='\nSource roof-height anchors, to distinguish upper roofs from apparent low podiums: '+json.dumps(self.geometry_evidence)
        raw=self.api.call('node-coder-'+str(index),prompt,images+self.styles,self.api.settings.code_model,13500)
        folder=self.run/'iterations'/f'{index:02d}';folder.mkdir(parents=True,exist_ok=True);write_json(folder/'coding-response.json',raw)
        corrected=raw.get('source') or patch_fragment(source,raw.get('edits'));validate_source(corrected)
        self.source.write_text(corrected,encoding='utf-8');self.city=apply_adjustments(self.city,raw.get('scene_adjustments',{}));write_json(self.run/'city.json',self.city)
        return raw

    def execute(self):
        observations=self.node('observe',self.observer)
        if not self.resume:
            seed=(self.parent/'building-generator.ts').read_text(encoding='utf-8');validate_source(seed);self.source.write_text(seed,encoding='utf-8')
            write_json(self.run/'generation.json',{'seed_provenance':{'parent':self.parent.name,'sha256':hashlib.sha256(seed.encode()).hexdigest(),'selection':'Pending parent program must be validated and judged by workflow nodes before acceptance.'}})
        self.node('validate-initial',self.validate_initial)
        current,images=self.node('critic-0',lambda:self.critic(0,observations))
        history=[current];status='needs_improvement';stalls=0
        for index in range(1,self.max_repairs+1):
            if current['accepted']:break
            folder=self.run/'iterations'/f'{index:02d}';folder.mkdir(parents=True,exist_ok=True)
            snapshot_runtime(self.run,folder/'accepted-runtime');before=self.city
            order=self.node('plan-'+str(index),lambda:work_order(current,observations,index));write_json(folder/'work-order.json',order)
            try:
                self.node('code-'+str(index),lambda:self.coder(index,order,observations,images))
                self.node('validate-'+str(index),lambda:self.render(str(index)))
                candidate,new_images=self.node('critic-'+str(index),lambda:self.critic(index,observations,current,order))
                keep=candidate['accepted'] or review_better(current,candidate)
                write_json(folder/'decision.json',{'kept':keep,'previous_scores':current['scores'],'candidate_scores':candidate['scores'],'coder_claims_used_for_acceptance':False})
                history.append(candidate)
                if keep:current,images=candidate,new_images;stalls=0
                else:
                    restore_runtime(self.run,folder/'accepted-runtime');self.city=before;stalls+=1
                    # Retain critic feedback about the failed attempt for the next coding node.
                    current={**current,'failed_attempt_feedback':candidate,'avoid_repeating':'Prior changes were not accepted; change the structural approach, not just prose or tint.'}
                    if stalls>=2:status='stagnated';break
            except BudgetExceeded:
                restore_runtime(self.run,folder/'accepted-runtime');self.city=before;status='budget_exhausted';break
            except Exception as exc:
                write_json(folder/'rejection.json',{'error':str(exc)[:1600]})
                for name in ('building-generator.ts','urban-runtime-result.json','urban-geometry-checks.json'):
                    if (self.run/name).exists():shutil.copy2(self.run/name,folder/('rejected-'+name))
                restore_runtime(self.run,folder/'accepted-runtime');self.city=before;stalls+=1
                current={**current,'technical_feedback':str(exc)}
                if stalls>=2:status='technical_rejection';break
        try:
            validate_evidence_captures(self.run,self.training+self.details+self.held)
        except ValueError:
            self.node('publication-recapture',lambda:self.render('publication'))
            current,_=self.node('publication-training-critic',lambda:self.critic(self.max_repairs+1,observations))
        try:final,_=self.node('heldout-critic',lambda:self.critic(self.max_repairs+1,observations,validation=True))
        except BudgetExceeded:final={'accepted':False,'reason':'budget exhausted before heldout review'}
        accepted=current['accepted'] and final['accepted'];self.api.save_usage()
        result={'model':'gpt-6-sol','architecture':'observer -> critic -> deterministic work-order node -> coding node -> technical validator/repair node -> critic -> heldout critic','scope':'joint whole-scene program with region evidence','accepted':accepted,'status':'accepted' if accepted else status,'mandatory_texture_roles':[],'exact_texture_match_required':False,'training':current,'heldout':final,'usage':self.api.usage,'node_events':self.events,'limitations':['Qualitative model review is not calibrated geometric accuracy.','Context planting/lights/markings and hidden details may be inferred.']}
        write_json(self.run/'scene-first-result.json',result);make_report(self.run);write_json(self.run/'workflow-state.json',{'status':'finished','accepted':accepted,'events':self.events});return result


    def validate_initial(self):
        if self.resume:
            result=json.loads((self.run/'urban-runtime-result.json').read_text(encoding='utf-8'))
            presentation=json.loads((self.run/'presentation.json').read_text(encoding='utf-8'))
            source_hash=hashlib.sha256(self.source.read_bytes()).hexdigest()
            if result.get('ok') and result['metrics']['source_sha256']==source_hash and presentation['data']==self.city and presentation['profile']==json.loads((self.run/'style-profile.json').read_text(encoding='utf-8')):
                try:validate_evidence_captures(self.run,self.training+self.details+self.held)
                except ValueError:pass
                else:
                    self.api.trace('validated_capture_reused',source_sha256=source_hash,reason='Same source, rendered city data, style, camera plan and verified reference visibility.')
                    return result
        return self.render('initial')


def run_coordinated(parent,evidence,run,max_repairs=3,resume=False):
    workflow=SceneWorkflow(parent,evidence,run,max_repairs,resume)
    try:return workflow.execute()
    finally:workflow.api.save_usage();workflow.api.client.close()


def audit_publication(run,evidence):
    """Reconcile an older completed run using the same bounded validator/critic nodes."""
    workflow=SceneWorkflow.__new__(SceneWorkflow);workflow.run=Path(run);workflow.evidence=Path(evidence)
    workflow.source=workflow.run/'building-generator.ts';workflow.city=json.loads((workflow.run/'city.json').read_text(encoding='utf-8'))
    workflow.views=json.loads((workflow.evidence/'source-views.json').read_text())['views']
    workflow.training=[v for v in workflow.views if not v.get('held_out') and v['id'] in ('overhead','south','west','north','east')]
    workflow.held=[v for v in workflow.views if v.get('held_out')];workflow.details=[]
    for b in workflow.city['buildings']:
        candidates=[v for v in workflow.views if not v.get('held_out') and v.get('object_id')==b['id']]
        if candidates:workflow.details.append(candidates[0])
    workflow.styles=sorted((workflow.run/'style-inputs').glob('*.jpg'))
    workflow.events=json.loads((workflow.run/'workflow-state.json').read_text()).get('events',[])
    workflow.geometry_evidence=load_geometry_evidence(workflow.city,workflow.evidence)
    s=Settings.load();s.model=s.code_model=s.review_model=s.vision_model='gpt-6-sol'
    workflow.api=Provider(s,workflow.run,max_calls=14,max_tokens=600000,max_seconds=2700,max_attempts=1,request_timeout=240)
    try:
        result=json.loads((workflow.run/'scene-first-result.json').read_text(encoding='utf-8'))
        write_json(workflow.run/'before-publication-audit.json',result)
        observations=json.loads((workflow.run/'observer/observations.json').read_text(encoding='utf-8'))
        workflow.node('publication-recapture',lambda:workflow.render('publication'))
        validate_evidence_captures(workflow.run,workflow.training+workflow.details+workflow.held)
        current,_=workflow.node('publication-training-critic',lambda:workflow.critic(4,observations))
        final,_=workflow.node('publication-heldout-critic',lambda:workflow.critic(5,observations,validation=True))
        result.update(training=current,heldout=final,accepted=current['accepted'] and final['accepted'],status='accepted' if current['accepted'] and final['accepted'] else 'needs_improvement',usage=workflow.api.usage,node_events=workflow.events,publication_capture_contract='matching-source-visibility-v2')
        write_json(workflow.run/'scene-first-result.json',result);make_report(workflow.run)
        write_json(workflow.run/'workflow-state.json',{'status':'finished','accepted':result['accepted'],'events':workflow.events})
        return result
    finally:workflow.api.save_usage();workflow.api.client.close()
