"""Readiness, exact source coverage and advisory continuity from the same graph."""
from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
import math

from storyboarder.media.files import safe_path, sha256
from .evaluate import (evaluate_graph, project_point, segment_box, vec, add, sub, norm,
                       shot_duration_frames, action_frame_for_shot, seconds)
from .graph import fragment_equivalent, ref_for
from .models import ProductionError, digest, parse_record, references
from .service import ProductionService
from .external import verify_external


def media_refs(value):
    if isinstance(value,dict):
        if set(value)=={'media_id','path','sha256','description'}:
            yield value
        else:
            for child in value.values():
                yield from media_refs(child)
    elif isinstance(value,list):
        for child in value:
            yield from media_refs(child)


def coverage_report(graph, records):
    scripts=[r for r in records if r['kind']=='script']
    scenes=[r for r in records if r['kind']=='scene']
    shots=[r for r in records if r['kind']=='shot']
    actions=[r for r in records if r['kind']=='action']
    material=[]
    for script in scripts:
        for scene in script['data']['scenes']:
            for block in scene['blocks']:
                if block['type'] not in ('action','dialogue','lyric'):
                    continue
                owners,covering,decisions=[],[],[]
                def includes(fragment):
                    if fragment['script']['id']!=script['id'] or fragment['script_scene_id']!=scene['id']:
                        return False
                    if fragment['block_ids'] and block['id'] not in fragment['block_ids']:
                        return False
                    old=graph.require(fragment['script'])
                    return fragment_equivalent({**fragment,'block_ids':[block['id']]},old,script['data'])
                for production_scene in scenes:
                    for f in production_scene['data']['fragments']:
                        if includes(f):
                            if f['disposition']=='planned':
                                owners.append(production_scene['id'])
                            else:
                                decisions.append({'scene_id':production_scene['id'],'disposition':f['disposition'],'reason':f['reason']})
                for shot in shots:
                    p=shot['data']
                    direct=any(includes(f) and f['disposition']=='planned' for f in p['fragments'])
                    # Shared-action coverage also resolves through its exact production scene.
                    if not direct and p['action'] and p['interval']:
                        action=graph.require(p['action'])
                        source_scene=graph.require(action['scene'])
                        mapped=any(includes(f) and f['disposition']=='planned' for f in source_scene['fragments'])
                        direct=mapped and any(block['id'] in b['block_ids'] and b['id'] in p['beat_ids'] and
                            max(b['interval']['start'],p['interval']['start'])<min(b['interval']['end'],p['interval']['end'])
                            for b in action['beats'])
                    if direct:
                        covering.append(shot['id'])
                status='covered' if covering else 'intentionally_unfilmed' if any(d['disposition'] in ('omitted','intentionally_unfilmed') for d in decisions) else 'deferred' if decisions else 'uncovered'
                material.append({'script':ref_for(script),'script_scene_id':scene['id'],'scene_heading':scene['heading'],
                                 'block_id':block['id'],'type':block['type'],'text':block['text'],
                                 'production_scene_ids':sorted(set(owners)),'shot_ids':covering,'status':status,
                                 'decisions':decisions,'multiple_shot_coverage':len(covering)>1})
    beats=[]
    # Include action versions actually photographed, even if not the latest selected
    # alternative, so a coverage report cannot silently evaluate another action.
    action_map={(r['id'],r['version']):r for r in actions}
    for r in shots:
        ref=r['data']['action']
        if ref:
            action_map[ref['id'],ref['version']]=graph.resolve(ref['id'],ref['version'])
    for action in action_map.values():
        for beat in action['data']['beats']:
            intervals=[]
            for shot in shots:
                p=shot['data']
                if p['action']!=ref_for(action) or beat['id'] not in p['beat_ids'] or not p['interval']:
                    continue
                a=max(beat['interval']['start'],p['interval']['start'])
                b=min(beat['interval']['end'],p['interval']['end'])
                if a<b:
                    intervals.append({'shot_id':shot['id'],'start':a,'end':b,'cameras':p['cameras']})
            merged=[]
            for interval in sorted(intervals,key=lambda x:(x['start'],x['end'])):
                if merged and interval['start']<=merged[-1][1]:
                    merged[-1][1]=max(merged[-1][1],interval['end'])
                else:
                    merged.append([interval['start'],interval['end']])
            gaps=[]; cursor=beat['interval']['start']
            for a,b in merged:
                if a>cursor:
                    gaps.append({'start':cursor,'end':a})
                cursor=max(cursor,b)
            if cursor<beat['interval']['end']:
                gaps.append({'start':cursor,'end':beat['interval']['end']})
            covered=sum(b-a for a,b in merged)
            duplicate=sum(x['end']-x['start'] for x in intervals)-covered
            beats.append({'action':ref_for(action),'beat_id':beat['id'],'label':beat['label'],
                          'interval':beat['interval'],'frame_rate':action['data']['frame_rate'],
                          'coverage':intervals,'gaps':gaps,'covered_frames':covered,'overlap_frames':duplicate,
                          'status':'covered' if not gaps else 'partial' if covered else 'uncovered'})
    return {'material':material,'beats':beats,
            'summary':{'script_passages':len(material),'uncovered_passages':sum(x['status']=='uncovered' for x in material),
                       'deferred_passages':sum(x['status']=='deferred' for x in material),
                       'uncovered_or_partial_beats':sum(x['status']!='covered' for x in beats)},
            'limitations':['Multiple angles and overlapping coverage may be intentional. Artistic sufficiency is not calculated.',
                           'An old script pin counts against the current script only when the covered passage and heading are unchanged.']}


