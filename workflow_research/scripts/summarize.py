"""Consolidate real usage and equivalent uncached API work from saved traces."""
import json
from pathlib import Path
from building_workflow.config import ROOT
from building_workflow.provider import write_json

runs=ROOT/"runs"
original_times={}
for path in runs.glob("*/usage.json"):
    for attempt in json.loads(path.read_text(encoding="utf-8")).get("attempts",[]):
        if attempt.get("http_status")==200:
            original_times[attempt["cache_key"]]=attempt["seconds"]
rows=[]
for result in sorted(runs.glob("*/result.json")):
    run=result.parent
    data=json.loads(result.read_text(encoding="utf-8"))
    config=json.loads((run/"config.json").read_text(encoding="utf-8"))
    usage=json.loads((run/"usage.json").read_text(encoding="utf-8"))
    effective_in=effective_out=effective_seconds=0
    for line in (run/"trace.jsonl").read_text(encoding="utf-8").splitlines():
        event=json.loads(line)
        if event["event"] not in ("api_success","cache_hit"):
            continue
        key=event.get("cache_key",event.get("key"))
        cached=ROOT/".cache/api"/(key+".json")
        info=json.loads(cached.read_text(encoding="utf-8")) if cached.exists() else {}
        tokens=info.get("usage",event.get("usage",{}))
        effective_in+=tokens.get("prompt_tokens",0);effective_out+=tokens.get("completion_tokens",0)
        effective_seconds+=original_times.get(key,0)
    best=next((c for c in data.get("candidates",[]) if c["iteration"]==data.get("best_iteration")),None)
    rows.append({"run":run.name,"sample":config["sample"]["id"],"strategy":config["strategy"],
        "refinement_scope":config.get("refinement_scope","targeted"),"status":data["status"],"quality":best.get("quality") if best else None,
        "best_iteration":data.get("best_iteration"),"actual_calls":usage["calls"],"actual_tokens":usage["input_tokens"]+usage["output_tokens"],
        "equivalent_uncached_tokens":effective_in+effective_out,"equivalent_api_seconds":round(effective_seconds,2),
        "observed_wall_seconds":round(data["seconds"],2),"cache_hits":usage["cache_hits"],"cost_usd":usage["cost_usd"]})
actual_total=sum(r["actual_tokens"] for r in rows)
calls_total=sum(r["actual_calls"] for r in rows)
reliability=ROOT/"reports/reliability/smoke-bauhaus-spec-v2/usage.json"
if reliability.exists():
    independent=json.loads(reliability.read_text())
    actual_total+=independent["input_tokens"]+independent["output_tokens"];calls_total+=independent["calls"]
write_json(ROOT/"reports/experiment-summary.json",{"runs":rows,"actual_total_tokens_including_failures_and_independent_review":actual_total,
    "actual_total_calls_including_failures_and_independent_review":calls_total,"monetary_cost_usd":None,
    "caveat":"Equivalent uncached tokens/API time sum the original successful responses consumed by each run. They are not new charges and are not a measured cold end-to-end rerun. Failed trials remain separate rows."})
table=["# Measured Experiment Comparison","", "Scores are uncalibrated; all reconstructions remain partial. Equivalent uncached tokens include reused API responses, avoiding warm-cache cost bias. API seconds exclude deterministic processing and retries.","",
    "| Run | Status | Quality | Selected | Actual calls | Actual tokens | Equivalent uncached tokens | API seconds equivalent | Wall seconds observed | Cache hits |",
    "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
for r in rows:
    score=f'{r["quality"]:.3f}' if r["quality"] is not None else "—"
    table.append(f'| [{r["run"]}](../runs/{r["run"]}/index.html) | {r["status"]} | {score} | {r["best_iteration"]} | {r["actual_calls"]} | {r["actual_tokens"]:,} | {r["equivalent_uncached_tokens"]:,} | {r["equivalent_api_seconds"]:.1f} | {r["observed_wall_seconds"]:.1f} | {r["cache_hits"]} |')
table.extend(["",f"Actual total including failed trials and independent review: **{calls_total} calls, {actual_total:,} tokens**. USD cost unknown (no verified prices configured).",""])
(ROOT/"reports/comparison-table.md").write_text("\n".join(table),encoding="utf-8")
print(json.dumps({"calls":calls_total,"tokens":actual_total,"rows":len(rows)}))
