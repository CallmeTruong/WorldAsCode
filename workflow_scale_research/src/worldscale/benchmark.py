"""Cross-site reports and an unchanged-code recipe transfer experiment."""

import json
from pathlib import Path

from . import design, georef
from .artifacts import file_hash, write_json
from .config import Settings
from .provider import Provider


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def summarize(runs, out, probes=()):
    cases=[]
    for source in map(Path,runs):
        result=read(source/'result.json')
        attempt=result.get('best_attempt')
        folder=Path(result['selected_render']) if result.get('selected_render') else source/f'attempt-{attempt}'
        review=read(folder/'review.json') if (folder/'review.json').exists() else {}
        metrics=read(folder/'metrics.json') if (folder/'metrics.json').exists() else {}
        render=read(folder/'render-manifest.json') if (folder/'render-manifest.json').exists() else {}
        usage=read(source/'usage.json')
        cases.append({'run':str(source),'object_id':result.get('object_id'),'buildable':attempt is not None,
            'status':result.get('status'),'evaluation_complete':result.get('evaluation_complete',True),
            'accepted':result['accepted'],'metrics_passed':metrics.get('passed',False),
            'scores':{k:review.get(k) for k in design.ACCEPT},'metrics':metrics,
            'performance':render.get('manifest',{}).get('performance'),
            'attempts':len(result.get('attempts',[])),
            'attempt_errors':[a['error'] for a in result.get('attempts',[]) if a.get('error')],
            'unreviewed_attempts':[a['attempt'] for a in result.get('attempts',[]) if a.get('evaluation')=='unreviewed'],
            'usage':{k:usage.get(k) for k in ('calls','input_tokens','output_tokens','unknown_token_reserve','cache_hits','active_seconds','cost_usd')},
            'render':str(folder/'render-sheet.jpg')})
    report={'scope':'Small real-building pilot in one city; no statistical or production-scale guarantee.',
        'cases':cases,'buildable_cases':sum(c['buildable'] for c in cases),
        'metric_pass_cases':sum(c['metrics_passed'] for c in cases),'visually_accepted_cases':sum(c['accepted'] for c in cases),
        'probes':[{'path':str(p),'result':read(Path(p)/'result.json')} for p in probes]}
    write_json(out,report)
    return report


def replay(source_run,target_run,evidence_path,out,settings=None):
    source_run,target_run,out=map(Path,(source_run,target_run,out))
    if out.exists():
        raise ValueError('USE_NEW_REPLAY_DIRECTORY')
    out.mkdir(parents=True)
    source_result=read(source_run/'result.json')
    source=source_run/f"attempt-{source_result['best_attempt']}"/'design.mjs'
    kit=source_run/'kit-versions/base/kit.mjs'
    if file_hash(kit)!=file_hash(target_run/'kit-versions/base/kit.mjs'):
        raise ValueError('REPLAY_REQUIRES_SAME_KIT_VERSION')
    evidence=georef.load_evidence(evidence_path)
    if file_hash(evidence['path'])!=read(target_run/'result.json')['evidence_sha256']:
        raise ValueError('TARGET_EVIDENCE_CHANGED')
    site,style=read(target_run/'site.json'),read(target_run/'style.json')
    code=source.read_text(encoding='utf-8')
    metrics,error=design.render_attempt(out,code,site,style,evidence,kit_path=kit)
    result={'source_code_sha256':file_hash(source),'replay_code_sha256':file_hash(out/'design.mjs'),
            'source_run':str(source_run),'target_run':str(target_run),'kit_sha256':file_hash(kit),
            'author_calls':0,'metrics':metrics,'error':error,'accepted':False,'evaluation_complete':False}
    write_json(out/'result.json',result)
    if not error:
        provider=Provider(settings or Settings.load(),out,max_calls=1,max_tokens=65000,max_seconds=300)
        images=[target_run/'reference-sheet.jpg',out/'render-sheet.jpg',*sorted(target_run.glob('style-*.jpg')),
                target_run/'reference-details.jpg',out/'detail-sheet.jpg']
        try:
            review=design.critic(provider,'unchanged-recipe-transfer',site,style,metrics,images)
            write_json(out/'review.json',review)
            scores=design.validated_scores(review)
            result.update({'scores':scores,'accepted':metrics['passed'] and all(scores[k]>=v for k,v in design.ACCEPT.items()),
                           'usage':provider.usage,'evaluation_complete':True})
        except Exception as exc:
            result.update({'review_error':type(exc).__name__+': '+str(exc),'usage':provider.usage})
    write_json(out/'result.json',result)
    return result


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--runs',type=Path,nargs='+')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--probes',type=Path,nargs='*',default=[])
    p.add_argument('--replay-from',type=Path)
    p.add_argument('--target-run',type=Path)
    p.add_argument('--evidence',type=Path)
    args=p.parse_args()
    if args.replay_from:
        print(json.dumps(replay(args.replay_from,args.target_run,args.evidence,args.out)))
    else:
        print(json.dumps(summarize(args.runs,args.out,args.probes)))
