"""Per-object visual inspection and bounded, evidence-driven source patches."""
import json
import hashlib
from pathlib import Path
from ..provider import write_json
from ..runtime import validate_source


def object_view_name(identifier):
    return 'object-'+hashlib.sha256(identifier.encode()).hexdigest()[:12]


def patch_fragment(fragment,edits):
    """A fragment has no exported build factory; validate the composed module later."""
    if not isinstance(edits,list) or not 1<=len(edits)<=64:raise ValueError('INVALID_OBJECT_PATCH')
    for edit in edits:
        old,new=edit.get('old'),edit.get('new')
        if not isinstance(old,str) or not old or fragment.count(old)!=1 or not isinstance(new,str):raise ValueError('OBJECT_PATCH_ANCHOR_NOT_UNIQUE')
        fragment=fragment.replace(old,new,1)
    return fragment


def inspect_objects(run,provider,iteration):
    manifest=run/'object-observations.json';reviews=[]
    if manifest.exists():
        objects=json.loads(manifest.read_text(encoding='utf-8'))['objects']
        for item in objects:
            folder=run/item['folder'];refs=sorted(folder.glob('reference-*.jpg'))
            prompt='''Assess reconstruction quality for this ONE object. First images are factual photographs, followed by actual generated front and overhead renders. Viewpoints are approximate, not calibrated. The overhead render is NOT aerial ground truth. Compare target identity, silhouette, proportions, roof, openings, base/stairs, distinguishing details, material boundaries and visible texture. Do not reward a generic building merely for having windows. Do not request invented hidden details. Return JSON {object_id,accepted:boolean,identity_features_matched:[],issues:[{severity:"critical|major|minor",part,cause:"geometry|material|camera|data",evidence,action}],missing_evidence:[],confidence:0..1}. accepted must be false while any critical/major identity/material issue remains. Missing photo views must be disclosed; do not call this metric accuracy. No palette/style color matching: preserve the object's own appearance. Target and observation: '''+json.dumps(item,ensure_ascii=False)
            result=provider.call('object-quality-'+str(iteration)+'-'+Path(item['folder']).name,prompt,
                [*refs,run/'renders'/('styled-'+object_view_name(item['object_id'])+'.png'),run/'renders'/('styled-'+object_view_name(item['object_id'])+'-top.png')],provider.settings.review_model,3000)
            if not isinstance(result.get('accepted'),bool) or not isinstance(result.get('issues'),list):raise ValueError('INVALID_OBJECT_QUALITY_REVIEW')
            if any(i.get('severity') in ['critical','major'] for i in result['issues']):result['accepted']=False
            result['object_id']=item['object_id'];result['folder']=item['folder'];reviews.append(result)
    report={'iteration':iteration,'technical_valid':True,'visual_accepted':bool(reviews) and all(r['accepted'] for r in reviews),
        'objects':reviews,'unobserved_context':'Proxies are not reconstructed/accepted objects.'}
    write_json(run/f'quality-review-{iteration:02d}.json',report);write_json(run/'quality-review.json',report)
    return report


def refine_objects(run,provider,review):
    source_path=run/'building-generator.ts';source=source_path.read_text(encoding='utf-8');changed=False
    for item in review['objects']:
        actionable=[i for i in item['issues'] if i['severity'] in ['critical','major'] and i['cause'] in ['geometry','material']]
        if not actionable:continue
        folder=run/item['folder'];name='buildObserved_'+Path(item['folder']).name[:10]
        start=source.index('function '+name+'(')
        ends=[p for token in ['\nfunction buildObserved_','\nexport function build('] if (p:=source.find(token,start+1))>=0]
        fragment=source[start:min(ends) if ends else len(source)]
        prompt='''Repair ONLY this object function based on the actual rendered defects and factual photos. Return JSON {edits:[{old:"unique exact source substring",new:"replacement"}],reason}. Preserve object anchor, other objects and native material identity. No palette, URLs, imports or host APIs. Prioritize silhouette/roof/part proportions and visible identity before adding tiny detail. Do not increase unseen detail. Fix geometry rather than hide it using camera. Source and actual review: '''+json.dumps({'source':fragment,'issues':actionable},ensure_ascii=False)
        raw=provider.call('object-visual-refine-'+Path(item['folder']).name,prompt,
            [*sorted(folder.glob('reference-*.jpg')),run/'renders'/('styled-'+object_view_name(item['object_id'])+'.png')],provider.settings.code_model,6500)
        history=run/'source-history';history.mkdir(exist_ok=True);write_json(history/('visual-'+Path(item['folder']).name+'.json'),raw)
        try:corrected=patch_fragment(fragment,raw.get('edits'))
        except ValueError as error:
            write_json(history/('visual-rejected-'+Path(item['folder']).name+'.json'),{'error':str(error),'object_id':item['object_id']})
            continue
        candidate=source[:start]+corrected+source[start+len(fragment):];validate_source(candidate);source=candidate
        changed=True
    if changed:
        validate_source(source);(run/'source-history'/'before-visual-refinement.ts').write_text(source_path.read_text(encoding='utf-8'),encoding='utf-8');source_path.write_text(source,encoding='utf-8')
    return changed
