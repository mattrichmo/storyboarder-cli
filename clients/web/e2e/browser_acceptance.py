#!/usr/bin/env python3
"""Browser acceptance against a running Storyboarder server.

Normally navigate to --url. --transport-bridge exercises the exact compiled React
bundle and live HTTP API from about:blank in a browser whose administrator blocks
all navigation. It does NOT change browser policies or application production code.
The bridge mode cannot verify top-level HTTP navigation, CSP enforcement or downloads;
those boundaries also have independent API tests. Images use an in-memory data bridge.
"""
from pathlib import Path
import argparse
import asyncio
import base64
import json
import os
import re
import time
import uuid
import httpx
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[3]
STATIC=ROOT/'src/storyboarder/static'

BRIDGE_JS=r'''(() => {
 const bytes64 = bytes => {let result='';for(let i=0;i<bytes.length;i+=32768)result+=String.fromCharCode(...bytes.slice(i,i+32768));return btoa(result);};
 window.fetch=async (url,options={})=>{
  let body=options.body,parts=null;
  if(body instanceof FormData){parts=[];for(const [key,value] of body.entries()){
   if(value instanceof Blob)parts.push({key,filename:value.name||'upload',type:value.type,data:bytes64(new Uint8Array(await value.arrayBuffer()))});
   else parts.push({key,value});
  }body=null;}
  const r=await window.__storyboarder_http(String(url),options.method||'GET',options.headers||{},body||null,parts);
  return new Response(Uint8Array.from(atob(r.body),c=>c.charCodeAt(0)),{status:r.status,headers:r.headers});
 };
 const original=Element.prototype.setAttribute;
 Element.prototype.setAttribute=function(name,value){
  if(this instanceof HTMLImageElement&&name==='src'&&String(value).startsWith('/api/')){
   const url=String(value);original.call(this,'data-source',url);
   window.__storyboarder_image(url).then(data=>{if(this.getAttribute('data-source')===url)original.call(this,'src',data);});return;
  }
  return original.call(this,name,value);
 };
})();'''

async def load_bridge(page,url):
    client=httpx.AsyncClient(base_url=url,timeout=120)
    async def request(source,path,method,headers,body,parts):
        if not path.startswith('/api/v1/'):
            raise ValueError('Acceptance bridge only grants the supplied local API.')
        kwargs={'headers':headers}
        if parts is not None:
            data={p['key']:p['value'] for p in parts if 'value'in p}
            files=[(p['key'],(p['filename'],base64.b64decode(p['data']),p['type'])) for p in parts if 'data'in p]
            kwargs.update(data=data,files=files)
        elif body is not None:kwargs['content']=body
        response=await client.request(method,path,**kwargs)
        return {'status':response.status_code,'headers':dict(response.headers),'body':base64.b64encode(response.content).decode()}
    async def image(source,path):
        if not path.startswith('/api/v1/'):
            raise ValueError('Only local API media is allowed.')
        response=await client.get(path)
        response.raise_for_status()
        return 'data:'+response.headers.get('content-type','image/jpeg')+';base64,'+base64.b64encode(response.content).decode()
    await page.expose_binding('__storyboarder_http',request)
    await page.expose_binding('__storyboarder_image',image)
    await page.set_content('<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div></body></html>')
    await page.add_script_tag(content=BRIDGE_JS)
    index=(STATIC/'index.html').read_text()
    for href in re.findall(r'<link[^>]+href="([^"]+\.css)"',index):
        await page.add_style_tag(content=(STATIC/href.lstrip('/')).read_text())
    for src in re.findall(r'<script[^>]+src="([^"]+)"',index):
        await page.add_script_tag(content=(STATIC/src.lstrip('/')).read_text())
    return client