def equipment_report(graph, records):
    equipment={}
    def add_item(ref,qty,setup,role):
        key=(ref['id'],ref['version'])
        asset=graph.require(ref)
        row=equipment.setdefault(key,{'asset':ref,'title':asset['title'],'category':asset['category'],
                                     'specifications':asset['specifications'],'uses':[]})
        row['uses'].append({'setup':setup,'quantity':qty,'role':role})
    setup_refs={}
    for r in records:
        if r['kind']=='shot':
            for ref in r['data']['cameras']+([r['data']['lighting']] if r['data']['lighting'] else []):
                setup_refs[ref['id'],ref['version']]=ref
        elif r['kind'] in ('camera_setup','lighting_setup'):
            setup_refs[r['id'],r['version']]=ref_for(r)
    for ref in setup_refs.values():
        p=graph.require(ref)
        if p['kind']=='camera_setup':
            for field in ('camera_asset','lens_asset'):
                if p[field]:
                    add_item(p[field],1,ref,field)
        else:
            for f in p['fixtures']:
                add_item(f['asset'],1,ref,f['role'])
                for r in f['modifiers']:
                    add_item(r,1,ref,'modifier')
                for r in f['supports']:
                    add_item(r,1,ref,'support')
    for row in equipment.values():
        per_setup=defaultdict(int)
        for use in row['uses']:
            per_setup[(use['setup']['id'],use['setup']['version'])]+=use['quantity']
        row['max_in_one_setup']=max(per_setup.values(),default=0)
        row['total_planned_uses']=sum(per_setup.values())
    return {'items':sorted(equipment.values(),key=lambda x:(x['category'],x['title'],x['asset']['id'])),
            'limitations':['Quantities are per setup, not a booking schedule or inventory availability guarantee.',
                           'Listed wattage is a fixture specification, not circuit sizing or electrical-safety advice.']}


