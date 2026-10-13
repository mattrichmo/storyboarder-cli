"""Deterministic Doorway-to-table acceptance payload; no project mutations."""
from math import pi
from uuid import uuid5, NAMESPACE_URL
from .spatial_evaluation import yaw_pitch_roll


def fixed(name):
    return str(uuid5(NAMESPACE_URL,"storyboarder/spatial/doorway/"+name))


def doorway(scene_id,chair_asset_id=None):
    def v(x=0,y=0,z=0):return {"x":x,"y":y,"z":z}
    def pose(x=0,y=0,z=0,yaw=0,pitch=0):return {"position":v(x,y,z),"orientation":yaw_pitch_roll(yaw,pitch)}
    def box(w,d,h):return {"kind":"box","extents":{"width_m":w,"depth_m":d,"height_m":h}}
    def instance(name,kind,x,y,shape,z=0):
        return {"id":fixed(name),"kind":kind,"label":name,"pose":pose(x,y,z),"shape":shape,"notes":"","source_claims":[]}
    def aim(name,height):return {"target":{"kind":"item","item_id":fixed(name),"offset_world":v(0,0,height)},"roll_rad":0}
    actor={"kind":"actor-proxy","radius_m":.24,"standing_height_m":1.7,"seated_height_m":1.1}
    mara=instance("Mara","actor",0,0,actor)|{"posture":"standing","eyeline":aim("Lee",1.6)}
    lee=instance("Lee","actor",1.5,4,actor)|{"posture":"standing","eyeline":aim("Mara",1.6)}
    instances=[mara,lee,instance("Table","prop",0,4.8,box(1.5,.8,.75)),instance("Door","prop",.65,0,box(.8,.08,2.1))]
    for name,x,y in [("Chair 1",0,4.1),("Chair 2",1.5,4.2)]:
        chair=instance(name,"prop",x,y,box(.45,.45,.9))
        if chair_asset_id:chair["asset_id"]=chair_asset_id
        instances.append(chair)
    for name,x,y,w,d in [("West wall",-3,4,.15,8),("East wall",3,4,.15,8),("Back wall",0,8,6,.15),("Front left",-1.75,0,2.5,.15),("Front right",1.75,0,2.5,.15)]:
        instances.append(instance(name,"wall",x,y,box(w,d,2.8)))
    def camera(name,x,y,z,lens,target):
        return {"id":fixed(name),"label":name,"resource_id":fixed("Camera body"),"pose":pose(x,y,z),"aim":target,
                "projection":{"kind":"perspective","focal_length_mm":lens,"sensor_width_mm":36,"sensor_height_mm":24,"active_gate_mm":{"x":0,"y":0,"width":36,"height":24}},"coverage_display_distance_m":12,"notes":"Sequential plan: shared camera resource does not share optics."}
    cameras=[camera("Camera A",2,-2,1.5,35,aim("Mara",1.2)),camera("Camera B",-2,5,1.4,85,aim("Mara",.9))]
    def light(name,role,p,emitter,dimensions,output):
        return {"id":fixed(name),"label":name,"role":role,"pose":p,"emitter":emitter,"source_dimensions_m":dimensions,
                "color":{"mode":"cct","kelvin":5600},"output":{"mode":"schematic","relative":output},"enabled":True,"modifier_ids":[],"coverage_display_distance_m":12,"notes":"Authored envelope, not photometric output."}
    key=light("Key spot","key",pose(0,4,3,0,-pi/2),{"kind":"spot","full_beam_angle_deg":60},{"width_m":.2,"depth_m":.15,"height_m":.2},.5)
    fill=light("Fill area","fill",pose(-2,4,2.4),{"kind":"area","planned_spread_deg":80},{"width_m":1,"depth_m":.1,"height_m":1},.3)|{"aim":aim("Mara",1.1)}
    rim=light("Rim directional","rim",pose(0,7,3,pi,-.35),{"kind":"directional"},{"width_m":.3,"depth_m":.2,"height_m":.3},.4)
    modifiers=[{"id":fixed("Flag"),"label":"Flag","kind":"flag","pose":pose(1.1,4,2),"width_m":.6,"height_m":.9,"notes":"Blocking intent only; no shadow simulation."},
               {"id":fixed("Bounce"),"label":"Bounce","kind":"bounce","pose":pose(-1,4,1),"width_m":1,"height_m":1.2,"notes":"Bounce intent only; light transport not modelled."}]
    key["modifier_ids"]=[fixed("Flag")];fill["modifier_ids"]=[fixed("Bounce")]
    def point(x,y,z=0):return {"kind":"point","point":v(x,y,z)}
    def mark(name):return {"kind":"mark","mark_id":fixed(name),"offset_world":v()}
    def track(name,owner,prop,keys):
        return {"id":fixed(name),"owner_id":fixed(owner),"property":prop,"keys":[{"id":fixed(name+"/"+str(i)),"time_us":t*1000000,"value":value,"next":n} for i,(t,value,n) in enumerate(keys)]}
    tracks=[track("Mara movement","Mara","position",[(0,mark("Mark A"),"linear"),(4,mark("Mark B"),"hold"),(6,mark("Mark B"),"hold")]),
            track("Mara turn","Mara","orientation",[(0,yaw_pitch_roll(0),"hold"),(6,yaw_pitch_roll(0),"linear"),(8,yaw_pitch_roll(-pi/2),"hold")]),
            track("Mara posture","Mara","actor-posture",[(0,"standing","hold"),(8,"seated","hold")]),
            track("Camera A dolly","Camera A","position",[(0,point(2,-2,1.5),"linear"),(4,point(2,2,1.5),"hold")]),
            track("Key spread","Key spot","light-spread",[(4,60,"linear"),(6,40,"hold")]),
            track("Key output","Key spot","light-output",[(4,.5,"linear"),(6,.8,"hold")])]
    return {"schema":"storyboarder.spatial-plan/v1","frame":"rh-z-up-x-right-y-forward/v1","length_unit":"m","setup_label":"Doorway to table","scene_ids":[scene_id],"location_asset_id":None,
            "scale":{"status":"approximate","note":"Authored 6 m × 8 m demo room; not a surveyed location."},"action":{"duration_us":8000000},"floor_plans":[],
            "instances":instances,"marks":[{"id":fixed(n),"label":n,"position":v(x,y)} for n,x,y in [("Mark A",0,0),("Mark B",0,4),("Partner mark",1.5,4)]],
            "beats":[{"id":fixed(n),"label":n,"order":i,"time_us":t*1000000} for i,(n,t) in enumerate([("Entry",0),("Pass-through",2),("At table",4),("End hold",6),("Seated",8)])],
            "resources":[{"id":fixed("Camera body"),"kind":"camera","label":"Shared camera body / sequential plans"}],"cameras":cameras,"lights":[key,fill,rim],"modifiers":modifiers,"tracks":tracks,"source_pins":[],
            "assumptions":["Actor posture is an authored proxy, not skeletal animation.","Modifier links do not attenuate or bounce light.","Relative output controls symbols only; it does not predict exposure."],"origin":None}
