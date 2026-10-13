"""Bounded imports with preserved original bytes and conservative scene identity.

Fountain is a documented core profile, not a promise of full screenplay layout.
Uninterpreted constructs are reported and retained, never discarded invisibly.
"""
from __future__ import annotations

import base64
from collections import Counter, defaultdict
import copy
import hashlib
import json
import re
import uuid

from .models import ProductionError, SourceFile, ScriptScene, decode, parse_record

HEADING = re.compile(r'^(?:INT\.?/EXT|EXT\.?/INT|INT|EXT|EST|I/E)(?:\.|\s)', re.I)
NUMBER = re.compile(r'\s+#([^#]+)#\s*$')


def identity(namespace, name):
    return str(uuid.uuid5(uuid.UUID(namespace), name))


def parse_fountain(text, script_id):
    lines = text.splitlines(keepends=True)
    scenes, issues = [], []
    offset, scene, character, index = 0, None, '', 0
    source_hash = hashlib.sha256(text.encode()).hexdigest()
    offsets = []
    for line in lines:
        offsets.append(offset); offset += len(line)
    offset = 0

    def issue(code, message, line):
        issues.append({'code':code,'message':message,'line':line,'candidates':[]})

    def start_scene(heading, number, i, synthetic=False):
        nonlocal scene
        if scene is not None:
            scene['source']['end'] = offsets[i]
        scene = {'id':identity(script_id,f'{source_hash}:scene:{len(scenes)}'),
                 'heading':heading[:240], 'number':number,
                 'source':{'start':offsets[i], 'end':len(text),'line':i+1},'blocks':[]}
        scenes.append(scene)
        if synthetic:
            issue('unscened_material', 'Material before a scene heading is retained in a separate source scene; review its classification.',i+1)

    while index < len(lines):
        line, i = lines[index], index
        stripped = line.strip()
        if not stripped:
            character = ''; index += 1; continue
        forced = stripped.startswith('.') and len(stripped)>1 and stripped[1].isalnum()
        blank_before = i == 0 or not lines[i-1].strip()
        heading = forced or bool(HEADING.match(stripped)) and blank_before
        if heading:
            display = stripped[1:] if forced else stripped
            match = NUMBER.search(display)
            number = match.group(1) if match else ''
            display = NUMBER.sub('',display)
            start_scene(display,number,i)
            character = ''; index += 1; continue
        if scene is None:
            start_scene('Unscened source material','',i,True)
        next_nonempty = i+1 < len(lines) and bool(lines[i+1].strip())
        # Forced Fountain action/character syntax is consumed only for interpretation;
        # raw bytes and source spans still preserve exactly what was imported.
        candidate = re.sub(r'\s*\([^)]*\)\s*\^?$', '', stripped).rstrip('^').strip()
        is_character = stripped.startswith('@') or (blank_before and next_nonempty and
                       candidate.isupper() and any(c.isalpha() for c in candidate) and
                       len(candidate)<100 and not stripped.endswith('TO:') and
                       not stripped.startswith(('!', '#','>','~','[[','/*','=')))
        if stripped.startswith(('[[','/*','#','=')) or stripped.startswith('>') and stripped.endswith('<'):
            typ, content = 'note', line.rstrip('\r\n')
            issue('uninterpreted_construct','Notes, sections, boneyards, page breaks and centered text are retained as source notes; inspect multiline constructs.',i+1)
            character = ''
        elif is_character:
            typ, content = 'character', stripped[1:] if stripped.startswith('@') else stripped
            character = content.rstrip('^').strip()
            if stripped.endswith('^'):
                issue('dual_dialogue','Dual dialogue is retained in source order; simultaneous timing must be planned explicitly.',i+1)
        elif stripped.startswith('~'):
            typ, content = 'lyric', line.rstrip('\r\n')[line.index('~')+1:]
        elif stripped.startswith('>') or stripped.endswith('TO:') and stripped.isupper() and blank_before:
            typ, content = 'transition', stripped.lstrip('>')
            character = ''
        elif stripped.startswith('(') and stripped.endswith(')') and character:
            typ, content = 'parenthetical', line.rstrip('\r\n')
        else:
            typ = 'dialogue' if character and not stripped.startswith('!') else 'action'
            content = line.rstrip('\r\n')
            if stripped.startswith('!'):
                content = content[:content.index('!')] + content[content.index('!')+1:]
                character = ''
            # Coalesce a paragraph without consuming headings, parentheticals or forced syntax.
            j = i+1
            while j < len(lines) and lines[j].strip():
                following = lines[j].strip()
                if HEADING.match(following) or following.startswith(('.', '@','!','~','>','[[','/*','#','=')) or following.startswith('(') and character:
                    break
                content += lines[j-1][len(lines[j-1].rstrip('\r\n')):] + lines[j].rstrip('\r\n')
                j += 1
            index = j-1
        end = offsets[index]+len(lines[index].rstrip('\r\n'))
        scene['blocks'].append({'id':identity(script_id,f'{source_hash}:block:{i}'), 'type':typ,
                                'text':content,'character':character if typ in ('dialogue','character','parenthetical') else '',
                                'source':{'start':offsets[i],'end':end,'line':i+1}})
        index += 1
    if not scenes:
        raise ProductionError('The script contains no nonblank material.')
    return scenes, issues