class Reporter:
    def __init__(self,service,conn,include_proposals=False):
        self.service,self.conn=service,conn
        self.prod=ProductionService(service)
        self.graph=self.prod._graph(conn)
        self.records=[self.graph.resolve(h['id'],h['selected_version'] or h['head_version'])
                      for h in self.graph.heads.values() if not h['archived'] and (include_proposals or h['selected_version'])]
        self.records.sort(key=lambda r:(r['kind'],r['id']))
        self.issues=[]
        self.invalid=set()
        self.sample_cache={}
        self.checks_remaining=50000
        self.partial_checks=set()
        self.exceptions=[r for r in self.records if r['kind']=='exception']

    def issue(self,r,code,message,category='completeness',severity='warning',field='',details=None):
        p=r['data'] if r else {}
        finding={'code':code,'message':message,'category':category,'severity':severity,
                 'record_id':r['id'] if r else None,'version':r['version'] if r else None,
                 'title':p.get('title','Production'),'field':field,'details':details or {},
                 'responsibility':p.get('responsibility',''),'next_action':p.get('next_action',''),
                 'status':'open'}
        if r and category=='continuity':
            for exception in self.exceptions:
                e=exception['data']
                if e['subject']==ref_for(r) and e['check_code']==code and not any(s['needs_attention'] for s in self.graph.stale(ref_for(exception))):
                    finding.update({'status':'accepted_exception','severity':'info',
                                    'exception':ref_for(exception),'reason':e['reason'],'reviewer':e['reviewer']})
                    break
        self.issues.append(finding)

    def media(self,record,hashes=False):
        for ref in media_refs(record['data']):
            path,expected=ref['path'],ref['sha256']
            if ref['media_id']:
                row=self.conn.execute('SELECT path,sha256 FROM media WHERE id=?',(ref['media_id'],)).fetchone()
                if not row:
                    self.issue(record,'missing_media','Managed media reference is missing.',field='media',details=ref)
                    continue
                if path and path!=row['path'] or expected and expected!=row['sha256']:
                    self.issue(record,'media_identity_conflict','Media ID, path and content hash disagree.','structural','error',details=ref)
                    continue
                path,expected=row['path'],row['sha256']
            try:
                file=safe_path(self.service.root,path,must_exist=True)
                if not file.is_file():
                    raise OSError('Not a file')
                if hashes and sha256(file)!=expected:
                    self.issue(record,'media_hash_mismatch','Referenced media content changed.','structural','error',details=ref)
            except Exception as exc:
                self.issue(record,'missing_media','Referenced media file is missing or unsafe.',details={**ref,'error_type':type(exc).__name__})

    def run(self,hashes=False):
        graph=self.graph
        if not any(r['kind']=='production' for r in self.records):
            self.issue(None,'missing_production_defaults','Select a production record with explicit format and frame defaults.')
        if sum(r['kind']=='production' for r in self.records)>1:
            self.issue(None,'multiple_production_defaults','Multiple selected production defaults are ambiguous.','structural','error')
        for r in self.records:
            p,kind=r['data'],r['kind']
            try:
                if parse_record(p)!=p or digest(p)!=r['sha256']:
                    raise ProductionError('Stored canonical payload or hash differs.')
                graph.validate(r)
            except Exception as exc:
                self.issue(r,'invalid_graph',str(exc),'structural','error')
                self.invalid.add(r['id'])
                continue
            for stale in graph.stale(ref_for(r)):
                self.issue(r,'stale_dependency' if stale['needs_attention'] else 'pin_drift_unaffected',
                           'A selected dependency changed; inspect the affected plan.' if stale['needs_attention'] else 'Source revision advanced, but this covered wording and heading are unchanged.',
                           'review','warning' if stale['needs_attention'] else 'info',details=stale)
            prov=p['provenance']
            if prov['legacy_entity_id']:
                entity=self.conn.execute('SELECT revision,archived FROM entities WHERE id=?',(prov['legacy_entity_id'],)).fetchone()
                if entity is None or entity['archived'] or entity['revision']!=prov['legacy_entity_revision']:
                    self.issue(r,'legacy_source_changed','The original story-editor record changed after explicit adoption; compare before re-adopting.','provenance')
            if prov['origin']=='agent' and (not prov['author'].strip() or not prov['rationale'].strip()):
                self.issue(r,'agent_provenance_incomplete','Agent work needs an author and an explanation of the proposed choice.','provenance')
            for question in prov['questions']:
                self.issue(r,'unresolved_question',question,'review')
            self.media(r,hashes)
            if p['planning']!='planned':
                self.issue(r,'explicit_planning_exception',p['planning_reason'],'completeness','info')
                continue
            def missing(field,code,message):
                if not p.get(field):
                    scope=p.get('applicability',{}).get(field)
                    if scope and scope['state']!='required':
                        self.issue(r,'explicit_'+field,scope['reason'],'completeness','info',field)
                    else:
                        self.issue(r,code,message,field=field)
            if kind=='scene':
                missing('location','scene_without_location','Assign an exact filming-location revision.')
                if not p['fragments'] and not p['unscripted_objectives']:
                    self.issue(r,'scene_without_context','Link script material or author unscripted objectives.')
                missing('purpose','scene_without_purpose','Describe the scene’s narrative or production purpose.')
                if not any(s['kind']=='shot' and s['data']['scene']==ref_for(r) for s in self.records):
                    self.issue(r,'scene_without_shots','No selected shots reference this exact scene revision.')
            elif kind=='location':
                missing('geometry','location_without_geometry','Add measured or explicitly estimated proxy geometry.')
                if p['dimension_quality']=='unknown':
                    self.issue(r,'unknown_location_scale','Location dimensions have not been measured or estimated.')
                if any(g['quality']=='unknown' for g in p['geometry']):
                    self.issue(r,'unknown_geometry_dimensions','Some geometry dimensions have unknown accuracy.')
            elif kind=='shot':
                missing('cameras','shot_without_camera','Assign at least one exact camera setup.')
                missing('action','shot_without_blocking','Link the shared scene action and photographed interval.')
                missing('lighting','shot_without_lighting','Assign a lighting setup or explicitly mark lighting not applicable.')
                missing('purpose','shot_without_purpose','Explain why this shot exists.')
                if p['action'] and not p['beat_ids']:
                    self.issue(r,'shot_without_beats','Assign the action beats this shot covers.')
                if p['action']:
                    action=graph.require(p['action'])
                    if p['handles_before']>p['interval']['start'] or p['interval']['end']+p['handles_after']>action['duration_frames']:
                        self.issue(r,'handles_outside_action','Planned handles extend outside authored action. Handles use action frames.')
                    dur=shot_duration_frames(p,action)
                    if abs(dur-round(dur))>1e-8:
                        self.issue(r,'fractional_shot_duration','Rate conversion produces fractional shot frames; choose an explicit editorial rounding policy.')
                self.shot_checks(r)
            elif kind=='action':
                missing('instances','blocking_without_instances','Place actor/prop instances in the shared action.')
                missing('beats','action_without_beats','Define beats and their continuity anchors.')
                self.path_checks(r)
            elif kind=='camera_setup':
                missing('camera_asset','camera_without_equipment','Choose a camera library definition, or record why a generic gate is being used.')
            elif kind=='lighting_setup':
                missing('fixtures','lighting_without_fixtures','Place fixtures or mark this lighting plan not applicable.')
            elif kind=='panel':
                if not p['artwork'] and not p['drawing']:
                    self.issue(r,'panel_without_artwork','Draw a panel, attach artwork or use a camera preview in the review packet.')
                if p['action_frame'] is None:
                    self.issue(r,'panel_without_moment','Pin this panel to an exact moment in the shared action.')
            elif kind=='edit':
                self.edit_checks(r)
            elif kind=='script':
                for issue in p['import_issues']:
                    if not issue['code'].startswith(('scene_identity_','passage_identity_')):
                        self.issue(r,'script_import_review',issue['message'],'review',details=issue)
        valid_records=[r for r in self.records if r['id'] not in self.invalid]
        try:
            coverage=coverage_report(graph,valid_records)
        except Exception as exc:
            self.issue(None,'coverage_unavailable',str(exc),'structural','error')
            coverage={'material':[],'beats':[],'summary':{},'complete':False}
        for row in coverage['material']:
            if row['status'] in ('uncovered','deferred'):
                r=graph.resolve(row['script']['id'],row['script']['version'])
                self.issue(r,'uncovered_script_passage' if row['status']=='uncovered' else 'deferred_script_passage',
                           'Script passage has no selected covering shot.' if row['status']=='uncovered' else 'Script passage was explicitly deferred.',
                           details={k:row[k] for k in ('script_scene_id','block_id','type','shot_ids')})
        for row in coverage['beats']:
            if row['gaps']:
                self.issue(graph.resolve(row['action']['id'],row['action']['version']),'coverage_gap',
                           'This beat has uncovered action frames.',details=row)
            if row['overlap_frames']:
                self.issue(graph.resolve(row['action']['id'],row['action']['version']),'overlapping_coverage',
                           'Multiple shots cover some of the same action. This may be intentional.','continuity','info',details=row)
        reviews=[r for r in self.records if r['kind']=='review']
        creative=[]
        for r in self.records:
            if r['kind']!='shot':
                continue
            matches=sorted([x for x in reviews if x['data']['subject']==ref_for(r) and x['data']['dimension']=='creative'],
                           key=lambda x:(x['version_created_at'],x['id']))
            latest=matches[-1] if matches else None
            current=latest and not any(s['needs_attention'] for s in graph.stale(ref_for(latest)))
            decision=latest['data']['decision'] if current else 'not_reviewed' if latest is None else 'stale_review'
            creative.append({'shot':ref_for(r),'title':r['data']['title'],'decision':decision,
                             'review':ref_for(latest) if latest else None})
        open_issues=[i for i in self.issues if i['status']=='open' and i['severity']!='info']
        structural=[i for i in open_issues if i['category']=='structural']
        completeness=[i for i in open_issues if i['category']=='completeness']
        return {'format':'storyboarder.production-report/v1','checkpoint':self.prod._clock(self.conn),
                'source_versions':[{'id':r['id'],'version':r['version'],'sha256':r['sha256']} for r in self.records],
                'structural':{'valid':not structural,'errors':len(structural)},
                'planning':{'complete':not completeness,'gaps':len(completeness)},
                'creative':{'accepted':bool(creative) and all(x['decision'] in ('accepted','not_applicable') for x in creative),'shots':creative},
                'summary':{'selected_records':len(self.records),'scenes':sum(r['kind']=='scene' for r in self.records),
                           'shots':sum(r['kind']=='shot' for r in self.records),'open_issues':len(open_issues),
                           'stale_records':len({i['record_id'] for i in open_issues if i['code']=='stale_dependency'}),
                           'proposals':sum(not h['archived'] and (h['selected_version'] is None or h['selected_version']!=h['head_version']) for h in graph.heads.values())},
                'issues':self.issues,'coverage':coverage,'equipment':equipment_report(graph,[r for r in self.records if r['id'] not in self.invalid]) if not self.invalid else {'items':[],'limitations':['Repair structural errors before equipment aggregation.']},
                'continuity_sampling':{'complete':not self.partial_checks,'partial_record_ids':sorted(self.partial_checks),'samples':len(self.sample_cache),'max_samples':256,'remaining_proxy_checks':self.checks_remaining},
                'read_only':True,'limitations':['Structural validity, planning completeness and creative acceptance are independent.',
                                               'Continuity checks are advisory; exceptions require a revision-pinned reason.']}

    def sample(self,r,frame):
        key=(r['id'],r['version'],frame)
        if key in self.sample_cache:
            return self.sample_cache[key]
        if len(self.sample_cache)>=256:
            if r['id'] not in self.partial_checks:
                self.issue(r,'continuity_partial','Continuity sampling reached its 256-sample project budget; inspect this scene separately.','review')
            self.partial_checks.add(r['id'])
            return None
        result=evaluate_graph(self.graph,r['id'],r['version'],frame)
        self.sample_cache[key]=result
        return result

    def path_checks(self,r):
        p=r['data']; location=self.graph.require(p['location'])
        boxes=[g for g in location['geometry'] if g['solid'] and g['type'] not in ('floor','room')]
        if not boxes:
            return
        times=sorted({0,p['duration_frames']}|{k['frame'] for i in p['instances'] for k in i['keyframes']}|{e['frame'] for e in p['prop_events']})
        previous=None; found=set()
        for frame in times:
            sample=self.sample(r,frame)
            if sample is None:
                return
            current={i['id']:i for i in sample['instances']}
            if previous is not None:
                for iid,b in current.items():
                    if iid in found:
                        continue
                    a=previous[iid]
                    if not a['present'] and not b['present']:
                        continue
                    size=b['dimensions'];pa,pb=vec(a['pose']['position']),vec(b['pose']['position'])
                    if b['category'] in ('character','performer'):
                        pa=add(pa,[0,0,size['z']/2]);pb=add(pb,[0,0,size['z']/2])
                    margin=max(size['x'],size['y'])/2
                    for box in boxes:
                        self.checks_remaining-=1
                        if self.checks_remaining<0:
                            self.issue(r,'continuity_partial','Proxy intersection budget reached; unsampled paths require inspection.','review')
                            self.partial_checks.add(r['id']);return
                        if segment_box(pa,pb,box,margin):
                            self.issue(r,'path_obstacle','A swept proxy path may intersect a solid obstacle.','continuity',details={'instance_id':iid,'obstacle_id':box['id'],'obstacle':box['label'],'model':'conservative endpoint segments; hold jumps and rotating attachments require human inspection'})
                            found.add(iid);break
            previous=current

    def shot_checks(self,r):
        p=r['data']
        if not p['action'] or not p['interval']:
            return
        frame=(p['interval']['start']+p['interval']['end'])/2
        sample=self.sample(r,frame)
        if sample is None:
            return
        for warning in sample['warnings']:
            self.issue(r,warning['code'],warning['message'],'continuity')
        all_equipment=[{'id':c['id'],'label':c['title'],'position':c['pose']['position']} for c in sample['cameras']]
        all_equipment += [{'id':f['id'],'label':f['label'],'position':f['pose']['position']} for f in sample['fixtures']]
        for camera in sample['cameras']:
            for equipment in all_equipment:
                if equipment['id']==camera['id']:
                    continue
                point=project_point(camera,equipment['position'])
                if point and point['inside']:
                    self.issue(r,'equipment_in_view','Equipment falls inside another camera’s geometric view; occlusion is not resolved.','continuity',
                               details={'camera_id':camera['id'],'equipment_id':equipment['id'],'label':equipment['label'],'frame':frame})
        boxes=[b for b in sample['location']['geometry'] if b['solid'] and b['type'] not in ('floor','room')]
        for light in sample['fixtures']:
            if not light['enabled']:
                continue
            for actor in sample['instances']:
                if actor['category'] not in ('character','performer') or not actor['present']:
                    continue
                target=add(vec(actor['pose']['position']),[0,0,actor['dimensions']['z']*.8])
                hit=next((b for b in boxes if segment_box(vec(light['pose']['position']),target,b)),None)
                if hit:
                    self.issue(r,'light_obstruction','A solid proxy intersects a fixture-to-subject ray; this is not a photometric result.','continuity',
                               details={'fixture_id':light['id'],'instance_id':actor['id'],'obstacle_id':hit['id']})
        beat_by={b['id']:b for b in self.graph.require(p['action'])['beats']}
        for bid in p['beat_ids']:
            b=beat_by[bid]
            if max(p['interval']['start'],b['interval']['start'])>=min(p['interval']['end'],b['interval']['end']):
                self.issue(r,'beat_outside_shot','Shot names a beat outside its photographed action interval.','completeness',details={'beat_id':bid})

    def edit_checks(self,r):
        entries=r['data']['entries']
        for left,right in zip(entries,entries[1:]):
            a,b=self.graph.require(left['shot']),self.graph.require(right['shot'])
            if not a['action'] or not b['action']:
                continue
            aa,ba=self.graph.require(a['action']),self.graph.require(b['action'])
            at=action_frame_for_shot(a,aa,max(left['shot_interval']['start'],left['shot_interval']['end']-1e-7))
            bt=action_frame_for_shot(b,ba,right['shot_interval']['start'])
            if aa['location']!=ba['location']:
                if aa['location']['id']==ba['location']['id']:
                    self.issue(r,'cut_location_revision','Adjacent cut uses different revisions of the same set.','continuity')
                continue
            sa=self.sample(self.graph.resolve(left['shot']['id'],left['shot']['version']),at)
            sb=self.sample(self.graph.resolve(right['shot']['id'],right['shot']['version']),bt)
            if sa is None or sb is None:
                self.partial_checks.add(r['id']);return
            if left['match_action_anchor'] and left['match_action_anchor']==right['match_action_anchor'] and (a['action']!=b['action'] or abs(float(seconds(Fraction(str(at)),aa['frame_rate']))-float(seconds(Fraction(str(bt)),ba['frame_rate'])))>1/float(aa['frame_rate']['numerator']/aa['frame_rate']['denominator'])):
                self.issue(r,'match_action_timing','Cuts naming the same match-action anchor have different action times or versions.','continuity',details={'left_action_frame':at,'right_action_frame':bt,'left_shot':left['shot'],'right_shot':right['shot']})
            # Compare stable asset identity only when it is unique on each side.
            ma,mb=defaultdict(list),defaultdict(list)
            for item in sa['instances']:
                ma[item['asset']['id']].append(item)
            for item in sb['instances']:
                mb[item['asset']['id']].append(item)
            for aid in ma.keys() & mb.keys():
                if len(ma[aid])!=1 or len(mb[aid])!=1:
                    continue
                ia,ib=ma[aid][0],mb[aid][0]
                delta=norm(sub(vec(ia['pose']['position']),vec(ib['pose']['position'])))
                if delta>.1 or ia['present']!=ib['present']:
                    self.issue(r,'cut_position','Actor/prop position or presence differs across this cut.','continuity',details={'asset_id':aid,'distance_m':delta,'left_shot':left['shot'],'right_shot':right['shot']})
                if ia['state']!=ib['state']:
                    self.issue(r,'cut_prop_state','An object’s authored state differs across this cut.','continuity',details={'asset_id':aid,'before':ia['state'],'after':ib['state']})
                diff=abs((ia['pose']['yaw_deg']-ib['pose']['yaw_deg']+180)%360-180)
                if diff>20:
                    self.issue(r,'cut_facing','Actor/prop facing differs by more than the 20° advisory threshold.','continuity',details={'asset_id':aid,'degrees':diff})
                if ia['eyeline_target'] and ib['eyeline_target'] and norm(sub(vec(ia['eyeline_target']),vec(ib['eyeline_target'])))>.15:
                    self.issue(r,'cut_eyeline','Authored eyeline targets differ across this cut.','continuity',details={'asset_id':aid})
            if a['screen_direction'] not in ('neutral','unknown') and b['screen_direction'] not in ('neutral','unknown') and a['screen_direction']!=b['screen_direction']:
                self.issue(r,'screen_direction','Adjacent shots declare opposing screen directions.','continuity',details={'left_shot':left['shot'],'right_shot':right['shot']})
            if a['axis_start'] and a['axis_end'] and sa['cameras'] and sb['cameras']:
                origin,axis=vec(a['axis_start']),sub(vec(a['axis_end']),vec(a['axis_start']))
                def side(camera):
                    v=sub(vec(camera['pose']['position']),origin)
                    return axis[0]*v[1]-axis[1]*v[0]
                if side(sa['cameras'][0])*side(sb['cameras'][0])<0:
                    self.issue(r,'axis_crossing','Adjacent primary cameras are on opposing sides of the declared action axis.','continuity',details={'left_shot':left['shot'],'right_shot':right['shot']})
            scene_a,scene_b=self.graph.require(a['scene']),self.graph.require(b['scene'])
            states_a={x['asset']['id']:x['state'] for x in scene_a['requirements']+scene_a['dressing']}
            states_b={x['asset']['id']:x['state'] for x in scene_b['requirements']+scene_b['dressing']}
            for aid in states_a.keys() & states_b.keys():
                if states_a[aid]!=states_b[aid]:
                    self.issue(r,'cut_wardrobe_dressing','Wardrobe/dressing requirement state changes across the cut.','continuity',details={'asset_id':aid})