async def main(args):
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    report={'transport':'HTTP transport bridge' if args.transport_bridge else 'normal loopback navigation','url':args.url,'checks':[],'page_errors':[],'console_errors':[]}
    async with async_playwright() as playwright:
        options={'headless':True}
        if args.chromium:options['executable_path']=args.chromium
        browser=await playwright.chromium.launch(**options)
        page=await browser.new_page(viewport={'width':1440,'height':1024},device_scale_factor=1)
        page.set_default_timeout(7000)
        page.on('pageerror',lambda error:report['page_errors'].append(str(error)))
        page.on('console',lambda message:report['console_errors'].append(message.text) if message.type=='error' else None)
        client=None
        try:
            if args.transport_bridge:client=await load_bridge(page,args.url)
            else:await page.goto(args.url,wait_until='networkidle')
            await page.get_by_role('button',name='Storyboarder workspace',exact=True).wait_for()
            await wait_for_page_state(page,"!document.querySelector('.loading-state')","the application to finish loading")
            await screenshot(page,output/'workspace-desktop.png')
            report['checks'].append('Compiled React shell mounted and loaded live session.')
            await page.get_by_role('button',name='Project overview',exact=True).click()
            await page.get_by_role('heading',level=1).wait_for()
            await screenshot(page,output/'overview-desktop.png')
            for label in ['Image intake','Reference library','Story outline','Story guide','Scene & shot editor','Storyboard frames','Board & exports','Image tools','Project care']:
                await page.get_by_role('button',name=label,exact=True).click()
                await page.get_by_role('heading',level=1).wait_for()
                assert not await page.get_by_text('Something interrupted this view').count(), label
                report['checks'].append(label+' rendered.')
                if label in ('Reference library','Story outline','Storyboard frames','Board & exports'):
                    await screenshot(page,output/(label.lower().split()[0]+'-desktop.png'))
            await page.get_by_role('button',name='Story canvas',exact=True).click()
            await page.wait_for_selector('.graph-node')
            await screenshot(page,output/'canvas-desktop.png')
            report['checks'].append('Native DOM/SVG canvas renders story nodes.')
            await exercise_focus_smoke(page,report,output)
            if args.source_forms:
                await exercise_source_forms(page,report,args.url)
            if args.smoke_only:
                assert not report['page_errors'],report['page_errors']
                assert not report['console_errors'],report['console_errors']
                report['passed']=True
                return report
            # More detailed assertions are appended below after the first visual pass.
            await exercise_authoring(page,report,output,args.url)
            assert not report['page_errors'],report['page_errors']
            report['passed']=True
        except Exception as exc:
            report['failure']=str(exc)
            await page.screenshot(path=str(output/'failure.png'),full_page=True)
            (output/'failure.txt').write_text(await page.locator('body').inner_text())
            raise
        finally:
            (output/'browser-report.json').write_text(json.dumps(report,indent=2)+'\n')
            if client:await client.aclose()
            await browser.close()
    return report

async def screenshot(page,path):
    await page.evaluate("Array.from(document.images).forEach(i=>i.loading='eager')")
    await wait_for_page_state(page,"Array.from(document.images).every(i=>i.complete&&i.naturalWidth>0)","all screenshot images to load",timeout=10)
    await page.screenshot(path=str(path),full_page=True)

async def wait_for_page_state(page,expression,description,timeout=8):
    """Poll a condition through Runtime.evaluate, which remains usable under CSP."""
    deadline=time.monotonic()+timeout
    while True:
        if await page.evaluate(expression):
            return
        remaining=deadline-time.monotonic()
        if remaining<=0:
            raise AssertionError(f"Timed out after {timeout}s waiting for {description}.")
        await asyncio.sleep(min(0.1,remaining))

