"""Run a bounded GPT Sol visual repair experiment without changing the parent run."""
import argparse
import json
import shutil
from pathlib import Path
from building_workflow.config import ROOT,Settings
from building_workflow.provider import Provider
from building_workflow.urban.strict_loop import run_target,write_strict_report
from building_workflow.urban.report import viewer_files

p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--object-id',required=True);p.add_argument('--repairs',type=int,default=2)
p.add_argument('--parent',type=Path,default=ROOT/'runs/urban/tokyo-materials-v3')
p.add_argument('--components-parent',type=Path,default=ROOT/'runs/urban/tokyo-scene-v2')
p.add_argument('--evidence',type=Path,default=ROOT/'runs/urban/tokyo-measured-v1');a=p.parse_args()
if not 0<=a.repairs<=4 or not a.run_id.replace('-','').isalnum():p.error('invalid run ID or repairs')
run=ROOT/'runs/urban'/a.run_id
if not run.exists():
    run.mkdir(parents=True)
    parent=a.parent.resolve()
    for name in ('ground-observation','style-inputs','textures'):
        shutil.copytree(parent/name,run/name)
    shutil.copytree(a.components_parent.resolve()/'components',run/'components')
    for name in ('city.json','scene-plan.json','scene-contract.json','building-generator.ts','asset-manifest.json','style-profile.json','style-references.json','mesh-height-evidence.json','boundary-checks.json','presentation-settings.json','render-probe.json','surface-requests.json'):
        shutil.copy2(parent/name,run/name)
settings=Settings.load()
settings.model=settings.vision_model=settings.code_model=settings.review_model='gpt-6-sol'
provider=Provider(settings,run,max_calls=12,max_tokens=250000,max_seconds=1800,max_attempts=1)
try:
    result=run_target(run,a.evidence.resolve(),a.object_id,provider,a.repairs)
    viewer_files(run)
    write_strict_report(run)
    print(json.dumps({'accepted':result['accepted'],'status':result['status'],'calls':provider.usage['calls'],'tokens':provider.usage['input_tokens']+provider.usage['output_tokens'],'cost_usd':provider.usage.get('cost_usd'),'run':str(run)}))
finally:
    provider.save_usage();provider.client.close()
