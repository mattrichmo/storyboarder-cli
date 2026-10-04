from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import os
import signal
import sys
import time
import pytest
from storyboarder.automation.registry import ScriptRegistry
from storyboarder.automation.jobs import Jobs
from storyboarder.domain.errors import StoryboardError, InUse, Conflict

SAMPLE=Path(__file__).parents[1]/'examples'/'sample_adapter.py'

def register_sample(**kwargs):
    registry=ScriptRegistry()
    registry.register('sample',[sys.executable,str(SAMPLE.resolve())],**kwargs)
    return registry


def test_external_roundtrip_pending_preview_then_idempotent_import(story):
    s=story['service'];register_sample();jobs=Jobs(s)
    existing=s.attach_frame(story['shot']['id'],story['first']['id'])
    s.set_frame_state(existing['id'],1,'approved')
    request=jobs.create('sample','frame',story['shot']['id'],'New candidate',prompt='Soft morning light.')
    assert request['status']=='queued'
    assert request['request']['authored']['shots'][0]['fields']['action']=='Mara turns the key.'
    result=jobs.run(request['id'],request['revision'])
    assert result['status']=='succeeded',result['result']
    assert not result['approved'] and len(s.state()['frames'])==1
    preview=jobs.preview(result['id'])
    assert preview
    approved=jobs.approve(result['id'],result['revision'])
    assert service_job(s,request['id'])['approved']
    current=service_job(s,request['id'])
    again=jobs.approve(current['id'],current['revision'])
    assert again['already_imported'] and len(s.state()['frames'])==2
    assert s.get('frames',existing['id'])['state']=='approved'
    candidate=next(f for f in s.state()['frames'] if f['id']!=existing['id'])
    assert candidate['state']=='draft' and candidate['provenance']['job_id']==request['id']
    with pytest.raises(StoryboardError):jobs.retry(current['id'],current['revision'])


def test_result_approval_rechecks_output_hashes(service):
    register_sample();jobs=Jobs(service);queued=jobs.create('sample')
    result=jobs.run(queued['id'],1)
    output=result['result']['outputs'][0]
    (service.root/output['stored_path']).write_bytes(b'modified')
    with pytest.raises(StoryboardError):jobs.approve(result['id'],result['revision'])
    assert service.list_entities('asset')['total']==0


def test_script_not_discovered_or_auto_executed(service,tmp_path):
    (service.root/'generate.py').write_text('raise RuntimeError("should never run")')
    with pytest.raises(StoryboardError):Jobs(service).create('generate')
    assert not service.state()['jobs']


@pytest.mark.parametrize('command,timeout,keys',[
 ('python script.py',120,[]), ([],120,[]),(['surely-no-such-executable'],120,[]),
 ([sys.executable],0,[]),([sys.executable],True,[]),([sys.executable],3601,[]),
 ([sys.executable],120,['API_KEY=value']),([sys.executable],120,['lower-case-key']),
])
def test_registry_rejects_unsafe_configuration(command,timeout,keys):
    with pytest.raises(StoryboardError):ScriptRegistry().register('bad',command,timeout,keys)


def test_timeout_failed_retry_explicit_and_logs_secret_redacted(service,tmp_path,monkeypatch):
    script=tmp_path/'slow.py';script.write_text("import os,time\nprint(os.environ['TEST_SECRET'],flush=True)\ntime.sleep(5)\n")
    monkeypatch.setenv('TEST_SECRET','credential-for-redaction-test')
    reg=ScriptRegistry();reg.register('slow',[sys.executable,str(script)],timeout=1,env_keys=['TEST_SECRET'])
    jobs=Jobs(service);queued=jobs.create('slow');start=time.monotonic();result=jobs.run(queued['id'],1)
    assert time.monotonic()-start<5
    assert result['status']=='failed' and 'timeout' in result['result']['error']
    assert 'credential-for-redaction-test' not in json.dumps(result)
    assert 'credential-for-redaction-test' not in json.dumps(queued['request'])
    again=jobs.retry(result['id'],result['revision'])
    assert again['status']=='queued' and again['attempt']==1
    cancelled=jobs.cancel(again['id'],again['revision']);assert cancelled['status']=='cancelled'


