#!/usr/bin/env python3
"""Create a fictional portable demo through the public application layer.
The included slates are explicitly labelled demo graphics, not photographs.
"""
from pathlib import Path
import argparse
import json
import tempfile
from PIL import Image, ImageDraw, ImageFont
from storyboarder.application.projects import Workspace
from storyboarder.application.service import Service


def make_slate(path, name, subtitle, number):
    palette = [(207,216,201),(194,211,207),(218,207,188),(210,204,218)]
    image = Image.new('RGB',(1200,800),(242,242,231))
    draw = ImageDraw.Draw(image)
    shade=palette[number%len(palette)]
    draw.rectangle((40,40,1160,650), fill=shade)
    for i in range(7):
        x=75+i*190
        y=520-(i%3)*90
        draw.polygon([(x-120,650),(x+100,y-250),(x+320,650)],fill=tuple(max(0,v-15-(i%3)*9) for v in shade))
    draw.rectangle((72,76,1128,104),fill=(242,242,231))
    draw.text((88,81),'STORYBOARDER / FICTIONAL DEMO REFERENCE',font=ImageFont.load_default(size=15),fill=(55,69,48))
    draw.text((70,675),name,font=ImageFont.load_default(size=38),fill=(46,57,39))
    draw.text((72,731),subtitle,font=ImageFont.load_default(size=18),fill=(74,83,65))
    image.save(path,quality=92)


def create_demo(workspace_path,slug='winter-station'):
    workspace=Workspace(workspace_path);workspace.init()
    project=workspace.create('Winter Station',slug)
    service=Service(project)
    service.update_entity(project.id,1,{'description':'A fictional short film about a quiet place at the edge of change.','fields':{
        'premise':'On the last morning before a remote station closes, its caretaker walks the grounds with the person who will inherit its stories.',
        'visual_style':'A calm, observational camera. Soft winter daylight, readable shadows, natural texture. Let the space and gestures carry the scene.',
        'constraints':'No decorative camera movement. Preserve the geography between the platform and the maintenance room.'}})
    assets={}
    with tempfile.TemporaryDirectory() as temp:
        definitions=[('Mara','character','The long-serving caretaker; deliberate, unsentimental movements.'),('Eli','character','A young archivist arriving to document the station.'),('North platform','location','A modest rural platform, wind and empty tracks.'),('Maintenance room','location','Practical tools, handwritten notes, and diffuse window light.'),('Brass key','prop','The final station key; an ordinary object with narrative weight.'),('Winter light','reference','Overcast daylight without theatrical contrast.')]
        for i,(name,kind,description) in enumerate(definitions):
            path=Path(temp)/(name.lower().replace(' ','-')+'.jpg');make_slate(path,name,'Demo graphic — replace with your own production reference',i)
            imported=service.import_file(path)
            asset=service.create_entity('asset',name,description=description,fields={'type':kind},tags=['winter',kind],aliases=['Caretaker'] if name=='Mara' else [])
            service.review_intake(imported['intake']['id'],1,'accepted',asset_id=asset['id'])
            assets[name]=(asset,imported['media'])
        # Intentionally preserve a duplicate import in intake to demonstrate review grouping.
        service.import_file(Path(temp)/'north-platform.jpg')
        sequence=service.create_entity('sequence','The last morning',fields={'arc':'From routine to a quiet handover.','tone':'Patient, ordinary, quietly irreversible.'})
        opening=service.create_entity('scene','Before the first arrival',sequence['id'],fields={'summary':'Mara opens the station as she has done for decades. Today the routine will end.','location_id':assets['North platform'][0]['id'],'time':'Blue-grey morning','continuity':'Key remains in the right coat pocket until the maintenance room.'})
        interior=service.create_entity('scene','An ordinary handover',sequence['id'],fields={'summary':'Eli listens while Mara decides which details are worth remembering.','location_id':assets['Maintenance room'][0]['id'],'time':'Morning','continuity':'Coats stay on. The room is not heated.'})
        shots=[]
        shot_defs=[(opening,'01','The platform waits','Locked wide','A still platform. Mara enters from frame left, small against the station.',12,'Hold the empty frame before Mara enters.'),
                   (opening,'02','The familiar route','Medium follow','Mara checks a latch and brushes frost from the noticeboard.',8,'Move at walking pace; no reveal flourish.'),
                   (opening,'03','A small arrival','Two-shot','Eli approaches. Mara pauses, then makes room beside her.',10,'Keep both figures at an ordinary conversational distance.'),
                   (interior,'04','What stays on the wall','Medium','Eli studies a wall of notes while Mara sorts a small tray of keys.',9,'Eye-level, soft window light.'),
                   (interior,'05','The final key','Close-up','Mara places one brass key on the table. Her hand remains there briefly.',7,'Observe the gesture. Do not overstate its importance.'),
                   (interior,'06','Leave the door open','Wide','They leave together. The room stays in the frame after they are gone.',15,'Return to stillness. Allow the room to finish the sequence.')]
        for scene,number,title,framing,action,duration,camera in shot_defs:
            shot=service.create_entity('shot',title,scene['id'],fields={'number':number,'framing':framing,'action':action,'duration':duration,'camera':camera,'dialogue':'','notes':'Demo shot; revise for your production.'})
            shots.append(shot)
            for name,role in [('Mara','subject'),('North platform' if scene['id']==opening['id'] else 'Maintenance room','setting-reference')]:
                asset,media=assets[name];service.assign(shot['id'],asset['id'],role,media['id'])
        service.assign(shots[4]['id'],assets['Brass key'][0]['id'],'prop',assets['Brass key'][1]['id'])
        service.assign(shots[2]['id'],assets['Eli'][0]['id'],'subject',assets['Eli'][1]['id'])
        service.create_link(assets['Mara'][0]['id'],assets['North platform'][0]['id'],'appears-at')
        service.create_link(assets['Eli'][0]['id'],assets['Maintenance room'][0]['id'],'appears-at')
        service.create_link(assets['Brass key'][0]['id'],assets['Maintenance room'][0]['id'],'part-of')
        service.put_context(project.id,'camera','append','Avoid visual punctuation that tells the audience what to feel.')
        service.put_context(opening['id'],'weather','append','Fine frost, no visible snowfall, low wind.')
        service.put_context(shots[4]['id'],'camera','replace','For this insert only, let the stationary frame settle on the hand and key.')
        for i in (0,4):
            path=Path(temp)/f'frame-{i}.jpg';make_slate(path,shot_defs[i][2],'Demo storyboard candidate — illustrative slate, not shot artwork',i+2)
            frame=service.add_frame(shots[i]['id'],path,notes='Example frame candidate for workflow demonstration.')
            service.set_frame_state(frame['id'],frame['revision'],'approved' if i==0 else 'selected')
    graph=service.graph('assets')
    positions={}
    for t,kind in enumerate(('character','location','prop','reference')):
        for i,a in enumerate(n for n in graph['nodes'] if n['fields']['type']==kind):positions[a['id']]={'x':t*310,'y':i*275}
    service.save_layout('Reference desk','assets',positions,{'viewport':{'x':45,'y':55,'scale':.68},'hidden':[],'collapsed':[]})
    return {'project':project.summary(),'sequence_id':sequence['id'],'scene_ids':[opening['id'],interior['id']],'shot_ids':[s['id'] for s in shots],'asset_ids':{name:a['id'] for name,(a,m) in assets.items()}}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('workspace');parser.add_argument('--slug',default='winter-station');args=parser.parse_args()
    print(json.dumps(create_demo(args.workspace,args.slug),ensure_ascii=False,indent=2))
