import pytest
from storyboarder.application.commands import execute, COMMANDS, options_for
from storyboarder.domain.errors import StoryboardError, Conflict, InUse


def test_alias_search_and_literal_search_escaping(story):
    s=story['service']
    assert s.list_entities('asset',query='Mara')['items'][0]['id']==story['character']['id']
    assert s.list_entities('asset',tag='winter')['total']==1
    assert s.list_entities('asset',query='%')['total']==0
    assert s.list_entities('asset',query='_')['total']==0


@pytest.mark.parametrize('kind,fields',[
 ('shot',{'duration':-1}),('shot',{'duration':float('nan')}),('shot',{'duration':86401}),
 ('shot',{'action':'a\x00b'}),('shot',{'made_up':'no'}),('asset',{'type':'vehicle'}),
 ('scene',{'dialogue':'only a shot field'}),('sequence',{'unknown':True}),
])
def test_typed_authored_fields_rejected(service,kind,fields):
    with pytest.raises(StoryboardError): service.create_entity(kind,'Invalid',fields=fields)


def test_no_dangling_or_wrong_parent(story):
    s=story['service']
    with pytest.raises(StoryboardError):s.create_entity('shot','Wrong parent',story['sequence']['id'])
    with pytest.raises(StoryboardError):s.create_entity('scene','Wrong parent',story['character']['id'])


def test_order_ids_and_reparent_revision(story):
    s=story['service'];a=story['shot'];scene=story['scene']
    b=s.create_entity('shot','Second',scene['id']);c=s.create_entity('shot','Third',scene['id'])
    s.move(c['id'],c['revision'],0)
    rows=s.list_entities('shot',parent_id=scene['id'])['items']
    assert [r['id'] for r in rows]==[c['id'],a['id'],b['id']]
    assert [r['position'] for r in rows]==[0,1,2]
    with pytest.raises(Conflict):s.update_entity(a['id'],a['revision'],{'title':'Stale'})
    other=s.create_entity('scene','Elsewhere',story['sequence']['id'])
    a=s.get('entities',a['id']);moved=s.move(a['id'],a['revision'],0,other['id'])
    assert moved['id']==a['id'] and moved['parent_id']==other['id']
    assert [r['position'] for r in s.list_entities('shot',parent_id=scene['id'])['items']]==[0,1]


def test_relationship_types_cycles_and_archive_references(story):
    s=story['service'];char=story['character'];loc=story['location'];prop=story['prop']
    s.create_link(char['id'],loc['id'],'appears-at')
    s.create_link(char['id'],prop['id'],'wears')
    with pytest.raises(StoryboardError):s.create_link(loc['id'],char['id'],'wears')
    with pytest.raises(StoryboardError):s.create_link(loc['id'],loc['id'],'related-to')
    with pytest.raises(StoryboardError):s.create_link(char['id'],prop['id'],'alternate-view-of')
    s.create_link(prop['id'],loc['id'],'part-of')
    with pytest.raises(StoryboardError):s.create_link(loc['id'],prop['id'],'part-of')
    assert not s.usage(char['id'])['can_delete']
    with pytest.raises(InUse):s.lifecycle(char['id'],char['revision'],'delete')
    archived=s.lifecycle(char['id'],char['revision'],'archive')
    assert archived['archived']==1
    restored=s.lifecycle(char['id'],archived['revision'],'restore')
    assert restored['archived']==0


def test_type_change_cannot_invalidate_references(story):
    s=story['service'];loc=story['location']
    with pytest.raises(StoryboardError):s.update_entity(loc['id'],loc['revision'],{'fields':{'type':'prop'}})
    assert s.get('entities',loc['id'])['fields']['type']=='location'


def test_exact_selection_no_primary_substitution(story):
    s=story['service'];shot=story['shot'];char=story['character']
    composition=s.compose(shot['id'])
    ref=composition['scenes'][0]['shots'][0]['assignments'][0]
    assert ref['media']['id']==story['exact']['id']
    assert ref['media']['id']!=story['first']['id']
    with pytest.raises(InUse):s.detach_media(story['exact_member']['id'],story['exact_member']['revision'])
    unattached=s.import_file(story['image_factory']())['media']
    with pytest.raises(StoryboardError):s.update_assignment(story['assignment']['id'],1,'subject',unattached['id'])
    s.update_assignment(story['assignment']['id'],1,'subject',None)
    assert s.compose(shot['id'])['scenes'][0]['shots'][0]['assignments'][0]['media'] is None