def _stable_blocks(old, new, script_id, scene_id, report):
    """Exact-content unique matches, then one-for-one same-type gaps, never broad fuzzy matching."""
    a, b = old['blocks'], new['blocks']
    old_by_id = {x['id']:x for x in a}
    used = set()
    matches = {}
    signature = lambda x: (x['type'],x['character'],x['text'])
    old_counts, new_counts = Counter(map(signature,a)), Counter(map(signature,b))
    unique_old = {signature(x):x for x in a if old_counts[signature(x)] == 1}
    for i, block in enumerate(b):
        found = old_by_id.get(block['id'])
        if found is None and new_counts[signature(block)] == 1:
            found = unique_old.get(signature(block))
        if found and found['id'] not in used:
            matches[i] = found['id']; used.add(found['id'])
    # Preserve a changed passage only when an aligned gap contains a single candidate
    # of the same element type and speaker. All ambiguous multi-passage edits get new IDs.
    old_pos = {x['id']:i for i,x in enumerate(a)}
    anchors = [(-1,-1)] + [(i,old_pos[bid]) for i,bid in sorted(matches.items())] + [(len(b),len(a))]
    if [p for _,p in anchors] == sorted(p for _,p in anchors):
        for (bi,ai),(bj,aj) in zip(anchors,anchors[1:]):
            if bj-bi == 2 and aj-ai == 2:
                nb, ob = b[bi+1], a[ai+1]
                if nb['type'] == ob['type'] and nb['character'] == ob['character']:
                    matches[bi+1] = ob['id']; used.add(ob['id'])
                    report.append({'code':'passage_identity_aligned','message':'One changed passage was matched by its sole aligned type/speaker position; review the revision diff.','line':nb.get('source',{}).get('line') if nb.get('source') else None,'candidates':[ob['id']]})
    for i, block in enumerate(b):
        if i in matches:
            block['id'] = matches[i]
        # New IDs from explicit structured input remain explicit. Fountain IDs are already
        # deterministic for the same source/record, enabling preview and retry parity.


