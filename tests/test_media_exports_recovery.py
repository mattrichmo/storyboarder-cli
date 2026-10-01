from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import shutil
import zipfile
import pytest
from PIL import Image
from storyboarder.application.projects import Project
from storyboarder.application.service import Service
from storyboarder.application.recovery import restore
from storyboarder.domain.errors import StoryboardError, UnsafePath
from storyboarder.media.files import safe_path, thumbnail


@pytest.mark.parametrize('fmt',['PNG','JPEG','WEBP','TIFF','BMP'])
def test_supported_images_hashes_relative_paths(service,image_factory,fmt):
    source=image_factory(fmt=fmt)
    imported=service.import_file(source)
    media=imported['media']
    assert media['format']==fmt and media['width']==48 and media['height']==32
    assert not Path(media['path']).is_absolute()
    assert (service.root/media['path']).read_bytes()==source.read_bytes()
    assert media['sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
    assert service.doctor(True)['healthy']


def test_duplicate_hash_preserves_each_intake_path(service,image_factory):
    source=image_factory()
    first=service.import_file(source)
    again=service.import_file(source,original_name='another.png',original_path='archive/another.png')
    assert first['media']['id']==again['media']['id'] and again['duplicate']
    assert first['intake']['id']!=again['intake']['id']
    assert again['intake']['original_path']=='archive/another.png'
    assert len(service.state()['media'])==1
    assert len(service.state()['intake'])==2


def test_accept_discard_and_media_tags(service,image_factory):
    imported=service.import_file(image_factory())
    accepted=service.review_intake(imported['intake']['id'],1,'accepted',create_title='Caretaker',create_type='character',tags=['winter'])
    assert accepted['state']=='accepted'
    asset=service.list_entities('asset')['items'][0]
    assert asset['fields']['type']=='character' and asset['tags']==['winter']
    again=service.import_file(image_factory())
    discarded=service.review_intake(again['intake']['id'],1,'discarded')
    assert discarded['state']=='discarded'
    assert (service.root/again['media']['path']).exists()
    tagged=service.tag_media(again['media']['id'],1,['discarded-source'])
    assert tagged['tags']==['discarded-source']


def test_folder_import_explicit_recursion_skips_unsupported(service,image_factory,tmp_path):
    source=tmp_path/'references'
    image_factory('references/first.png')
    image_factory('references/subfolder/second.png')
    (source/'notes.txt').write_text('Not an image')
    shallow=service.import_path(source)
    assert len(shallow['items'])==1 and len(shallow['skipped'])==1
    deep=service.import_path(source,True)
    assert len(deep['items'])==2 and len(deep['skipped'])==1


@pytest.mark.parametrize('body,name',[(b'<svg></svg>','unsafe.svg'),(b'not an image','fake.png'),(b'','empty.jpg')])
def test_bad_images_rejected_without_records(service,tmp_path,body,name):
    path=tmp_path/name;path.write_bytes(body)
    with pytest.raises(StoryboardError):service.import_file(path)
    assert not service.state()['media']
    assert not list((service.root/'.storyboarder/staging').glob('*.part'))


def test_multiframe_image_rejected(service,tmp_path):
    path=tmp_path/'animated.webp'
    frames=[Image.new('RGB',(20,20),'red'),Image.new('RGB',(20,20),'blue')]
    frames[0].save(path,'WEBP',save_all=True,append_images=frames[1:],duration=100,loop=0)
    with pytest.raises(StoryboardError):service.import_file(path)


@pytest.mark.parametrize('path',['../secret','/etc/passwd','x/../../secret','x\\..\\secret','x\x00y'])
def test_paths_never_escape_root(tmp_path,path):
    with pytest.raises(StoryboardError):safe_path(tmp_path,path)


def test_symlink_paths_rejected(tmp_path):
    inside=tmp_path/'inside';outside=tmp_path/'outside';inside.mkdir();outside.mkdir()
    try:(inside/'escape').symlink_to(outside,target_is_directory=True)
    except (OSError,NotImplementedError):pytest.skip('This user cannot create symlinks')
    with pytest.raises(StoryboardError):safe_path(inside,'escape/data')


def test_changed_original_reported_and_duplicate_not_silently_accepted(service,image_factory):
    source=image_factory();imported=service.import_file(source)
    managed=service.root/imported['media']['path'];managed.write_bytes(b'changed')
    assert not service.doctor(True)['healthy']
    with pytest.raises(StoryboardError):service.import_file(source)


def test_cache_is_rebuildable_and_does_not_modify_original(story):
    s=story['service'];media=story['exact'];before=(s.root/media['path']).read_bytes()
    thumb=thumbnail(s.root,media,160)
    assert thumb.exists() and Image.open(thumb).width<=160
    s.cache(False)
    assert not thumb.exists()
    s.cache(True)
    assert (s.root/media['path']).read_bytes()==before
    with pytest.raises(StoryboardError):thumbnail(s.root,media,99999)


def test_bundle_contains_exact_selection_not_default_and_is_deterministic(story):
    s=story['service'];owner=story['scene']['id']
    result=s.export_bundle(owner)
    archive=s.root/result['archive'];before=archive.read_bytes()
    second=s.export_bundle(owner)
    assert before==(s.root/second['archive']).read_bytes()
    with zipfile.ZipFile(archive) as z:
        doc=json.loads(z.read('scene.json'))
        selected=doc['scenes'][0]['shots'][0]['assignments'][0]['media']
        assert selected['id']==story['exact']['id']
        assert z.read(selected['bundle_path'])==(s.root/story['exact']['path']).read_bytes()
        assert not any(story['first']['id'] in p for p in z.namelist())
        assert 'context-provenance.json' in z.namelist()
        manifest=json.loads(z.read('manifest.json'))
        assert all(hashlib.sha256(z.read(f['path'])).hexdigest()==f['sha256'] for f in manifest['files'])
        assert all(not Path(name).is_absolute() for name in z.namelist())


def test_modified_manifest_is_not_reused(story):
    s=story['service'];result=s.export_bundle(story['scene']['id'])
    (s.root/result['path']/'manifest.json').write_text('{}')
    with pytest.raises(StoryboardError,match='edited|modified'):s.export_bundle(story['scene']['id'])


def test_concurrent_exports_publish_identical_complete_zip(story):
    s=story['service'];owner=story['scene']['id']
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda _:s.export_bundle(owner),range(3)))
    assert len({r['archive'] for r in results})==1
    with zipfile.ZipFile(s.root/results[0]['archive']) as z:assert z.testzip() is None
    assert not list((s.root/'exports/scenes').glob('*.part-*'))


