#!/usr/bin/env python3
"""Execute empty-workspace → authored story → moved project → portable exports.

Only creates a NEW destination. No provider, network or existing project is used.
"""
import argparse
import json
from pathlib import Path
import shutil
from PIL import Image,ImageDraw
from storyboarder.application.projects import Workspace,Project
from storyboarder.application.service import Service

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    root=args.destination.expanduser().resolve()
    if root.exists():
        raise SystemExit('Choose a nonexistent destination for this disposable walkthrough.')
    workspace=Workspace(root);workspace.init()
    project=workspace.create('Acceptance story','acceptance')
    service=Service(project)
    reference=root/'test-reference.png'
    image=Image.new('RGB',(640,360),'#efeee6')
    ImageDraw.Draw(image).text((30,35),'FICTIONAL ACCEPTANCE TEST / NOT PRODUCTION ART',fill='#303b31')
    image.save(reference)
    asset=service.create_entity('asset','Caretaker',fields={'type':'character'},tags=['test'])
    media=service.import_file(reference)['media'];service.attach_media(asset['id'],media['id'])
    sequence=service.create_entity('sequence','Opening')
    scene=service.create_entity('scene','The platform',sequence['id'])
    shot=service.create_entity('shot','Open the door',scene['id'],fields={'action':'The caretaker opens the door.','framing':'Wide'})
    service.put_context(project.id,'light','append','Soft morning light.')
    service.assign(shot['id'],asset['id'],'subject',media['id'])
    frame=service.attach_frame(shot['id'],media['id'],'Same bytes, separate candidate record.')
    service.set_frame_state(frame['id'],frame['revision'],'selected')
    graph=service.graph('scene',scene_id=scene['id'])
    service.save_layout('Acceptance layout','scene',{n['id']:{'x':i*310,'y':0} for i,n in enumerate(graph['nodes'])},{'scene_id':scene['id']})
    before=service.state()['entities']
    moved=root/'projects'/'acceptance-moved'
    shutil.move(project.root,moved)
    workspace.register(moved)
    reopened=Service(Project(moved))
    assert reopened.project.id==project.id
    assert reopened.state()['entities']==before
    bundle=reopened.export_bundle(scene['id'])
    board=reopened.export_board(sequence['id'],'all')
    health=reopened.doctor(True)
    assert health['healthy']
    result={'project_id':project.id,'moved_project':str(moved),'graph_nodes':len(graph['nodes']),
            'graph_edges':len(graph['edges']),'exact_reference':media['id'],
            'bundle':bundle['archive'],'board':board['archive'],'healthy':health['healthy']}
    (root/'acceptance-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
