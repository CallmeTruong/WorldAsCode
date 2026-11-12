"""Bounded documentation retrieval and method dependency slices for a kit.

This is a cooperative authoring contract, not a JavaScript security parser.
Master releases remain complete; render jobs compile only referenced methods.
"""

import json
import re
import shutil
from collections import Counter
from pathlib import Path

from .artifacts import digest, file_hash, write_json

METHOD = re.compile(r'^  ([A-Za-z_]\w*)\([^\n]*\) \{',re.M)
GROUPS={
    'core':{'walls','material','edge','along','at','look'},
    'shell':{'walls','band','ground'},
    'roofs':{'roof','roofY','gable','dormer'},
    'facades':{'window','bay','portal','pilasters','quoins'},
    'details':{'turret','chimney'},
    'geometry':{'box','cylinder','cone','prism','loft','add'},
}


def methods(source):
    matches=list(METHOD.finditer(source))
    if any(n!=1 for n in Counter(m.group(1) for m in matches).values()):
        raise ValueError('DUPLICATE_KIT_METHOD')
    return {m.group(1):source[m.start():matches[i+1].start() if i+1<len(matches) else source.index('\n}',m.start())]
            for i,m in enumerate(matches)}


def cards(api_path):
    text=Path(api_path).read_text(encoding='utf-8')
    result={name:{'id':name,'methods':sorted(names),'text':''} for name,names in GROUPS.items()}
    result['materials']={'id':'materials','methods':['material'],'text':''}
    for section in re.split(r'(?=^## )',text,flags=re.M):
        heading=section.split('\n',1)[0]
        if heading.startswith('# Building') or heading in ('## What you receive','## Rules','## Frames'):
            result['core']['text']+=section+'\n'
        elif heading=='## Materials':
            result['materials']['text']+=section+'\n'
        elif heading=='## Look':
            result['core']['text']+=section+'\n'
        elif heading=='## Candidate capability':
            key='extension.'+digest(section)[:12]
            names=sorted(set(re.findall(r'\b([A-Za-z_]\w*)\(',section)))
            result[key]={'id':key,'methods':names,'text':section}
        elif heading=='## Example fragment':
            continue
        else:
            for line in section.splitlines():
                used=set(re.findall(r'\bb\.([A-Za-z_]\w*)',line))
                for name,names in GROUPS.items():
                    if name!='core' and used&names:
                        result[name]['text']+=line+'\n'
    return {k:v for k,v in result.items() if v['text'].strip()}


def context(api_path, site=None, previous='', feedback=None, requested=(), method_names=(), max_chars=16000):
    catalog=cards(api_path)
    if any(key not in catalog for key in requested):
        raise ValueError('KIT_DOC_ID_NOT_FOUND')
    query=json.dumps([site or {},feedback or {}]).lower()
    used=set(re.findall(r'\bb\.([A-Za-z_]\w*)',previous or ''))|set(method_names)
    selected={'core','materials','shell','geometry'}&catalog.keys()
    selected.update(requested)
    # Direct API references always beat lexical matching; newest extension docs
    # are ranked first without injecting an unbounded accumulated history.
    scored=[]
    for order,(key,card) in enumerate(catalog.items()):
        score=20*bool(used&set(card['methods']))
        score+=sum(bool(re.search(r'\b'+re.escape(name)+r's?\b',query)) for name in card['methods'])
        if key=='facades':
            score+=2
        if key=='roofs':
            score+=2
        if score:
            scored.append((score,order,key))
    ranked=[key for _,_,key in sorted(scored,reverse=True)]
    # Small discovery index; documents themselves are loaded only when chosen.
    discover=list(dict.fromkeys([*requested,*ranked,*catalog]))[:12]
    required=set(selected)
    for key in ranked:
        if len(selected)>=8:
            break
        if sum(len(catalog[k]['text']) for k in selected|{key})<=max_chars:
            selected.add(key)
    if not required<=selected or sum(len(catalog[k]['text']) for k in selected)>max_chars:
        raise ValueError('KIT_CONTEXT_BUDGET_EXCEEDED')
    order=[k for k in catalog if k in selected]
    payload='\n'.join(catalog[k]['text'] for k in order)
    index=[{'id':k,'methods':catalog[k]['methods']} for k in discover]
    return {'text':payload,'index':index,'selected':order,'characters':len(payload),
            'api_sha256':file_hash(api_path),'catalog_size':len(catalog)}


def runtime_slice(kit_path, design_code, destination):
    kit_path,destination=Path(kit_path),Path(destination)
    source=kit_path.read_text(encoding='utf-8')
    blocks=methods(source)
    used=set(re.findall(r'\bb\.([A-Za-z_]\w*)',design_code))
    used.update(re.findall(r'\bb\[[\'"]([A-Za-z_]\w*)[\'"]\]',design_code))
    unknown=used-set(blocks)-{'THREE'}
    if unknown:
        raise ValueError('KIT_UNKNOWN_REFERENCED_METHOD:'+','.join(sorted(unknown)))
    keep={'constructor','walls','finish'}|(used&blocks.keys())
    while True:
        called=set(re.findall(r'this\.([A-Za-z_]\w*)\(', '\n'.join(blocks[k] for k in keep)))&blocks.keys()
        if called<=keep:
            break
        keep.update(called)
    sliced=source
    for name,block in blocks.items():
        if name not in keep:
            sliced=sliced.replace(block,'',1)
    destination.mkdir(parents=True,exist_ok=False)
    (destination/'kit.mjs').write_text(sliced,encoding='utf-8')
    pending=['kit.mjs']
    copied={'kit.mjs'}
    while pending:
        name=pending.pop()
        text=(destination/name).read_text(encoding='utf-8')
        for relative in re.findall(r"from\s+['\"]\./([^'\"]+)['\"]",text):
            if Path(relative).name!=relative:
                raise ValueError('KIT_SLICE_UNSUPPORTED_RELATIVE_IMPORT')
            if relative not in copied:
                shutil.copy2(kit_path.parent/relative,destination/relative)
                copied.add(relative)
                pending.append(relative)
    write_json(destination/'selection.json',{'master_sha256':file_hash(kit_path),'selected_methods':sorted(keep),
        'omitted_methods':sorted(blocks.keys()-keep),'master_characters':len(source),'selected_characters':len(sliced),
        'modules':{name:file_hash(destination/name) for name in copied}})
    return destination/'kit.mjs'
