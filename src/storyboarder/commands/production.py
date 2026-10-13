"""One explicit production command surface for CLI, HTTP, viewer and optional MCP."""
from .core import F, register
from storyboarder.production.models import schema
from storyboarder.production.service import ProductionService
from storyboarder.production.reports import report
from storyboarder.production.evaluate import evaluate, convert_frames
from storyboarder.production.scripts import import_preview
from storyboarder.production.example import example


def text(name,required=False,default=None):
    return F(name,type='text',required=required,default=default)


def integer(name,required=False,default=None):
    return F(name,type='integer',required=required,default=default)


def obj(name,required=True):
    return F(name,type='json',required=required)


def array(name,required=True):
    return F(name,type='json-array',required=required)


def reg(name,fields,method=None,handler=None,read=True):
    register('production.'+name,'Production '+name.replace('-',' '),fields,
             handler or (lambda s,p:getattr(ProductionService(s),method or name.replace('-','_'))(**p)),
             browser=False,api_safe=True,read_only=read,page='production')


page=[integer('limit',default=100),integer('offset',default=0)]
reg('schema',[],handler=lambda s,p:schema())
reg('snapshot',[F('mode',type='select',options=('selected','head'),default='selected'),
                F('include_archived',type='boolean',default=False),F('closure',type='boolean',default=False),*page])
reg('show',[text('id',True),integer('version')])
reg('history',[text('id',True),*page])
reg('preview',[obj('batch')])
reg('apply',[obj('batch')],read=False)
reg('query',[text('kind'),text('text',default=''),text('scene_id'),text('script_block_id'),
             F('include_proposals',type='boolean',default=False),*page])
reg('impact',[text('id',True)])
reg('changes',[integer('since',default=0),*page])
reg('diff',[text('id',True),integer('from_version',True),integer('to_version',True)])
reg('reconcile',[array('replacements'),array('ids'),text('operation_id',True),integer('expected_checkpoint',True),F('select',type='boolean',default=False)])
reg('report',[F('include_proposals',type='boolean',default=False),F('hashes',type='boolean',default=False)],handler=lambda s,p:report(s,**p))
reg('evaluate',[text('id',True),integer('version'),F('frame',type='number',default=0.0)],handler=lambda s,p:evaluate(s,**p))
reg('convert-time',[integer('frames',True),obj('from_rate'),obj('to_rate'),
                    F('rounding',type='select',options=('exact','floor','ceil','nearest'),default='exact')],handler=lambda s,p:convert_frames(**p))
reg('script-import-preview',[text('id',True),integer('expected_revision',True),integer('expected_checkpoint',True),
                             text('operation_id',True),text('filename',True),
                             F('format',type='select',options=('fountain','structured-json','screenjson'),default='fountain'),
                             F('text',type='textarea'),text('bytes_base64'),obj('identity_map',False),
                             F('select',type='boolean',default=False)],handler=lambda s,p:import_preview(s,**p))
reg('example',[integer('expected_checkpoint',default=0)],handler=lambda s,p:example(s,**p))


from storyboarder.production.portability import export_package, import_package
from storyboarder.production.outputs import packet
reg('export',[],handler=lambda s,p:export_package(s))
reg('import-preview',[obj('package'),text('operation_id',True),integer('expected_checkpoint',True)],handler=lambda s,p:import_package(s,**p))
reg('import-apply',[obj('package'),text('operation_id',True),integer('expected_checkpoint',True)],handler=lambda s,p:import_package(s,**p,apply=True),read=False)
reg('packet',[text('scene_id'),F('include_pdf',type='boolean',default=True)],handler=lambda s,p:packet(s,**p),read=False)

from storyboarder.production.legacy import adopt_preview
reg('adopt-preview',[integer('expected_checkpoint',True),text('operation_id',True),F('select',type='boolean',default=False)],handler=lambda s,p:adopt_preview(s,**p))
