import json
from pathlib import Path
from ..provider import write_json


PROXY_SOURCE = '''import * as THREE from 'three';
export function build(params:any={}) {
 const root=new THREE.Group();
 const mat=new THREE.MeshStandardMaterial({name:'unobserved_context_proxy',color:0xb9bdc1,roughness:.9});
 for(const b of params.city.buildings) {
   const points=(r:any)=>r.map(([x,z]:number[])=>new THREE.Vector2(x,-z));
   let outer=points(b.outer);if(!THREE.ShapeUtils.isClockWise(outer))outer.reverse();
   const shape=new THREE.Shape(outer);
   for(const h of b.holes||[]){let ring=points(h);if(THREE.ShapeUtils.isClockWise(ring))ring.reverse();shape.holes.push(new THREE.Path(ring));}
   const group=new THREE.Group();group.name=b.id;group.userData.objectId=b.id;group.userData.evidence='unobserved proxy';
   const contour=shape.getPoints(),holes=shape.holes.map(h=>h.getPoints());
   if(contour.length>1&&contour[0].equals(contour[contour.length-1]))contour.pop();
   for(const h of holes)if(h.length>1&&h[0].equals(h[h.length-1]))h.pop();
   const vertices=[...contour,...holes.flat()];
   for(const face of THREE.ShapeUtils.triangulateShape(contour,holes)){
     const triangle=new THREE.Shape(face.map(i=>vertices[i]));
     const geo=new THREE.ExtrudeGeometry(triangle,{depth:b.height,bevelEnabled:false});geo.rotateX(-Math.PI/2);
     group.add(new THREE.Mesh(geo,mat));
   }
   root.add(group);
 }
 return root;
}'''


def generate_buildings(city,run:Path,provider):
    """Unknown objects stay explicit context proxies; photos create bespoke modules."""
    path=run/'building-generator.ts'
    if path.exists():return path
    path.write_text(PROXY_SOURCE,encoding='utf-8')
    write_json(run/'generation-notes.json',{'scope':'Unobserved context proxies only. No invented generic facade detail. Photo-backed targets replace these independently.'})
    return path


def repair_source(run:Path,provider,error):
    from ..workflow import apply_edits
    from ..runtime import validate_source
    path=run/'building-generator.ts';source=path.read_text(encoding='utf-8')
    evidence=[str(error)]
    for name in ['urban-compile.log','urban-runtime-result.json','placement-checks.json','material-binding-checks.json']:
        if (run/name).exists():evidence.append((run/name).read_text(encoding='utf-8')[:7000])
    if (run/'urban-geometry-checks.json').exists():
        gate=json.loads((run/'urban-geometry-checks.json').read_text(encoding='utf-8'))
        failures=gate.get('failures',[])
        evidence.append(json.dumps({'ACTUAL_GATE_FAILURES':failures,'triangleCount':gate.get('triangleCount'),
            'note':'LOD metadata fields are informational unless explicitly listed in failures. Do not add LOD or change object hierarchy. Open edges require truly capped/closed geometry, not overlapping separate caps.'}))
    prompt='Repair this procedural Three.js TypeScript generator with minimal unique exact edits. Keep all object identities/materials and root hierarchy. Do not introduce new features such as LOD or hardcoded building heights. Fix ACTUAL_GATE_FAILURES only. No host APIs, no palette override. Return JSON {"edits":[{"old":"exact unique substring with sufficient context","new":"replacement"}],"reason":"why"}.\nEvidence:\n'+'\n'.join(evidence)+'\nSource:\n'+source
    raw=provider.call('urban-repair',prompt,(),provider.settings.code_model,5000)
    corrected=apply_edits(source,raw.get('edits'));validate_source(corrected)
    history=run/'source-history';history.mkdir(exist_ok=True);index=len(list(history.glob('*.ts')))
    (history/f'failed-{index:02d}.ts').write_text(source,encoding='utf-8');write_json(history/f'patch-{index:02d}.json',raw)
    path.write_text(corrected,encoding='utf-8');return raw
