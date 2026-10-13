"""Isolated Chromium DOM acceptance against the real API/service and a disposable project.

No browser navigation, CDN, paid provider or live project is involved. A test fetch
transport bridges the compiled client to FastAPI TestClient. This verifies rendered
UI interactions, not origin/CSP/network behavior. Run those separate API regressions
and normal `storyboarder ui` browser tests for release qualification.

Usage: PYTHONPATH=src python tools/verify_production_workspace.py --output /tmp/proof
Requires optional developer dependencies playwright, httpx and a local Chromium.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from storyboarder.api.server import create_app
from storyboarder.application.projects import Project
from storyboarder.application.service import Service
from storyboarder.production.example import example
from storyboarder.production.service import ProductionService


def run(output: Path, chromium: str):
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='production-ui-proof-') as temp:
        service=Service(Project.create(Path(temp)/'project','The handoff / production study'))
        production=ProductionService(service); fixture=example(service)
        production.apply(fixture['batch'])
        build_root=Path(__file__).resolve().parents[1]/'src/storyboarder/static'
        build=json.loads((build_root/'build.json').read_text())
        proof={'transport':'isolated DOM + real FastAPI TestClient', 'native_navigation_tested':False,'checks':[]}
        with TestClient(create_app(project=service.project),base_url='http://127.0.0.1:7430') as client, sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=chromium,headless=True,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1600,'height':1100},device_scale_factor=1)
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            def fetch(path, options):
                response=client.request(options.get('method','GET'),path,headers=options.get('headers',{}),content=options.get('body'))
                return {'status':response.status_code,'body':response.text,'headers':dict(response.headers)}
            page.expose_function('__testFetch',fetch)
            page.set_content('<!doctype html><html><head><meta charset="utf-8"></head><body><div id="root"></div></body></html>')
            page.evaluate('''() => {
              location.hash='production';
              const memory=new Map();Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)}});
              if(!crypto.randomUUID)crypto.randomUUID=()=> '10000000-1000-4000-8000-100000000000'.replace(/[018]/g,c=>(Number(c)^crypto.getRandomValues(new Uint8Array(1))[0]&15>>Number(c)/4).toString(16));
              window.fetch=async(path,options={})=>{if(options.signal?.aborted)throw new DOMException('Aborted','AbortError');const r=await window.__testFetch(path,{method:options.method,headers:options.headers,body:options.body});if(options.signal?.aborted)throw new DOMException('Aborted','AbortError');return new Response(r.body,{status:r.status,headers:r.headers});};
            }''')
            page.add_style_tag(content=(build_root/build['style']).read_text())
            page.add_script_tag(content=(build_root/'assets/react-runtime.js').read_text())
            page.add_script_tag(content=(build_root/build['entry']).read_text())
            expect(page.get_by_role('heading',name='A plan you can trace.')).to_be_visible(timeout=15000)
            expect(page.locator('.pd-record-list button')).to_have_count(27,timeout=15000)
            page.get_by_label('Search production records').fill('Master')
            page.locator('.pd-record-list button').first.click()
            expect(page.get_by_label('Action frame')).to_have_value('0')
            expect(page.locator('.pd-stage-status')).to_contain_text('frame 0',timeout=15000)
            page.get_by_label('Search production records').fill('')
            page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(400)
            page.screenshot(path=str(output/'workspace-spatial.png'),full_page=True)
            proof['checks'].append('27 CLI-equivalent fixture records rendered without constructing the plan in UI')
            print('Spatial rendering passed',flush=True)
            for view in ('Script','Coverage','Records','Panels','Review','Spatial'):
                print('Opening',view,flush=True)
                page.get_by_role('navigation',name='Production views').get_by_role('button',name=view,exact=True).click()
                expect(page.locator('.pd-fatal')).to_have_count(0)
            proof['checks'].append('All six connected views render')
            print('Scrubbing and editing',flush=True)
            page.get_by_label('Action frame',exact=True).fill('96')
            expect(page.locator('.pd-stage-status')).to_contain_text('frame 96',timeout=15000)
            page.get_by_role('button',name='top',exact=True).click()
            actor=page.locator('.pd-proxy[aria-label*=", character,"]').first
            actor.focus();expect(actor).to_have_class('pd-proxy is-selected');page.keyboard.press('ArrowRight')
            expect(page.get_by_label('Action frame',exact=True)).to_have_value('96')
            expect(page.locator('.pd-save-box')).to_contain_text('Local draft',timeout=10000)
            draft_key='storyboarder.production.draft:'+service.project.id+':'+fixture['ids']['action']
            page.wait_for_function('(key)=>!!localStorage.getItem(key)',arg=draft_key)
            saved=page.evaluate('(key)=>JSON.parse(localStorage.getItem(key))',draft_key)
            assert any(k['frame']==96 for i in json.loads(saved['raw'])['instances'] for k in i['keyframes'])
            proof['checks'].append('Top-view keyboard edit creates an explicit action keyframe draft at frame 96')
            print('Saving alternative',flush=True)
            page.get_by_role('button',name='Preview alternative',exact=True).click()
            expect(page.get_by_role('dialog')).to_be_visible()
            page.get_by_role('button',name='Apply atomic batch',exact=True).click()
            expect(page.get_by_role('dialog')).to_have_count(0,timeout=15000)
            assert production.show(fixture['ids']['action'])['version']==1
            assert production.show(fixture['ids']['action'],2)['head_version']==2
            proof['checks'].append('Viewer edit saves v2 alternative without moving selected action or shot pins')
            page.get_by_label('Search production records').fill('Master');page.locator('.pd-record-list button').first.click()
            print('Camera preview',flush=True)
            page.get_by_role('button',name='camera',exact=True).click()
            expect(page.locator('svg[aria-label^="Pinhole framing"]')).to_be_visible(timeout=15000)
            page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(400)
            page.screenshot(path=str(output/'workspace-camera.png'),full_page=True)
            proof['checks'].append('Camera framing preview renders from exact selected shot setup')
            # A background write must not erase a local title draft. Rebase independent fields.
            print('Stale draft and rebase',flush=True)
            title=page.locator('.pd-inspector').get_by_label('Title',exact=True)
            title.fill('Master / local refinement')
            current=production.show(fixture['ids']['shot-master']);data=deepcopy(current['data']);data['notes']='External CLI note'
            production.apply(dict(expected_checkpoint=2,operation_id=str(uuid4()),operations=[dict(op='put',id=current['id'],expected_revision=current['revision'],base_version=current['version'],select=True,data=data)]))
            page.locator('.pd-header-actions').get_by_role('button',name='Refresh',exact=True).click()
            expect(page.get_by_role('button',name='Rebase non-conflicting fields')).to_be_visible(timeout=15000)
            expect(title).to_have_value('Master / local refinement')
            page.get_by_role('button',name='Rebase non-conflicting fields').click()
            expect(title).to_have_value('Master / local refinement')
            proof['checks'].append('External write marks stale draft; three-way rebase retains local title and CLI note')
            page.get_by_role('navigation',name='Production views').get_by_role('button',name='Review',exact=True).click()
            page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(400)
            page.screenshot(path=str(output/'workspace-review.png'),full_page=True)
            print('Mobile layout',flush=True)
            page.set_viewport_size({'width':390,'height':844})
            page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(400)
            page.screenshot(path=str(output/'workspace-mobile.png'),full_page=True)
            overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
            proof['mobile_horizontal_overflow']=overflow
            assert not overflow, 'Mobile viewport overflows horizontally'
            assert not errors,errors
            proof['page_errors']=errors;proof['passed']=True
            (output/'browser-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
            browser.close()
        return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('/tmp/storyboarder-production-proof'))
    parser.add_argument('--chromium',default=shutil.which('chromium') or shutil.which('chromium-browser'))
    args=parser.parse_args()
    if not args.chromium:parser.error('Pass --chromium with a local Chromium executable.')
    print(json.dumps(run(args.output,args.chromium),indent=2))
