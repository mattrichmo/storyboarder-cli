"""One deterministic primitive list rendered to SVG, Pillow PNG, and PDF."""
from __future__ import annotations

from io import BytesIO
from html import escape
import json
import math
from importlib.metadata import version as package_version

from storyboarder.domain.spatial import SpatialError, canonical
from storyboarder.domain.spatial_evaluation import evaluate, rotate, vec, add, LIMITATIONS, resolve_position

RENDERER = "storyboarder.spatial-diagram/v1"
WIDTH, HEIGHT = 1200, 1000


def primitives(payload,evaluation,metadata):
    b=evaluation["bounds"];x0,y0,w,h=60,170,1080,620
    scale=min(w/(b["max_x"]-b["min_x"]),h/(b["max_y"]-b["min_y"]))
    ox=x0+(w-scale*(b["max_x"]-b["min_x"]))/2-b["min_x"]*scale
    oy=y0+(h-scale*(b["max_y"]-b["min_y"]))/2+b["max_y"]*scale
    def point(p):return [ox+p[0]*scale,oy-p[1]*scale]
    result=[]
    def text(x,y,content,size=14,color="#182c30"):
        result.append({"kind":"text","x":x,"y":y,"text":str(content),"size":size,"color":color})
    def path(points,color="#647576",fill=None,dash=False,width=1.5,closed=False):
        result.append({"kind":"path","points":points,"stroke":color,"fill":fill,"dash":dash,"width":width,"closed":closed})
    text(60,52,payload["setup_label"][:76],28)
    text(60,82,f"{evaluation['evaluated_time_us']/1e6:g} s  /  target plane Z={evaluation['target_plane_z_m']:g} m  /  scale: {payload['scale']['status']}",17)
    text(60,106,f"Setup {metadata['setup_id']} · version {metadata['version_id']}",12)
    text(60,127,"SHA-256 "+metadata["content_sha256"],11)
    text(60,149,"Metres · +X right / +Y up the drawing / +Z height · heading +90° points toward −X",12)
    spacing=max(1,10**math.floor(math.log10(max(b['max_x']-b['min_x'],b['max_y']-b['min_y']))-1))
    for x in range(math.ceil(b["min_x"]/spacing),math.floor(b["max_x"]/spacing)+1):
        path([point([x*spacing,b['min_y']]),point([x*spacing,b['max_y']])],"#e5ebea",width=.7)
    for y in range(math.ceil(b["min_y"]/spacing),math.floor(b["max_y"]/spacing)+1):
        path([point([b['min_x'],y*spacing]),point([b['max_x'],y*spacing])],"#e5ebea",width=.7)
    for coverage in evaluation['light_coverage']:
        for poly in coverage['polygons']:
            path([point(p) for p in poly],"#b68c35","#fcf4de",'clipped' in coverage['status'],.8,True)
    for coverage in evaluation['camera_coverage']:
        for poly in coverage['polygons']:
            path([point(p) for p in poly],"#3598a0",None,coverage['status']=='clipped',1.4,True)
    marks={m['id']:m for m in payload['marks']}
    for track in payload['tracks']:
        if track['property']!='position':continue
        points=[resolve_position(k['value'],marks) for k in track['keys']]
        for i in range(len(points)-1):
            if track['keys'][i]['next']=='linear':path([point(points[i]),point(points[i+1])],"#ad6586",None,True,2)
        for k,p in zip(track['keys'],points):
            x,y=point(p);text(x+7,y+15,f"{k['time_us']/1e6:g}s {k['next']}",10,"#8a4062")
    for item in evaluation['items']:
        if not item['present']:continue
        pos=vec(item['pose']['position']);x,y=point(pos);cat=item['category']
        if cat=='instances':
            shape=item['shape'];q=item['pose']['orientation']
            if shape['kind']=='box':
                d=shape['extents'];corners=[add(pos,rotate(q,[sx*d['width_m']/2,sy*d['depth_m']/2,0])) for sx,sy in [(-1,-1),(1,-1),(1,1),(-1,1)]]
                path([point(p) for p in corners],"#405e61","#e5eae8",False,2,True)
            else:
                radius=shape['radius_m'];poly=[[pos[0]+radius*math.cos(i*math.tau/32),pos[1]+radius*math.sin(i*math.tau/32)] for i in range(32)]
                path([point(p) for p in poly],"#264b4c","#d4e6df",False,2,True)
            direction=rotate(q,[0,.65,0]);path([point(pos),point(add(pos,direction))],"#264b4c",None,False,2)
            if item.get('eyeline_target_world'):path([point(pos),point(vec(item['eyeline_target_world']))],"#a55875",None,True,1)
            label=item['label']+(f" · {item['posture']}" if item.get('posture') else '')
        elif cat=='cameras':
            path([[x-6,y-5],[x+6,y-5],[x+6,y+5],[x-6,y+5]],"#277d84","#d9f0f0",False,2,True)
            path([point(pos),point(add(pos,rotate(item['pose']['orientation'],[0,.8,0])))],"#277d84",width=2)
            label=item['label']
        elif cat=='lights':
            path([[x,y-7],[x+7,y],[x,y+7],[x-7,y]],"#9c751e","#f9df92",False,2,True)
            if not item['enabled'] or item['output']['relative']==0:path([[x-8,y-8],[x+8,y+8]],"#654a24",width=2)
            label=item['label']+' · '+item['role']
        else:
            corners=[add(pos,rotate(item['pose']['orientation'],[sx*item['width_m']/2,0,sz*item['height_m']/2])) for sx,sz in [(-1,-1),(1,-1),(1,1),(-1,1)]]
            path([point(p) for p in corners],"#696076",None,True,4,True)
            label=item['label']+' · '+item['kind']
        text(x+10,y-9,label[:42],12)
    for m in payload['marks']:
        x,y=point(vec(m['position']));path([[x-5,y],[x+5,y]],"#854266",width=2);path([[x,y-5],[x,y+5]],"#854266",width=2)
        text(x+7,y+22,m['label'][:32],11,"#854266")
    text(60,827,"LEGEND",13)
    text(60,852,"Dashed rose: timed motion / eyeline · Teal: camera gate · Gold: planned light envelope · Dashed edge: clipped display",13)
    text(60,875,"Stops are holds, not every waypoint. Output percent is symbolic opacity, not measured brightness.",13)
    statuses=' · '.join(next((l['label'] for l in payload['lights'] if l['id']==c['id']),c['id'])+': '+c['status'] for c in evaluation['light_coverage'])
    text(60,898,statuses[:140],12)
    text(60,925,"Occlusion, transmission, bounce, ambient, photometry, exposure and safety certification: NOT MODELLED.",13)
    text(60,950,f"{RENDERER} · deterministic geometry · PNG: Pillow default font / PDF: Helvetica",11)
    return result


