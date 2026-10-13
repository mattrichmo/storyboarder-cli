"""Random-access XYZ action evaluation and explicitly schematic coverage.

+Y is local forward, +Z is up. Gate x/y offsets start at the sensor's
left/bottom. Framing uses world-up look-at followed by inverse gate-ray
correction; roll rotates the world-up target basis before that correction.
No previous frame, database state, viewport zoom, or frame rate is used.
"""
from __future__ import annotations

from bisect import bisect_right
from copy import deepcopy
import math

from .spatial import EVALUATOR, MAX_TIME, SpatialError

EPS = 1e-10
LIMITATIONS = "Planned coverage only. Occlusion, transmission, bounce, ambient, photometry, exposure and safety certification: not modelled."


def vec(v):
    return [v["x"], v["y"], v["z"]]


def xyz(v):
    return dict(zip(("x", "y", "z"), v))


def add(a, b):
    return [a[i] + b[i] for i in range(3)]


def sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def mul(a, n):
    return [v * n for v in a]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def unit(v):
    n = math.hypot(*v)
    return mul(v, 1 / n) if n > EPS else None


def qvalues(q):
    return [q[k] for k in ("x", "y", "z", "w")]


def qdict(q):
    n = math.hypot(*q)
    q = [x / n for x in q]
    sign = next((1 if x > 0 else -1 for x in [q[3], *q[:3]] if x != 0), 1)
    return dict(zip(("x", "y", "z", "w"), [0.0 if x == 0 else x * sign for x in q]))


def qmul(a, b):
    x, y, z, w = qvalues(a)
    X, Y, Z, W = qvalues(b)
    return qdict([w*X+x*W+y*Z-z*Y, w*Y-x*Z+y*W+z*X, w*Z+x*Y-y*X+z*W, w*W-x*X-y*Y-z*Z])


def qinverse(q):
    return {"x": -q["x"], "y": -q["y"], "z": -q["z"], "w": q["w"]}


def rotate(q, v):
    u = [q["x"], q["y"], q["z"]]
    t = mul(cross(u, v), 2)
    return add(v, add(mul(t, q["w"]), cross(u, t)))


def yaw_pitch_roll(yaw, pitch=0, roll=0):
    return qmul(qmul(qdict([0, 0, math.sin(yaw/2), math.cos(yaw/2)]),
                     qdict([math.sin(pitch/2), 0, 0, math.cos(pitch/2)])),
                qdict([0, math.sin(roll/2), 0, math.cos(roll/2)]))


def slerp(a, b, t):
    a, b = qvalues(a), qvalues(b)
    d = dot(a, b)
    if d < 0:
        b, d = [-x for x in b], -d
    d = min(1.0, d)
    if d > 0.9995:
        return qdict([x + (y-x)*t for x, y in zip(a, b)])
    angle = math.acos(d)
    u, v = math.sin((1-t)*angle)/math.sin(angle), math.sin(t*angle)/math.sin(angle)
    return qdict([x*u+y*v for x, y in zip(a, b)])


def from_basis(right, forward, up):
    m = [[right[i], forward[i], up[i]] for i in range(3)]
    tr = m[0][0] + m[1][1] + m[2][2]
    if tr > 0:
        s = math.sqrt(tr+1)*2
        q = [(m[2][1]-m[1][2])/s, (m[0][2]-m[2][0])/s, (m[1][0]-m[0][1])/s, s/4]
    else:
        i = max(range(3), key=lambda k: m[k][k])
        j, k = (i+1)%3, (i+2)%3
        s = math.sqrt(max(0, 1+m[i][i]-m[j][j]-m[k][k]))*2
        q = [0.0]*4
        q[i], q[j], q[k], q[3] = s/4, (m[j][i]+m[i][j])/s, (m[k][i]+m[i][k])/s, (m[k][j]-m[j][k])/s
    return qdict(q)


def look(direction, roll=0):
    forward = unit(direction)
    if forward is None:
        return None
    right = unit(cross(forward, [0, 0, 1]))
    if right is None:
        right = unit(cross(forward, [0, 1, 0]))
    up = cross(right, forward)
    c, s = math.cos(roll), math.sin(roll)
    return from_basis(sub(mul(right, c), mul(up, s)), forward, add(mul(right, s), mul(up, c)))


