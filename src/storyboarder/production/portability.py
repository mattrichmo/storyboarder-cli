"""Canonical graph packages, preserving immutable histories rather than flattening them.

Graph packages intentionally do not masquerade as media backups. Script originals are
inline; managed/portable media are listed and verified by doctor. Use project backup
for a self-contained database + media archive. Restore into an empty production graph
only: merging independent histories requires explicit reconciliation, not overwrite.
"""
from __future__ import annotations

import json
import re
from uuid import UUID

from storyboarder.domain.errors import Conflict
from storyboarder.domain.models import dumps, now
from .graph import Graph
from .models import MAX_RECORDS, ProductionError, digest, parse_record, references
from .reports import media_refs
from .service import ProductionService, size_check
from .external import validate_external, insert_external

PACKAGE = 'storyboarder.production-package/v1'
MAX_VERSIONS = 25000
HEADER_KEYS = {'id','kind','revision','head_version','selected_version','archived','created_at','updated_at'}
VERSION_KEYS = {'record_id','number','parent_number','data','sha256','created_at'}


def export_package(service):
    prod = ProductionService(service)
    with prod.repo.transaction(False) as conn:
        heads = sorted(prod._heads(conn).values(), key=lambda h: h['id'])
        versions = []
        for r in conn.execute('SELECT * FROM production_versions ORDER BY record_id,number'):
            versions.append({'record_id':r['record_id'],'number':r['number'],'parent_number':r['parent_number'],
                             'data':json.loads(r['payload_json']),'sha256':r['sha256'],'created_at':r['created_at']})
        graph = {'headers':heads,'versions':versions}
        result = {'format':PACKAGE,'graph':graph,'graph_sha256':digest(graph),
                  'source':{'project_id':service.project.id,'checkpoint':prod._clock(conn)},
                  'media_policy':'references-only; use project backup for original media',
                  'media_manifest':list({dumps(m):m for v in versions for m in media_refs(v['data'])}.values())}
        size_check(result)
        return result


