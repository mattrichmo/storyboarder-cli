"""Intentional editor commands, shared by CLI and project-granted local API."""
from .core import F,register
from storyboarder.application.spatial_plans import SpatialPlans
from storyboarder.application.spatial_review import SpatialReviews
from storyboarder.application.spatial_transfer import SpatialTransfer
from storyboarder.application.spatial_delivery import diagram_export
from storyboarder.application.spatial_recovery import doctor,backup,restore
from storyboarder.domain.spatial import SpatialPayload,SpatialBinding,SpatialReview
from storyboarder.domain.spatial_fixture import doorway


def text(name,required=True):return F(name,type='text',required=required)
def number(name,required=False,default=None):return F(name,type='integer',required=required,default=default)
def obj(name,required=True):return F(name,type='json',required=required)
def array(name,required=True):return F(name,type='json-array',required=required)
def reg(name,fields,method=None,*,read=False,handler=None):
    register('spatial.'+name,'Spatial '+name.replace('-',' '),fields,handler or (lambda s,p:getattr(SpatialPlans(s),method or name.replace('-','_'))(**p)),browser=False,api_safe=True,read_only=read,page='blocking')

setup=[text('setup_id')]
revision=[*setup,number('revision',True)]
candidate=[*revision,obj('payload')]
create=[text('setup_id'),number('expected_project_revision',True),obj('payload')]
review_token=text('expected_basis_sha256')
op=text('operation_id',False)
pagination=[number('limit',default=100),number('offset',default=0)]

reg('schema',[],read=True,handler=lambda s,p:{'payload':SpatialPayload.model_json_schema(by_alias=True),'binding':SpatialBinding.model_json_schema(by_alias=True),'review':SpatialReview.model_json_schema(by_alias=True)})
reg('fixture',[text('scene_id'),text('chair_asset_id',False)],read=True,handler=lambda s,p:doorway(p['scene_id'],p.get('chair_asset_id')))
reg('create-preview',create,read=True)
reg('create',[*create,review_token,op])
reg('list',[text('scene_id',False),F('include_archived',type='boolean',default=False),*pagination],read=True)
reg('show',[*setup,text('version_id',False)],read=True)
reg('history',[*setup,*pagination],read=True)
reg('validate',[obj('payload'),text('setup_id',False)],read=True)
reg('revise-preview',candidate,read=True)
reg('revise',[*candidate,review_token,op])
reg('diff',[*setup,text('from_version_id'),text('to_version_id')],read=True)
reg('restore-preview',[*revision,text('version_id')],read=True)
reg('restore',[*revision,text('version_id'),review_token])
reg('archive',revision)
reg('unarchive',revision,handler=lambda s,p:SpatialPlans(s).archive(**p,unarchive=True))
duplicate=[*setup,text('version_id'),text('new_setup_id'),text('title')]
reg('duplicate-preview',duplicate,read=True)
reg('duplicate',[*duplicate,review_token])
reg('evaluate',[text('version_id'),array('times_us'),F('target_plane_z_m',type='number',default=0.0),obj('view_bounds',False)],read=True)
bind=[text('shot_id'),number('expected_shot_revision',True),text('binding_id'),obj('binding')]
reg('bind-preview',bind,read=True)
reg('bind',[*bind,review_token,op])
reg('rebind-preview',[*bind,number('revision',True)],method='bind_preview',read=True)
reg('rebind',[*bind,number('revision',True),review_token,op],method='bind')
reg('binding-show',[text('shot_id',False),text('binding_id',False),text('version_id',False)],read=True)
reg('binding-history',[text('binding_id'),*pagination],read=True)
reg('detach',[text('binding_id'),number('revision',True),number('expected_shot_revision',True)])
reg('impact',[text('setup_id',False),text('dependency_id',False),*pagination],read=True)
reg('operation-show',[text('operation_id')],read=True)
reg('doctor',[],read=True,handler=lambda s,p:doctor(s))
reg('backup',[],handler=lambda s,p:backup(s))
reg('plan-export',[*setup,F('scope',type='select',options=('full-history','selected-with-history-closure','sparse-snapshot'),default='full-history'),text('version_id',False)],handler=lambda s,p:SpatialTransfer(s).export(**p))
imports=[obj('package',False),text('archive_base64',False),F('mode',type='select',options=('exact','copy'),default='exact'),obj('mappings',False)]
reg('plan-import-preview',imports,read=True,handler=lambda s,p:SpatialTransfer(s).preview(**p))
reg('plan-import-apply',[*imports,review_token],handler=lambda s,p:SpatialTransfer(s).apply(**p))
reg('diagram-export',[text('version_id',False),text('binding_version_id',False),array('times_us',False),F('target_plane_z_m',type='number',default=0.0),obj('view_bounds',False),F('format',type='select',options=('all','svg','png','pdf'),default='all')],handler=lambda s,p:diagram_export(s,**p))
register('spatial.backup-restore','Restore spatial project backup',[text('archive'),text('destination')],lambda s,p:restore(**p),browser=False,api_safe=False)

v2=[text('shot_id'),number('expected_previous_number',True),obj('review')]
for name,fields,method,read in [
    ('spatial-review-preview',v2,'preview',True),
    ('spatial-review',v2+[review_token],'apply',False),
    ('spatial-review-show',[text('shot_id',False),text('review_id',False)],'show',True),
    ('spatial-review-validate',[text('shot_id',False),text('review_id',False)],'show',True),
    ('spatial-review-history',[text('shot_id'),*pagination],'history',True),
]:
    register('observation.'+name,'Spatial plan reviewed',fields,lambda s,p,m=method:getattr(SpatialReviews(s),m)(**p),browser=False,api_safe=True,read_only=read,page='blocking')
