"""Revision-stamped production packets. Pure geometry, never exposure simulation.

All data is captured within one read transaction. Output publication is atomic and
content-addressed; retries cannot overwrite a different packet. HTML/SVG are escaped,
CSV formula prefixes are neutralised, and no scripts or external resources are used.
"""
from __future__ import annotations

import csv
from html import escape
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

from storyboarder.domain.models import dumps
from storyboarder.media.files import safe_path, sha256, inspect_image
from . import EVALUATOR
from .evaluate import evaluate_graph, rotate, rotation, add
from .graph import ref_for
from .models import ProductionError, digest
from .reports import Reporter
from .service import ProductionService


def text(value):
    return escape(str(value), quote=True)


def csv_text(headers, rows):
    handle=io.StringIO(newline='')
    writer=csv.writer(handle,lineterminator='\n')
    writer.writerow(headers)
    for row in rows:
        writer.writerow(["'"+str(v) if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@','\t','\r')) else v for v in row])
    return handle.getvalue()


def pose_point(pose, point):
    return add(_point(pose['position']), rotate(rotation(pose), point))


def _point(p):
    return [p['x'],p['y'],p['z']]


def plot_svg(sample, title='', stamp=''):
    """Top-view oriented proxies; world metres. Source stamp lives inside the SVG."""
    boxes=[]
    for g in sample['location']['geometry']:
        if g['type']=='room':
            continue
        size=g['size']
        corners=[pose_point(g['pose'],[sx*size['x']/2,sy*size['y']/2,0]) for sx,sy in [(-1,-1),(1,-1),(1,1),(-1,1)]]
        boxes.append((g,corners))
    points=[p for _,corners in boxes for p in corners]+[_point(i['pose']['position']) for i in sample['instances']]
    points += [_point(c['pose']['position']) for c in sample['cameras']]+[_point(f['pose']['position']) for f in sample['fixtures']]
    points=points or [[-4,-3,0],[4,3,0]]
    lo=[min(p[i] for p in points)-1 for i in (0,1)]; hi=[max(p[i] for p in points)+1 for i in (0,1)]
    scale=min(860/max(hi[0]-lo[0],1),440/max(hi[1]-lo[1],1))
    def xy(p):
        return (70+(p[0]-lo[0])*scale,540-(p[1]-lo[1])*scale)
    def label(p,s):
        x,y=xy(p)
        return f'<text x="{x+10:.2f}" y="{y-8:.2f}" font-size="12">{text(s)}</text>'
    out=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="620" viewBox="0 0 1000 620" role="img">',
         f'<title>{text(title)} — top-view proxy diagram</title><rect width="1000" height="620" fill="#f7f8f3"/>',
         '<g font-family="sans-serif" fill="#243c36">',f'<text x="38" y="38" font-size="23">{text(title)}</text>',
         f'<text x="38" y="63" font-size="12">Action frame {sample["action_frame"]} · metres · +Y up · geometric proxies</text>']
    for g,corners in boxes:
        coords=' '.join(f'{xy(p)[0]:.2f},{xy(p)[1]:.2f}' for p in corners)
        out.append(f'<polygon points="{coords}" fill="{"#e6e9e1" if g["type"]=="floor" else "#d2d9cf"}" stroke="#728377" stroke-width="1.4"/>')
        if g['type'] not in ('floor','wall'):
            out.append(label(_point(g['pose']['position']),g['label']))
    for mark in sample['location'].get('marks',[]):
        x,y=xy(_point(mark['position']))
        out.append(f'<path d="M{x-4:.2f} {y:.2f}h8 M{x:.2f} {y-4:.2f}v8" stroke="#938a5d"/>')
        out.append(label(_point(mark['position']),mark['label']))
    for path in sample['paths']:
        if path['parent_id']:
            continue
        pts=[_point(k['pose']['position']) for k in path['keys']]
        if pts:
            out.append('<polyline points="'+' '.join(f'{xy(p)[0]:.2f},{xy(p)[1]:.2f}' for p in pts)+'" fill="none" stroke="#7d9186" stroke-dasharray="5 5"/>')
    for camera in sample['cameras']:
        pos=_point(camera['pose']['position']); x,y=xy(pos)
        f=camera.get('frustum',{})
        corners=f.get('corners',[]) if isinstance(f,dict) else []
        if corners:
            coords=[pos]+[_point(c) for c in corners[:2]]+[pos]
            out.append('<polyline points="'+' '.join(f'{xy(p)[0]:.2f},{xy(p)[1]:.2f}' for p in coords)+'" fill="none" stroke="#477a9c" stroke-dasharray="4 3"/>')
        out.append(f'<rect x="{x-6:.2f}" y="{y-5:.2f}" width="12" height="10" rx="2" fill="#477a9c"/>')
        out.append(label(pos,camera['title']))
    for fixture in sample['fixtures']:
        pos=_point(fixture['pose']['position']); x,y=xy(pos)
        out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="7" fill="{"#d9b869" if fixture["enabled"] else "#aaa"}" stroke="#6d6949"/>')
        out.append(label(pos,fixture['label']))
    for item in sample['instances']:
        if not item['present']:
            continue
        pos=_point(item['pose']['position']); x,y=xy(pos)
        radius=max(4,min(22,item['dimensions']['x']*scale/2))
        out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" fill="#547767" stroke="#203b32"/>')
        out.append(label(pos,item['label']))
    out.extend([f'<text x="38" y="583" font-size="11">{text(stamp)}</text>',
                '<text x="38" y="603" font-size="10">Symbolic camera/light positions. No photometric, exposure, rigging or electrical-safety determination.</text>','</g></svg>'])
    return ''.join(out)


def panel_svg(data, stamp=''):
    out=['<svg xmlns="http://www.w3.org/2000/svg" width="800" height="500" viewBox="0 0 800 500">',
         '<rect width="800" height="500" fill="#fafaf5"/>',f'<title>{text(data["title"])}</title>',
         '<rect x="10" y="10" width="780" height="438" fill="#fff" stroke="#b7c4ba"/>']
    for stroke in data['drawing']:
        points=' '.join(f'{10+p["x"]*780:.2f},{10+p["y"]*438:.2f}' for p in stroke['points'])
        out.append(f'<polyline points="{points}" fill="none" stroke="{stroke["color"]}" stroke-width="{max(1,stroke["width"]*780):.2f}" stroke-linecap="round" stroke-linejoin="round"/>')
    if not data['drawing']:
        out.append('<text x="30" y="200" font-family="sans-serif" fill="#5d6f63">Artwork reference — see panel record / original media</text>')
    out.append(f'<text x="14" y="470" font-family="sans-serif" font-size="14">{text(data["title"])}</text>')
    out.append(f'<text x="14" y="489" font-family="sans-serif" font-size="9">{text(stamp)}</text></svg>')
    return ''.join(out)


def _image(service, conn, ref):
    if not ref:
        return None
    path,expected=ref.get('path'),ref.get('sha256')
    if ref.get('media_id'):
        row=conn.execute('SELECT path,sha256 FROM media WHERE id=?',(ref['media_id'],)).fetchone()
        if not row:
            return None
        path,expected=row['path'],row['sha256']
    try:
        file=safe_path(service.root,path,must_exist=True)
        info=inspect_image(file)
        if info['sha256']!=expected or info['size']>10*1024*1024:
            return None
        # Re-encode to bounded PNG, stripping metadata and avoiding active formats.
        from PIL import Image, ImageOps
        with Image.open(file) as im:
            im=ImageOps.exif_transpose(im).convert('RGB'); im.thumbnail((1600,1000))
            buf=io.BytesIO(); im.save(buf,format='PNG')
            return buf.getvalue()
    except Exception:
        # Presentation-only decoding failure: doctor retains the missing/invalid-file report.
        return None


def _make_pdf(path, records, report, images, stamp):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, KeepTogether
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='PacketNote',fontName='Helvetica',fontSize=8,leading=11,textColor=colors.HexColor('#4e6158')))
    def p(value,style='BodyText'):
        return Paragraph(text(value).replace('\n','<br/>'),styles[style])
    story=[p('Production review packet','Title'),p(stamp,'PacketNote'),Spacer(1,12),
           p('One selected dataset. Three independent review dimensions.','Heading2'),
           p(f"Structural: {'valid' if report['structural']['valid'] else 'needs repair'} | Planning gaps: {report['planning']['gaps']} | Creative: {'accepted' if report['creative']['accepted'] else 'not yet accepted'}"),
           p('Proxy diagrams and symbolic lighting are planning aids, not exposure, collision, rigging or electrical-safety certification.','PacketNote')]
    for r in records:
        if r['kind'] not in ('scene','shot','panel'):
            continue
        group_start=len(story)
        d=r['data']; marker=f'{r["id"]} v{r["version"]} | SHA256 {r["sha256"][:16]}'
        story.extend([Spacer(1,12),p(f'{d["label"] or r["kind"].upper()}  {d["title"]}','Heading2'),p(marker,'PacketNote')])
        if r['kind']=='scene':
            story.extend([p(d['purpose'] or 'Purpose not yet planned.'),p(f'Story location: {d["story_location"]} | Story time: {d["story_time"]} | Shoot date: {d["shoot_date"] or "not scheduled"}','PacketNote')])
        elif r['kind']=='shot':
            interval=d.get('interval')
            interval_label=f"frames {interval['start']}–{interval['end']} (end exclusive)" if interval else 'not planned'
            action=d.get('action')
            action_label=f"{action['id'][:8]} v{action['version']}" if action else 'not planned'
            story.extend([p(d['purpose'] or 'Shot purpose not yet planned.'),p(f'{d["framing"]}\n{d["composition"]}'),
                          p(f'Action interval: {interval_label} | Camera setups: {len(d["cameras"])} | Shared action: {action_label}','PacketNote')])
        else:
            if r['id'] in images:
                image=Image(io.BytesIO(images[r['id']]),width=6.3*inch,height=3.55*inch,kind='proportional')
                story.append(image)
            elif d['drawing']:
                from reportlab.graphics.shapes import Drawing, PolyLine, Rect
                drawing=Drawing(450,253)
                drawing.add(Rect(0,0,450,253,fillColor=colors.white,strokeColor=colors.HexColor('#b7c4ba')))
                for stroke in d['drawing']:
                    pts=[coordinate for point in stroke['points'] for coordinate in (point['x']*450,(1-point['y'])*253)]
                    drawing.add(PolyLine(pts,strokeColor=colors.HexColor(stroke['color']),strokeWidth=max(1,stroke['width']*450)))
                story.append(drawing)
            story.extend([p(d['dialogue']),p(d['annotation'],'PacketNote')])
            # Keep each panel's heading and source stamp with its artwork.
            panel_group=story[group_start:]
            del story[group_start:]
            story.append(KeepTogether(panel_group))
    story.extend([PageBreak(),p('Readiness & continuity','Title')])
    for issue in report['issues']:
        story.append(p(f'{issue["severity"].upper()} / {issue["status"]}: {issue["title"]} — {issue["message"]}'))
        if issue.get('reason'):
            story.append(p('Recorded exception: '+issue['reason'],'PacketNote'))
    story.extend([Spacer(1,12),p('Equipment by setup','Heading2')])
    rows=[[p(x,'PacketNote') for x in ('Item','Category','Max / setup','Total uses')]]
    for item in report['equipment']['items']:
        rows.append([p(item['title'],'PacketNote'),p(item['category'],'PacketNote'),p(item['max_in_one_setup'],'PacketNote'),p(item['total_planned_uses'],'PacketNote')])
    table=Table(rows,colWidths=[230,90,65,65],repeatRows=1,hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8eee7')),('LINEBELOW',(0,0),(-1,0),.5,colors.HexColor('#97aa9b')),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    story.append(table)
    def footer(canvas,doc):
        canvas.saveState(); canvas.setFont('Helvetica',7); canvas.setFillColor(colors.HexColor('#4e6158'))
        canvas.drawString(42,25,stamp[:135]); canvas.drawRightString(570,25,str(doc.page)); canvas.restoreState()
    SimpleDocTemplate(str(path),pagesize=(612,792),leftMargin=42,rightMargin=42,topMargin=42,bottomMargin=46,title='Storyboarder production review',author='Storyboarder').build(story,onFirstPage=footer,onLaterPages=footer)


def packet(service, scene_id=None, include_pdf=True):
    if type(include_pdf) is not bool:
        raise ProductionError('include_pdf must be a boolean.')
    prod=ProductionService(service)
    with prod.repo.transaction(False) as conn:
        reporter=Reporter(service,conn)
        report=reporter.run()
        records=reporter.records
        if scene_id:
            if scene_id not in reporter.graph.heads or reporter.graph.heads[scene_id]['kind']!='scene':
                raise ProductionError('Choose a production scene ID for the packet scope.')
            records=[r for r in records if r['id']==scene_id or r['data'].get('scene',{}).get('id')==scene_id or
                     r['kind']=='panel' and reporter.graph.require(r['data']['shot'])['scene']['id']==scene_id]
        if len(records)>500:
            raise ProductionError('Limit packets to 500 selected records; export a scene at a time.')
        records=sorted(records,key=lambda r:({'scene':0,'shot':1,'panel':2}.get(r['kind'],3),r['data']['orders']['shooting'] or 0,r['data']['label'],r['id']))
        checkpoint=prod._clock(conn)
        source_versions=report['source_versions']
        packet_hash=digest({'sources':source_versions,'scene_id':scene_id,'evaluator':EVALUATOR,'pdf':include_pdf,'packet':'v1'})
        stamp=f'Storyboarder | checkpoint {checkpoint} | selection {packet_hash[:16]} | {EVALUATOR}'
        samples={}
        images={}
        for r in records:
            if r['kind'] in ('shot','action','camera_setup','lighting_setup'):
                frame=r['data'].get('interval',{}).get('start',0) if r['data'].get('interval') else 0
                samples[r['id']]=evaluate_graph(reporter.graph,r['id'],r['version'],frame)
            if r['kind']=='panel':
                image=_image(service,conn,r['data']['artwork'])
                if image:
                    images[r['id']]=image
        # Snapshot exact dependency closure for agents, including pinned old alternatives.
        closure={}
        for r in records:
            closure.update(reporter.graph.closure(ref_for(r)))
        dataset={'format':'storyboarder.production-selection/v1','checkpoint':checkpoint,'source_versions':source_versions,
                 'scope_scene_id':scene_id,'records':records,'pinned_versions':list(closure.values())}
    name=f'production-c{checkpoint}-{packet_hash[:16]}'
    target=safe_path(service.root,'exports/'+name)
    if target.exists():
        manifest=json.loads(safe_path(target,'manifest.json',must_exist=True).read_text())
        if (sha256(safe_path(target,'packet.zip',must_exist=True)) != safe_path(target,'packet.zip.sha256',must_exist=True).read_text().strip()):
            raise ProductionError('Existing packet ZIP checksum differs; it was not overwritten.')
        if manifest['packet_sha256']!=packet_hash or any(sha256(safe_path(target,f['path'],must_exist=True))!=f['sha256'] for f in manifest['files']):
            raise ProductionError('An existing packet was modified. Preserve it and use a new selected revision; it was not overwritten.')
        return {'path':'exports/'+name+'/packet.zip','files':['exports/'+name+'/'+f for f in [*[item['path'] for item in manifest['files']],'manifest.json','packet.zip','packet.zip.sha256']],
                'checkpoint':checkpoint,'packet_sha256':packet_hash,'replayed':True}
    staging=Path(tempfile.mkdtemp(prefix='storyboarder-production-'))
    try:
        def write(file,content):
            dest=staging/file; dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(content,encoding='utf-8')
        write('selection.json',dumps(dataset)); write('report.json',dumps(report))
        shots=[r for r in records if r['kind']=='shot']
        write('shot-list.csv',csv_text(['shot_id','version','label','title','scene_id','purpose','action_start','action_end','cameras','lighting','source_checkpoint'],
            [[r['id'],r['version'],r['data']['label'],r['data']['title'],r['data']['scene']['id'],r['data']['purpose'],
              (r['data']['interval'] or {}).get('start',''),(r['data']['interval'] or {}).get('end',''),
              '; '.join(f'{c["id"]}@{c["version"]}' for c in r['data']['cameras']),dumps(r['data']['lighting']),checkpoint] for r in shots]))
        write('equipment.csv',csv_text(['asset_id','version','title','category','max_in_one_setup','total_planned_uses','source_checkpoint'],
            [[i['asset']['id'],i['asset']['version'],i['title'],i['category'],i['max_in_one_setup'],i['total_planned_uses'],checkpoint] for i in report['equipment']['items']]))
        html=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Production review</title>',
              '<style>body{margin:40px auto;max-width:1100px;padding:0 24px;color:#243c36;background:#f8f9f4;font:16px/1.55 system-ui}h1{font-size:44px;letter-spacing:-1.8px;line-height:1.1}h2{margin:10px 0}small,.meta{font-size:12px;color:#546b60}section{background:white;border:1px solid #dce3d9;border-radius:12px;margin:24px 0;padding:24px;break-inside:avoid}img{max-width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%}td,th{text-align:left;border-bottom:1px solid #ddd;padding:8px}a{color:inherit}@media print{body{margin:0;padding:0;background:white}section{border:0;border-radius:0}h1{font-size:30px}a{display:none}} </style>',
              f'<h1>Production, connected.</h1><p class="meta">{text(stamp)}</p>',
              f'<p>Structural: {"valid" if report["structural"]["valid"] else "needs repair"} · Planning gaps: {report["planning"]["gaps"]} · Creative: {"accepted" if report["creative"]["accepted"] else "not yet accepted"}</p>',
              '<p>Selected revisions only. Coverage and continuity findings are advisory; the complete machine-readable report includes revision-pinned exceptions and exact source records.</p>']
        for r in records:
            d=r['data']; marker=f'{r["id"]} v{r["version"]} | SHA256 {r["sha256"]}'
            if r['kind'] in ('scene','shot','camera_setup','lighting_setup','panel','action'):
                html.append(f'<section id="{r["id"]}"><small>{text(r["kind"].replace("_"," ").upper())} / {text(d["label"])}</small><h2>{text(d["title"])}</h2><p class="meta">{text(marker)}</p>')
                if r['kind']=='scene':
                    html.append(f'<p>{text(d["purpose"])}</p><p>Story location: {text(d["story_location"])} · Story time: {text(d["story_time"])} · Shoot: {text(d["shoot_date"] or "not scheduled")}</p>')
                    write('scenes/'+r['id']+'.json',dumps({'source':ref_for(r),'sha256':r['sha256'],'data':d,'checkpoint':checkpoint}))
                if r['kind']=='shot':
                    html.append(f'<p>{text(d["purpose"])}</p><p>{text(d["framing"])} · {text(d["composition"])}</p>')
                if r['id'] in samples:
                    svg=plot_svg(samples[r['id']],d['title'],stamp+' | '+marker[:60])
                    write('plots/'+r['id']+'.svg',svg)
                    write('plots/'+r['id']+'.json',dumps(samples[r['id']]))
                    html.append(f'<img src="plots/{r["id"]}.svg" alt="{text(d["title"])} top-view camera and lighting plot">')
                if r['kind']=='panel':
                    svg=panel_svg(d,stamp+' | '+marker[:60]); write('panels/'+r['id']+'.svg',svg)
                    if r['id'] in images:
                        (staging/'panels'/f'{r["id"]}.png').write_bytes(images[r['id']]); extension='png'
                    else:
                        extension='svg'
                    html.append(f'<img src="panels/{r["id"]}.{extension}" alt="{text(d["title"])}"><p>{text(d["dialogue"])}</p><p>{text(d["annotation"])}</p>')
                html.append(f'<p>{text(d["notes"])}</p></section>')
            elif r['kind'] in ('animatic','edit'):
                write('timelines/'+r['id']+'.json',dumps({'source':ref_for(r),'sha256':r['sha256'],'checkpoint':checkpoint,'data':d}))
        html.extend(['<section><h2>Readiness & continuity</h2><table><tr><th>Record</th><th>Finding</th><th>Status</th></tr>'])
        for i in report['issues']:
            html.append(f'<tr><td>{text(i["title"])}</td><td>{text(i["message"])}<br><small>{text(i.get("reason",""))}</small></td><td>{text(i["status"])}</td></tr>')
        html.extend(['</table></section>',f'<footer class="meta">{text(stamp)}<p>Geometric proxies and pinhole camera calculations only. No photometric, exposure, distortion, rigging, circuit or electrical-safety certification. PDF and HTML packets are snapshots, not live plans. Audio cues and animatic durations are exported as JSON; no audio/video mix is rendered.</p></footer></html>'])
        write('index.html',''.join(html))
        write('README.md',f'# Production review packet\n\n{stamp}\n\nOpen index.html for storyboard sheets, scene breakdowns and top-view plots. '
              'Shot and equipment CSVs neutralise spreadsheet formulas. selection.json includes exact pinned dependencies; report.json includes source coverage, readiness, continuity and unresolved questions. '
              'timelines/ contains frame-rate-aware animatic/editorial plans, not rendered audio/video. '
              'Missing artwork is labelled rather than replaced with unrelated images. The report always covers the project; rendered pages can be scene-scoped.\n')
        if include_pdf:
            _make_pdf(staging/'review.pdf',records,report,images,stamp)
        manifest={'format':'storyboarder.production-output/v1','checkpoint':checkpoint,'packet_sha256':packet_hash,
                  'source_versions':source_versions,'scope_scene_id':scene_id,
                  'files':[{'path':f.relative_to(staging).as_posix(),'sha256':sha256(f),'size':f.stat().st_size} for f in sorted(staging.rglob('*')) if f.is_file()]}
        write('manifest.json',dumps(manifest))
        with zipfile.ZipFile(staging/'packet.zip','w',zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(staging.rglob('*')):
                if file.is_file() and file.name!='packet.zip':
                    archive.write(file,file.relative_to(staging).as_posix())
        write('packet.zip.sha256',sha256(staging/'packet.zip')+'\n')
        target.parent.mkdir(parents=True,exist_ok=True)
        # Rename on the destination filesystem (including cross-device temporary dirs).
        incoming=Path(tempfile.mkdtemp(prefix='.'+name+'-',dir=target.parent))
        try:
            shutil.copytree(staging,incoming,dirs_exist_ok=True)
            try:
                os.rename(incoming,target)
            except OSError:
                if not target.exists():
                    raise
                return packet(service,scene_id,include_pdf)
        finally:
            if incoming.exists():
                shutil.rmtree(incoming)
        files=['exports/'+name+'/'+f.relative_to(target).as_posix() for f in sorted(target.rglob('*')) if f.is_file()]
        return {'path':'exports/'+name+'/packet.zip','files':files,'checkpoint':checkpoint,'packet_sha256':packet_hash,'replayed':False}
    finally:
        shutil.rmtree(staging,ignore_errors=True)
