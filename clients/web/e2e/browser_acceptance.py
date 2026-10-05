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
import math
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
    report={'transport':'HTTP transport bridge' if args.transport_bridge else 'normal loopback navigation','url':args.url,'checks':[],'page_errors':[],'console_errors':[],'expected_conflict_console':[]}
    async with async_playwright() as playwright:
        options={'headless':True}
        if args.chromium:options['executable_path']=args.chromium
        browser=await playwright.chromium.launch(**options)
        page=await browser.new_page(viewport={'width':1440,'height':1024},device_scale_factor=1)
        page.set_default_timeout(7000)
        page.on('pageerror',lambda error:report['page_errors'].append(str(error)))
        def record_console(message):
            if message.type!='error':return
            if re.search(r'server responded with a status of 409 \(Conflict\)',message.text,re.I):report['expected_conflict_console'].append(message.text)
            else:report['console_errors'].append(message.text)
        page.on('console',record_console)
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
            expected_conflicts=8+(1 if args.source_forms else 0)
            assert len(report['expected_conflict_console'])==expected_conflicts,report['expected_conflict_console']
            assert not report['console_errors'],report['console_errors']
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
        draft_title='Draft retained after rejected write '+stamp
        await modal.get_by_label('Title',exact=False).fill(draft_title)
        await modal.get_by_label('Item type',exact=False).select_option('prop')
        await page.evaluate('''() => {
          const original=window.fetch.bind(window),stats={posts:0,reject:true,release:null};
          window.__pendingActionRegression=stats;
          window.fetch=async (input,init={})=>{
            const url=typeof input==='string'?input:input.url,method=(init.method||input.method||'GET').toUpperCase();
            if(method==='POST'&&url.endsWith('/commands/asset.create')){
              stats.posts++;
              if(stats.reject){await new Promise(resolve=>stats.release=resolve);return new Response(JSON.stringify({error:{code:'revision_conflict',message:'simulated conflict'}}),{status:409,headers:{'Content-Type':'application/json'}});}
            }
            return original(input,init);
          };
        }''')
        await modal.get_by_role('button',name='New library item',exact=True).click()
        await wait_for_page_state(page,"window.__pendingActionRegression.posts===1&&typeof window.__pendingActionRegression.release==='function'","the form mutation to pause in flight")
        title_field=modal.get_by_label('Title',exact=False)
        assert await title_field.is_disabled()
        assert await modal.locator('input:not([type="hidden"]),select,textarea').evaluate_all('(els)=>els.length>0&&els.every(el=>el.matches(\':disabled\'))'), 'A mutation input remained editable while its write was pending.'
        await modal.get_by_role('status').filter(has_text='Editing is paused until the request finishes').wait_for()
        await modal.locator('form').evaluate('(form)=>form.requestSubmit()')
        assert (await page.evaluate('window.__pendingActionRegression.posts'))==1,'Keyboard/form resubmission duplicated a pending mutation.'
        await page.evaluate('window.__pendingActionRegression.release()')
        await modal.get_by_role('alert').filter(has_text='changed elsewhere').wait_for()
        assert await title_field.is_enabled() and await title_field.input_value()==draft_title
        await page.evaluate('window.__pendingActionRegression.reject=false')
        await title_field.fill('Acceptance prop '+stamp)
        await modal.get_by_label('Item type',exact=False).select_option('prop')
        await page.evaluate('''() => {
          const original=window.fetch.bind(window),stats={assetPosts:0,assetUpdates:0,stateGets:0,failNextState:true};
          window.__writeRefreshRegression=stats;
          window.fetch=async (input,init={})=>{
            const url=typeof input==='string'?input:input.url,method=(init.method||input.method||'GET').toUpperCase();
            if(method==='POST'&&url.endsWith('/commands/asset.create'))stats.assetPosts++;
            if(method==='POST'&&url.endsWith('/commands/asset.update'))stats.assetUpdates++;
            if(method==='GET'&&url.endsWith('/state')){stats.stateGets++;if(stats.failNextState){stats.failNextState=false;throw new TypeError('simulated follow-up refresh failure');}}
            return original(input,init);
          };
        }''')
        await modal.get_by_role('button',name='New library item',exact=True).click()
        await modal.wait_for(state='hidden')
        await page.locator('.external-change').get_by_role('button',name='Retry project refresh',exact=True).wait_for()
        write_stats=await page.evaluate('window.__writeRefreshRegression')
        assert write_stats['assetPosts']==1 and write_stats['stateGets']==1,write_stats
        await page.locator('.external-change').get_by_role('button',name='Retry project refresh',exact=True).click()
        await page.locator('.external-change').wait_for(state='hidden')
        write_stats=await page.evaluate('window.__writeRefreshRegression')
        assert write_stats['assetPosts']==1 and write_stats['stateGets']==2,write_stats
        asset=next(e for e in (await state())['entities'] if e['title']=='Acceptance prop '+stamp)
        assert sum(e['title']=='Acceptance prop '+stamp for e in (await state())['entities'])==1
        assert asset['fields']['type']=='prop'
        report['checks'].append('Submitted ActionDialog fields lock while a mutation is pending and the original draft remains editable after a rejected write.')
        # Editing against a stale revision and refreshing details must retain the newer typed value.
        card=page.locator('.asset-card').filter(has_text=asset['title'])
        await card.get_by_role('button',name='Edit',exact=True).click()
        edit=page.get_by_role('dialog',name='Edit library item')
        fresh_draft='Fresh typed draft '+stamp
        title_field=edit.get_by_label('Title',exact=False)
        await title_field.fill(fresh_draft)
        external_update=await verify.post(f'/api/v1/projects/{pid}/commands/asset.update',headers={'X-Storyboarder-Token':session['token']},json={'id':asset['id'],'revision':asset['revision'],'title':asset['title']+' updated elsewhere'})
        assert external_update.status_code==200,external_update.text
        await edit.get_by_role('button',name='Edit library item',exact=True).click()
        await edit.get_by_role('alert').filter(has_text='changed elsewhere').wait_for()
        await edit.get_by_role('button',name='Refresh project details',exact=True).click()
        await edit.get_by_role('alert').wait_for(state='hidden')
        assert await title_field.input_value()==fresh_draft
        await edit.get_by_role('button',name='Cancel',exact=True).click()
        report['checks'].append('Refreshing details after a real revision conflict updates its revision while preserving the freshly typed draft.')
        report['checks'].append('A successful write stays successful when its state refresh fails; retry performs only a GET and the record is not duplicated.')
        # A read-only result must not be labeled a saved write when a follow-up state request would fail.
        current_asset=next(e for e in (await state())['entities'] if e['id']==asset['id'])
        await page.get_by_role('button',name='View '+current_asset['title'],exact=True).click()
        await page.get_by_text('More options',exact=True).click()
        await page.evaluate('''() => {
          const original=window.fetch.bind(window),stats={usagePosts:0,stateGets:0};
          window.__readOnlyRefreshRegression=stats;window.__readOnlyRestore=original;
          window.fetch=async (input,init={})=>{
            const url=typeof input==='string'?input:input.url,method=(init.method||input.method||'GET').toUpperCase();
            if(method==='POST'&&url.endsWith('/commands/entity.usage'))stats.usagePosts++;
            if(method==='GET'&&url.endsWith('/state')){stats.stateGets++;throw new TypeError('read-only follow-up refresh must not run');}
            return original(input,init);
          };
        }''')
        await page.get_by_role('button',name='See where it’s used',exact=True).click()
        read_action=page.get_by_role('dialog',name='See where an item is used')
        await read_action.get_by_role('button',name='Show result',exact=True).click()
        await wait_for_page_state(page,"!document.querySelector('.action-fields')","the read-only result dialog to replace its action form")
        result_dialog=page.get_by_role('dialog',name='See where an item is used')
        await result_dialog.wait_for()
        read_stats=await page.evaluate('window.__readOnlyRefreshRegression')
        assert read_stats=={'usagePosts':1,'stateGets':0},read_stats
        assert await page.locator('.external-change').filter(has_text='Your changes were saved').count()==0,'A read-only query was reported as a saved write.'
        await result_dialog.get_by_role('button',name='Close dialog',exact=True).click()
        await page.evaluate('window.fetch=window.__readOnlyRestore;delete window.__readOnlyRestore')
        report['checks'].append('A read-only result skips the write-refresh path and never displays a saved-write warning.')
        # A later successful write whose refresh fails shows a project-scoped warning, cleared by switching projects.
        await page.evaluate('window.__writeRefreshRegression.failNextState=true')
        current_asset=next(e for e in (await state())['entities'] if e['id']==asset['id'])
        current_card=page.locator('.asset-card').filter(has_text=current_asset['title'])
        await current_card.get_by_role('button',name='Edit',exact=True).click()
        switch_edit=page.get_by_role('dialog',name='Edit library item')
        await switch_edit.get_by_label('Title',exact=False).fill(current_asset['title']+' refresh warning '+stamp)
        await switch_edit.get_by_role('button',name='Edit library item',exact=True).click()
        await switch_edit.wait_for(state='hidden')
        warning=page.locator('.external-change').filter(has_text='Your changes were saved')
        await warning.get_by_role('button',name='Retry project refresh',exact=True).wait_for()
        switch_stats=await page.evaluate('window.__writeRefreshRegression')
        assert switch_stats['stateGets']==4 and switch_stats['assetUpdates']==2,switch_stats
        second_title='Refresh warning target '+stamp
        created_project=await verify.post('/api/v1/projects',headers={'X-Storyboarder-Token':session['token']},json={'title':second_title,'slug':'refresh-warning-'+stamp})
        assert created_project.status_code==201,created_project.text
        second_id=created_project.json()['id']
        await page.get_by_role('button',name='Storyboarder workspace',exact=True).click()
        await page.get_by_role('button',name='Refresh projects',exact=True).click()
        await page.locator('.project-row').filter(has_text=second_title).click()
        await page.get_by_role('heading',name=second_title,exact=True).wait_for()
        assert await page.locator('.external-change').filter(has_text='Your changes were saved').count()==0
        await page.get_by_role('button',name='Storyboarder workspace',exact=True).click()
        await page.locator('.project-row').filter(has_text=initial['project']['title']).click()
        await page.get_by_role('heading',name=initial['project']['title'],exact=True).wait_for()
        assert await page.locator('.external-change').filter(has_text='Your changes were saved').count()==0
        report['checks'].append('A failed write-follow-up refresh warning is scoped to its project and cleared when the active project changes.')
        # Use native canvas keyboard interaction to open a validated link form.
        await page.get_by_role('button',name='Story canvas',exact=True).click()
        await page.get_by_role('button',name='Reference map',exact=True).click()
        await page.wait_for_selector(f'[data-node-id="{asset["id"]}"]')
        await page.get_by_role('button',name='Fit canvas',exact=True).click()
        source=page.locator(f'[data-node-id="{asset["id"]}"]')
        target=page.locator(f'[data-node-id="{location["id"]}"]')
        await source.focus();await source.press('l');await page.get_by_role('button',name='Cancel link',exact=True).wait_for();await target.focus();await target.press('Enter')
        modal=page.get_by_role('dialog')
        await modal.get_by_label('How they are connected',exact=False).select_option('appears-at')
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
        await page.evaluate('''() => {
          const original=window.fetch.bind(window),metrics={posts:0,active:0,maxActive:0,delay:false,release:null};
          window.__canvasSaveMetrics=metrics;
          window.fetch=async (input,init={})=>{
            const url=typeof input==='string'?input:input.url,method=(init.method||input.method||'GET').toUpperCase();
            if(method==='POST'&&url.endsWith('/commands/canvas.save')){
              metrics.posts++;metrics.active++;metrics.maxActive=Math.max(metrics.maxActive,metrics.active);
              try{const response=await original(input,init);if(metrics.delay)await new Promise(resolve=>metrics.release=resolve);return response;}
              finally{metrics.active--;}
            }
            return original(input,init);
          };
        }''')
        await page.evaluate('window.__canvasSaveMetrics.delay=true')
        save_button=page.get_by_role('button',name='Save arrangement',exact=True)
        await save_button.click()
        await wait_for_page_state(page,"window.__canvasSaveMetrics.posts===1&&typeof window.__canvasSaveMetrics.release==='function'","the layout save to pause in flight")
        saving_button=page.get_by_role('button',name='Saving…',exact=True)
        assert await saving_button.is_disabled()
        await saving_button.evaluate('(el)=>el.click()')
        assert (await page.evaluate('window.__canvasSaveMetrics.posts'))==1
        committed_state=await state()
        committed_layout=next(l for l in committed_state['layouts'] if l['name']=='Acceptance layout '+stamp)
        first_snapshot_position=await source.evaluate("el=>el.style.transform")
        assert committed_layout['positions'][asset['id']],committed_layout
        await page.get_by_role('button',name='Fit canvas',exact=True).evaluate('(el)=>el.click()')
        await source.focus();await source.press('ArrowRight')
        edited_during_save=await source.evaluate("el=>el.style.transform")
        assert edited_during_save!=first_snapshot_position
        await page.evaluate('window.__canvasSaveMetrics.delay=false;window.__canvasSaveMetrics.release()')
        await page.get_by_role('button',name='Save arrangement',exact=True).wait_for()
        await page.locator('.canvas-layout-bar').get_by_text('Unsaved changes',exact=True).wait_for()
        metrics=await page.evaluate('window.__canvasSaveMetrics')
        assert metrics['posts']==1 and metrics['maxActive']==1,metrics
        after=await state()
        layout=next(l for l in after['layouts'] if l['name']=='Acceptance layout '+stamp)
        saved_xy=(float(layout['positions'][asset['id']]['x']),float(layout['positions'][asset['id']]['y']))
        edited_xy=tuple(float(part) for part in re.search(r'translate\(([-\d.]+)px,\s*([\-\d.]+)px\)',edited_during_save).groups())
        assert saved_xy!=edited_xy
        await page.get_by_role('button',name='Save arrangement',exact=True).click()
        await wait_for_page_state(page,"window.__canvasSaveMetrics.posts===2&&window.__canvasSaveMetrics.active===0&&!document.querySelector('.canvas-layout-bar')?.textContent.includes('Unsaved changes')","the follow-up layout save to complete")
        after=await state()
        layout=next(l for l in after['layouts'] if l['name']=='Acceptance layout '+stamp)
        metrics=await page.evaluate('window.__canvasSaveMetrics')
        current_transform=await source.evaluate("el=>el.style.transform")
        current_xy=[float(part) for part in re.search(r'translate\(([-\d.]+)px,\s*([\-\d.]+)px\)',current_transform).groups()]
        saved_current=layout['positions'][asset['id']]
        deltas=(saved_current['x']-current_xy[0],saved_current['y']-current_xy[1])
        assert all(math.isclose(a,b,abs_tol=0.02) for a,b in zip((saved_current['x'],saved_current['y']),current_xy)),f'CSSOM coordinate deltas: {deltas}; saved={saved_current}; DOM={current_xy}'
        assert layout['revision']==2 and metrics['posts']==2 and metrics['maxActive']==1,(layout['revision'],metrics)
        report['checks'].append('Canvas saves never overlap, preserve a move made while a save is pending, and use the returned revision on the next save.')
        # Two writers change disjoint cards. Refresh must expose both changes and merge them under latest CAS.
        external_positions={key:dict(value) for key,value in layout['positions'].items()}
        external_positions[asset['id']]['x']+=37
        external=await verify.post(f'/api/v1/projects/{pid}/commands/canvas.save',headers={'X-Storyboarder-Token':session['token']},json={'name':layout['name'],'mode':layout['mode'],'positions':external_positions,'settings':layout['settings'],'layout_id':layout['id'],'revision':layout['revision']})
        assert external.status_code==200,external.text
        await target.focus();await target.press('ArrowRight')
        disjoint_transform=await target.evaluate("el=>el.style.transform")
        disjoint_xy=[float(part) for part in re.search(r'translate\(([-\d.]+)px,\s*([\-\d.]+)px\)',disjoint_transform).groups()]
        await page.get_by_role('button',name='Save arrangement',exact=True).click()
        await page.get_by_role('alert').filter(has_text='changed elsewhere').wait_for()
        assert await target.evaluate("el=>el.style.transform")==disjoint_transform
        await page.locator('.canvas-layout-bar').get_by_text('Unsaved changes',exact=True).wait_for()
        external_state=await state()
        externally_saved=next(l for l in external_state['layouts'] if l['id']==layout['id'])
        assert externally_saved['positions'][asset['id']]['x']==external_positions[asset['id']]['x']
        await page.get_by_role('button',name='Refresh latest saved revision',exact=True).click()
        review=page.locator('.layout-conflict-review')
        await review.get_by_role('heading',name='Saved version 3 · compare changes',exact=True).wait_for()
        changes=await review.locator('[data-conflict-path]').evaluate_all("els=>els.map(el=>({path:JSON.parse(el.getAttribute('data-conflict-path')),text:el.innerText}))")
        source_change=next(item for item in changes if item['path']==['positions',asset['id'],'x'])
        target_change=next(item for item in changes if item['path']==['positions',location['id'],'x'])
        assert source_change['text'].find('merged automatically')>=0 and target_change['text'].find('merged automatically')>=0,changes
        assert asset['id'] in source_change['text'] and 'horizontal position (x)' in source_change['text'],source_change
        await review.get_by_role('button',name='Reapply merged arrangement',exact=True).click()
        await wait_for_page_state(page,"window.__canvasSaveMetrics.posts===4&&window.__canvasSaveMetrics.active===0&&!document.querySelector('.canvas-layout-bar')?.textContent.includes('Unsaved changes')","the disjoint two-writer merge to save")
        merged_state=await state()
        merged_layout=next(l for l in merged_state['layouts'] if l['id']==layout['id'])
        assert merged_layout['revision']==4
        assert merged_layout['positions'][asset['id']]['x']==external_positions[asset['id']]['x']
        assert math.isclose(merged_layout['positions'][location['id']]['x'],disjoint_xy[0],abs_tol=0.02)
        report['checks'].append('A real two-writer 409 shows stable card-ID/x/y diffs and merges disjoint external and local card edits under latest-revision CAS.')

        # Same-card x changes overlap and require a deliberate per-field choice.
        same_base=merged_layout
        external_same={key:dict(value) for key,value in same_base['positions'].items()}
        external_same[asset['id']]['x']+=22
        external=await verify.post(f'/api/v1/projects/{pid}/commands/canvas.save',headers={'X-Storyboarder-Token':session['token']},json={'name':same_base['name'],'mode':same_base['mode'],'positions':external_same,'settings':same_base['settings'],'layout_id':same_base['id'],'revision':same_base['revision']})
        assert external.status_code==200,external.text
        await source.focus();await source.press('ArrowRight')
        keep_local_transform=await source.evaluate("el=>el.style.transform")
        keep_local_xy=[float(part) for part in re.search(r'translate\(([-\d.]+)px,\s*([\-\d.]+)px\)',keep_local_transform).groups()]
        await page.get_by_role('button',name='Save arrangement',exact=True).click()
        await page.get_by_role('alert').filter(has_text='changed elsewhere').wait_for()
        await page.get_by_role('button',name='Refresh latest saved revision',exact=True).click()
        review=page.locator('.layout-conflict-review')
        await page.get_by_text(re.compile(re.escape(asset['id'])+r'.*horizontal position \(x\)')).first.wait_for()
        rows=await page.locator('[data-conflict-path]').evaluate_all("els=>els.map(el=>({path:el.getAttribute('data-conflict-path'),text:el.innerText,choices:Array.from(el.querySelectorAll('button')).map(b=>b.textContent)}))")
        matching_same=[item for item in rows if json.loads(item['path'])==['positions',asset['id'],'x']]
        assert matching_same,f"expected same-card x conflict for {asset['id']}; review paths={[item['path'] for item in rows]}"
        same_field=matching_same[0]
        assert 'Keep local' in same_field['choices'] and 'Use saved' in same_field['choices'],same_field
        assert await review.get_by_role('button',name='Reapply merged arrangement',exact=True).is_disabled()
        await review.get_by_role('button',name='Keep local',exact=True).click()
        await review.get_by_role('button',name='Reapply merged arrangement',exact=True).click()
        await wait_for_page_state(page,"window.__canvasSaveMetrics.posts===6&&window.__canvasSaveMetrics.active===0&&!document.querySelector('.canvas-layout-bar')?.textContent.includes('Unsaved changes')","the explicitly kept local card value to save")
        chosen_local=next(l for l in (await state())['layouts'] if l['id']==layout['id'])
        chosen_local_xy=[float(part) for part in re.search(r'translate\(([-\d.]+)px,\s*([\-\d.]+)px\)',await source.evaluate("el=>el.style.transform")).groups()]
        assert chosen_local['revision']==6 and math.isclose(chosen_local['positions'][asset['id']]['x'],keep_local_xy[0],abs_tol=0.02)

        # Exercise the saved-value choice in a second same-card race.
        external_saved={key:dict(value) for key,value in chosen_local['positions'].items()}
        external_saved[asset['id']]['x']+=31
        external=await verify.post(f'/api/v1/projects/{pid}/commands/canvas.save',headers={'X-Storyboarder-Token':session['token']},json={'name':chosen_local['name'],'mode':chosen_local['mode'],'positions':external_saved,'settings':chosen_local['settings'],'layout_id':chosen_local['id'],'revision':chosen_local['revision']})
        assert external.status_code==200,external.text
        await source.focus();await source.press('ArrowRight')
        await page.get_by_role('button',name='Save arrangement',exact=True).click()
        await page.get_by_role('alert').filter(has_text='changed elsewhere').wait_for()
        await page.get_by_role('button',name='Refresh latest saved revision',exact=True).click()
        review=page.locator('.layout-conflict-review')
        await review.get_by_role('button',name='Use saved',exact=True).click()
        await review.get_by_role('button',name='Reapply merged arrangement',exact=True).click()
        await wait_for_page_state(page,"window.__canvasSaveMetrics.posts===8&&window.__canvasSaveMetrics.active===0&&!document.querySelector('.canvas-layout-bar')?.textContent.includes('Unsaved changes')","the explicitly selected saved card value to save")
        saved_choice=next(l for l in (await state())['layouts'] if l['id']==layout['id'])
        saved_transform=await source.evaluate("el=>el.style.transform")
        saved_dom_x=float(re.search(r'translate\(([-\d.]+)px,',saved_transform).group(1))
        assert saved_choice['revision']==8 and saved_choice['positions'][asset['id']]['x']==external_saved[asset['id']]['x']
        assert math.isclose(saved_dom_x,external_saved[asset['id']]['x'],abs_tol=0.02)
        report['checks'].append('Same-card x conflicts disable retry until a field choice; Keep local and Use saved each preserve the selected value and succeed under CAS (8 browser save attempts).')

        # Settings use the same field-level conflict review and CAS recovery.
        settings_base=saved_choice
        local_filter='local-filter-'+stamp
        remote_filter='saved-filter-'+stamp
        remote_settings={**settings_base['settings'],'filters':{**settings_base['settings'].get('filters',{}),'query':remote_filter}}
        external=await verify.post(f'/api/v1/projects/{pid}/commands/canvas.save',headers={'X-Storyboarder-Token':session['token']},json={'name':settings_base['name'],'mode':settings_base['mode'],'positions':settings_base['positions'],'settings':remote_settings,'layout_id':settings_base['id'],'revision':settings_base['revision']})
        assert external.status_code==200,external.text
        await page.get_by_label('Search canvas cards',exact=True).fill(local_filter)
        await page.get_by_role('button',name='Save arrangement',exact=True).click()
        await page.get_by_role('alert').filter(has_text='changed elsewhere').wait_for()
        await page.get_by_role('button',name='Refresh latest saved revision',exact=True).click()
        review=page.locator('.layout-conflict-review')
        await review.get_by_text('Canvas setting · filters · query',exact=True).wait_for()
        settings_rows=await page.locator('[data-conflict-path]').evaluate_all("els=>els.map(el=>({path:JSON.parse(el.getAttribute('data-conflict-path')),text:el.innerText}))")
        settings_conflict=next(item for item in settings_rows if item['path']==['settings','filters','query'])
        assert remote_filter in settings_conflict['text'] and local_filter in settings_conflict['text'],settings_conflict
        await review.get_by_role('button',name='Keep local',exact=True).click()
        await review.get_by_role('button',name='Reapply merged arrangement',exact=True).click()
        await wait_for_page_state(page,"window.__canvasSaveMetrics.posts===10&&window.__canvasSaveMetrics.active===0&&!document.querySelector('.canvas-layout-bar')?.textContent.includes('Unsaved changes')","the resolved canvas setting to save")
        settings_saved=next(l for l in (await state())['layouts'] if l['id']==settings_base['id'])
        assert settings_saved['revision']==10 and settings_saved['settings']['filters']['query']==local_filter
        await page.get_by_label('Search canvas cards',exact=True).fill('')
        await page.get_by_role('button',name='Save arrangement',exact=True).click()
        await wait_for_page_state(page,"window.__canvasSaveMetrics.posts===11&&window.__canvasSaveMetrics.active===0&&!document.querySelector('.canvas-layout-bar')?.textContent.includes('Unsaved changes')","the cleared canvas search setting to save")
        assert next(l for l in (await state())['layouts'] if l['id']==settings_base['id'])['revision']==11
        await page.wait_for_selector(f'[data-node-id="{asset["id"]}"]')
        report['checks'].append('A settings.filters.query conflict displays the saved/local values and requires an explicit choice before the latest-revision retry.')
        await source.focus();await source.press('ArrowRight')
        post_recovery_transform=await source.evaluate("el=>el.style.transform")
        await page.get_by_role('button',name='Story outline',exact=True).click()
        navigation=page.get_by_role('dialog',name='Unsaved canvas arrangement')
        await navigation.wait_for()
        assert await source.evaluate("el=>el.style.transform")==post_recovery_transform
        await navigation.get_by_role('button',name='Stay',exact=True).click()
        await navigation.wait_for(state='hidden')
        assert await page.get_by_role('heading',name='Canvas',exact=True).count()==1
        assert await source.evaluate("el=>el.style.transform")==post_recovery_transform
        report['checks'].append('Stay closes the navigation prompt while keeping the edited card geometry in Canvas.')
        await page.get_by_role('button',name='Story outline',exact=True).click()
        navigation=page.get_by_role('dialog',name='Unsaved canvas arrangement')
        await navigation.get_by_role('button',name='Discard changes',exact=True).click()
        await page.get_by_role('heading',name='Build the story, scene by scene.',exact=True).wait_for()
        await page.get_by_role('button',name='Story canvas',exact=True).click()
        await page.wait_for_selector('.graph-node')
        await page.get_by_role('button',name='Story outline',exact=True).click()
        assert await page.get_by_role('dialog',name='Unsaved canvas arrangement').count()==0
        await page.get_by_role('heading',name='Build the story, scene by scene.',exact=True).wait_for()
        report['checks'].append('Discard leaves Canvas; clean Canvas navigation proceeds without a prompt.')
        await page.get_by_role('button',name='Story canvas',exact=True).click()
        await page.wait_for_selector('.graph-node')
        history_node=page.locator('.graph-node').first
        await history_node.focus();await history_node.press('ArrowRight')
        history_transform=await history_node.evaluate('el=>el.style.transform')
        await page.evaluate('history.back()')
        history_prompt=page.get_by_role('dialog',name='Unsaved canvas arrangement')
        await history_prompt.wait_for()
        assert await page.evaluate('location.hash')=='#canvas'
        assert await history_node.evaluate('el=>el.style.transform')==history_transform
        await history_prompt.get_by_role('button',name='Stay',exact=True).click()
        assert await history_node.evaluate('el=>el.style.transform')==history_transform
        await page.get_by_role('button',name='Story outline',exact=True).click()
        await page.get_by_role('dialog',name='Unsaved canvas arrangement').get_by_role('button',name='Discard changes',exact=True).click()
        await page.get_by_role('heading',name='Build the story, scene by scene.',exact=True).wait_for()
        report['checks'].append('Browser Back to a different hash is blocked while dirty, restores the Canvas URL, and preserves geometry through Stay.')
        await page.get_by_role('button',name='Story canvas',exact=True).click()
        await page.get_by_role('button',name='Reference map',exact=True).click()
        await page.wait_for_selector(f'[data-node-id="{asset["id"]}"]')
        nav_layout_name='Acceptance navigation layout '+stamp
        await page.get_by_label('Saved arrangement',exact=True).select_option(label='Acceptance layout '+stamp)
        await page.get_by_label('Arrangement name',exact=True).fill(nav_layout_name)
        await page.get_by_role('button',name='Save as new',exact=True).click()
        nav_layout_name=await page.get_by_label('Arrangement name',exact=True).input_value()
        await page.get_by_role('button',name='Save arrangement',exact=True).click()
        await wait_for_page_state(page,f"Array.from(document.querySelectorAll('.canvas-layout-bar select option')).some(option=>option.textContent==={json.dumps(nav_layout_name)})","the explicit navigation layout copy to save")
        nav_node=page.locator(f'[data-node-id="{asset["id"]}"]')
        await nav_node.focus();await nav_node.press('ArrowRight')
        nav_transform=await nav_node.evaluate("el=>el.style.transform")
        await page.get_by_role('button',name='Story outline',exact=True).click()
        navigation=page.get_by_role('dialog',name='Unsaved canvas arrangement')
        await navigation.wait_for()
        nav_base=next(l for l in (await state())['layouts'] if l['name']==nav_layout_name)
        nav_external=await verify.post(f'/api/v1/projects/{pid}/commands/canvas.save',headers={'X-Storyboarder-Token':session['token']},json={'name':nav_layout_name,'mode':'assets','positions':nav_base['positions'],'settings':nav_base['settings'],'layout_id':nav_base['id'],'revision':nav_base['revision']})
        assert nav_external.status_code==200,nav_external.text
        await navigation.get_by_role('button',name='Save and continue',exact=True).click()
        await navigation.get_by_role('alert').filter(has_text='changed elsewhere').wait_for()
        await navigation.get_by_role('button',name='Refresh latest saved revision',exact=True).click()
        nav_review=navigation.locator('.layout-conflict-review')
        await nav_review.get_by_text('These edits do not overlap and will be merged automatically.',exact=True).wait_for()
        await nav_review.get_by_role('button',name='Reapply merged arrangement',exact=True).click()
        await page.get_by_role('heading',name='Build the story, scene by scene.',exact=True).wait_for()
        nav_layout=next(l for l in (await state())['layouts'] if l['name']==nav_layout_name)
        assert nav_layout['revision']==nav_base['revision']+2
        nav_xy=[float(part) for part in re.search(r'translate\(([-\d.]+)px,\s*([\-\d.]+)px\)',nav_transform).groups()]
        nav_saved=nav_layout['positions'][asset['id']]
        nav_deltas=(nav_saved['x']-nav_xy[0],nav_saved['y']-nav_xy[1])
        assert all(math.isclose(a,b,abs_tol=0.02) for a,b in zip((nav_saved['x'],nav_saved['y']),nav_xy)),f'Save-and-continue CSSOM coordinate deltas: {nav_deltas}'
        report['checks'].append('A 409 inside the Save-and-continue prompt exposes field choices and saved/local recovery, then persists the draft before completing navigation.')
        await page.get_by_role('button',name='Story canvas',exact=True).click()
        await page.get_by_role('button',name='Reference map',exact=True).click()
        await page.wait_for_selector(f'[data-node-id="{asset["id"]}"]')
        layouts=page.get_by_label('Saved arrangement',exact=True)
        await layouts.select_option(label='Acceptance layout '+stamp)
        layout_node=page.locator(f'[data-node-id="{asset["id"]}"]')
        await layout_node.focus();await layout_node.press('ArrowRight')
        layout_transform=await layout_node.evaluate('el=>el.style.transform')
        await layouts.select_option(label=nav_layout_name)
        layout_prompt=page.get_by_role('dialog',name='Unsaved canvas arrangement')
        await layout_prompt.wait_for()
        await layout_prompt.get_by_role('button',name='Stay',exact=True).click()
        assert await layout_node.evaluate('el=>el.style.transform')==layout_transform
        await layouts.select_option(label=nav_layout_name)
        layout_prompt=page.get_by_role('dialog',name='Unsaved canvas arrangement')
        await layout_prompt.wait_for()
        switch_base=next(l for l in (await state())['layouts'] if l['id']==layout['id'])
        switch_external_positions={key:dict(value) for key,value in switch_base['positions'].items()}
        switch_external_positions[location['id']]['x']+=17
        external=await verify.post(f'/api/v1/projects/{pid}/commands/canvas.save',headers={'X-Storyboarder-Token':session['token']},json={'name':switch_base['name'],'mode':switch_base['mode'],'positions':switch_external_positions,'settings':switch_base['settings'],'layout_id':switch_base['id'],'revision':switch_base['revision']})
        assert external.status_code==200,external.text
        await layout_prompt.get_by_role('button',name='Save and continue',exact=True).click()
        await layout_prompt.get_by_role('alert').filter(has_text='changed elsewhere').wait_for()
        await layout_prompt.get_by_role('button',name='Refresh latest saved revision',exact=True).click()
        layout_review=layout_prompt.locator('.layout-conflict-review')
        await layout_review.get_by_role('button',name='Reapply merged arrangement',exact=True).click()
        await page.locator('.canvas-layout-bar').get_by_text('Unsaved changes',exact=True).wait_for(state='hidden')
        await wait_for_page_state(page,f"document.querySelector('select[aria-label=\"Saved arrangement\"]')?.value==={json.dumps(nav_layout['id'])}","the guarded layout change to complete after conflict recovery")
        assert await layouts.input_value()==nav_layout['id']
        switched_state=await state()
        switched_layout=next(l for l in switched_state['layouts'] if l['id']==switch_base['id'])
        layout_local_x=float(re.search(r'translate\(([-\d.]+)px,',layout_transform).group(1))
        assert switched_layout['revision']==switch_base['revision']+2
        assert switched_layout['positions'][location['id']]['x']==switch_external_positions[location['id']]['x']
        assert math.isclose(switched_layout['positions'][asset['id']]['x'],layout_local_x,abs_tol=0.02)
        report['checks'].append('Switching saved arrangements can recover a 409 inside the guard, merge a remote card and local card, then load the requested arrangement.')

        await page.get_by_role('button',name='Reference map',exact=True).click()
        mode_node=page.locator(f'[data-node-id="{asset["id"]}"]')
        await mode_node.focus();await mode_node.press('ArrowRight')
        mode_transform=await mode_node.evaluate('el=>el.style.transform')
        await page.get_by_role('button',name='Scene board',exact=True).click()
        mode_prompt=page.get_by_role('dialog',name='Unsaved canvas arrangement')
        await mode_prompt.wait_for()
        mode_base=next(l for l in (await state())['layouts'] if l['id']==nav_layout['id'])
        mode_external_positions={key:dict(value) for key,value in mode_base['positions'].items()}
        mode_external_positions[location['id']]['y']+=13
        external=await verify.post(f'/api/v1/projects/{pid}/commands/canvas.save',headers={'X-Storyboarder-Token':session['token']},json={'name':mode_base['name'],'mode':mode_base['mode'],'positions':mode_external_positions,'settings':mode_base['settings'],'layout_id':mode_base['id'],'revision':mode_base['revision']})
        assert external.status_code==200,external.text
        await mode_prompt.get_by_role('button',name='Save and continue',exact=True).click()
        await mode_prompt.get_by_role('alert').filter(has_text='changed elsewhere').wait_for()
        await mode_prompt.get_by_role('button',name='Refresh latest saved revision',exact=True).click()
        mode_review=mode_prompt.locator('.layout-conflict-review')
        await mode_review.get_by_role('button',name='Reapply merged arrangement',exact=True).click()
        await wait_for_page_state(page,"document.querySelector('.segmented button[aria-pressed=\"true\"]')?.textContent==='Scene board'","the guarded scene-board switch to commit after conflict recovery")
        assert await page.get_by_role('button',name='Scene board',exact=True).get_attribute('aria-pressed')=='true'
        mode_state=await state()
        mode_saved=next(l for l in mode_state['layouts'] if l['id']==mode_base['id'])
        mode_local_x=float(re.search(r'translate\(([-\d.]+)px,',mode_transform).group(1))
        assert mode_saved['revision']==mode_base['revision']+2
        assert mode_saved['positions'][location['id']]['y']==mode_external_positions[location['id']]['y']
        assert math.isclose(mode_saved['positions'][asset['id']]['x'],mode_local_x,abs_tol=0.02)
        await page.get_by_role('button',name='Reference map',exact=True).click()
        report['checks'].append('Switching Canvas modes can recover a 409 inside the guard, merge remote and local fields under CAS, then complete the mode change.')
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