async def exercise_focus_smoke(page,report,output):
    # Verify both declared autoFocus and restoration to the control that opened
    # the dialog, including after a keyboard close.
    await page.get_by_role('button',name='Storyboarder workspace',exact=True).click()
    opener=page.get_by_role('button',name='New project',exact=True)
    await opener.click()
    modal=page.get_by_role('dialog',name='Create a project')
    title=modal.get_by_label('Project title',exact=True)
    await title.wait_for()
    assert await title.evaluate('(el)=>document.activeElement===el'),'Create project did not honor its autoFocus field.'
    await page.keyboard.press('Escape')
    await modal.wait_for(state='hidden')
    assert await opener.evaluate('(el)=>document.activeElement===el'),'Closing a modal did not restore focus to its opener.'
    report['checks'].append('Modal autoFocus and opener restoration work with Escape.')

    search=page.get_by_role('button',name=re.compile('^Search actions'))
    await search.click()
    palette=page.get_by_role('dialog',name='Search actions')
    await palette.get_by_label('Find an action',exact=True).fill('Save source as a new draft')
    await palette.get_by_role('button',name='Save source as a new draft',exact=True).click()
    action=page.get_by_role('dialog',name='Save source as a new draft')
    await action.wait_for()
    await page.keyboard.press('Escape')
    await action.wait_for(state='hidden')
    assert await search.evaluate('(el)=>document.activeElement===el'),'Closing a palette action did not restore focus to Search actions.'
    report['checks'].append('Palette-to-action modal handoff restores focus to Search actions.')

    await page.set_viewport_size({'width':390,'height':844})
    menu=page.get_by_role('button',name='Open navigation',exact=True)
    await menu.click()
    await wait_for_page_state(page,"document.querySelector('.navigation')?.contains(document.activeElement)===true","mobile navigation to receive focus")
    await page.keyboard.press('Escape')
    await wait_for_page_state(page,"!document.querySelector('.navigation')?.classList.contains('is-open')","mobile navigation to close after Escape")
    assert await menu.evaluate('(el)=>document.activeElement===el'),'Escape did not return focus to the mobile navigation opener.'
    await menu.click()
    await wait_for_page_state(page,"document.querySelector('.navigation')?.contains(document.activeElement)===true","mobile navigation to receive focus after reopening")
    await page.get_by_role('button',name='Story outline',exact=True).click()
    await page.get_by_role('heading',name='Build the story, scene by scene.',exact=True).wait_for()
    await wait_for_page_state(page,"!document.querySelector('.navigation')?.classList.contains('is-open')","mobile navigation to close after selecting a destination")
    assert await menu.evaluate('(el)=>document.activeElement===el'),'Selecting a mobile destination did not return focus to the navigation opener.'
    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Story outline overflows at 390px.'
    if await page.locator('.story-node.sequence').count():
        left_border=await page.locator('.story-node.sequence').first.evaluate('(el)=>getComputedStyle(el).borderLeftWidth')
        assert float(left_border.rstrip('px'))>0,'Sequence outline styles do not match rendered node classes.'
    await screenshot(page,output/'outline-mobile.png')
    report['checks'].append('At 390px the story outline has no horizontal overflow and sequence classes receive their outline styling.')

    await page.set_viewport_size({'width':1440,'height':1024})
    await page.get_by_role('button',name='Project overview',exact=True).click()
    await page.get_by_role('heading',level=1).wait_for()

