from building_workflow.urban.streetscape import decorate_streets


def rect(x0,z0,x1,z1):return {'outer':[[x0,z0],[x1,z0],[x1,z1],[x0,z1]],'holes':[]}


def test_context_rows_are_seeded_idempotent_and_preserve_observed_core():
    city={'bounds':[-120,-80,120,80],'core_bounds':[-20,-20,20,20],'buildings':[dict(rect(30,5,40,20),id='b')],
          'surfaces':{'road':[rect(-120,-5,120,5)],'pavement':[rect(-120,5,120,8),rect(-120,-8,120,-5)]},
          'roads':[{'id':'way/1','points':[[-100,0],[100,0]],'width':10,'walk':False,'area':False}],
          'trees':[{'id':'observed','position':[-60,6.7],'seed':123}],'lamps':[]}
    options={'curbs':True,'extend_tree_rows':True,'add_lamps':True,'inferred_lane_dashes':True,'include_core':False,'tree_spacing_m':14}
    a=decorate_streets(city,options);b=decorate_streets(city,options)
    assert a['trees']==b['trees'] and a['trees'][0]==city['trees'][0]
    assert len(a['trees'])>1 and len(a['lamps'])>0
    assert all(abs(t['position'][0])>20 for t in a['trees'][1:])
    assert not any(29<t['position'][0]<41 and t['position'][1]>4 for t in a['trees'][1:])
    assert decorate_streets(a,options)['trees']==a['trees']
    assert a['roads'][0]['markings_inferred'] and not a['roads'][0].get('markings_verified')
    disabled=decorate_streets(a,{**options,'extend_tree_rows':False,'inferred_lane_dashes':False})
    assert disabled['trees']==city['trees'] and disabled['lamps']==[]
    assert not disabled['roads'][0].get('markings_inferred')
