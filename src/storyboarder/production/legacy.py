"""Explicit legacy adoption, never hidden two-way synchronisation.

Existing outline/source/spatial workflows continue unchanged. The preview copies
active legacy records with their stable identities and revision provenance. Unknown
scale, free-text camera directions and absent blocking stay visibly incomplete.
"""
import json

from storyboarder.domain.models import dumps
from storyboarder.domain.errors import Conflict
from .models import ProductionError, parse_record
from .service import ProductionService


def adopt_preview(service,expected_checkpoint,operation_id,select=False):
    prod=ProductionService(service)
    with service.repo.transaction(False) as conn:
        if prod._clock(conn)!=expected_checkpoint:
            raise Conflict('Production checkpoint changed before adoption.')
        if conn.execute('SELECT 1 FROM production_records LIMIT 1').fetchone():
            raise Conflict('Initial adoption requires an empty production graph. Existing production work is not overwritten or resynchronised.')
        rows=[]
        for row in conn.execute('SELECT * FROM entities WHERE archived=0 ORDER BY kind,position,id'):
            r=dict(row);r['fields']=json.loads(r['fields']);rows.append(r)
        assets={r['id']:r for r in rows if r['kind']=='asset'}
        ids={r['id'] for r in rows}
        operations=[];report=[]
        def put(id,data):
            operations.append({'op':'put','id':id,'expected_revision':0,'select':select,'data':parse_record(data)})
        def ref(id):
            return {'id':id,'version':1} if id in ids else None
        for r in rows:
            f=r['fields'];kind=r['kind']
            # Retain every authoring field in plain notes as an exact JSON snapshot;
            # interpretations below never pretend camera prose is calibrated optics.
            retained=dumps({'description':r['description'],'fields':f})
            if len(retained)>19900:
                raise ProductionError('Legacy authored text exceeds the connected record note limit. Export it and split the record before adoption; it was not truncated.',{'id':r['id']})
            data={'title':r['title'],'notes':'Legacy source snapshot:\n'+retained,
                  'orders':{'narrative':r['position'] if kind in ('sequence','scene','shot') else None},
                  'provenance':{'origin':'legacy','legacy_entity_id':r['id'],'legacy_entity_revision':r['revision'],
                                'rationale':'Explicit adoption of legacy authored data. No inferred camera, lens, scale or blocking.',
                                'assumptions':['Legacy fields are retained in notes; outline and production edits are not silently synchronised.']}}
            if kind=='project':
                data.update(kind='production',production_type='other')
            elif kind=='asset':
                if f['type']=='location':
                    data.update(kind='location',dimension_quality='unknown')
                else:
                    data.update(kind='asset',category=f['type'],dimension_quality='unknown')
                media=[{'media_id':m['media_id']} for m in conn.execute('SELECT media_id FROM asset_media WHERE asset_id=? ORDER BY is_primary DESC,id',(r['id'],))]
                data['references']=media
            elif kind=='sequence':
                data.update(kind='sequence',objective=f.get('arc',''))
            elif kind=='scene':
                location=f.get('location_id')
                data.update(kind='scene',sequence=ref(r['parent_id']),location=ref(location),
                            story_location=assets[location]['title'] if location in assets else '',
                            story_time=f.get('time',''),purpose=f.get('summary',''),unscripted_objectives=[f['summary']] if f.get('summary') else [])
            elif kind=='shot':
                data.update(kind='shot',scene=ref(r['parent_id']),label=f.get('number',''),purpose=f.get('action',''),framing=f.get('framing',''))
                if f.get('duration') is not None:
                    report.append({'id':r['id'],'code':'duration_unmapped','message':'Legacy duration is retained in notes. A shared-action interval must be authored before timing can be mapped.'})
                requirements=[]
                for a in conn.execute('SELECT * FROM assignments WHERE shot_id=? ORDER BY id',(r['id'],)):
                    if a['asset_id'] not in assets or assets[a['asset_id']]['fields']['type']=='location':
                        continue
                    requirements.append({'asset':ref(a['asset_id']),'quantity':1,'role':'Legacy assignment: '+a['role']})
                data['requirements']=requirements
            else:
                continue
            if f.get('constraints'):
                data['constraints']=[f['constraints']]
            put(r['id'],data)
        for frame in conn.execute("SELECT * FROM frames WHERE state!='archived' ORDER BY shot_id,version,id"):
            if frame['shot_id'] not in ids:
                continue
            put(frame['id'],{'kind':'panel','title':'Legacy storyboard frame','shot':ref(frame['shot_id']),
                              'artwork':{'media_id':frame['media_id']},'annotation':frame['notes'],
                              'provenance':{'origin':'legacy','rationale':'Explicitly adopted storyboard artwork; original frame approval is not transferred as creative acceptance of the new plan.'}})
        if len(operations)>500:
            raise ProductionError('Initial adoption supports up to 500 active records per batch. Use structured batches for larger projects; nothing was truncated.')
    batch={'expected_checkpoint':expected_checkpoint,'operation_id':operation_id,'operations':operations}
    return {'batch':batch,'preview':prod.preview(batch),'adoption_report':report,
            'limitations':['No automatic synchronization with legacy outline edits.',
                           'Screenplay sources and spatial plans retain their original versioned workflows; use script import or the legacy spatial workspace explicitly.',
                           'Missing camera, lighting, action, scale and source mappings remain readiness gaps.'], 'persisted':False}