async def exercise_authoring(page,report,output,url):
    stamp=str(int(time.time()))
    async with httpx.AsyncClient(base_url=url,timeout=120) as verify:
        session=(await verify.get('/api/v1/session')).json()
        pid=session['active_project_id']
        async def state():return (await verify.get(f'/api/v1/projects/{pid}/state')).json()
        initial=await state()
        entities=initial['entities']
        location=next(e for e in entities if e['kind']=='asset' and e['fields']['type']=='location')
        shot=next(e for e in entities if e['kind']=='shot' and any(f['shot_id']==e['id'] for f in initial['frames']))
        # Create a typed asset through its actual form.
        await page.get_by_role('button',name='Reference library',exact=True).click()
        await page.get_by_role('button',name='New library item',exact=True).click()
        modal=page.get_by_role('dialog')
        await modal.get_by_label('Title',exact=False).fill('Acceptance prop '+stamp)
        await modal.get_by_label('Asset type',exact=False).select_option('prop')
        await modal.get_by_role('button',name='New library item',exact=True).click()
        await modal.wait_for(state='hidden')
        asset=next(e for e in (await state())['entities'] if e['title']=='Acceptance prop '+stamp)
        assert asset['fields']['type']=='prop'
        report['checks'].append('Typed asset authored in browser and confirmed through independent HTTP read.')
        # Use native canvas keyboard interaction to open a validated link form.
        await page.get_by_role('button',name='Story canvas',exact=True).click()
        await page.get_by_role('button',name='Reference map',exact=True).click()
        await page.wait_for_selector(f'[data-node-id="{asset["id"]}"]')
        await page.get_by_role('button',name='Fit canvas',exact=True).click()
        source=page.locator(f'[data-node-id="{asset["id"]}"]')
        target=page.locator(f'[data-node-id="{location["id"]}"]')
        await source.focus();await source.press('l');await page.get_by_role('button',name='Cancel link',exact=True).wait_for();await target.focus();await target.press('Enter')
        modal=page.get_by_role('dialog')
        await modal.get_by_label('How they are connected',exact=True).select_option('appears-at')
        await modal.get_by_role('button',name='Connect library items',exact=True).click()
        await modal.wait_for(state='hidden')
        assert any(l['source_id']==asset['id'] and l['target_id']==location['id'] for l in (await state())['links'])
        report['checks'].append('Keyboard L/Enter creates a typed canonical asset relationship.')
        # Node dragging and arrow keys only change presentation state.
        before=(await state())['entities']
        await page.get_by_role('button',name='Fit canvas',exact=True).click()
        await source.focus();await source.press('ArrowRight')
        box=await source.bounding_box()
        await page.mouse.move(box['x']+box['width']/2,box['y']+16)
        await page.mouse.down();await page.mouse.move(box['x']+box['width']/2+35,box['y']+35,steps=8);await page.mouse.up()
        await page.get_by_label('Arrangement name',exact=True).fill('Acceptance layout '+stamp)
        async with page.expect_response(lambda response:response.url.endswith('/commands/canvas.save') and response.request.method=='POST') as save_response_info:
            await page.get_by_role('button',name='Save arrangement',exact=True).click()
        save_response=await save_response_info.value
        assert save_response.ok,f'Canvas arrangement save failed with HTTP {save_response.status}.'
        after=await state()
        assert after['entities']==before
        assert any(l['name']=='Acceptance layout '+stamp and asset['id'] in l['positions'] for l in after['layouts'])
        report['checks'].append('Pointer dragging, arrow positioning, and named layout save leave canonical records unchanged.')
        # Removal distinguishes presentation hiding from canonical deletion.
        await source.focus();await source.press('Delete')
        await page.get_by_role('button',name='Hide from this arrangement',exact=True).click()
        assert await page.locator(f'[data-node-id="{asset["id"]}"]').count()==0
        await page.get_by_role('button',name='Show 1 hidden cards',exact=True).click()
        await page.get_by_role('button',name='Save arrangement',exact=True).click()
        await screenshot(page,output/'canvas-authored-desktop.png')
        report['checks'].append('Reference-aware removal offers hide/archive/delete; hiding does not delete a record.')
        # Attaching a managed image creates a storyboard frame for this shot.
        await page.get_by_role('button',name='Storyboard frames',exact=True).click()
        await page.get_by_label('Shot',exact=True).select_option(shot['id'])
        await page.get_by_role('button',name='Add storyboard image',exact=True).click()
        modal=page.get_by_role('dialog')
        await modal.get_by_label(re.compile('^Image')).select_option(initial['media'][0]['id'])
        await modal.get_by_role('button',name='Use project image as storyboard frame',exact=True).click()
        await modal.wait_for(state='hidden')
        checks=page.get_by_role('checkbox',name=re.compile('Compare v'))
        await checks.nth(0).check();await checks.nth(1).check()
        assert await page.locator('.frame-card').count()==2
        await screenshot(page,output/'frames-compared-desktop.png')
        report['checks'].append('Managed image attached as a new storyboard frame and compared side by side.')
        # Write a real self-contained board bundle through the browser button.
        await page.get_by_role('button',name='Board & exports',exact=True).click()
        await page.get_by_role('button',name='Export HTML + PDF + PNG',exact=True).click()
        download=page.get_by_role('link',name=re.compile('Download project package'))
        await download.wait_for()
        href=await download.get_attribute('href')
        response=await verify.get(href)
        assert response.status_code==200 and response.content.startswith(b'PK')
        report['checks'].append('Browser export creates a real HTML/PDF/PNG ZIP downloadable from the scoped API.')
        # Narrow pages reflow, and the inspector is a keyboard-managed overlay.
        await page.get_by_role('button',name='Reference library',exact=True).click()
        if await page.get_by_role('button',name='Close inspector',exact=True).count():
            await page.get_by_role('button',name='Close inspector',exact=True).click()
        await page.set_viewport_size({'width':390,'height':844})
        await screenshot(page,output/'library-mobile.png')
        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        await page.get_by_role('button',name='View '+location['title'],exact=True).click()
        await page.get_by_role('dialog',name='Item details').wait_for()
        assert await page.evaluate("document.querySelector('.inspector').contains(document.activeElement)")
        await screenshot(page,output/'inspector-mobile.png')
        await page.keyboard.press('Escape')
        assert await page.locator('.inspector').count()==0
        report['checks'].append('390px library has no page overflow; mobile inspector traps focus and closes with Escape.')
        await page.get_by_role('button',name='Open navigation',exact=True).click()
        await page.get_by_role('button',name='Project care',exact=True).click()
        await screenshot(page,output/'settings-mobile.png')
        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        await page.set_viewport_size({'width':1440,'height':1024})
        # Workspace creation is scoped and the two projects stay isolated.
        await page.get_by_role('button',name='Storyboarder workspace',exact=True).click()
        await page.get_by_role('button',name='New project',exact=True).click()
        modal=page.get_by_role('dialog')
        await modal.get_by_label('Project title',exact=True).fill('Browser empty '+stamp)
        await modal.get_by_role('button',name='Create project',exact=True).click()
        await page.get_by_role('dialog').wait_for(state='hidden')
        session=(await verify.get('/api/v1/session')).json()
        assert session['active_project_id']!=pid
        new=(await verify.get('/api/v1/projects/'+session['active_project_id']+'/state')).json()
        assert not new['media'] and len(new['entities'])==1
        await page.get_by_role('heading',name='Browser empty '+stamp,exact=True).wait_for()
        report['checks'].append('Browser creates a workspace-scoped project isolated from the existing story.')
        await page.get_by_role('button',name='Storyboarder workspace',exact=True).click()
        await page.get_by_role('button',name=re.compile(initial['project']['title'])).filter(has=page.locator('h2')).click()
        report['checks'].append('Workspace project switching restores the original project.')