def test_missing_selected_file_prevents_self_contained_export(story):
    s=story['service'];(s.root/story['exact']['path']).unlink()
    assert not s.compose(story['shot']['id'])['valid']
    with pytest.raises(StoryboardError):s.export_bundle(story['scene']['id'])
    data=s.export_bundle(story['scene']['id'],False)
    assert not data['manifest']['self_contained']
    with pytest.raises(StoryboardError):s.export_board(story['scene']['id'])


def test_all_board_outputs_real_and_offline(story):
    s=story['service'];shot=story['shot']
    frame=s.attach_frame(shot['id'],story['first']['id']);s.set_frame_state(frame['id'],1,'approved')
    result=s.export_board(story['sequence']['id'],'all')
    directory=s.root/result['path']
    assert (directory/'board.pdf').read_bytes().startswith(b'%PDF-')
    assert Image.open(directory/'board-001.png').size==(1800,1960)
    text=(directory/'board.html').read_text()
    assert 'Approved storyboard image' in text and 'https://' not in text
    assert 'board.css' in text
    assert (directory/'scene.json').exists()
    before=(s.root/result['archive']).read_bytes()
    assert before==(s.root/s.export_board(story['sequence']['id'],'all')['archive']).read_bytes()


def test_html_tiff_uses_derived_jpeg_keeps_exact_original(story):
    s=story['service'];tiff=s.import_file(story['image_factory'](fmt='TIFF'))['media']
    s.attach_media(story['character']['id'],tiff['id'])
    s.update_assignment(story['assignment']['id'],1,'subject',tiff['id'])
    result=s.export_board(story['scene']['id'],'html');directory=s.root/result['path']
    assert f"previews/{tiff['id']}.jpg" in (directory/'board.html').read_text()
    doc=json.loads((directory/'scene.json').read_text())
    exact=doc['scenes'][0]['shots'][0]['assignments'][0]['media']
    assert (directory/exact['bundle_path']).read_bytes()==(s.root/tiff['path']).read_bytes()


def test_backup_restore_and_move_keep_ids_hashes(story,tmp_path):
    s=story['service'];result=s.backup();archive=s.root/result['path']
    dest=tmp_path/'restored';restored=restore(archive,dest)
    assert restored['id']==s.project.id
    fresh=Service(dest)
    assert fresh.state()['entities']==s.state()['entities']
    assert fresh.doctor(True)['healthy']
    assert fresh.compose(story['shot']['id'])['valid']
    moved=tmp_path/'moved-restored';shutil.move(dest,moved)
    assert Service(moved).doctor(True)['healthy']
    with pytest.raises(StoryboardError):restore(archive,moved)


@pytest.mark.parametrize('bad_name',['../escaped','/absolute','a\\b','a/../../escape'])
def test_restore_zip_traversal_rejected(tmp_path,bad_name):
    archive=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr(bad_name,'bad')
    with pytest.raises(StoryboardError):restore(archive,tmp_path/'destination')
    assert not (tmp_path/'destination').exists()


def test_restore_detects_corrupted_media(story,tmp_path):
    s=story['service'];original=s.root/s.backup()['path'];corrupt=tmp_path/'corrupt.zip'
    with zipfile.ZipFile(original) as source,zipfile.ZipFile(corrupt,'w') as dest:
        for name in source.namelist():dest.writestr(name,b'corrupt' if name.startswith('media/') else source.read(name))
    with pytest.raises(StoryboardError):restore(corrupt,tmp_path/'not-created')
    assert not (tmp_path/'not-created').exists()
