from pathlib import Path
import pytest
from PIL import Image
from storyboarder.application.projects import Project, Workspace
from storyboarder.application.service import Service

@pytest.fixture
def service(tmp_path):
    return Service(Project.create(tmp_path / 'project', 'Test production'))

@pytest.fixture
def workspace(tmp_path):
    workspace = Workspace(tmp_path / 'workspace')
    workspace.init()
    return workspace

@pytest.fixture
def image_factory(tmp_path):
    counter = [0]
    def create(name=None, fmt='PNG', size=(48,32), color=None):
        counter[0] += 1
        path = tmp_path / (name or f'image-{counter[0]}.{fmt.lower()}')
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', size, color or (counter[0]*23%255,85,105)).save(path, fmt)
        return path
    return create

@pytest.fixture
def story(service, image_factory):
    location = service.create_entity('asset', 'Station', fields={'type':'location'})
    character = service.create_entity('asset', 'Caretaker', fields={'type':'character'}, tags=['winter'], aliases=['Mara'])
    prop = service.create_entity('asset', 'Brass key', fields={'type':'prop'})
    sequence = service.create_entity('sequence', 'The last morning')
    scene = service.create_entity('scene', 'Opening the station', sequence['id'], fields={'location_id':location['id'],'time':'Dawn'})
    shot = service.create_entity('shot', 'The door opens', scene['id'], fields={'action':'Mara turns the key.','framing':'Wide','duration':8})
    first = service.import_file(image_factory('first.png'))['media']
    exact = service.import_file(image_factory('exact.png'))['media']
    first_member = service.attach_media(character['id'], first['id'])
    exact_member = service.attach_media(character['id'], exact['id'])
    assignment = service.assign(shot['id'], character['id'], 'subject', exact['id'])
    return locals() | {'service':service}

@pytest.fixture(autouse=True)
def isolated_registry(tmp_path,monkeypatch):
    monkeypatch.setenv('STORYBOARDER_CONFIG_DIR', str(tmp_path/'user-config'))