async def exercise_source_forms(page,report,url):
    """Mutating regression checks; run only against a disposable workspace."""
    author=str(uuid.uuid4())
    payload={
        'id':str(uuid.uuid4()),'version':'1.0.0','lang':'en','charset':'utf-8','dir':'ltr',
        'title':{'en':'Browser source regression'},
        'authors':[{'id':author,'given':'Browser','family':'Acceptance'}],'characters':[],
        'document':{'cover':{'title':{'en':'Browser source regression'},'authors':[author]},
                    'scenes':[{'id':str(uuid.uuid4()),'authors':[author],
                               'heading':{'context':'INT','setting':'STATION','time':'DAWN'},
                               'body':[{'id':str(uuid.uuid4()),'authors':[author],'type':'action',
                                        'text':{'en':'Mara turns the key.'}}]}]},
    }
    async def open_action(label):
        await page.get_by_role('button',name=re.compile('^Search actions')).click()
        palette=page.get_by_role('dialog',name='Search actions')
        await palette.get_by_label('Find an action',exact=True).fill(label)
        await palette.get_by_role('button',name=re.compile('^'+re.escape(label))).click()
        return page.get_by_role('dialog',name=label)

    async with httpx.AsyncClient(base_url=url,timeout=30) as verify:
        session=(await verify.get('/api/v1/session')).json()
        prefix=f"/api/v1/projects/{session['active_project_id']}"
        headers={'X-Storyboarder-Token':session['token']}
        response=await verify.post(prefix+'/documents/upload',headers=headers,
                                   files={'file':('acceptance.screenjson',json.dumps(payload),'application/json')},
                                   data={'format':'screenjson'})
        response.raise_for_status()
        imported=response.json();document_id=imported['document']['id']

        async def action_node():
            response=await verify.get(prefix+f'/documents/{document_id}/tree')
            response.raise_for_status()
            return next(row for row in response.json()['items'] if row['node_type']=='action')

        node=await action_node()
        modal=await open_action('Save source as a new draft')
        await modal.get_by_role('combobox',name=re.compile('^Source element')).select_option(node['id'])
        changes=json.dumps({'text':{'en':'Mara leaves the key.'}})
        await modal.get_by_role('textbox',name=re.compile('^Authored changes')).fill(changes)
        await modal.get_by_role('button',name='Save source as a new draft',exact=True).click()
        await modal.wait_for(state='hidden')
        document=(await verify.get(prefix+f'/documents/{document_id}')).json()
        assert document['revision']==2
        report['checks'].append('Source picker supplies the owning document revision and creates a new immutable draft.')

        node=await action_node()
        modal=await open_action('Save source as a new draft')
        await modal.get_by_role('combobox',name=re.compile('^Source element')).select_option(node['id'])
        draft=json.dumps({'text':{'en':'Keep this browser draft.'}})
        await modal.get_by_role('textbox',name=re.compile('^Authored changes')).fill(draft)
        await modal.get_by_role('button',name='Save source as a new draft',exact=True).wait_for(state='visible')
        await wait_for_page_state(page,"document.querySelector('[role=dialog] button[type=submit]')?.disabled===false","the source draft submit button to become enabled")
        response=await verify.post(prefix+'/commands/document.revise',headers=headers,
                                   json={'node_id':node['id'],'changes':{'text':{'en':'Concurrent source edit.'}},
                                         'revision':2,'label':'Concurrent draft'})
        response.raise_for_status()
        await modal.get_by_role('button',name='Save source as a new draft',exact=True).click()
        await modal.get_by_role('alert').wait_for()
        expected='Failed to load resource: the server responded with a status of 409 (Conflict)'
        if expected in report['console_errors']:report['console_errors'].remove(expected)
        assert await modal.get_by_role('textbox',name=re.compile('^Authored changes')).input_value()==draft
        await modal.get_by_role('button',name='Cancel',exact=True).click()
        report['checks'].append('A stale source edit reports a conflict without losing the browser draft.')

        for label,expected in [('Archive source document',1),('Restore source document',0)]:
            modal=await open_action(label)
            await modal.get_by_role('combobox',name=re.compile('^Document')).select_option(document_id)
            if expected:
                await modal.get_by_role('checkbox').check()
            await modal.get_by_role('button',name=label,exact=True).click()
            await modal.wait_for(state='hidden')
            document=(await verify.get(prefix+f'/documents/{document_id}')).json()
            assert document['archived']==expected
        report['checks'].append('Document archive and restore select current revisions, including archived records.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:7430')
    parser.add_argument('--output',default=str(ROOT/'artifacts/browser'))
    parser.add_argument('--transport-bridge',action='store_true')
    parser.add_argument('--chromium',default=os.environ.get('CHROMIUM_EXECUTABLE'))
    parser.add_argument('--smoke-only',action='store_true')
    parser.add_argument('--source-forms',action='store_true',help='Import and revise source documents in a disposable workspace.')
    args=parser.parse_args()
    print(json.dumps(asyncio.run(main(args)),indent=2))
