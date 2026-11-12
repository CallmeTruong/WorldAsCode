import html
import json
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw
from ..config import ROOT
from ..provider import write_json


def paired_images(run):
    for view in ['overview','street','detail','seam']:
        sheet=Image.new('RGB',(1440,580),'#edf0f2');draw=ImageDraw.Draw(sheet)
        for i,name in enumerate(['neutral','styled']):
            im=Image.open(run/'renders'/f'{name}-{view}.png').convert('RGB');im.thumbnail((720,540));sheet.paste(im,(i*720,35))
            draw.text((i*720+15,12),name.upper()+' | identical geometry and camera',fill='#192c38')
        sheet.save(run/f'comparison-{view}.jpg',quality=94)


def viewer_files(run):
    (run/'viewer.html').write_text('''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'unsafe-inline'; object-src 'none'">
<title>Urban AOI — procedural style pilot</title><style>
*{box-sizing:border-box}body{margin:0;background:#dce3e3;font:14px system-ui;color:#eef5f6;overflow:hidden}canvas{position:fixed;inset:0;width:100vw!important;height:100vh!important;object-fit:contain}
header{position:fixed;top:18px;left:20px;right:20px;z-index:2;display:flex;gap:18px;align-items:flex-start;pointer-events:none}
.panel{background:#112932eb;border:1px solid #54727677;border-radius:14px;padding:16px 20px;box-shadow:0 8px 35px #08232533;pointer-events:auto;max-width:560px}
h1{font-size:21px;margin:0 0 5px}p{margin:7px 0;line-height:1.5;color:#c7d7d8}.tag{color:#eac975;font-size:12px}label{display:inline-flex;gap:5px;margin:6px 10px 0 0;align-items:center}
button,select{background:#29464e;color:#fff;border:1px solid #5c7c85;border-radius:6px;padding:7px 10px;cursor:pointer}a{color:#abdbef}.views{margin-top:10px;display:flex;gap:5px;flex-wrap:wrap}
footer{position:fixed;bottom:15px;left:20px;right:20px;z-index:2;display:flex;justify-content:space-between;gap:18px}.small{font-size:12px;max-width:750px}.reference{width:120px;border-radius:7px;display:block;margin:8px 0}.right{margin-left:auto;max-width:230px}
</style></head><body><header><div class="panel"><h1>Urban procedural reconstruction</h1><div class="tag">OSM context / individual reference-backed candidates / quality under review</div>
<p id="summary">Loading validated scene…</p><label>Style <select id="style"><option value="styled">Reference presentation</option><option value="neutral">Evidence materials</option></select></label>
<label>Object <select id="object"><option value="">Full context</option></select></label><label><input type="checkbox" id="grid">Grid</label><label><input type="checkbox" id="trees" checked>Trees</label><label><input type="checkbox" id="furniture" checked>Lamps</label>
<label>Tree variation <input id="tree-seed" type="number" value="0" step="1" style="width:70px"> <button id="apply-tree-seed">Apply</button></label>
<div class="views"><button data-view="overview">Overview</button><button data-view="north">North</button><button data-view="grid">Top</button><button data-view="street">Street</button><button data-view="detail">Detail</button><button data-view="seam">Seam</button><button data-view="landmark">Object detail</button></div>
<p class="small">Drag to orbit · scroll to zoom · right-drag to pan. <a href="index.html">Evidence report</a> · <a href="city.json">City data</a></p></div>
<div class="panel right"><b>Style from image folder</b><img class="reference" src="style-inputs/reference-00.jpg"><p class="small" id="profile"></p><a href="style-profile.json">Extracted profile</a></div></header>
<footer><div class="panel small">© OpenStreetMap contributors · ODbL. PBR: Poly Haven / CC0. Reference sources and approximate tree positions are recorded in the report. Unseen details and ground height remain inferred.</div><div class="panel small" id="stats">Preparing renderer</div></footer>
<script src="viewer-app.js"></script></body></html>''',encoding='utf-8')
    (run/'viewer-app.js').write_text('''window.__CITY_INTERACTIVE__=true;
const bundle=document.createElement('script');bundle.src='urban-viewer.js';document.head.appendChild(bundle);
bundle.onload=async()=>{try{const p=await (await fetch('presentation.json')).json();await window.initCity(p);
document.getElementById('summary').textContent=`${p.data.observed_objects?.length||0} reference-backed targets / ${p.data.buildings.length-(p.data.observed_objects?.length||0)} context proxies / ${p.data.trees.length} trees. Original materials preserved; fidelity remains partial.`;
document.getElementById('profile').textContent=p.profile.name+' — '+p.profile.description;
const objects=document.getElementById('object');for(const b of p.data.buildings.filter(b=>p.data.observed_objects?.includes(b.id))){const o=document.createElement('option');o.value=b.id;o.textContent=b.name;objects.appendChild(o);}
objects.onchange=e=>{if(e.target.value)window.selectCityObject(e.target.value,true);else {window.resetCityObjects();window.setCityView('overview');}};
document.getElementById('style').onchange=e=>window.setCityStyle(e.target.value==='neutral'?p.neutral:p.profile,e.target.value==='neutral');
document.getElementById('grid').onchange=e=>window.showCityGrid(e.target.checked);
document.getElementById('trees').onchange=e=>window.toggleCityLayer('vegetation',e.target.checked);
document.getElementById('furniture').onchange=e=>window.toggleCityLayer('furniture',e.target.checked);
document.getElementById('apply-tree-seed').onclick=()=>window.reseedCityTrees(Number(document.getElementById('tree-seed').value));
for(const button of document.querySelectorAll('[data-view]'))button.onclick=()=>window.setCityView(button.dataset.view);
setInterval(()=>{const s=window.cityStats();document.getElementById('stats').textContent=`${s.draw_calls} draw calls · ${s.triangles.toLocaleString()} visible triangles`;},1800);
}catch(error){document.getElementById('summary').textContent='Load failed: '+error.message;}};
''',encoding='utf-8')