def gate_bounds(projection):
    g = projection["active_gate_mm"]
    left, bottom = g["x"] - projection["sensor_width_mm"]/2, g["y"] - projection["sensor_height_mm"]/2
    return left, left+g["width"], bottom, bottom+g["height"]


def framing_orientation(camera, position, target, framing):
    relative = sub(target, position)
    length = math.hypot(*relative)
    if length < EPS:
        return None
    p = camera["projection"]
    if p["kind"] == "perspective":
        l, r, b, t = gate_bounds(p)
        ray = [l+(framing["ndc_x"]+1)*(r-l)/2, p["focal_length_mm"], b+(framing["ndc_y"]+1)*(t-b)/2]
    else:
        x, z = framing["ndc_x"]*p["width_m"]/2, framing["ndc_y"]*p["width_m"]/p["aspect"]/2
        depth2 = length*length-x*x-z*z
        if depth2 <= EPS:
            return None
        ray = [x, math.sqrt(depth2), z]
    return qmul(look(relative, framing["roll_rad"]), qinverse(look(ray)))


def project_point(camera, point):
    p = camera["projection"]
    local = rotate(qinverse(camera["pose"]["orientation"]), sub(vec(point), vec(camera["pose"]["position"])))
    x, y, z = local
    if y <= EPS:
        return {"in_front": False, "inside": False, "depth_m": y, "ndc": None}
    if p["kind"] == "perspective":
        l, r, b, t = gate_bounds(p)
        nx, ny = 2*(x/y*p["focal_length_mm"]-l)/(r-l)-1, 2*(z/y*p["focal_length_mm"]-b)/(t-b)-1
    else:
        nx, ny = 2*x/p["width_m"], 2*z/(p["width_m"]/p["aspect"])
    return {"in_front": True, "inside": abs(nx) <= 1+EPS and abs(ny) <= 1+EPS, "depth_m": y, "ndc": [nx, ny]}


def interpolate(a, b, t):
    if isinstance(a, dict):
        return {k: interpolate(v, b[k], t) if k in b else v for k, v in a.items()}
    if isinstance(a, (int, float)) and not isinstance(a, bool):
        return a+(b-a)*t
    return a


def resolve_position(value, marks):
    if value["kind"] == "point":
        return vec(value["point"])
    return add(vec(marks[value["mark_id"]]["position"]), vec(value["offset_world"]))


def track_value(track, time_us, marks):
    keys = track["keys"]
    i = max(0, bisect_right([k["time_us"] for k in keys], time_us)-1)
    a = keys[i]
    prop = track["property"]
    av = resolve_position(a["value"], marks) if prop == "position" else a["value"]
    if i == len(keys)-1 or time_us <= a["time_us"] or a["next"] == "hold":
        return deepcopy(av)
    b = keys[i+1]
    t = (time_us-a["time_us"])/(b["time_us"]-a["time_us"])
    if prop == "position":
        return add(av, mul(sub(resolve_position(b["value"], marks), av), t))
    if prop == "orientation":
        return slerp(av, b["value"], t)
    return interpolate(av, b["value"], t)


def clip_polygon(poly, function):
    if not poly:
        return []
    out = []
    previous, a = poly[-1], function(poly[-1])
    for current in poly:
        b = function(current)
        if (a >= 0) != (b >= 0):
            u = a/(a-b)
            out.append([previous[0]+u*(current[0]-previous[0]), previous[1]+u*(current[1]-previous[1])])
        if b >= 0:
            out.append(current)
        previous, a = current, b
    return out


def checked_bounds(bounds=None):
    b = bounds or {"min_x": -10, "max_x": 10, "min_y": -10, "max_y": 10}
    if set(b) != {"min_x", "max_x", "min_y", "max_y"} or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v)>100000 for v in b.values()):
        raise SpatialError("View bounds must contain four finite metre coordinates.")
    if b["min_x"] >= b["max_x"] or b["min_y"] >= b["max_y"]:
        raise SpatialError("View bounds must have positive width and height.")
    return b


def rectangle(b):
    return [[b["min_x"], b["min_y"]], [b["max_x"], b["min_y"]], [b["max_x"], b["max_y"]], [b["min_x"], b["max_y"]]]


def clip_bounds(poly, b):
    for f in (lambda p:p[0]-b["min_x"], lambda p:b["max_x"]-p[0], lambda p:p[1]-b["min_y"], lambda p:b["max_y"]-p[1]):
        poly = clip_polygon(poly, f)
    return poly


