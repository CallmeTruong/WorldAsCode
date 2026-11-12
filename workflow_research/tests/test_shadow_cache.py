import io,json,subprocess
from PIL import Image,ImageChops
from building_workflow.config import ROOT
from building_workflow.urban.style import NEUTRAL


def test_cached_shadows_match_live_shadows_after_light_and_visibility_changes(tmp_path):
    from playwright.sync_api import sync_playwright
    code="""import * as T from 'three';const root=new T.Group(),container=new T.Group();root.add(container);for(let i=0;i<2;i++){const a=new T.Group();a.userData.objectId='b'+i;const m=new T.Mesh(new T.BoxGeometry(5,10,5),new T.MeshStandardMaterial({color:0xb98565}));m.position.set(i*9-4.5,5,0);a.add(m);container.add(a);}console.log(JSON.stringify(root.toJSON()));"""
    scene=json.loads(subprocess.run(['node','--input-type=module','-e',code],cwd=ROOT,capture_output=True,text=True,check=True).stdout)
    bundle=tmp_path/'viewer.js'
    subprocess.run(['node',str(ROOT/'runtime/urban-bundle.mjs'),'viewer',str(tmp_path/'unused.ts'),str(bundle)],cwd=ROOT,capture_output=True,text=True,check=True)
    city={'bounds':[-25,-25,25,25],'scene_mode':True,'buildings':[{'id':'b'+str(i),'center':[i*9-4.5,0],'height':10,'outer':[[0,0],[5,0],[5,5],[0,5]]} for i in range(2)],'surfaces':{'road':[],'pavement':[]},'parks':[],'roads':[],'trees':[],'lamps':[],'cells':[]}
    settings={'exposure':1,'sun_intensity':2.5,'ambient_intensity':.5,'shadow_softness':2,'sun_azimuth_deg':50,'sun_elevation_deg':55}
    payload={'data':city,'buildings':scene,'assets':{},'profile':NEUTRAL,'presentation':settings,'neutral_presentation':{**settings,'sun_azimuth_deg':-70,'sun_elevation_deg':35},'render_probe':{'shadowSize':1024,'fitShadow':True}}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,chromium_sandbox=True);page=browser.new_page();page.set_content('<body></body>');page.add_script_tag(content=bundle.read_text())
        page.evaluate('p=>window.initCity(p)',payload)
        def pixels():return Image.open(io.BytesIO(page.locator('canvas').screenshot())).convert('RGB')
        def equivalent():
            page.evaluate('()=>window.probeCityShadowCaching(true)');cached=pixels()
            page.evaluate('()=>window.probeCityShadowCaching(false)');live=pixels()
            assert ImageChops.difference(cached,live).getbbox() is None
            return cached
        initial=equivalent()
        page.evaluate('()=>{window.probeCityShadowCaching(true);window.setCityStyle({},true)}');changed=pixels()
        assert ImageChops.difference(initial,changed).getbbox() is not None
        page.evaluate('()=>window.probeCityShadowCaching(false)');assert ImageChops.difference(changed,pixels()).getbbox() is None
        page.evaluate("()=>{window.probeCityShadowCaching(true);window.selectCityObject('b0',true)}");isolated=pixels()
        assert page.evaluate('()=>window.cityVisibleObjectIds()')==['b0']
        page.evaluate('()=>window.probeCityShadowCaching(false)');assert ImageChops.difference(isolated,pixels()).getbbox() is None
        page.evaluate('()=>window.resetCityObjects()');assert page.evaluate('()=>window.cityVisibleObjectIds()')==['b0','b1']
        browser.close()