def reconcile_identity(scenes, previous, script_id, identity_map=None):
    identity_map = identity_map or {}
    if not isinstance(identity_map,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in identity_map.items()):
        raise ProductionError('identity_map must map incoming zero-based scene indexes to prior scene UUIDs.')
    old = previous.get('scenes',[]) if previous else []
    by_id = {s['id']:s for s in old}
    old_heading, old_number = defaultdict(list), defaultdict(list)
    for s in old:
        old_heading[s['heading'].casefold()].append(s)
        if s['number']:
            old_number[s['number']].append(s)
    new_headings = Counter(s['heading'].casefold() for s in scenes)
    new_numbers = Counter(s['number'] for s in scenes if s['number'])
    used, reports = set(), []
    if any(not k.isdigit() or int(k)>=len(scenes) for k in identity_map):
        raise ProductionError('identity_map contains an incoming scene index that does not exist.')
    for i,s in enumerate(scenes):
        chosen, method = None, ''
        if str(i) in identity_map:
            chosen = by_id.get(identity_map[str(i)])
            if chosen is None:
                raise ProductionError('Explicit scene identity is absent from the prior script revision.')
            method = 'explicit'
        elif s['id'] in by_id:
            chosen, method = by_id[s['id']], 'source_id'
        elif s['number'] and len(old_number[s['number']]) == 1 and new_numbers[s['number']] == 1:
            chosen, method = old_number[s['number']][0], 'unique_number'
        elif len(old_heading[s['heading'].casefold()]) == 1 and new_headings[s['heading'].casefold()] == 1:
            chosen, method = old_heading[s['heading'].casefold()][0], 'unique_heading'
        if chosen:
            if chosen['id'] in used:
                raise ProductionError('Two incoming scenes resolve to one prior scene. Supply an unambiguous identity map.')
            used.add(chosen['id']); s['id'] = chosen['id']
            _stable_blocks(chosen,s,script_id,s['id'],reports)
            reports.append({'code':'scene_identity_'+method,'message':f'Scene {i+1} retains its stable identity using {method}.','line':None,'candidates':[s['id']]})
        else:
            candidates = old_heading.get(s['heading'].casefold(),[])
            if candidates:
                reports.append({'code':'ambiguous_scene_identity','message':f'Scene {i+1} has multiple possible matches; a new identity was retained. Supply identity_map before applying.','line':None,'candidates':[x['id'] for x in candidates][:100]})
    return scenes, reports


def compare_scripts(a,b):
    def compare(old,new,category):
        old_by, new_by = {x['id']:x for x in old}, {x['id']:x for x in new}
        positions = {x['id']:i for i,x in enumerate(old)}
        rows = []
        for i,item in enumerate(new):
            rid = item['id']
            if rid not in old_by:
                rows.append({'kind':category,'id':rid,'change':'added','position':i}); continue
            previous = old_by[rid]
            # Source offsets move with upstream changes; they are not wording changes.
            fields = ('heading','number') if category == 'scene' else ('type','text','character')
            changed = [f for f in fields if previous.get(f)!=item.get(f)]
            if changed:
                rows.append({'kind':category,'id':rid,'change':'changed','fields':changed})
            if positions[rid] != i:
                rows.append({'kind':category,'id':rid,'change':'moved','from':positions[rid],'to':i})
        rows.extend({'kind':category,'id':rid,'change':'removed'} for rid in old_by if rid not in new_by)
        return rows
    rows = compare(a['scenes'],b['scenes'],'scene')
    old = {s['id']:s for s in a['scenes']}
    for scene in b['scenes']:
        rows.extend({**r,'scene_id':scene['id']} for r in compare(old.get(scene['id'],{}).get('blocks',[]),scene['blocks'],'passage'))
    for scene in a['scenes']:
        if scene['id'] not in {s['id'] for s in b['scenes']}:
            rows.extend({'kind':'passage','id':x['id'],'change':'removed','scene_id':scene['id']} for x in scene['blocks'])
    return rows