def on_edge(poly, bounds):
    return any(abs(p[0]-bounds[k])<1e-7 for p in poly for k in ("min_x", "max_x")) or any(abs(p[1]-bounds[k])<1e-7 for p in poly for k in ("min_y", "max_y"))


def local_at(item, point):
    return rotate(qinverse(item["pose"]["orientation"]), sub(point, vec(item["pose"]["position"])))


def camera_coverage(camera, z, bounds):
    projection = camera["projection"]
    def local(p):
        return local_at(camera, [*p, z])
    if projection["kind"] == "perspective":
        left, right, bottom, top = gate_bounds(projection)
        f = projection["focal_length_mm"]
        planes = [lambda p:f*local(p)[0]-left*local(p)[1], lambda p:right*local(p)[1]-f*local(p)[0],
                  lambda p:f*local(p)[2]-bottom*local(p)[1], lambda p:top*local(p)[1]-f*local(p)[2]]
        fov = {"horizontal_deg": math.degrees(math.atan2(right, f)-math.atan2(left, f)),
               "vertical_deg": math.degrees(math.atan2(top, f)-math.atan2(bottom, f))}
    else:
        w, h = projection["width_m"]/2, projection["width_m"]/projection["aspect"]/2
        planes = [lambda p:local(p)[0]+w, lambda p:w-local(p)[0], lambda p:local(p)[2]+h, lambda p:h-local(p)[2]]
        fov = None
    planes += [lambda p:local(p)[1]-EPS, lambda p:camera["coverage_display_distance_m"]-local(p)[1]]
    poly = rectangle(bounds)
    for plane in planes:
        poly = clip_polygon(poly, plane)
    clipped = on_edge(poly, bounds) or any(abs(local(p)[1]-camera["coverage_display_distance_m"])<1e-6 for p in poly)
    return {"id": camera["id"], "polygons": [poly] if len(poly)>=3 else [], "status": "no-intersection" if len(poly)<3 else "clipped" if clipped else "bounded",
            "fov": fov, "display_clip_m": camera["coverage_display_distance_m"], "label": "Camera gate coverage; display clip is not visibility proof"}


def light_contains(light, point, *, display_clip=False):
    local = local_at(light, vec(point) if isinstance(point, dict) else point)
    distance = math.hypot(*local)
    if not light["enabled"] or light["output"]["relative"] == 0:
        return False
    if distance < EPS:
        return False  # Source point has no defined ray; evaluator reports it separately.
    if display_clip and distance > light["coverage_display_distance_m"]:
        return False
    kind = light["emitter"]["kind"]
    if kind in ("point", "directional"):
        return True
    if local[1] <= 0:
        return False
    if kind == "spot":
        return local[1]/distance >= math.cos(math.radians(light["emitter"]["full_beam_angle_deg"]/2))-EPS
    half = math.tan(math.radians(light["emitter"]["planned_spread_deg"]/2))
    d = light["source_dimensions_m"]
    return abs(local[0]) <= d["width_m"]/2+local[1]*half and abs(local[2]) <= d["height_m"]/2+local[1]*half