def render_svg(items,metadata):
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="Spatial movement and planned light coverage">',
         '<metadata>'+escape(canonical(metadata))+'</metadata>','<rect width="100%" height="100%" fill="white"/>']
    for p in items:
        if p['kind']=='text':
            out.append(f'<text x="{p["x"]:.6f}" y="{p["y"]:.6f}" font-family="sans-serif" font-size="{p["size"]}" fill="{p["color"]}">{escape(p["text"])}</text>')
        elif p['points']:
            tag='polygon' if p['closed'] else 'polyline';pts=' '.join(f'{x:.6f},{y:.6f}' for x,y in p['points'])
            dash=' stroke-dasharray="5 4"' if p['dash'] else ''
            out.append(f'<{tag} points="{pts}" stroke="{p["stroke"]}" fill="{p["fill"] or "none"}" stroke-width="{p["width"]}"{dash}/>')
    return ('\n'.join(out)+'\n</svg>\n').encode()


def render_png(items):
    from PIL import Image,ImageDraw,ImageFont
    image=Image.new('RGB',(WIDTH,HEIGHT),'white');draw=ImageDraw.Draw(image)
    for p in items:
        if p['kind']=='text':
            font=ImageFont.load_default(size=p['size'])
            draw.text((p['x'],p['y']),p['text'],font=font,fill=p['color'],anchor='ls')
        elif p['points']:
            pts=[tuple(v) for v in p['points']]
            if p['fill'] and len(pts)>2:draw.polygon(pts,fill=p['fill'])
            if p['closed']:pts=pts+[pts[0]]
            if p['dash']:
                for a,b in zip(pts,pts[1:]):
                    length=math.dist(a,b)
                    if not length:continue
                    for start in range(0,math.ceil(length),9):
                        end=min(start+5,length)
                        draw.line([(a[0]+(b[0]-a[0])*u/length,a[1]+(b[1]-a[1])*u/length) for u in (start,end)],fill=p['stroke'],width=max(1,round(p['width'])))
            elif len(pts)>1:draw.line(pts,fill=p['stroke'],width=max(1,round(p['width'])))
    output=BytesIO();image.save(output,format='PNG',optimize=False,compress_level=9);return output.getvalue()


