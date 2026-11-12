"""Independent-model check of a saved before/after pair; not calibration."""
import argparse
import json
from pathlib import Path
from building_workflow.config import ROOT, Settings
from building_workflow.models import Review
from building_workflow.provider import Provider, write_json

parser=argparse.ArgumentParser()
parser.add_argument("run")
parser.add_argument("--model",default="gpt-6-luna")
args=parser.parse_args()
run=ROOT/"runs"/args.run
out=ROOT/"reports"/"reliability"/args.run
out.mkdir(parents=True,exist_ok=True)
provider=Provider(Settings.load(),out,max_calls=3,max_tokens=45000,max_seconds=240)
prompt="""Independently review two reference/render comparison images for the same real building. Image FIRST and image SECOND are two candidates; order does not indicate quality. Ignore background and photograph lighting; evaluate architectural correspondence only. Hidden sides are unknown. A high average cannot excuse missing landmark structure. Return JSON {"first":REVIEW,"second":REVIEW,"preferred":"first"|"second"|"tie","reason":"concrete visual evidence"}. Each REVIEW has: scores object (mass,facade,roof,details,materials,proportions; all 0..1), critical_defects array, defects array of {component,severity,cause,fix}, matched_features array, inferred_regions array, confidence 0..1. Do not invent image metrics or exact dimensions. This is a small evaluator reliability check, not a fidelity certification."""
# Reverse presentation order relative to the main evaluator's chronology.
raw=provider.call("independent-pair",prompt,[run/"iteration-01/comparison.jpg",run/"iteration-00/comparison.jpg"],args.model,4500)
first=Review.model_validate(raw["first"]);second=Review.model_validate(raw["second"])
write_json(out/"pair-review.json",{**raw,"model":args.model,"first_iteration":1,"second_iteration":0,
    "first_quality":first.quality,"second_quality":second.quality,
    "limitation":"One pair with unblinded image content and one alternate evaluator; not human calibration or a stability estimate."})
print(json.dumps({"preferred":raw["preferred"],"refined_quality":first.quality,"baseline_quality":second.quality,"output":str(out)},indent=2))