def light_coverage(light, z, bounds, resolution=32):
    kind, o = light["emitter"]["kind"], vec(light["pose"]["position"])
    axis = rotate(light["pose"]["orientation"], [0, 1, 0])
    out = {"id": light["id"], "kind": kind, "polygons": [], "status": "disabled", "label": "Schematic planned coverage; output opacity is not brightness"}
    if not light["enabled"] or light["output"]["relative"] == 0:
        return out
    delta = z-o[2]
    display = light["coverage_display_distance_m"]
    if kind == "directional":
        return out | {"polygons": [rectangle(bounds)], "status": "clipped-unbounded", "axis": xyz(axis), "label": "Directional source: unbounded parallel rays"}
    if kind == "point":
        if abs(delta) >= display:
            return out | {"status": "no-intersection", "label": "Omnidirectional source; outside display radius"}
        radius = math.sqrt(display*display-delta*delta)
        poly = [[o[0]+radius*math.cos(i*math.tau/64), o[1]+radius*math.sin(i*math.tau/64)] for i in range(64)]
        return out | {"polygons": [clip_bounds(poly, bounds)], "status": "display-only", "label": "Omnidirectional display-radius outline; no attenuation"}
    if kind == "area":
        tangent = math.tan(math.radians(light["emitter"]["planned_spread_deg"]/2))
        w, h = light["source_dimensions_m"]["width_m"]/2, light["source_dimensions_m"]["height_m"]/2
        def local(p): return local_at(light, [*p, z])
        poly = rectangle(bounds)
        for f in [lambda p:local(p)[1]-EPS, lambda p:display-local(p)[1],
                  lambda p:w+local(p)[1]*tangent-local(p)[0], lambda p:w+local(p)[1]*tangent+local(p)[0],
                  lambda p:h+local(p)[1]*tangent-local(p)[2], lambda p:h+local(p)[1]*tangent+local(p)[2]]:
            poly = clip_polygon(poly, f)
        return out | {"polygons": [poly] if len(poly)>=3 else [], "status": "no-intersection" if len(poly)<3 else "clipped-schematic" if on_edge(poly,bounds) else "bounded-schematic", "label": "Area source: authored rectangular spread envelope; not light transport"}
    a = math.radians(light["emitter"]["full_beam_angle_deg"]/2)
    cos_a, sin_a = math.cos(a), math.sin(a)
    dz = axis[2]
    min_z = dz*cos_a-math.sqrt(max(0,1-dz*dz))*sin_a
    max_z = dz*cos_a+math.sqrt(max(0,1-dz*dz))*sin_a
    if dz >= cos_a: max_z = 1
    if dz <= -cos_a: min_z = -1
    if (delta > EPS and max_z <= 0) or (delta < -EPS and min_z >= 0):
        return out | {"status": "no-intersection"}
    bounded = (delta>EPS and min_z>EPS) or (delta<-EPS and max_z<-EPS)
    if bounded:
        r = rotate(light["pose"]["orientation"], [1,0,0])
        u = rotate(light["pose"]["orientation"], [0,0,1])
        poly, clipped_distance = [], False
        for i in range(96):
            angle = math.tau*i/96
            ray = add(mul(axis,cos_a), add(mul(r,sin_a*math.cos(angle)),mul(u,sin_a*math.sin(angle))))
            t = delta/ray[2]
            if t>display: clipped_distance=True
            p = add(o,mul(ray,t));poly.append(p[:2])
        if not clipped_distance:
            poly = clip_bounds(poly,bounds)
            out.update(polygons=[poly] if len(poly)>=3 else [], status="no-intersection" if len(poly)<3 else "clipped" if on_edge(poly,bounds) else "bounded")
            if abs(abs(dz)-1)<1e-12:
                out["analytic_radius_m"] = abs(delta)*math.tan(a)
            return out
    # Unbounded/grazing or distance-clipped cones use a deterministic occupancy
    # mesh of this view rectangle, never a fabricated circular footprint.
    dx, dy = (bounds["max_x"]-bounds["min_x"])/resolution,(bounds["max_y"]-bounds["min_y"])/resolution
    polygons=[]
    for iy in range(resolution):
        run=None
        for ix in range(resolution+1):
            inside=ix<resolution and light_contains(light,[bounds["min_x"]+(ix+.5)*dx,bounds["min_y"]+(iy+.5)*dy,z],display_clip=True)
            if inside and run is None:run=ix
            if not inside and run is not None:
                x1,x2=bounds["min_x"]+run*dx,bounds["min_x"]+ix*dx
                y1=bounds["min_y"]+iy*dy
                polygons.append([[x1,y1],[x2,y1],[x2,y1+dy],[x1,y1+dy]]);run=None
    return out | {"polygons":polygons,"status":"degenerate-source-plane" if abs(delta)<EPS else "clipped" if bounded else "clipped-unbounded",
                  "mesh_resolution":resolution,"label":"Clipped planned cone intersection (sampled mesh); dashed boundary is a display limit"}


