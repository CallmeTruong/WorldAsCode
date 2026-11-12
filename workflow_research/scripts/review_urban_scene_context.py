"""One bounded scene-wide diagnosis; observations are not a generated reconstruction."""
import argparse,json
from PIL import Image
from building_workflow.config import ROOT,Settings
from building_workflow.provider import Provider,write_json
from building_workflow.urban.scene import scene_map

p=argparse.ArgumentParser();p.add_argument('--run',type=str,required=True);p.add_argument('--output',type=str,required=True)
p.add_argument('--evidence',type=str,default='tokyo-measured-v1');a=p.parse_args()
run=ROOT/'runs/urban'/a.run;out=ROOT/'runs/urban'/a.output;out.mkdir(parents=True,exist_ok=True)
evidence=ROOT/'runs/urban'/a.evidence
city=json.loads((run/'city.json').read_text(encoding='utf-8'))
images=[]
for name,path in [('source-overhead',evidence/'overhead.jpg'),('source-west',evidence/'west.jpg'),('source-south',evidence/'south.jpg'),('generated-overhead',run/'renders/evidence-overhead.png'),('style',next((run/'style-inputs').glob('*.jpg')))]:
    with Image.open(path) as im:
        im=im.convert('RGB');im.thumbnail((1280,1280));target=out/(name+'.jpg');im.save(target,quality=85);images.append(target)
points=[p for b in city['buildings'] for p in b['outer']]
diagram={**city,'bounds':[min(p[0] for p in points)-10,min(p[1] for p in points)-10,max(p[0] for p in points)+10,max(p[1] for p in points)+10]}
scene_map(diagram,out/'scene-id-map.png');images.append(out/'scene-id-map.png')
views=json.loads((evidence/'source-views.json').read_text())['views']
prompt='''Analyze the WHOLE AOI as one related scene, not independent buildings. Attachments: three FACTUAL Google 3D Tiles area views (overhead,west,south), current GENERATED overhead, STYLE reference, and north-up OSM ID diagram (not photography). Do not enforce a style palette or any fixed texture catalog. Distinguish physical materials from baked illumination, black clipping voids, photogrammetry holes and occlusion. A generic scan is a candidate, not evidence of correspondence. Infer surfaces first, then recommend retrieval/procedural/source-projection strategy with uncertainty. Assign each defect to its actual stable object or shared scene subsystem; a crop of an L-shaped building can include its neighbor or shared ground. Do not infer a passage from one mesh hole. Assess global roof topology, streets/sidewalks, courtyard ownership, vegetation anchors, material relationships, and what a whole-scene generation step should resolve before local detail. Recommend a budgeted A/B experiment for full-AOI code versus joint planning with modular code; do not claim either wins without running it. Return JSON {root_causes:[],scene_dependencies:[],observed_surface_requirements:[{surface,owner,source_views,appearance,pattern_scale_confidence,confidence,preferred_representation,missing_evidence}],ownership_or_source_artifacts:[],next_generation_scope:{shared_scene_work:[],local_work:[]},comparison_protocol:{same_inputs:[],quality_checks:[],cost_checks:[]},limitations:[]}. No exact metric measurements from appearance alone. Whole scene data: '''+json.dumps({'buildings':city['buildings'],'roads':city['roads'],'trees_count':len(city['trees']),'bounds':city['bounds']},ensure_ascii=False)+'\nFactual camera metadata: '+json.dumps([{k:v.get(k) for k in ('id','heading','pitch','local_camera')} for v in views if v['id'] in ('overhead','west','south')])
s=Settings.load();s.model=s.vision_model=s.code_model=s.review_model='gpt-6-sol'
api=Provider(s,out,max_calls=1,max_tokens=100000,max_seconds=180,max_attempts=1)
try:
    result=api.call('whole-scene-material-diagnosis',prompt,images,s.review_model,3500)
    write_json(out/'scene-context-analysis.json',result)
    print(json.dumps({'output':str(out/'scene-context-analysis.json'),'calls':api.usage['calls'],'tokens':api.usage['input_tokens']+api.usage['output_tokens']}))
finally:api.save_usage();api.client.close()
