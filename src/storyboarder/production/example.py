"""Deterministic, provider-free acceptance plan. Produces a batch, never writes it."""
from __future__ import annotations

import base64
import hashlib
from uuid import UUID, uuid5

from .models import parse_record
from .scripts import parse_fountain

SCRIPT = '''INT. STATION OFFICE - DAWN #1#

Mara crosses the room carrying a brass key.

MARA
Keep it safe.

Mara hands the key to Leon. He closes his hand around it.

Leon stays by the table as Mara steps away.
'''


def example(service, expected_checkpoint=0):
    namespace=UUID(service.project.id)
    ids={}
    def uid(name):
        ids.setdefault(name,str(uuid5(namespace,'production-example/'+name)))
        return ids[name]
    def ref(name):
        return {'id':uid(name),'version':1}
    def pose(x=0,y=0,z=0,yaw=0,pitch=0):
        return {'position':{'x':x,'y':y,'z':z},'yaw_deg':yaw,'pitch_deg':pitch,'roll_deg':0}
    def key(frame,x,y,z=0,yaw=0):
        return {'frame':frame,'pose':pose(x,y,z,yaw),'interpolation':'linear'}
    records=[]
    def put(name,kind,title,**data):
        data={'kind':kind,'title':title,'provenance':{'origin':'agent','author':'Storyboarder deterministic example',
              'rationale':'Synthetic demonstration plan for local validation; no production safety claim.',
              'assumptions':['Proxy dimensions are estimates; revise against a measured scout.']},**data}
        records.append({'op':'put','id':uid(name),'expected_revision':0,'select':True,'data':parse_record(data)})
    put('production','production','The handoff',production_type='short',frame_rate={'numerator':24,'denominator':1})
    put('sequence','sequence','01 / An entrusted object',orders={'narrative':1})
    scenes,issues=parse_fountain(SCRIPT,uid('script'))
    script_scene=scenes[0]
    blocks=script_scene['blocks']
    actions=[b for b in blocks if b['type']=='action']
    dialogue=[b for b in blocks if b['type']=='dialogue']
    put('script','script','The handoff — source draft',scenes=scenes,wording_status='imported',import_issues=issues,
        source_file={'name':'the-handoff.fountain','format':'fountain','bytes_base64':base64.b64encode(SCRIPT.encode()).decode(),'sha256':hashlib.sha256(SCRIPT.encode()).hexdigest()})
    geom=[]
    for name,typ,x,y,z,sx,sy,sz in [('Floor','floor',0,0,-.1,8,6,.2),('Back wall','wall',0,3,1.4,8,.15,2.8),('West wall','wall',-4,0,1.4,.15,6,2.8),('East wall','wall',4,0,1.4,.15,6,2.8),('Table','obstacle',1.8,1,.4,1.2,.7,.8)]:
        geom.append({'id':uid('geometry-'+name),'label':name,'type':typ,'pose':pose(x,y,z),
                     'size':{'x':sx,'y':sy,'z':sz},'quality':'estimated','solid':True})
    put('location','location','Station office / 8 × 6 m proxy set',dimension_quality='estimated',geometry=geom,
        marks=[{'id':uid('entrance'),'label':'South entrance','type':'entrance','position':{'x':-2,'y':-3,'z':0}},
               {'id':uid('handoff-mark'),'label':'Handoff mark','type':'mark','position':{'x':0,'y':0,'z':0}}])
    for name,title in [('mara','Mara'),('leon','Leon')]:
        put(name,'asset',title,category='character',dimensions={'x':.45,'y':.35,'z':1.75},dimension_quality='estimated',
            reference_points={'right_hand':{'x':.2,'y':.15,'z':1.1}})
        put('performer-'+name,'asset',title+' performer placeholder',category='performer',portrays=ref(name),
            dimensions={'x':.45,'y':.35,'z':1.75},dimension_quality='estimated')
    put('key','asset','Brass station key',category='prop',dimensions={'x':.08,'y':.025,'z':.006},dimension_quality='estimated',owner='Art department')
    put('coat','asset','Mara’s rust coat',category='wardrobe')
    put('body','asset','Generic full-frame camera',category='camera',specifications={'sensor_width_mm':36,'sensor_height_mm':24})
    put('lens','asset','32–50 mm planning lens',category='lens',specifications={'min_focal_length_mm':32,'max_focal_length_mm':50})
    put('lamp','asset','Daylight soft key',category='light',specifications={'wattage':200,'color_kelvin':5600,'beam_angle_deg':60})
    put('diffusion','asset','Diffusion frame',category='modifier')
    put('stand','asset','Key stand',category='grip')
    fragment={'script':ref('script'),'script_scene_id':script_scene['id'],'block_ids':[]}
    put('scene','scene','01 / Pass the key',label='1',sequence=ref('sequence'),fragments=[fragment],purpose='Transfer responsibility through a small physical action.',
        story_location='Station office',location=ref('location'),interior_exterior='INT',story_time='Dawn',
        requirements=[{'asset':ref('mara'),'role':'giver'},{'asset':ref('leon'),'role':'receiver'},
                      {'asset':ref('key'),'state':{'condition':'brass, intact'}},{'asset':ref('coat'),'state':{'worn_by':'Mara'}}],orders={'narrative':1,'shooting':1})
    beats=[{'id':uid('approach'),'label':'Approach','interval':{'start':0,'end':48},'block_ids':[actions[0]['id']],
            'start_anchor':'Mara at entrance, key in right hand.','end_anchor':'Mara reaches the handoff mark.'},
           {'id':uid('handoff'),'label':'Entrust the key','interval':{'start':48,'end':120},
            'block_ids':[actions[1]['id']]+[b['id'] for b in dialogue],
            'start_anchor':'Key held by Mara.','end_anchor':'Key held by Leon.'},
           {'id':uid('withdraw'),'label':'Step away','interval':{'start':120,'end':192},'block_ids':[actions[2]['id']],
            'start_anchor':'Leon closes his hand.','end_anchor':'Mara returns toward the entrance.'}]
    instances=[{'id':uid('mara-instance'),'label':'Mara','asset':ref('mara'),'pose':pose(-2,0,0,-90),
                'eyeline':{'instance_id':uid('leon-instance'),'offset':{'x':0,'y':0,'z':1.6}},
                'keyframes':[key(0,-2,0,yaw=-90),key(48,-.6,0,yaw=-90),key(120,-.6,0,yaw=-90),key(192,-2,0,yaw=-90)]},
               {'id':uid('leon-instance'),'label':'Leon','asset':ref('leon'),'pose':pose(.6,0,0,90),
                'eyeline':{'instance_id':uid('mara-instance'),'offset':{'x':0,'y':0,'z':1.6}}},
               {'id':uid('key-instance'),'label':'Brass key','asset':ref('key'),'parent_id':uid('mara-instance'),
                'attachment':'right_hand','pose':pose(),'state':{'condition':'intact'}}]
    put('action','action','Blocking A / approach, handoff, withdraw',scene=ref('scene'),location=ref('location'),duration_frames=192,
        beats=beats,instances=instances,prop_events=[{'frame':96,'instance_id':uid('key-instance'),'type':'handoff',
                     'from_instance_id':uid('mara-instance'),'to_instance_id':uid('leon-instance'),'pose':pose(),
                     'state':{'transferred':'yes'}}],alternative='A / quiet exchange')
    for name,title,pos,lens in [('camera-wide','A / room geography',pose(0,-5,1.6),32),('camera-insert','B / the handoff',pose(-1,-2.5,1.5),50)]:
        put(name,'camera_setup',title,scene=ref('scene'),location=ref('location'),action=ref('action'),
            camera_asset=ref('body'),lens_asset=ref('lens'),pose=pos,focal_length_mm=lens,
            target={'point':{'x':0,'y':0,'z':1.0}},focus_target={'point':{'x':0,'y':0,'z':1.1}})
    put('lighting','lighting_setup','L1 / soft dawn from the south',scene=ref('scene'),location=ref('location'),action=ref('action'),
        fixtures=[{'id':uid('key-fixture'),'label':'Soft key','asset':ref('lamp'),'role':'key','pose':pose(-2,-2,3,-25,-35),
                   'relative_intensity':.7,'modifiers':[ref('diffusion')],'supports':[ref('stand')]}],
        cues=[{'frame':120,'fixture_id':uid('key-fixture'),'enabled':True,'relative_intensity':.6}],intended_look='Quiet daylight; practical exposure is not calculated.')
    put('shot-master','shot','01A / Witness the exchange',label='1A',scene=ref('scene'),shot_type='master',purpose='Hold the relationship and the transfer in one geography.',
        subject='Mara and Leon',framing='Wide two-shot',action=ref('action'),beat_ids=[b['id'] for b in beats],interval={'start':0,'end':192},
        cameras=[ref('camera-wide')],lighting=ref('lighting'),orders={'narrative':1,'shooting':1,'editorial':1},
        axis_start={'x':-2,'y':0,'z':0},axis_end={'x':2,'y':0,'z':0},screen_direction='left_to_right')
    put('shot-insert','shot','01B / The key changes hands',label='1B',scene=ref('scene'),shot_type='insert',purpose='Make the transfer unmistakable.',
        subject='The key',framing='Close insert',action=ref('action'),beat_ids=[uid('handoff')],interval={'start':48,'end':120},
        cameras=[ref('camera-insert')],lighting=ref('lighting'),orders={'narrative':2,'shooting':2,'editorial':2})
    for name,shot,camera,frame in [('panel-wide','shot-master','camera-wide',24),('panel-key','shot-insert','camera-insert',96)]:
        put(name,'panel',name.replace('-',' ').title(),shot=ref(shot),camera=ref(camera),action_frame=frame,duration_frames=48,
            drawing=[{'points':[{'x':.2,'y':.8},{'x':.2,'y':.3},{'x':.35,'y':.45},{'x':.65,'y':.45},{'x':.8,'y':.3},{'x':.8,'y':.8}]}],
            annotation='Synthetic composition sketch; inspect the exact camera preview.')
    put('animatic','animatic','The exchange / two-panel timing',entries=[{'panel':ref('panel-wide'),'duration_frames':48},
                                                                       {'panel':ref('panel-key'),'duration_frames':48,'audio_cue':'Keep it safe.'}])
    put('edit','edit','Cut A / geography → handoff → departure',entries=[
        {'shot':ref('shot-master'),'shot_interval':{'start':0,'end':48},'match_action_anchor':uid('handoff')},
        {'shot':ref('shot-insert'),'shot_interval':{'start':0,'end':72},'match_action_anchor':uid('handoff')},
        {'shot':ref('shot-master'),'shot_interval':{'start':120,'end':192}}])
    put('note','annotation','Director’s exact handoff note',subject=ref('action'),object_id=uid('handoff'),action_frame=96,
        body='Keep the transfer readable, without pushing the performers into an unnatural gesture.',author='Demo director')
    return {'batch':{'expected_checkpoint':expected_checkpoint,'operation_id':uid('example-operation'),'operations':records},
            'ids':ids,'script':SCRIPT,'description':'Synthetic provider-free acceptance fixture. Explicitly selected only when this batch is applied.',
            'persisted':False}
