import html
import json
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw
from .config import ROOT

STYLE = """body{font:16px system-ui;background:#101923;color:#e6edf3;max-width:1380px;margin:auto;padding:28px}a{color:#8ac6ff}h1,h2{color:#fff}article{background:#1b2938;padding:20px;margin:22px 0;border-radius:12px}img{max-width:100%;height:auto}table{border-collapse:collapse;width:100%}th,td{padding:10px;border-bottom:1px solid #496077;text-align:left}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.note{color:#ffd38a}pre{white-space:pre-wrap;font-size:13px}svg{background:#fff;border-radius:8px;max-width:100%}code{color:#9ed8ff}"""


def page(title, body):
    return f'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{html.escape(title)}</title><style>{STYLE}</style><h1>{html.escape(title)}</h1>{body}'


def comparison(reference, render, output):
    sheet = Image.new("RGB", (1600, 850), "#e8edf2")
    for i, (path, label) in enumerate([(reference,"REFERENCE — observed photograph"),(render,"RECONSTRUCTION — camera hypothesis")]):
        im = ImageOps.contain(Image.open(path).convert("RGB"), (790, 790))
        sheet.paste(im,(i*800+(800-im.width)//2, 45+(790-im.height)//2))
        ImageDraw.Draw(sheet).text((i*800+18,15),label,fill="#152333")
    sheet.save(output, quality=93)


def multiview(folder):
    names = ["front","back","left","right","isometric"]
    sheet = Image.new("RGB", (1500,330), "#e8edf2")
    draw = ImageDraw.Draw(sheet)
    for i, name in enumerate(names):
        im = Image.open(folder / (name+".png")).convert("RGB").resize((300,300))
        sheet.paste(im,(i*300,30)); draw.text((i*300+8,8),name,fill="#102030")
    sheet.save(folder / "multiview.jpg", quality=93)


def run_report(run):
    result = json.loads((run/"result.json").read_text(encoding="utf-8"))
    config = json.loads((run/"config.json").read_text(encoding="utf-8"))
    body = f'<p class="note">Status: {html.escape(result["status"])}. Single-view reconstruction: hidden geometry inferred. Scores are uncalibrated model judgments.</p>'
    body += f'<p>Stop: {html.escape(result["stop_reason"])} · Selected iteration: {result.get("best_iteration")} · Runtime: {result.get("seconds",0):.1f}s</p>'
    body += '<p><a href="result.json">Full result</a> · <a href="usage.json">Usage</a> · <a href="upstream-compatibility.json">Upstream compatibility limits</a></p>'
    sample=config["sample"]
    if sample["id"]=="rietveld":
        sample={**sample,"author":"Hay Kranen (User:Husky)"}
    body += '<p>Reference: <a href="'+html.escape(sample["source_page"],quote=True)+'">'+html.escape(sample["title"])+ '</a> · '+html.escape(sample["author"])+ ' · '+html.escape(sample["license"])+'. Original image resized; procedural render is a separate reconstruction.</p>'
    body += '<p class="note">IoU / SSIM / 3D error: unavailable — no verified segmentation, calibrated camera or 3D ground truth.</p>'
    for candidate in result.get("candidates",[]):
        folder = f'iteration-{candidate["iteration"]:02d}'
        selected = ' — SELECTED' if candidate["iteration"] == result.get("best_iteration") else ''
        body += f'<article><h2>Iteration {candidate["iteration"]}{selected}</h2>'
        if (run/folder/"comparison.jpg").exists():
            body += f'<img src="{folder}/comparison.jpg"><div class="grid">'
            for name in ["front","back","left","right","isometric"]:
                body += f'<figure><img src="{folder}/{name}.png"><figcaption>{name}</figcaption></figure>'
            body += '</div>'
        links=[]
        for name,label in [("generator.ts","Procedural source"),("geometry.json","Geometry gate"),("review.json","Review"),("compile.log","Compilation evidence")]:
            if (run/folder/name).exists():
                links.append(f'<a href="{folder}/{name}">{label}</a>')
        body+='<p>'+' · '.join(links)+'</p>'
        body += '<pre>'+html.escape(json.dumps(candidate,indent=2,ensure_ascii=False))+'</pre></article>'
    (run/"index.html").write_text(page(run.name, body),encoding="utf-8")


def scatter(rows, xkey, label):
    points = [r for r in rows if r.get("quality") is not None and r.get(xkey) is not None]
    if not points:
        return f'<p>{html.escape(label)}: unavailable; provider monetary pricing not configured.</p>'
    xmax = max(r[xkey] for r in points) or 1
    svg = f'<svg width="620" height="350" viewBox="0 0 620 350"><text x="40" y="26" fill="#123">Quality vs {html.escape(label)}</text><path d="M60 45V290H600" fill="none" stroke="#567"/>'
    for y in [0,0.25,0.5,0.75,1]:
        yy=290-y*230
        svg+=f'<text x="12" y="{yy}" font-size="12">{y}</text><path d="M60 {yy}H600" stroke="#dde"/>'
    for row in points:
        x=65+row[xkey]/xmax*500;y=290-row["quality"]*230
        color="#1674b8" if row["strategy"]=="spec" else "#df7a17"
        svg+=f'<circle cx="{x}" cy="{y}" r="6" fill="{color}"><title>{html.escape(row["id"])}</title></circle><text x="{x-65}" y="{y-10}" font-size="10">{html.escape(row["sample"]+"/"+row["strategy"])}</text>'
    svg+=f'<text x="70" y="325">0</text><text x="470" y="325">{xmax:.2f} {html.escape(label)}</text></svg>'
    return svg


def aggregate():
    dest=ROOT/"reports";dest.mkdir(exist_ok=True)
    rows=[]
    for path in sorted((ROOT/"runs").glob("*/result.json")):
        result=json.loads(path.read_text(encoding="utf-8"))
        config=json.loads((path.parent/"config.json").read_text(encoding="utf-8"))
        usage=json.loads((path.parent/"usage.json").read_text(encoding="utf-8"))
        best=next((c for c in result.get("candidates",[]) if c["iteration"]==result.get("best_iteration")),None)
        rows.append({"id":path.parent.name,"sample":config["sample"]["id"],"strategy":config["strategy"],"status":result["status"],
            "quality":best.get("quality") if best else None,"critical_defects":len(best["review"]["critical_defects"]) if best and best.get("review") else None,
            "valid":bool(best and best.get("geometry_passed")),"seconds":result.get("seconds",0),
            "calls":usage["calls"],"tokens":usage["input_tokens"]+usage["output_tokens"],"cost_usd":usage["cost_usd"],
            "cache_hits":usage["cache_hits"],"equivalent_tokens":usage["input_tokens"]+usage["output_tokens"]+usage.get("replayed_input_tokens",0)+usage.get("replayed_output_tokens",0),
            "refinement_scope":config.get("refinement_scope","targeted"),
            "best_iteration":result.get("best_iteration"),"stop_reason":result["stop_reason"]})
    from .provider import write_json
    write_json(dest/"results.json",rows)
    body='<p class="note">Development smoke experiments only. Visual scores are exploratory; geometry validity is separate from reconstruction fidelity. No held-out generalization claim.</p><p><a href="findings.md">Research findings</a> · <a href="validation.md">Validation evidence</a> · <a href="comparison-table.md">Cold-equivalent accounting</a> · <a href="results.json">Raw comparison</a></p>'
    body+='<table><tr>'+''.join(f'<th>{s}</th>' for s in ['Run','Strategy','Status','Geometry','Quality*','Critical','Calls','Tokens','Cache','USD','Seconds'])+'</tr>'
    for r in rows:
        cells=[f'<a href="../runs/{r["id"]}/index.html">{html.escape(r["id"])}</a>',r['strategy'],r['status'],str(r['valid']),f'{r["quality"]:.3f}' if r['quality'] is not None else '—',str(r['critical_defects']),str(r['calls']),str(r['tokens']),str(r['cache_hits']),str(r['cost_usd']) if r['cost_usd'] is not None else 'unknown',f'{r["seconds"]:.1f}']
        body+='<tr>'+''.join('<td>'+c+'</td>' for c in cells)+'</tr>'
    body+='</table><p>*Mean of six VLM feature scores, not calibrated accuracy. Blue: structured; orange: direct. Tokens/calls/seconds reflect actual work this run; cache reuse makes warm latency unsuitable for cold strategy comparisons. See findings for consolidated cold accounting.</p>'
    body+=scatter(rows,"seconds","seconds")+scatter(rows,"tokens","tokens")+scatter(rows,"cost_usd","USD")
    body+=f'<p>Geometry-valid runs: {sum(r["valid"] for r in rows)}/{len(rows)}. Fidelity-certified runs: 0 (uncalibrated and incomplete source views).</p>'
    (dest/"index.html").write_text(page("Building reconstruction experiments",body),encoding="utf-8")
    return rows