def validate_package(package):
    size_check(package)
    if not isinstance(package,dict) or set(package)!={'format','graph','graph_sha256','source','media_policy','media_manifest'} or package['format']!=PACKAGE:
        raise ProductionError('Choose a complete production-package/v1 JSON package.')
    graph = package['graph']
    if not isinstance(graph,dict) or set(graph)!={'headers','versions'} or not isinstance(graph['headers'],list) or not isinstance(graph['versions'],list):
        raise ProductionError('Package needs headers and immutable versions.')
    if not graph['headers'] or len(graph['headers'])>MAX_RECORDS or len(graph['versions'])>MAX_VERSIONS:
        raise ProductionError('Package must contain 1–5,000 records and at most 25,000 versions.')
    if package['graph_sha256']!=digest(graph):
        raise ProductionError('Package content hash does not match. Nothing was imported.')
    if not isinstance(package['source'],dict) or set(package['source'])!={'project_id','checkpoint'} or type(package['source']['checkpoint']) is not int or package['source']['checkpoint']<0:
        raise ProductionError('Invalid package source checkpoint.')
    try:
        if str(UUID(package['source']['project_id']))!=package['source']['project_id']:
            raise ValueError()
    except (ValueError,TypeError,AttributeError) as exc:
        raise ProductionError('Invalid package source project ID.') from exc
    if package['media_policy']!='references-only; use project backup for original media' or not isinstance(package['media_manifest'],list):
        raise ProductionError('Unsupported media transfer policy.')
    heads, versions = {}, {}
    for h in graph['headers']:
        if not isinstance(h,dict) or set(h)!=HEADER_KEYS:
            raise ProductionError('Invalid production record header.')
        try:
            if str(UUID(h['id']))!=h['id'] or h['id'] in heads:
                raise ValueError()
            for key in ('revision','head_version'):
                if type(h[key]) is not int or h[key]<1:
                    raise ValueError()
            if h['selected_version'] is not None and (type(h['selected_version']) is not int or not 1<=h['selected_version']<=h['head_version']):
                raise ValueError()
            if type(h['archived']) is not bool or h['revision']<h['head_version']:
                raise ValueError()
            for key in ('created_at','updated_at'):
                if not isinstance(h[key],str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T.{1,60}',h[key]):
                    raise ValueError()
        except (TypeError,ValueError,AttributeError) as exc:
            raise ProductionError('Invalid header IDs, revision, selection or timestamps.') from exc
        heads[h['id']]=h
    counts={rid:0 for rid in heads}
    for v in graph['versions']:
        if not isinstance(v,dict) or set(v)!=VERSION_KEYS or v['record_id'] not in heads:
            raise ProductionError('Invalid immutable version envelope.')
        h=heads[v['record_id']]
        n=v['number']
        if type(n) is not int or n<1 or n>h['head_version'] or (v['record_id'],n) in versions:
            raise ProductionError('Duplicate or invalid immutable version number.')
        if (n==1 and v['parent_number'] is not None) or (n>1 and (type(v['parent_number']) is not int or not 1<=v['parent_number']<n)):
            raise ProductionError('Invalid version ancestry.')
        data=parse_record(v['data'])
        if data!=v['data'] or data['kind']!=h['kind'] or v['sha256']!=digest(data):
            raise ProductionError('Immutable version content is noncanonical or its hash differs.')
        if not isinstance(v['created_at'],str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T.{1,60}',v['created_at']):
            raise ProductionError('Invalid version timestamp.')
        counts[h['id']]+=1
        versions[h['id'],n]={**h,'version':n,'data':data,'sha256':v['sha256'],
                              'version_created_at':v['created_at'],'parent_version':v['parent_number']}
    if any(counts[rid]!=h['head_version'] for rid,h in heads.items()):
        raise ProductionError('Missing immutable history: versions must be contiguous from 1 through head.')
    def resolve(rid,number):
        try:
            return versions[rid,number]
        except (KeyError,TypeError) as exc:
            raise ProductionError('Package has an unresolved exact reference.',{'id':rid,'version':number}) from exc
    # Historical references to archived records remain inspectable; no history is discarded.
    validator=Graph({rid:{**h,'archived':False} for rid,h in heads.items()},resolve)
    for r in versions.values():
        validator.validate(r)
    # Exact-version graphs are DAGs. An old version can be a dependency of a new one.
    state={}
    for node in versions:
        stack=[(node,False)]
        while stack:
            key,done=stack.pop()
            if done:
                state[key]=2
                continue
            if state.get(key)==1:
                raise ProductionError('Package exact-version dependencies contain a cycle.')
            if state.get(key)==2:
                continue
            state[key]=1
            stack.append((key,True))
            stack.extend(((r['id'],r['version']),False) for _,r in references(versions[key]['data']))
    canonical_media=list({dumps(m):m for v in graph['versions'] for m in media_refs(v['data'])}.values())
    if package['media_manifest']!=canonical_media:
        raise ProductionError('Media manifest differs from the immutable record references.')
    return heads,versions


def import_package(service, package, operation_id, expected_checkpoint, apply=False):
    heads,versions=validate_package(package)
    try:
        if str(UUID(operation_id))!=operation_id:
            raise ValueError()
    except (ValueError,TypeError,AttributeError) as exc:
        raise ProductionError('Operation ID must be a canonical UUID.') from exc
    if type(expected_checkpoint) is not int or expected_checkpoint<0 or type(apply) is not bool:
        raise ProductionError('Expected checkpoint and apply flag must be explicit, typed values.')
    prod=ProductionService(service)
    request_sha=digest({'command':'production.import','package':package,'expected_checkpoint':expected_checkpoint})
    with prod.repo.transaction(apply) as conn:
        receipt=conn.execute('SELECT * FROM production_operations WHERE id=?',(operation_id,)).fetchone()
        if receipt:
            if receipt['request_sha256']!=request_sha:
                raise Conflict('This operation ID was already used for different content.')
            return {**json.loads(receipt['result_json']),'replayed':True}
        if prod._clock(conn)!=expected_checkpoint:
            raise Conflict('Production checkpoint changed. The package was not imported.')
        if conn.execute('SELECT 1 FROM production_records LIMIT 1').fetchone():
            raise Conflict('Import preserves complete histories and requires an empty production graph. Use a new project or explicit revision reconciliation; existing work is never overwritten.')
        for record in versions.values():
            validate_external(conn, record)
        result={'checkpoint':expected_checkpoint+1,'record_count':len(heads),'version_count':len(versions),
                'graph_sha256':package['graph_sha256'],'source':package['source'],
                'media_references':len(package['media_manifest']),
                'media_policy':package['media_policy'],'persisted':apply}
        if not apply:
            return {**result,'checkpoint':expected_checkpoint,'proposed_checkpoint':expected_checkpoint+1,'valid':True}
        for h in heads.values():
            conn.execute('''INSERT INTO production_records(id,kind,revision,head_version,selected_version,archived,created_at,updated_at)
                            VALUES(:id,:kind,:revision,:head_version,:selected_version,:archived,:created_at,:updated_at)''',h)
        for (rid,n),v in versions.items():
            conn.execute('INSERT INTO production_versions VALUES(?,?,?,?,?,?)',(rid,n,v['parent_version'],dumps(v['data']),v['sha256'],v['version_created_at']))
            insert_external(conn, v)
            for path,ref in references(v['data']):
                conn.execute('INSERT INTO production_refs VALUES(?,?,?,?,?)',(rid,n,path,ref['id'],ref['version']))
        for h in heads.values():
            conn.execute('INSERT INTO production_changes VALUES(?,?,?,?,?)',(result['checkpoint'],h['id'],'import',None,h['selected_version']))
        conn.execute('UPDATE production_clock SET checkpoint=?',(result['checkpoint'],))
        conn.execute('INSERT INTO production_operations VALUES(?,?,?,?,?)',(operation_id,request_sha,result['checkpoint'],dumps(result),now()))
        prod.repo.event(conn,'production.import',service.project.id,{'graph_sha256':package['graph_sha256'],'source':package['source']})
        return {**result,'replayed':False}