def report(service, include_proposals=False, hashes=False):
    if type(include_proposals) is not bool or type(hashes) is not bool:
        raise ProductionError('Report flags must be booleans.')
    with service.repo.transaction(False) as conn:
        return Reporter(service,conn,include_proposals).run(hashes)


def integrity_issues(service,conn,hashes=False):
    """Doctor validates history hashes and normalized edges without treating missing planning as corruption."""
    issues=[]
    prod=ProductionService(service)
    try:
        heads=prod._heads(conn)
        graph=prod._graph(conn,{rid:{**h,'archived':False} for rid,h in heads.items()})
        for h in heads.values():
            versions=list(conn.execute('SELECT number,parent_number FROM production_versions WHERE record_id=? ORDER BY number',(h['id'],)))
            if not versions or [v['number'] for v in versions]!=list(range(1,h['head_version']+1)):
                raise ProductionError('Production version sequence is incomplete.',{'id':h['id']})
            if h['selected_version'] is not None and h['selected_version'] not in {v['number'] for v in versions}:
                raise ProductionError('Selected production version is missing.')
            for v in versions:
                r=graph.resolve(h['id'],v['number'])
                if parse_record(r['data'])!=r['data'] or digest(r['data'])!=r['sha256']:
                    raise ProductionError('Production version content/hash mismatch.',{'id':h['id'],'version':v['number']})
                if v['parent_number'] is not None and v['parent_number']>=v['number']:
                    raise ProductionError('Production version parent is not an earlier version.')
                graph.validate(r)
                verify_external(conn,r)
                expected={(path,ref['id'],ref['version']) for path,ref in references(r['data'])}
                actual={tuple(x) for x in conn.execute('SELECT path,target_id,target_version FROM production_refs WHERE source_id=? AND source_version=?',(h['id'],v['number']))}
                if expected!=actual:
                    raise ProductionError('Production edge index disagrees with immutable payload.')
                for _,ref in references(r['data']):
                    graph.require(ref)
        if hashes:
            checker=Reporter(service,conn,True)
            for h in heads.values():
                for v in conn.execute('SELECT number FROM production_versions WHERE record_id=?',(h['id'],)):
                    checker.media(graph.resolve(h['id'],v['number']),True)
            issues.extend({**i,'severity':'error'} for i in checker.issues)
    except Exception as exc:
        issues.append({'severity':'error','code':'production_integrity','message':str(exc),
                       'details':getattr(exc,'details',{})})
    return issues
