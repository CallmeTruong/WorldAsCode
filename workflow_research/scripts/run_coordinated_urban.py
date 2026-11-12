import argparse,json
from building_workflow.config import ROOT
from building_workflow.urban.coordinated import run_coordinated

p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--parent',default='tokyo-scene-first-v2');p.add_argument('--evidence',default='tokyo-measured-v1');p.add_argument('--repairs',type=int,choices=range(5),default=3);p.add_argument('--resume',action='store_true');a=p.parse_args()
for value in (a.run_id,a.parent,a.evidence):
    if not value.replace('-','').replace('_','').isalnum():p.error('invalid run ID')
r=run_coordinated(ROOT/'runs/urban'/a.parent,ROOT/'runs/urban'/a.evidence,ROOT/'runs/urban'/a.run_id,a.repairs,a.resume)
print(json.dumps({'accepted':r['accepted'],'status':r['status'],'calls':r['usage']['calls'],'tokens':r['usage']['input_tokens']+r['usage']['output_tokens']}))
