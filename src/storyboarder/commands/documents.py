"""Source document commands, explicitly shared by CLI, TUI and browser."""
from .core import F, ID, REV, register
from storyboarder.application.documents import Documents
from storyboarder.application.source_workflows import SourceWorkflows
from storyboarder.application.provenance import Provenance, TYPES, RELATIONS

DOC = F('document_id', 'Document', required=True)
VERSION = F('version_id', 'Draft (blank for current)')
NODE = F('node_id', 'Source element', required=True)
PAGING = [F('limit', 'Page size', 'integer', default=100), F('offset', 'Offset', 'integer', default=0)]
IMPORT = [F('path', 'Source file path', required=True), F('document_id', 'Existing document'),
          F('revision', 'Last-read document revision', 'integer'), F('label', 'Draft label', default='Imported draft'),
          F('dry_run', 'Validate without importing', 'boolean', default=False)]
register('document.import', 'Import source document', [*IMPORT, F('format', 'Source format', 'select', True, ('screenjson','otio'))],
         lambda s,p: SourceWorkflows(s).import_file(**p), browser=False, page='documents')
for group, format in (('screenplay','screenjson'),('edit','otio')):
    register(group+'.import', 'Import '+('screenplay' if group=='screenplay' else 'editorial cut'), IMPORT,
             lambda s,p,f=format: SourceWorkflows(s).import_file(format=f, **p), browser=False, page='documents')
    register(group+'.list', 'List '+group+' documents', PAGING,
             lambda s,p,k=group: Documents(s).list(kind=k, **p), read_only=True)
register('document.list','Find source documents',[F('kind', options=('screenplay','edit')),F('query'),F('archived',type='boolean'),*PAGING],lambda s,p:Documents(s).list(**p),read_only=True)
register('document.show','Show source document',[ID()],lambda s,p:Documents(s).show(p['id']),read_only=True)
register('document.versions','List creative drafts',[DOC,*PAGING],lambda s,p:Documents(s).versions(**p),read_only=True)
register('document.tree','Read source tree',[DOC,VERSION,F('query'),*PAGING],lambda s,p:SourceWorkflows(s).tree(**p),read_only=True,page='documents')
register('document.children','Read child elements',[F('version_id',required=True),F('parent_id'),*PAGING],lambda s,p:Documents(s).children(**p),read_only=True)
register('document.node','Read a source element',[ID()],lambda s,p:Documents(s).node(p['id']),read_only=True)
register('document.validate','Validate stored source',[ID(),VERSION],lambda s,p:SourceWorkflows(s).validate(p['id'],p.get('version_id')),read_only=True)
register('document.revise','Save source as a new draft',[NODE,F('changes','Authored changes','json',True),REV,F('label',default='Revised draft')],lambda s,p:Documents(s).revise_node(**p),page='documents')
register('document.diff','Compare creative drafts',[F('before_id','Earlier draft',required=True),F('after_id','Later draft',required=True)],lambda s,p:Documents(s).diff(**p),read_only=True,page='documents')
register('document.export','Export a source draft',[DOC,VERSION,F('include_identities','Add stable OTIO identities','boolean',default=False)],lambda s,p:SourceWorkflows(s).export(**p),page='documents')
for action, archived in (('archive',True),('restore',False)):
    register('document.'+action,action.title()+' source document',[DOC,REV],lambda s,p,a=archived:SourceWorkflows(s).archive(**p,archived=a),page='documents',destructive=archived)
register('shot.link-source','Link screenplay source',[F('shot_id',required=True,source='shots'),NODE,F('notes',type='textarea')],lambda s,p:Provenance(s).link('node',p['node_id'],'entity',p['shot_id'],'visualizes',p.get('notes','')),page='documents')
register('shot.sources','Inspect shot sources',[ID('shots')],lambda s,p:Provenance(s).sources(p['id']),read_only=True,page='documents')
register('provenance.link','Connect production provenance',[
    F('source_type','Source type','select',True,TYPES),F('source_id',required=True),F('target_type','Result type','select',True,TYPES),
    F('target_id',required=True),F('relation','Relationship','select',True,RELATIONS),F('notes',type='textarea')],lambda s,p:Provenance(s).link(**p),page='provenance')
register('provenance.trace','Trace production lineage',[
    F('kind','Item type','select',True,TYPES),F('record_id','Item',required=True),F('direction','Direction','select',options=('upstream','downstream','both'),default='both'),
    F('depth','Maximum depth','integer',default=6),F('limit','Maximum nodes','integer',default=100)],lambda s,p:Provenance(s).trace(p['kind'],p['record_id'],p['direction'],p['depth'],p['limit']),read_only=True,page='provenance')
register('provenance.retire','Retire a source link',[F('edge_id',required=True),REV],lambda s,p:Provenance(s).retire(**p),destructive=True,page='provenance')
register('provenance.impact','Review downstream draft impact',[F('before_id',required=True),F('after_id',required=True),F('limit',type='integer',default=300)],lambda s,p:Provenance(s).impact(p['before_id'],p['after_id'],p['limit']),read_only=True,page='provenance')
register('coverage.report','Review source and delivery coverage',[F('limit',type='integer',default=100)],lambda s,p:Provenance(s).coverage(**p),read_only=True,page='coverage')
register('annotation.create','Add a pinned review note',[F('endpoint_type',type='select',required=True,options=TYPES),F('endpoint_id',required=True),F('content','Review note','textarea',True)],lambda s,p:Provenance(s).annotate(p['endpoint_type'],p['endpoint_id'],p['content']),page='documents')
register('annotation.list','Read pinned notes',[F('kind',type='select',required=True,options=TYPES),F('record_id',required=True),*PAGING],lambda s,p:Provenance(s).annotations(p['kind'],p['record_id'],p['limit'],p['offset']),read_only=True)
register('annotation.update','Update review note',[F('annotation_id',required=True),REV,F('content',type='textarea',required=True),F('state',type='select',options=('open','resolved'),default='open')],lambda s,p:Provenance(s).update_annotation(p['annotation_id'],p['revision'],p['content'],p['state']),page='documents')