def test_media_picker_scopes_only_exact_assignment(story):
    s=story['service'];st=s.state();values={'asset_id':story['character']['id']}
    third=s.import_file(story['image_factory']())['media'];st=s.state()
    assert third['id'] in dict(options_for('media',st,values))
    assert third['id'] not in dict(options_for('asset_images',st,values))
    assert story['exact']['id'] in dict(options_for('asset_images',st,values))


def test_context_inheritance_sources_replace_and_exclude(story):
    s=story['service'];project=s.project.id;seq=story['sequence'];scene=story['scene'];shot=story['shot']
    root=s.get('entities',project)
    s.update_entity(root['id'],root['revision'],{'fields':{'camera':'Static camera','time':'Day'}})
    s.put_context(project,'light','append','Use natural light.')
    s.put_context(seq['id'],'light','append','Keep the highlights.')
    s.put_context(scene['id'],'light','replace','Overcast daylight.')
    s.put_context(shot['id'],'camera','exclude','')
    ctx=s.compose(shot['id'])['context']
    assert ctx['scalars']['time']['value']=='Dawn'
    assert ctx['scalars']['time']['source']['id']==scene['id']
    assert ctx['scalars']['camera']['value']=='Static camera'
    assert [e['text'] for e in ctx['blocks']['light']]==['Overcast daylight.']
    assert ctx['blocks']['light'][0]['source']['id']==scene['id']
    s.put_context(shot['id'],'light','exclude','')
    ctx=s.compose(shot['id'])['context']
    assert not ctx['blocks'].get('light')
    assert any(h['key']=='light' and h['operation']=='exclude' for h in ctx['history'])


def test_direction_edit_requires_revision_and_preserves_owner(story):
    s=story['service'];shot=story['shot']
    block=s.put_context(shot['id'],'weather','append','Mist.')
    with pytest.raises(Conflict):s.put_context(shot['id'],'weather','replace','Clear.')
    newer=s.put_context(shot['id'],'weather','replace','Clear.',block['revision'])
    from storyboarder.tui.pages import defaults
    assert defaults(newer)['owner_id']==shot['id']
    assert newer['id']==block['id'] and newer['revision']==2


def test_frames_are_distinct_records_and_approval_protected(story):
    s=story['service'];shot=story['shot']
    a=s.attach_frame(shot['id'],story['exact']['id']);b=s.attach_frame(shot['id'],story['first']['id'])
    assert a['id']!=a['media_id'] and (a['version'],b['version'])==(1,2)
    approved=s.set_frame_state(a['id'],a['revision'],'approved')
    with pytest.raises(InUse):s.set_frame_state(b['id'],b['revision'],'selected')
    s.set_frame_state(a['id'],approved['revision'],'draft')
    selected=s.set_frame_state(b['id'],b['revision'],'selected')
    assert selected['state']=='selected'
    assert len(s.state()['assignments'])==1


def test_merge_preserves_exact_images_and_redirects_links(story):
    s=story['service'];source=story['character'];target=s.create_entity('asset','Mara master',fields={'type':'character'})
    s.create_link(source['id'],story['location']['id'],'appears-at')
    s.merge_assets(source['id'],source['revision'],target['id'],target['revision'])
    assignment=s.get('assignments',story['assignment']['id'])
    assert assignment['asset_id']==target['id'] and assignment['media_id']==story['exact']['id']
    assert s.get('entities',source['id'])['archived']==1
    assert s.state()['links'][0]['source_id']==target['id']


def test_layout_changes_only_presentation_and_revision(story):
    s=story['service'];before=s.state()['entities'];nodes=s.graph('story')['nodes'];node=nodes[0]
    layout=s.save_layout('Working desk','story',{node['id']:{'x':12,'y':20}},{'viewport':{'x':0,'y':0,'scale':1}})
    assert s.state()['entities']==before
    with pytest.raises(Conflict):s.save_layout('Working desk','story',{})
    layout=s.save_layout('Working desk','story',{node['id']:{'x':100,'y':80}},revision=layout['revision'])
    assert layout['revision']==2 and s.state()['entities']==before
    graph=s.graph('story')
    assert len(graph['edges'])==2


