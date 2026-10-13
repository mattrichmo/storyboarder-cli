"""Pure deterministic blocking/camera/lighting evaluation; no photometric claims.

Frames belong to the shared action rate. Positions use linear/hold interpolation;
yaw/roll interpolate by the shortest angular arc. Parented poses are local metres.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import math

from . import EVALUATOR
from .models import ProductionError, Rate, decode

LIMITATIONS = [
    'Proxy geometry and rectilinear pinhole framing, not a physically accurate lens or renderer.',
    'Lighting cones and intensity are symbolic: no exposure, power distribution, rigging or electrical-safety validation.',
    'Visibility and collision warnings are geometric/advisory, not proof of occlusion, clearance or creative sufficiency.',
    'Scene geometry uses oriented box proxies; meshes are retained as references, not collision surfaces.',
]


def fps(rate):
    return Fraction(rate['numerator'],rate['denominator'])


def seconds(frames, rate):
    return Fraction(frames) / fps(rate)


def convert_frames(frames, from_rate, to_rate, rounding='exact'):
    if type(frames) is not int or frames < 0:
        raise ProductionError('Frame count must be a nonnegative integer.')
    from_rate, to_rate = decode(Rate,from_rate), decode(Rate,to_rate)
    value = Fraction(frames) * fps(to_rate) / fps(from_rate)
    if rounding not in ('exact','floor','ceil','nearest'):
        raise ProductionError('Rounding must be exact, floor, ceil or nearest (half-up).')
    rounded = None
    if value.denominator == 1:
        rounded = value.numerator
    elif rounding == 'floor':
        rounded = math.floor(value)
    elif rounding == 'ceil':
        rounded = math.ceil(value)
    elif rounding == 'nearest':
        rounded = math.floor(value+Fraction(1,2))
    return {'frames':rounded,'exact':{'numerator':value.numerator,'denominator':value.denominator},
            'rounding':rounding,'requires_rounding':value.denominator != 1,
            'seconds':float(seconds(frames,from_rate))}


def shot_duration_frames(shot, action):
    span = shot['interval']['end']-shot['interval']['start']
    speed = shot.get('time_map') or {'speed_numerator':1,'speed_denominator':1,'shot_start':0}
    value = Fraction(span)*fps(shot['frame_rate'])/fps(action['frame_rate'])
    value *= Fraction(speed['speed_denominator'],speed['speed_numerator'])
    return float(value)+speed['shot_start']


def action_frame_for_shot(shot, action, frame):
    mapping = shot.get('time_map') or {'action_start':shot['interval']['start'],'shot_start':0,
                                      'speed_numerator':1,'speed_denominator':1}
    return mapping['action_start'] + (frame-mapping['shot_start'])*float(fps(action['frame_rate'])/fps(shot['frame_rate']))*mapping['speed_numerator']/mapping['speed_denominator']


def vec(value):
    return [value['x'],value['y'],value['z']]


def xyz(v):
    return {'x':clean(v[0]),'y':clean(v[1]),'z':clean(v[2])}


def clean(x):
    return round(float(x),9) if abs(x)>1e-10 else 0.0


def add(a,b):
    return [a[i]+b[i] for i in range(3)]


def sub(a,b):
    return [a[i]-b[i] for i in range(3)]


def mul(a,s):
    return [x*s for x in a]


def dot(a,b):
    return sum(a[i]*b[i] for i in range(3))


def cross(a,b):
    return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]


def norm(v):
    return math.sqrt(dot(v,v))


def unit(v, fallback=None):
    n = norm(v)
    if n < 1e-9:
        return fallback or [0,1,0]
    return mul(v,1/n)


def rotation(pose):
    y,p,r = [math.radians(pose.get(k,0)) for k in ('yaw_deg','pitch_deg','roll_deg')]
    cy,sy,cp,sp,cr,sr = math.cos(y),math.sin(y),math.cos(p),math.sin(p),math.cos(r),math.sin(r)
    return [[cy*cr-sy*sp*sr,-sy*cp,cy*sr+sy*sp*cr],
            [sy*cr+cy*sp*sr,cy*cp,sy*sr-cy*sp*cr],[-cp*sr,sp,cp*cr]]


def rotate(matrix,v):
    return [dot(row,v) for row in matrix]


def transpose(m):
    return [list(row) for row in zip(*m)]


def matmul(a,b):
    cols = transpose(b)
    return [[dot(row,col) for col in cols] for row in a]


def angles(m):
    pitch = math.asin(max(-1,min(1,m[2][1])))
    if abs(math.cos(pitch))<1e-7:
        yaw,roll = math.atan2(m[1][0],m[0][0]),0
    else:
        yaw,roll = math.atan2(-m[0][1],m[1][1]),math.atan2(-m[2][0],m[2][2])
    return {'yaw_deg':clean(math.degrees(yaw)),'pitch_deg':clean(math.degrees(pitch)),'roll_deg':clean(math.degrees(roll))}


def pose_at(base, keys, frame):
    if not keys or frame < keys[0]['frame']:
        return deepcopy(base)
    for a,b in zip(keys,keys[1:]):
        if a['frame'] <= frame < b['frame']:
            if a['interpolation'] == 'hold':
                return deepcopy(a['pose'])
            t = (frame-a['frame'])/(b['frame']-a['frame'])
            av,bv = a['pose'],b['pose']
            result = {'position':xyz([av['position'][k]+(bv['position'][k]-av['position'][k])*t for k in ('x','y','z')])}
            for k in ('yaw_deg','pitch_deg','roll_deg'):
                diff = (bv[k]-av[k]+180)%360-180
                result[k] = clean(av[k]+diff*t)
            return result
    return deepcopy(keys[-1]['pose'])


def target_position(target, instances, location):
    if not target:
        return None
    if target['point']:
        pos = vec(target['point'])
    elif target['instance_id']:
        item = instances.get(target['instance_id'])
        if not item:
            return None
        pos = vec(item['pose']['position'])
    else:
        mark = next((m for m in location['marks'] if m['id']==target['mark_id']),None)
        if mark is None:
            return None
        pos = vec(mark['position'])
    return add(pos,vec(target['offset']))


def _world_instances(graph, action, location, frame, overrides):
    local = {}
    override_by = {o['instance_id']:o for o in overrides}
    for i in action['instances']:
        override = override_by.get(i['id'],{})
        pose = pose_at(override.get('pose') or i['pose'],override.get('keyframes') or i['keyframes'],frame)
        local[i['id']] = {**deepcopy(i),'pose':pose,'present':not i['presence'] or i['presence']['start']<=frame<i['presence']['end'],
                          'overridden':bool(override),'asset_data':graph.require(i['asset'])}
    for e in sorted(action['prop_events'],key=lambda x:x['frame']):
        if e['frame'] > frame:
            break
        i = local[e['instance_id']]
        i['state'].update(e['state'])
        if e['type'] in ('carried','handoff'):
            i['parent_id'] = e['to_instance_id']; i['present'] = True
            i['pose'] = e['pose'] or {'position':{'x':0,'y':0,'z':0},'yaw_deg':0,'pitch_deg':0,'roll_deg':0}
        elif e['type'] == 'placed':
            i['parent_id'] = None; i['present'] = True
            if e['pose']:
                i['pose'] = e['pose']
        elif e['type'] == 'removed':
            i['parent_id'] = None; i['present'] = False
    # Resolve parent chains iteratively, avoiding Python recursion on deep valid graphs.
    world, pending = {}, set(local)
    while pending:
        progress = False
        for rid in sorted(pending):
            i = local[rid]
            parent = i['parent_id']
            if parent and parent not in world:
                continue
            pos, mat = vec(i['pose']['position']), rotation(i['pose'])
            if parent:
                p = world[parent]
                refpoint = p['asset_data']['reference_points'].get(i['attachment'])
                if refpoint:
                    pos = add(pos,vec(refpoint))
                pos = add(vec(p['pose']['position']),rotate(p['basis'],pos))
                mat = matmul(p['basis'],mat)
            world[rid] = {**i, 'basis':mat,'pose':{'position':xyz(pos),**angles(mat)},
                          'present':i['present'] and (not parent or world[parent]['present'])}
            pending.remove(rid); progress = True
        if not progress:
            raise ProductionError('Unresolvable instance hierarchy.')
    # Facing constraints use resolved target positions; eyelines are separate hints.
    # Attachments subsequently follow the resolved parent facing. Re-evaluate to a
    # deterministic fixed point; report non-convergence rather than hiding it.
    converged = True
    for iteration in range(16):
        updated = {}
        max_delta = 0.0
        for rid,i in world.items():
            raw = local[rid]
            pos,mat = vec(raw['pose']['position']),rotation(raw['pose'])
            if raw['parent_id']:
                p = world[raw['parent_id']]
                refpoint = p['asset_data']['reference_points'].get(raw['attachment'])
                if refpoint:
                    pos = add(pos,vec(refpoint))
                pos = add(vec(p['pose']['position']),rotate(p['basis'],pos))
                mat = matmul(p['basis'],mat)
            target = target_position(raw['facing'],world,location)
            if target is not None and norm(sub(target,pos))>1e-8:
                delta = sub(target,pos)
                ang = angles(mat)
                ang['yaw_deg'] = math.degrees(math.atan2(-delta[0],delta[1]))
                mat = rotation(ang)
            max_delta = max(max_delta,norm(sub(pos,vec(i['pose']['position']))),
                            sum(abs(mat[y][x]-i['basis'][y][x]) for y in range(3) for x in range(3)))
            updated[rid] = {**i,'basis':mat,'pose':{'position':xyz(pos),**angles(mat)}}
        world = updated
        if max_delta<1e-7:
            break
        if iteration==15:
            converged=False
    for i in world.values():
        eye = target_position(i['eyeline'],world,location)
        i['eyeline_target'] = xyz(eye) if eye else None
        i['forward'] = xyz(rotate(i['basis'],[0,1,0]))
        i['dimensions'] = i['asset_data']['dimensions'] or {'x':0.5,'y':0.5,'z':1.75 if i['asset_data']['category'] in ('character','performer') else 0.3}
        i['dimension_assumption'] = i['asset_data']['dimensions'] is None
        i['category'] = i['asset_data']['category']
        del i['asset_data']
    return list(world.values()), converged


def camera_sample(camera, frame, items, location):
    pose = pose_at(camera['pose'],camera['keyframes'],frame)
    position, basis = vec(pose['position']),rotation(pose)
    target = target_position(camera['target'],items,location)
    if target is not None and norm(sub(target,position))>1e-9:
        forward = unit(sub(target,position))
        right = unit(cross(forward,[0,0,1]),[1,0,0])
        up = unit(cross(right,forward),[0,0,1])
        roll = math.radians(pose['roll_deg'])
        rr,uu = add(mul(right,math.cos(roll)),mul(up,-math.sin(roll))),add(mul(right,math.sin(roll)),mul(up,math.cos(roll)))
        basis = transpose([rr,forward,uu])
    right,forward,up = transpose(basis)
    aspect = camera['aspect_ratio']['width']/camera['aspect_ratio']['height']
    gate_w = camera['sensor_width_mm'] if camera['fit']=='horizontal' else camera['sensor_height_mm']*aspect
    gate_h = gate_w/aspect
    hfov = 2*math.atan(gate_w/(2*camera['focal_length_mm']))
    vfov = 2*math.atan(gate_h/(2*camera['focal_length_mm']))
    focus = target_position(camera['focus_target'],items,location)
    focus_distance = norm(sub(focus,position)) if focus is not None else camera['focus_distance_m']
    distance = 5.0
    centre = add(position,mul(forward,distance))
    corners = [add(add(centre,mul(right,x*distance*math.tan(hfov/2))),mul(up,z*distance*math.tan(vfov/2))) for x,z in [(-1,-1),(1,-1),(1,1),(-1,1)]]
    return {'pose':{'position':xyz(position),**angles(basis)},'basis':basis,'forward':xyz(forward),
            'horizontal_fov_deg':clean(math.degrees(hfov)),'vertical_fov_deg':clean(math.degrees(vfov)),
            'gate_width_mm':gate_w,'gate_height_mm':gate_h,'focus_distance_m':focus_distance,
            'safe_area':camera['safe_area'],'aspect_ratio':camera['aspect_ratio'],
            'frustum':{'origin':xyz(position),'corners':[xyz(c) for c in corners],'display_depth_m':distance},
            'model':'rectilinear-pinhole','assumptions':['Centred sensor crop; no distortion, breathing, depth-of-field or anamorphic model.']}


def project_point(camera, point):
    position = vec(camera['pose']['position'])
    right,forward,up = transpose(camera['basis'])
    delta = sub(vec(point) if isinstance(point,dict) else point,position)
    depth = dot(delta,forward)
    if depth <= 0.001:
        return None
    x = dot(delta,right)/(depth*math.tan(math.radians(camera['horizontal_fov_deg']/2)))
    y = dot(delta,up)/(depth*math.tan(math.radians(camera['vertical_fov_deg']/2)))
    return {'x':(x+1)/2,'y':(1-y)/2,'depth_m':depth,'inside':abs(x)<=1 and abs(y)<=1}


def segment_box(start, end, box, margin=0):
    """Segment / oriented-box slab check, with a conservative spherical expansion."""
    matrix = transpose(rotation(box['pose']))
    a = rotate(matrix,sub(start,vec(box['pose']['position'])))
    b = rotate(matrix,sub(end,vec(box['pose']['position'])))
    half = [box['size'][k]/2+margin for k in ('x','y','z')]
    lo,hi = 0.0,1.0
    for i in range(3):
        d=b[i]-a[i]
        if abs(d)<1e-12:
            if abs(a[i])>half[i]:
                return False
        else:
            t0,t1=(-half[i]-a[i])/d,(half[i]-a[i])/d
            lo,hi=max(lo,min(t0,t1)),min(hi,max(t0,t1))
            if lo>hi:
                return False
    return True


def evaluate_graph(graph, id, version=None, frame=0.0):
    h = graph.heads.get(id)
    if h is None:
        raise ProductionError('Unknown production record to evaluate.')
    version = version if version is not None else h['selected_version'] or h['head_version']
    record = graph.resolve(id,version)
    p = record['data']
    if isinstance(frame,bool) or not isinstance(frame,(int,float)) or not math.isfinite(frame) or frame<0:
        raise ProductionError('Evaluation frame must be finite and nonnegative.')
    shot,action,location = None,None,None
    cameras,lights = [],[]
    if p['kind']=='shot':
        shot=p
        if p['action']:
            action=graph.require(p['action'])
        scene=graph.require(p['scene'])
        loc = action['location'] if action else scene['location']
        location=graph.require(loc) if loc else None
        cameras=[(r,graph.require(r)) for r in p['cameras']]
        lights=[(p['lighting'],graph.require(p['lighting']))] if p['lighting'] else []
    elif p['kind']=='action':
        action=p; location=graph.require(p['location'])
        for header in graph.heads.values():
            if header['archived'] or not header['selected_version'] or header['kind'] not in ('camera_setup','lighting_setup'):
                continue
            ref={'id':header['id'],'version':header['selected_version']}
            setup=graph.require(ref)
            if setup['action']=={'id':id,'version':version}:
                (cameras if header['kind']=='camera_setup' else lights).append((ref,setup))
    elif p['kind'] in ('camera_setup','lighting_setup'):
        action=graph.require(p['action']) if p['action'] else None
        location=graph.require(p['location'])
        (cameras if p['kind']=='camera_setup' else lights).append(({'id':id,'version':version},p))
    elif p['kind']=='location':
        location=p
    elif p['kind']=='scene':
        location=graph.require(p['location']) if p['location'] else None
    else:
        raise ProductionError('Evaluate a scene, action, location, shot, camera or lighting setup.')
    if action and frame>action['duration_frames']:
        raise ProductionError('Evaluation frame lies beyond shared action duration.')
    location=location or {'geometry':[],'marks':[],'coordinate_frame':'rh-z-up-x-right-y-forward/v1','title':'Location not planned'}
    items,converged=_world_instances(graph,action,location,frame,shot['overrides'] if shot else []) if action else ([],True)
    by_id={i['id']:i for i in items}
    camera_rows=[{'id':ref['id'],'version':ref['version'],'title':camera['title'],
                  **camera_sample(camera,frame,by_id,location)} for ref,camera in cameras]
    fixture_rows=[]
    for ref,setup in lights:
        for fixture in setup['fixtures']:
            f=deepcopy(fixture)
            for cue in sorted(setup['cues'],key=lambda x:x['frame']):
                if cue['fixture_id']==f['id'] and cue['frame']<=frame:
                    f.update({'enabled':cue['enabled'],'relative_intensity':cue['relative_intensity']})
            f.update({'setup':ref,'basis':rotation(f['pose']),'display_depth_m':5.0})
            fixture_rows.append(f)
    for c in camera_rows:
        c['subjects']=[{'id':i['id'],'label':i['label'],'projection':project_point(c,i['pose']['position']),
                        'dimensions':i['dimensions'],'position':i['pose']['position']} for i in items if i['present']]
    warnings=[] if converged else [{'code':'facing_nonconvergent','message':'Mutually dependent facing/attachment constraints did not settle; inspect the plan.'}]
    return {'evaluator':EVALUATOR,'source':{'id':id,'version':version,'sha256':record['sha256']},
            'action_frame':frame,'frame_rate':action['frame_rate'] if action else None,
            'duration_frames':action['duration_frames'] if action else 0,
            'seconds':float(seconds(Fraction(str(frame)),action['frame_rate'])) if action else 0,
            'location':location,'instances':items,'cameras':camera_rows,'fixtures':fixture_rows,
            'beats':[b for b in action['beats'] if b['interval']['start']<=frame<b['interval']['end']] if action else [],
            'paths':[{'id':i['id'],'label':i['label'],'parent_id':i['parent_id'],'keys':i['keyframes']} for i in action['instances']] if action else [],
            'warnings':warnings,'limitations':LIMITATIONS}


def evaluate(service, id, version=None, frame=0.0):
    from .service import ProductionService
    prod=ProductionService(service)
    with service.repo.transaction(False) as conn:
        return {'checkpoint':prod._clock(conn),**evaluate_graph(prod._graph(conn),id,version,frame)}