def import_preview(service, id, expected_revision, expected_checkpoint, operation_id, filename,
                   format='fountain', text=None, bytes_base64=None, identity_map=None, select=False):
    from .service import ProductionService
    prod = ProductionService(service)
    if (text is None) == (bytes_base64 is None):
        raise ProductionError('Provide exactly one of text or bytes_base64.')
    if text is not None:
        if not isinstance(text,str):
            raise ProductionError('Script text must be a string.')
        raw = text.encode('utf-8')
    else:
        try:
            raw = base64.b64decode(bytes_base64,validate=True)
        except (ValueError, TypeError) as exc:
            raise ProductionError('Invalid original-file base64.') from exc
    if len(raw)>2*1024*1024:
        raise ProductionError('Scripts are limited to 2 MiB per imported revision.')
    try:
        content = raw.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ProductionError('Import UTF-8 text; PDF, FDX and binary formats are not interpreted by this adapter.') from exc
    previous = prod.show(id) if expected_revision else None
    if previous and previous['kind'] != 'script':
        raise ProductionError('The selected import target is not a script.')
    body = copy.deepcopy(previous['data']) if previous else {'kind':'script','title':filename,'scenes':[]}
    if format == 'fountain':
        scenes, issues = parse_fountain(content,id)
    elif format == 'structured-json':
        try:
            value = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProductionError('Structured script JSON could not be decoded.') from exc
        if not isinstance(value,dict) or set(value)-{'title','scenes'} or 'scenes' not in value:
            raise ProductionError('Structured script input is {title?, scenes:[{id?, heading, number?, blocks:[{id?,type,text,character?}]}]}.')
        scenes = value['scenes']
        if not isinstance(scenes,list):
            raise ProductionError('Structured scenes must be an array.')
        for i,s in enumerate(scenes):
            if not isinstance(s,dict) or not isinstance(s.get('blocks',[]),list):
                raise ProductionError('Each structured scene is an object with a blocks array.')
            s.setdefault('id',identity(id,f'structured:{hashlib.sha256(raw).hexdigest()}:scene:{i}'))
            s.setdefault('number','')
            for j,block in enumerate(s.get('blocks',[])):
                if not isinstance(block,dict):
                    raise ProductionError('Each structured passage is an object.')
                block.setdefault('id',identity(id,f'structured:{hashlib.sha256(raw).hexdigest()}:block:{i}:{j}'))
                block.setdefault('character','')
        if value.get('title'):
            body['title'] = value['title']
        issues = []
    elif format == 'screenjson':
        from storyboarder.formats.screenjson import parse_screenjson, text_value
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProductionError('ScreenJSON could not be decoded.') from exc
        parse_screenjson(payload)  # Keep the existing adapter's strict core profile.
        language = payload['lang']
        characters = {x['id']:x['name'] for x in payload.get('characters',[])}
        scenes, issues = [], [{'code':'screenjson_core','message':'Existing ScreenJSON core validation used; ancillary metadata is retained in the original file.','line':None,'candidates':[]}]
        for s in payload['document']['scenes']:
            h = s['heading']
            scene = {'id':str(uuid.UUID(s['id'])),'heading':f"{h['context']}. {h['setting']} — {h['time']}",
                     'number':str(h.get('no') or ''),'blocks':[]}
            for b in s['body']:
                typ = b['type']
                if typ not in ('action','dialogue','character','parenthetical','transition'):
                    issues.append({'code':'screenjson_element_note','message':f'{typ} is retained as a source note, not interpreted as a production shot.','line':None,'candidates':[]})
                    typ = 'note'
                scene['blocks'].append({'id':str(uuid.UUID(b['id'])),'type':typ,
                    'text':text_value(b.get('text'),language) or b.get('display') or characters.get(b.get('character'),''),
                    'character':characters.get(b.get('character'),'')})
            scenes.append(scene)
    else:
        raise ProductionError('Supported imports: fountain, structured-json and the existing screenjson core profile. PDF/FDX imports are unsupported.')
    scenes = [decode(ScriptScene, scene) for scene in scenes]
    scenes,reconciled = reconcile_identity(scenes,previous['data'] if previous else None,id,identity_map)
    body.update({'scenes':scenes,'wording_status':'imported','import_issues':issues+reconciled,
                 'source_file':decode(SourceFile,{'name':filename,'format':format,'bytes_base64':base64.b64encode(raw).decode(),
                                                  'sha256':hashlib.sha256(raw).hexdigest()})})
    body['provenance'] = {**body.get('provenance',{}),'origin':'import','author':body.get('provenance',{}).get('author',''),
                          'rationale':'Imported wording; interpretations remain in production planning records.'}
    body = parse_record(body)
    batch = {'expected_checkpoint':expected_checkpoint,'operation_id':operation_id,'operations':[
        {'op':'put','id':id,'expected_revision':expected_revision,'select':select,'data':body,
         **({'base_version':previous['version']} if previous else {})}]}
    return {'batch':batch,'preview':prod.preview(batch),'import_report':body['import_issues'],
            'revision_diff':compare_scripts(previous['data'],body) if previous else [],
            'original_sha256':body['source_file']['sha256'], 'persisted':False}
