import argparse,json
from building_workflow.config import ROOT
from building_workflow.urban.scene_first import run_scene_first

p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--parent',default='tokyo-sol-strict-v4');p.add_argument('--evidence',default='tokyo-measured-v1');p.add_argument('--repairs',type=int,choices=range(4),default=2)
p.add_argument('--seed-scene',action='store_true');p.add_argument('--expanded-context',action='store_true');a=p.parse_args()
for value in (a.run_id,a.parent,a.evidence):
    if not value.replace('-','').replace('_','').isalnum():p.error('invalid run name')
result=run_scene_first(ROOT/'runs/urban'/a.parent,ROOT/'runs/urban'/a.evidence,ROOT/'runs/urban'/a.run_id,a.repairs,a.seed_scene,a.expanded_context)
print(json.dumps({'accepted':result['accepted'],'status':result['status'],'calls':result['usage']['calls'],'tokens':result['usage']['input_tokens']+result['usage']['output_tokens']}))