def make_report(run,review=None):
    paired_images(run);viewer_files(run)
    city=json.loads((run/'city.json').read_text(encoding='utf-8'));profile=json.loads((run/'style-profile.json').read_text(encoding='utf-8'))
    runtime=json.loads((run/'urban-runtime-result.json').read_text(encoding='utf-8'));usage=json.loads((run/'usage.json').read_text())
    boundary=json.loads((run/'boundary-checks.json').read_text());result={'status':'partial','reason':'Working OSM/style procedural pilot; unobserved facades, missing heights, assumed ground and streetscape placement remain uncertain.',
        'buildings':len(city['buildings']),'cells':len(city['cells']),'trees':len(city['trees']),'lamps':len(city['lamps']),
        'estimated_height_buildings':sum(b['height_evidence']!='OSM height tag' for b in city['buildings']),
        'technical_valid':bool(runtime.get('ok')),'visual_accepted':bool((review or {}).get('visual_accepted',False)),
        'generated_geometry':runtime.get('metrics'),'boundary':boundary,'review':review,'usage':usage,
        'limitations':['Only objects listed in object-observations.json have individual photo analysis; all remaining facades are inferred. This is not whole-area high-fidelity reconstruction.',
            'Native eight-pass img2threejs baseline remains incomplete; real geometry gate reused.',
            'No measured terrain, photographic texture baking, large-area throughput or calibrated fidelity score.',
            'Descriptive style intent is consumed by object planning; executable presentation currently changes lighting only, preserving materials.','CPU submission timings do not establish display FPS.']}
    auxiliary={}
    if (run/'ground-observation/usage.json').exists():
        auxiliary['ground_observation']=json.loads((run/'ground-observation/usage.json').read_text())
    result['auxiliary_usage']=auxiliary
    result['total_api_calls']=usage['calls']+sum(u['calls'] for u in auxiliary.values())
    result['total_metered_tokens']=usage['input_tokens']+usage['output_tokens']+sum(u['input_tokens']+u['output_tokens'] for u in auxiliary.values())
    if (run/'scene-plan.json').exists():
        plan=json.loads((run/'scene-plan.json').read_text(encoding='utf-8'))
        result['scene_evidence_coverage']={v:sum(b['visibility']==v for b in plan['buildings']) for v in ['observed','partial','unobserved']}
        result['generated_components']=len(plan['buildings'])
        result['factual_accepted']=bool((review or {}).get('factual_accepted',False))
        result['style_accepted']=bool((review or {}).get('style_accepted',False))
        result['limitations'][0]='All AOI buildings have scene-informed modules; visible, partial and unobserved evidence statuses remain separate from reconstruction acceptance.'
        result['limitations'][3]='Actual style images guide component generation and review; the interactive presentation switch changes lighting only.'
    write_json(run/'result.json',result)
    style='body{margin:0;background:#10242c;color:#d7e5e9;font:16px system-ui;padding:35px;max-width:1500px;margin:auto}h1,h2{color:#fff}a{color:#94d6ed}img{max-width:100%;border-radius:12px}article{margin:25px 0;padding:20px;background:#1b333e;border-radius:15px}.note{color:#f3cd86}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}pre{white-space:pre-wrap;font-size:13px}table{border-collapse:collapse;width:100%}td,th{padding:10px;border-bottom:1px solid #526975;text-align:left}'
    body=f'<h1>Urban AOI — procedural urban style experiment</h1><p class="note">PARTIAL: source footprints and available heights are OSM-derived; unseen facades, many heights and added streetscape are inferred.</p><p><a href="viewer.html">Open interactive viewer</a> · <a href="result.json">Full evidence</a> · <a href="building-generator.ts">API-generated procedural source</a> · <a href="style-profile.json">Extracted style</a> · <a href="boundary-checks.json">Boundary validation</a></p>'
    body+=f'<p>{len(city["buildings"])} buildings / {len(city["cells"])} cells / {len(city["trees"])} trees · {len(city["lamps"])} lamps · {result["total_api_calls"]} API attempts including auxiliary observations / {result["total_metered_tokens"]:,} metered tokens.</p>'
    body+='<article><h2>Reference folder → LLM style extraction</h2><img src="style-contact-sheet.jpg"><p>'+html.escape(profile['description'])+'</p><pre>'+html.escape(json.dumps(profile,indent=2,ensure_ascii=False))+'</pre></article>'
    for view in ['overview','street','detail','seam']:
        body+=f'<article><h2>{view.title()} · same geometry and camera</h2><img src="comparison-{view}.jpg"></article>'
    if (run/'object-observations.json').exists():
        objects=json.loads((run/'object-observations.json').read_text(encoding='utf-8'));result['object_observation_coverage']=objects['coverage'];write_json(run/'result.json',result)
        from .quality import object_view_name
        for item in objects['objects']:
            folder=item['folder'];record=item['reference']
            body+='<article><h2>'+html.escape(record.get('label',item['object_id']))+' ? per-object evidence</h2><div class="grid">'+''.join('<img src="'+folder+'/reference-'+str(i).zfill(2)+'.jpg">' for i in range(item.get('image_count',1)))+'<img src="renders/styled-'+object_view_name(item['object_id'])+'.png"></div><p>Photo: '+html.escape(record['author'])+' ? '+html.escape(record['license'])+' ? <a href="'+html.escape(record['source_page'],quote=True)+'">source</a>. Approximate camera; hidden geometry uncertain.</p><pre>'+html.escape(json.dumps(item['observation'],indent=2,ensure_ascii=False))+'</pre></article>'
            for index,name in enumerate(record.get('images',[])):
                candidates=[o['reference'] for o in objects['objects'] if o['reference'].get('images')==[name]]
                credit=candidates[0] if candidates else record
                body+='<p>Reference '+str(index+1)+': '+html.escape(credit['author'])+' / '+html.escape(credit['license'])+' / <a href="'+html.escape(credit['source_page'],quote=True)+'">original and license</a>.</p>'
    if (run/'scene-plan.json').exists():
        body+='<article><h2>Shared scene reconstruction</h2><p>Every AOI building has a component; observation coverage does not establish fidelity. Factual and style acceptance are separate.</p><p><a href="scene-plan.json">Scene plan</a> | <a href="placement-checks.json">Placement checks</a> | <a href="material-binding-checks.json">Material bindings</a> | <a href="surface-bindings.json">Actual renderer surfaces</a></p><img src="scene-id-map.png"><pre>'+html.escape(json.dumps(result.get('scene_evidence_coverage'),indent=2))+'</pre></article>'
    body+='<article><h2>Styled views</h2><div class="grid">'+''.join(f'<a href="renders/styled-{v}.png"><img src="renders/styled-{v}.png">{v}</a>' for v in ['overview','north','grid','street','detail','seam'])+'</div></article>'
    body+='<article><h2>Checks and limitations</h2><pre>'+html.escape(json.dumps({'boundary':boundary,'performance':runtime.get('performance'),'review':review,'limitations':result['limitations']},indent=2,ensure_ascii=False))+'</pre></article>'
    body+='<p>© OpenStreetMap contributors / ODbL · Poly Haven textures / CC0 · Reference image supplied by user, style guidance only.</p>'
    (run/'index.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Urban AOI Style Pilot</title><style>'+style+'</style>'+body,encoding='utf-8')
    dest=ROOT/'reports/urban';dest.mkdir(parents=True,exist_ok=True)
    relative='../../runs/urban/'+run.name+'/'
    summary='<h1>Urban workflow · Urban AOI</h1><p class="note">Research pilot: partial, not validated photorealistic reconstruction.</p><p><a href="'+relative+'index.html">Open full visual evidence</a> · <a href="findings.md">Findings and reproducible commands</a></p><img src="'+relative+'comparison-overview.jpg"><p>Serve the run folder on localhost to open the interactive viewer. Opening the evidence report as a local file works without API keys.</p>'
    (dest/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Urban workflow research</title><style>'+style+'</style>'+summary,encoding='utf-8')
    return result