def render_pdf(pages):
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor
    output=BytesIO();pdf=canvas.Canvas(output,pagesize=(WIDTH,HEIGHT),invariant=1,pageCompression=1)
    pdf.setTitle('Spatial movement and planned coverage');pdf.setAuthor('Storyboarder')
    for items in pages:
        for p in items:
            if p['kind']=='text':
                pdf.setFillColor(HexColor(p['color']));pdf.setFont('Helvetica',p['size']);pdf.drawString(p['x'],HEIGHT-p['y'],p['text'])
            elif p['points']:
                pdf.setStrokeColor(HexColor(p['stroke']));pdf.setLineWidth(p['width']);pdf.setDash([5,4] if p['dash'] else [])
                if p['fill']:pdf.setFillColor(HexColor(p['fill']))
                path=pdf.beginPath();path.moveTo(p['points'][0][0],HEIGHT-p['points'][0][1])
                for x,y in p['points'][1:]:path.lineTo(x,HEIGHT-y)
                if p['closed']:path.close()
                pdf.drawPath(path,stroke=1,fill=int(bool(p['fill'])))
        pdf.showPage()
    pdf.save();return output.getvalue()


def diagrams(payload,version_id,setup_id,content_sha256,times_us,plane=0.0,view_bounds=None,format='all'):
    if format not in ('all','svg','png','pdf'):raise SpatialError('Choose SVG, PNG, PDF, or all.')
    if not isinstance(times_us,list) or not 1<=len(times_us)<=100:raise SpatialError('Export 1–100 time samples.',code='spatial_limit_exceeded')
    files,pages={},[]
    for index,t in enumerate(times_us):
        evaluation=evaluate(payload,t,plane,view_bounds)
        metadata={'schema':'storyboarder.spatial-diagram/v1','setup_id':setup_id,'version_id':version_id,'content_sha256':content_sha256,'requested_time_us':t,'time_us':evaluation['evaluated_time_us'],'target_plane_z_m':plane,'scale':payload['scale'],'length_unit':'m','frame':payload['frame'],'renderer':RENDERER,'limitations':LIMITATIONS,
                  'dependencies':{'Pillow':package_version('Pillow'),'reportlab':package_version('reportlab')}}
        items=primitives(payload,evaluation,metadata);pages.append(items)
        stem=f'sample-{index:03d}-{evaluation["evaluated_time_us"]}'
        files[stem+'.json']=canonical(metadata).encode()
        if format in ('svg','all'):files[stem+'.svg']=render_svg(items,metadata)
        if format in ('png','all'):files[stem+'.png']=render_png(items)
    if format in ('pdf','all'):files['spatial-plan.pdf']=render_pdf(pages)
    return files
