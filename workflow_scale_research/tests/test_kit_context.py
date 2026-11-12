import json

import pytest

from worldscale import design
from worldscale.config import ROOT
from worldscale.kit_context import context, methods, runtime_slice


def test_context_does_not_inject_hundreds_of_unrelated_extensions(tmp_path):
    api=tmp_path/'kit-api.md'
    original=(ROOT/'runtime/kit-api.md').read_text(encoding='utf-8')
    api.write_text(original+'\n'.join(f'\n## Candidate capability\nUnrelated vegetation feature {i}: b.treeVariant{i}(seed)' for i in range(300)),encoding='utf-8')
    result=context(api,{'roof':{'form':'flat'},'tags':{'building':'office'}})
    assert result['catalog_size']>300 and len(result['index'])<=12
    assert result['characters']<=16000 and 'Unrelated vegetation' not in result['text']
    with pytest.raises(ValueError,match='DOC_ID'):
        context(api,requested=['../../secrets'])


def test_runtime_slice_keeps_guards_and_transitive_helpers(tmp_path):
    selected=runtime_slice(ROOT/'runtime/kit.mjs',"b.material('x',{});b.walls({});b.window(f,{});",tmp_path/'selected')
    source=selected.read_text(encoding='utf-8')
    names=methods(source)
    assert {'constructor','walls','finish','window','_add','_material','_box'}<=names.keys()
    assert 'roof' not in names and 'chimney' not in names
    assert 'KIT_MEASURED_WALL_GEOMETRY_MUTATED' in source
    assert (selected.parent/'surfaces.mjs').exists()
    manifest=json.loads((selected.parent/'selection.json').read_text())
    assert manifest['selected_characters']<manifest['master_characters']
    with pytest.raises(ValueError,match='UNKNOWN_REFERENCED'):
        runtime_slice(ROOT/'runtime/kit.mjs','b.nonexistent()',tmp_path/'bad')


def test_author_can_request_one_document_without_receiving_all_sources(tmp_path):
    class Provider:
        run=tmp_path

        def __init__(self):
            self.prompts=[]

        def call(self,node,prompt,images,max_output):
            self.prompts.append(prompt)
            return {'request_kit_docs':['details']} if len(self.prompts)==1 else {'code':'export function design(site,b,style){}'}

    provider=Provider()
    result=design.author(provider,'author',{'views':['north'],'roof':{'form':'flat'}},{},[])
    assert result['code'] and len(provider.prompts)==2
    assert 'b.chimney(frame' not in provider.prompts[0]
    assert 'b.chimney(frame' in provider.prompts[1]
    assert 'class Builder' not in provider.prompts[1]