def evaluate(payload, requested_time_us, target_plane_z_m=0.0, bounds=None, *, coverage=True):
    if isinstance(requested_time_us,bool) or not isinstance(requested_time_us,int) or abs(requested_time_us)>9_007_199_254_740_991:
        raise SpatialError("Evaluation time must be integer microseconds within the safe integer range.")
    if isinstance(target_plane_z_m,bool) or not isinstance(target_plane_z_m,(int,float)) or not math.isfinite(target_plane_z_m) or abs(target_plane_z_m)>100000:
        raise SpatialError("Target plane must be a finite height in metres.")
    bounds=checked_bounds(bounds)
    time_us=max(0,min(payload["action"]["duration_us"],requested_time_us))
    tracks={(t["owner_id"],t["property"]):t for t in payload["tracks"]}
    marks={m["id"]:m for m in payload["marks"]}
    groups=("instances","cameras","lights","modifiers")
    items={i["id"]:deepcopy(i)|{"category":g} for g in groups for i in payload[g]}
    diagnostics=[]
    def sample(item,prop,default):
        t=tracks.get((item["id"],prop))
        return track_value(t,time_us,marks) if t else default
    # Position properties are independent. Aim/eyeline depend only on positions,
    # not on the target's aim; mutual eyelines are therefore not dependency cycles.
    for item in items.values():
        item["pose"]["position"]=xyz(sample(item,"position",vec(item["pose"]["position"])))
        item["pose"]["orientation"]=sample(item,"orientation",item["pose"]["orientation"])
        p=item.get("presence")
        item["present"]=not p or p["start_us"]<=time_us<=p["end_us"]
        if item.get("kind")=="actor":
            item["posture"]=sample(item,"actor-posture",item["posture"])
            item["evaluated_height_m"]=item["shape"][item["posture"]+"_height_m"]
        if item["category"]=="lights":
            item["enabled"]=sample(item,"light-enabled",item["enabled"])
            item["output"]["relative"]=sample(item,"light-output",item["output"]["relative"])
            spread="full_beam_angle_deg" if item["emitter"]["kind"]=="spot" else "planned_spread_deg"
            if spread in item["emitter"]:item["emitter"][spread]=sample(item,"light-spread",item["emitter"][spread])
    def target(value,owner):
        if value["kind"]!="item":return resolve_position(value,marks)
        item=items.get(value["item_id"])
        if item is None or not item["present"]:
            diagnostics.append({"code":"target_absent","item_id":owner,"target_id":value["item_id"]});return None
        return add(vec(item["pose"]["position"]),vec(value["offset_world"]))
    for item in items.values():
        if not item["present"]:continue
        position=vec(item["pose"]["position"])
        aim=sample(item,"aim",item.get("aim"))
        framing=item.get("framing_target")
        if aim or framing:
            definition=framing or aim
            point=target(definition["target"],item["id"])
            q=(framing_orientation(item,position,point,framing) if framing else look(sub(point,position),aim["roll_rad"])) if point is not None else None
            if q:item["pose"]["orientation"]=q
            else:diagnostics.append({"code":"aim_degenerate" if point is not None else "aim_unavailable","item_id":item["id"],"fallback":"authored quaternion"})
        eye=sample(item,"eyeline",item.get("eyeline"))
        if eye:
            point=target(eye["target"],item["id"])
            item["eyeline_target_world"]=xyz(point) if point is not None else None
    result={"schema":"storyboarder.spatial-evaluation/v1","evaluator":EVALUATOR,"requested_time_us":requested_time_us,"evaluated_time_us":time_us,
            "clamped":time_us!=requested_time_us,"target_plane_z_m":target_plane_z_m,"bounds":bounds,"items":list(items.values()),"diagnostics":diagnostics,"limitations":LIMITATIONS,
            "camera_coverage":[],"light_coverage":[]}
    if coverage:
        for camera in (i for i in items.values() if i["category"]=="cameras"):
            camera_result=camera_coverage(camera,target_plane_z_m,bounds)
            samples=[]
            for item in (i for i in items.values() if i["category"]=="instances" and i["present"]):
                p=vec(item["pose"]["position"]); shape=item["shape"]
                height=item.get("evaluated_height_m",shape.get("height_m",shape.get("extents",{}).get("height_m",0)))
                points=[xyz(p),xyz(add(p,[0,0,height/2])),xyz(add(p,[0,0,height]))]
                projected=[project_point(camera,p) for p in points]
                samples.append({"item_id":item["id"],"sample_kind":"base/mid/top centre; no occlusion","points":projected})
            camera_result["subject_samples"]=samples
            result["camera_coverage"].append(camera_result)
        for light in (i for i in items.values() if i["category"]=="lights"):
            c=light_coverage(light,target_plane_z_m,bounds)
            c["subject_samples"]=[{"item_id":i["id"],"inside":light_contains(light,{"x":i["pose"]["position"]["x"],"y":i["pose"]["position"]["y"],"z":target_plane_z_m})} for i in items.values() if i["category"]=="instances" and i["present"]]
            result["light_coverage"].append(c)
    return result
