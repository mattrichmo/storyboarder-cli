"""Regressions against the audited GitHub head, before domain expansion."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from storyboarder.application.commands import execute
from storyboarder.domain.errors import StoryboardError


def test_archived_flag_includes_active_and_archived(service):
    active = service.create_entity('asset', 'Active')
    archived = service.create_entity('asset', 'Archived')
    service.lifecycle(archived['id'], archived['revision'], 'archive')
    assert {r['id'] for r in service.list_entities('asset')['items']} == {active['id']}
    assert {r['id'] for r in service.list_entities('asset', archived=True)['items']} == {active['id'], archived['id']}


@pytest.mark.parametrize('args', [
    ['not-a-command', '--json'],
    ['asset', 'create', '--unknown-option', '--json'],
    ['--json', 'shot', 'update', '--revision', 'not-an-integer'],
])
def test_json_argument_errors_are_machine_readable(args):
    result = subprocess.run([sys.executable, '-m', 'storyboarder', *args], text=True, capture_output=True, timeout=10)
    assert result.returncode == 2
    assert not result.stdout
    try:
        error = json.loads(result.stderr)
    except json.JSONDecodeError:
        pytest.fail(f'--json returned unstructured argparse text: {result.stderr[:200]}')
    assert error['error']['code'] == 'invalid_arguments'


def test_wrong_kind_update_does_not_mutate_other_domain(story):
    s = story['service']
    shot = s.list_entities('shot')['items'][0]
    with pytest.raises(StoryboardError):
        execute(s, 'asset.update', {'id': shot['id'], 'revision': shot['revision'], 'title': 'Wrong domain'})
    assert s.get('entities', shot['id'])['title'] == shot['title']


@pytest.mark.parametrize('invalid', [None, [], 'not-a-mapping', 3])
def test_malformed_authored_fields_are_domain_errors(story, invalid):
    s = story['service']
    shot = s.list_entities('shot')['items'][0]
    with pytest.raises(StoryboardError):
        s.update_entity(shot['id'], shot['revision'], {'fields': invalid})


def test_optional_limit_null_uses_documented_default(story):
    result = execute(story['service'], 'shot.list', {'limit': None})
    assert result['limit'] == 200


def test_export_archive_edit_is_not_silently_overwritten(story):
    s = story['service']
    result = s.export_bundle(s.project.id)
    path = s.root / result['archive']
    path.write_bytes(b'user-modified-archive')
    with pytest.raises(StoryboardError, match='edited|modified'):
        s.export_bundle(s.project.id)
    assert path.read_bytes() == b'user-modified-archive'