def test_active_cancel_retry_serializes_old_worker(service,tmp_path):
    script=tmp_path/'slow.py';script.write_text('import time\ntime.sleep(20)\n')
    ScriptRegistry().register('slow',[sys.executable,str(script)],timeout=30)
    jobs=Jobs(service);queued=jobs.create('slow')
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(jobs.run,queued['id'],1)
        for _ in range(100):
            current=service.get('jobs',queued['id'])
            if current['status']=='running':break
            time.sleep(.02)
        cancelled=jobs.cancel(current['id'],current['revision'])
        try: jobs.retry(cancelled['id'],cancelled['revision'])
        except (InUse,Conflict):pass
        else:pytest.fail('Retry must not race an active runner.')
        finished=future.result(timeout=5)
    assert finished['status']=='cancelled'
    retried=jobs.retry(finished['id'],finished['revision'])
    stale=jobs._finish(finished['id'],'failed',{'attempt':1,'error':'old worker'})
    assert stale['status']=='queued' and stale['revision']==retried['revision']


@pytest.mark.skipif(os.name != 'posix', reason='process-group descendant cleanup requires POSIX')
def test_exited_script_parent_does_not_leave_term_ignoring_descendant(service,tmp_path):
    pid_file=tmp_path/'descendant.pid'
    script=tmp_path/'parent_exits.py'
    child_code=(
        'import os,signal,sys,time\n'
        'signal.signal(signal.SIGTERM, signal.SIG_IGN)\n'
        'with open(sys.argv[1], "w") as f: f.write(str(os.getpid()))\n'
        'time.sleep(60)\n'
    )
    script.write_text(
        'import pathlib,subprocess,sys,time\n'
        f'pid_file=pathlib.Path({str(pid_file)!r})\n'
        f'child_code={child_code!r}\n'
        'subprocess.Popen([sys.executable,"-c",child_code,str(pid_file)], '
        'stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n'
        'deadline=time.monotonic()+5\n'
        'while not pid_file.exists() and time.monotonic()<deadline: time.sleep(.01)\n'
        'if not pid_file.exists(): raise RuntimeError("descendant did not start")\n'
    )
    ScriptRegistry().register('parent-exits',[sys.executable,str(script)],timeout=10)
    jobs=Jobs(service)
    queued=jobs.create('parent-exits')
    started=time.monotonic()
    try:
        result=jobs.run(queued['id'],queued['revision'])
        elapsed=time.monotonic()-started
        assert result['status']=='failed'
        descendant_pid=int(pid_file.read_text())

        def descendant_running():
            stat_file=Path(f'/proc/{descendant_pid}/stat')
            if stat_file.is_file():
                state=stat_file.read_text().rsplit(')',1)[1].split()[0]
                return state not in ('Z','X')
            try:
                os.kill(descendant_pid,0)
                return True
            except ProcessLookupError:
                return False

        for _ in range(50):
            if not descendant_running():
                break
            time.sleep(.02)
        assert not descendant_running(), 'the TERM-ignoring descendant survived job cleanup'
        assert elapsed < 8, 'job cleanup should remain bounded'
    finally:
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
            except (ProcessLookupError, ValueError):
                pass


def test_registered_output_limit_enforced(service):
    register_sample(max_file_bytes=100,max_output_bytes=1000)
    jobs=Jobs(service);queued=jobs.create('sample')
    assert queued['request']['constraints']['max_file_bytes']==100
    result=jobs.run(queued['id'],1)
    assert result['status']=='failed' and 'limit' in result['result']['error']


@pytest.mark.parametrize('manifest',[
 {'schema':'wrong','outputs':[{'key':'a','path':'x.png'}]},
 {'schema':'storyboarder.result/v1','outputs':[]},
 {'schema':'storyboarder.result/v1','outputs':[{'key':'a','path':'../x.png'}]},
 {'schema':'storyboarder.result/v1','outputs':[{'key':'a','path':'x.png','secret':'not a contract field'}]},
 {'schema':'storyboarder.result/v1','outputs':[{'key':'a','path':'x.png'},{'key':'a','path':'x.png'}]},
])
def test_malformed_results_rejected(service,tmp_path,manifest):
    with pytest.raises(StoryboardError):Jobs(service)._validate_outputs(tmp_path,manifest)


def service_job(service,job_id):
    return service.get('jobs',job_id)