def test_layout_cas_by_stable_id_supports_disjoint_merge_and_explicit_overlap_choice(story):
    s=story['service'];cards=[node['id'] for node in s.graph('assets')['nodes'][:2]]
    assert len(cards)==2
    start={cards[0]:{'x':10,'y':20},cards[1]:{'x':30,'y':40}}
    base=s.save_layout('Shared desk','assets',start)
    external={**start,cards[0]:{'x':80,'y':20}}
    remote=s.save_layout(base['name'],base['mode'],external,base['settings'],base['revision'],base['id'])
    local={**start,cards[1]:{'x':95,'y':40}}
    with pytest.raises(Conflict):s.save_layout(base['name'],base['mode'],local,base['settings'],base['revision'],base['id'])
    merged={**external,cards[1]:local[cards[1]]}
    result=s.save_layout(base['name'],base['mode'],merged,base['settings'],remote['revision'],remote['id'])
    assert result['revision']==3 and result['positions']==merged

    same_card_local={**merged,cards[0]:{'x':120,'y':20}}
    remote_again={**merged,cards[0]:{'x':140,'y':20}}
    second=s.save_layout(base['name'],base['mode'],remote_again,result['settings'],result['revision'],result['id'])
    with pytest.raises(Conflict):s.save_layout(base['name'],base['mode'],same_card_local,result['settings'],result['revision'],result['id'])
    # The service accepts only the already-resolved value under the newest CAS revision.
    chosen={**remote_again,cards[0]:same_card_local[cards[0]]}
    resolved=s.save_layout(base['name'],base['mode'],chosen,second['settings'],second['revision'],second['id'])
    assert resolved['revision']==5 and resolved['positions'][cards[0]]=={'x':120,'y':20}


def test_layout_id_cas_can_rename_or_change_mode_and_rejects_stale_or_colliding_identity(story):
    s=story['service'];card=s.graph('assets')['nodes'][0]['id'];positions={card:{'x':1,'y':2}}
    first=s.save_layout('Original','assets',positions)
    renamed=s.save_layout('Renamed','scene',positions,first['settings'],first['revision'],first['id'])
    assert renamed['id']==first['id'] and renamed['name']=='Renamed' and renamed['mode']=='scene' and renamed['revision']==2
    collision=s.save_layout('Taken','assets',positions)
    with pytest.raises(StoryboardError):s.save_layout('Taken','assets',positions,renamed['settings'],renamed['revision'],renamed['id'])
    with pytest.raises(Conflict):s.save_layout('Stale','story',positions,{},first['revision'],first['id'])
    with pytest.raises(Conflict):s.save_layout('Missing','story',positions,{},1,'layout-from-another-project')
    assert s.get('layouts',collision['id'])['name']=='Taken'


def test_canvas_command_catalog_uses_stable_id_cas_through_shared_command_layer(story):
    s=story['service'];fields={field.name:field for field in COMMANDS['canvas.save'].fields}
    assert fields['layout_id'].source=='layouts' and fields['layout_id'].type=='select'
    payload={'name':'Command path','mode':'story','positions':{'stable-card':{'x':4,'y':8}},'settings':{}}
    first=execute(s,'canvas.save',payload)
    updated=execute(s,'canvas.save',{**payload,'layout_id':first['id'],'revision':first['revision'],'name':'Command path renamed'})
    assert updated['id']==first['id'] and updated['revision']==2 and updated['name']=='Command path renamed'
    with pytest.raises(Conflict):execute(s,'canvas.save',{**payload,'layout_id':first['id'],'revision':first['revision']})


@pytest.mark.parametrize('positions,settings',[
 ({'missing':{'x':0}},{}), ({'x':{'x':float('nan'),'y':0}},{}),
 ({},{'viewport':{'x':0,'y':0,'scale':100}}), ({},{'unsupported':'field'})
])
def test_invalid_layouts_rejected(service,positions,settings):
    with pytest.raises(StoryboardError):service.save_layout('Bad','story',positions,settings)


def test_all_canvas_modes_derive_domain_edges(story):
    s=story['service'];s.create_link(story['character']['id'],story['location']['id'],'appears-at')
    assets=s.graph('assets');flow=s.graph('story');board=s.graph('scene',scene_id=story['scene']['id'])
    assert any(e.get('relation')=='appears-at' or e.get('label')=='appears-at' for e in assets['edges'])
    assert len(flow['nodes'])==3
    assert any(e['id']==story['assignment']['id'] for e in board['edges'])
    assert s.graph('assets',query='Caretaker')['total']==1


def test_shared_commands_refuse_unknown_and_browser_filesystem(service):
    with pytest.raises(StoryboardError):execute(service,'not.a.command',{})
    with pytest.raises(StoryboardError):execute(service,'asset.create',{'title':'Test','sql':'DROP TABLE entities'})
    with pytest.raises(StoryboardError):execute(service,'media.import',{'path':'/etc/passwd'},browser=True)
    asset=execute(service,'asset.create',{'title':'Shared command','type':'reference'})
    assert service.get('entities',asset['id'])['title']=='Shared command'
