"""Provider-neutral script protocol. Not an operating-system security sandbox."""
from pathlib import Path
import hashlib
import json
import os
import signal
import shutil
import subprocess
import tempfile
import threading
import time
from filelock import FileLock, Timeout
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from storyboarder import JOB_VERSION
from storyboarder.domain.errors import StoryboardError, Conflict, InUse
from storyboarder.domain.models import uid, now, title, text, ASSET_TYPES, dumps, validate_fields
from storyboarder.media.files import safe_path, inspect_image, sha256, MAX_FILE_BYTES, FORMATS
from storyboarder.rendering.exports import json_file
from .registry import ScriptRegistry

MAX_OUTPUTS = 16
MAX_OUTPUT_BYTES = 250 * 1024 * 1024
MAX_LOG_BYTES = 1024 * 1024


class OutputEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    path: str = Field(min_length=1, max_length=300)
    title: str = Field(default="", max_length=240)
    notes: str = Field(default="", max_length=100000)
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class ResultManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_id: str = Field(alias="schema")
    provider: str = Field(default="external-script", max_length=200)
    model: str = Field(default="unspecified", max_length=200)
    outputs: list[OutputEntry] = Field(min_length=1, max_length=MAX_OUTPUTS)


class Jobs:
    def __init__(self, service, registry=None):
        self.service, self.repo = service, service.repo
        self.registry = registry or ScriptRegistry()

    def create(self, script, target="asset", shot_id=None, title_value="Generated reference", asset_type="reference", prompt=""):
        registered = self.registry.get(script)
        if target not in ("asset", "frame") or asset_type not in ASSET_TYPES:
            raise StoryboardError("Choose an asset or frame output and a supported asset type.")
        if target == "frame" and not shot_id:
            raise StoryboardError("Choose a shot before requesting frame candidates.")
        with self.repo.transaction(False) as conn:
            if shot_id:
                self.service.entity(conn, shot_id, "shot")
        source_event = self.service.change_token()['event_id']
        composition = self.service.compose(shot_id or self.service.project.id)
        from storyboarder.application.provenance import Provenance
        source_provenance = Provenance(self.service).pins(shot_id) if shot_id else []
        if not composition["valid"]:
            raise StoryboardError("Resolve missing selected media before creating a job request.", {"validation": composition["validation"]})
        job_id = uid()
        references = [{**m, "path": f"inputs/{m['id']}{FORMATS[m['format']]}"} for m in composition["media"]]
        request = {"schema": JOB_VERSION, "job_id": job_id, "project_id": self.service.project.id, "target": {"kind": target, "shot_id": shot_id, "title": title(title_value), "asset_type": asset_type}, "prompt": text(prompt), "context": composition["context"], "references": references, "constraints": {"allowed_formats": sorted(FORMATS), "max_file_bytes": registered.get("max_file_bytes", MAX_FILE_BYTES), "max_output_bytes": registered.get("max_output_bytes", MAX_OUTPUT_BYTES), "max_outputs": MAX_OUTPUTS}, "destination": "output/", "created_at": now()}
        request["source_provenance"] = source_provenance
        request["authored"] = {
            "owner": {key: composition["owner"][key] for key in ("id", "kind", "title", "description", "fields", "revision")},
            "shots": [{"id": shot["id"], "title": shot["title"], "fields": shot["fields"], "revision": shot["revision"], "context": shot["context"],
                       "assignments": [{"asset_id": a["asset_id"], "asset_title": a["asset"]["title"], "role": a["role"], "media_id": a["media_id"]} for a in shot["assignments"]]}
                      for scene in composition["scenes"] for shot in scene["shots"]]
        }
        if len(dumps(request).encode()) > 10*1024*1024:
            raise StoryboardError("Request snapshot exceeds 10 MiB. Choose a specific shot rather than the whole project.")
        with self.repo.transaction() as conn:
            if conn.execute('SELECT coalesce(max(id),0) FROM events').fetchone()[0] != source_event:
                raise Conflict('The project changed while the request was composed. Refresh and prepare the request again.')
            row = self.repo.insert(conn, "jobs", {"id": job_id, "status": "queued", "script": script, "target": target, "shot_id": shot_id, "title": title(title_value), "asset_type": asset_type, "request": request, "created_at": now(), "updated_at": now()})
            for source in source_provenance:
                conn.execute('INSERT INTO job_source_pins VALUES(?,?,?)', (job_id, source['node_id'], dumps(source)))
            for reference in references:
                conn.execute('INSERT INTO job_media_pins VALUES(?,?,?)', (job_id, reference['id'], reference['sha256']))
            self.repo.event(conn, "job.queued", job_id)
            return row

    def cancel(self, job_id, revision):
        with self.repo.transaction() as conn:
            row = self.repo.get(conn, "jobs", job_id)
            self.repo.check(row, revision)
            if row["status"] not in ("queued", "running"):
                raise StoryboardError("Only queued or running jobs can be cancelled.")
            result = self.repo.update(conn, "jobs", job_id, revision, {"status": "cancelled"})
            self.repo.event(conn, "job.cancelled", job_id)
            return result

    def _run_lock(self, job_id):
        self.service.get("jobs", job_id)
        directory = safe_path(self.service.root, f".storyboarder/jobs/{job_id}")
        directory.mkdir(parents=True, exist_ok=True)
        return FileLock(str(directory / "run.lock"), timeout=0)

    def retry(self, job_id, revision):
        try:
            with self._run_lock(job_id):
                return self._retry(job_id, revision)
        except Timeout as exc:
            raise InUse("The previous run is still stopping. Refresh its status before retrying.") from exc

    def _retry(self, job_id, revision):
        with self.repo.transaction() as conn:
            row = self.repo.get(conn, "jobs", job_id)
            self.repo.check(row, revision)
            if row["approved"]:
                raise InUse("Approved job outputs are immutable history. Create a new request for another generation.")
            if row["status"] not in ("failed", "cancelled"):
                raise StoryboardError("Retry only failed or cancelled jobs. A successful result should be reviewed or replaced by a new request.")
            result = self.repo.update(conn, "jobs", job_id, revision, {"status": "queued", "result": {}})
            self.repo.event(conn, "job.retry_queued", job_id)
            return result

    def _finish(self, job_id, status, result):
        with self.repo.transaction() as conn:
            row = self.repo.get(conn, "jobs", job_id)
            if result.get("attempt") != row["attempt"] or row["status"] not in ("running", "cancelled"):
                return row  # A stale worker cannot overwrite a retried or completed run.
            if row["status"] == "cancelled":
                status = "cancelled"
            updated = self.repo.update(conn, "jobs", job_id, row["revision"], {"status": status, "result": result})
            self.repo.event(conn, "job." + status, job_id)
            return updated

    @staticmethod
    def _stop(process):
        if os.name == "posix":
            # The script runs in a new session, so its pid is also the process
            # group id. Signal the group even when the direct child has already
            # exited: descendants may still be running in that group.
            group_id = process.pid
            try:
                os.killpg(group_id, signal.SIGTERM)
            except OSError:
                pass

            deadline = time.monotonic() + 2
            while True:
                try:
                    os.killpg(group_id, 0)
                except ProcessLookupError:
                    break
                except OSError:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    try:
                        os.killpg(group_id, signal.SIGKILL)
                    except OSError:
                        pass
                    break
                try:
                    process.wait(timeout=min(0.05, remaining))
                except (OSError, subprocess.TimeoutExpired):
                    pass
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))

            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    process.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            except OSError:
                pass
            return

        try:
            if process.poll() is None:
                process.send_signal(signal.CTRL_BREAK_EVENT)
        except OSError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        except OSError:
            pass
        try:
            # taskkill's tree mode is the available Windows process-tree
            # cleanup mechanism. Keep it bounded so cancellation cannot hang.
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
        except OSError:
            pass

    def _validate_outputs(self, output, manifest, max_file_bytes=MAX_FILE_BYTES, max_output_bytes=MAX_OUTPUT_BYTES):
        try:
            parsed = ResultManifest.model_validate(manifest)
        except ValidationError as exc:
            raise StoryboardError(f"Invalid result manifest: {exc}") from exc
        if parsed.schema_id != "storyboarder.result/v1":
            raise StoryboardError("Unsupported external result contract.")
        if len({o.key for o in parsed.outputs}) != len(parsed.outputs) or len({o.path for o in parsed.outputs}) != len(parsed.outputs):
            raise StoryboardError("Every result needs a unique key and file path.")
        validated, total = [], 0
        for entry in parsed.outputs:
            source = safe_path(output, entry.path, must_exist=True)
            info = inspect_image(source)
            if info["size"] > max_file_bytes:
                raise StoryboardError("Output image exceeds the registered per-file size limit.")
            total += info["size"]
            if total > max_output_bytes:
                raise StoryboardError("Combined output images exceed the registered size limit.")
            if entry.sha256 and entry.sha256 != info["sha256"]:
                raise StoryboardError("Result hash does not match the output file.")
            validated.append({**entry.model_dump(), **info})
        return {"schema": parsed.schema_id, "provider": parsed.provider, "model": parsed.model, "outputs": validated}

    def run(self, job_id, revision):
        try:
            with self._run_lock(job_id):
                return self._run(job_id, revision)
        except Timeout as exc:
            raise InUse("This job already has an active runner. Cancel it or wait for its current status.") from exc

    def _run(self, job_id, revision):
        with self.repo.transaction() as conn:
            row = self.repo.get(conn, "jobs", job_id)
            self.repo.check(row, revision)
            if row["status"] != "queued":
                raise Conflict("Only queued jobs can be launched. Retries require an explicit retry action.")
            script = self.registry.get(row["script"])
            row = self.repo.update(conn, "jobs", job_id, revision, {"status": "running", "attempt": row["attempt"] + 1})
            self.repo.event(conn, "job.running", job_id)
        work = Path(tempfile.mkdtemp(prefix="storyboarder-run-"))
        storage = safe_path(self.service.root, f".storyboarder/jobs/{job_id}/attempt-{row['attempt']}")
        process, started, stopped = None, now(), False
        stdout, stderr = bytearray(), bytearray()
        try:
            storage.mkdir(parents=True, exist_ok=False)
            (work / "inputs").mkdir()
            (work / "output").mkdir()
            for reference in row["request"]["references"]:
                media = self.service.get("media", reference["id"])
                source = safe_path(self.service.root, media["path"], must_exist=True)
                destination = safe_path(work, reference["path"])
                shutil.copyfile(source, destination)
                if sha256(destination) != reference["sha256"]:
                    raise StoryboardError("A source reference changed after this request was queued. Create a new request after restoring the reference.")
            request = {**row["request"], "attempt": row["attempt"]}
            json_file(work / "request.json", request)
            json_file(storage / "request.json", request)
            # Never pass the launch token or a project/database path. Only explicit env names.
            base_keys = ("PATH", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP")
            env = {k: os.environ[k] for k in (*base_keys, *script["env_keys"]) if k in os.environ}
            env["PYTHONUNBUFFERED"] = "1"
            process = subprocess.Popen(
                [*script["command"], str(work / "request.json"), str(work / "output")],
                cwd=work,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                start_new_session=os.name == "posix",
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            def drain(stream, store):
                while chunk := stream.read(8192):
                    if len(store) < MAX_LOG_BYTES:
                        store.extend(chunk[:MAX_LOG_BYTES-len(store)])
                stream.close()
            threads = [threading.Thread(target=drain, args=(process.stdout, stdout), daemon=True), threading.Thread(target=drain, args=(process.stderr, stderr), daemon=True)]
            for thread in threads:
                thread.start()
            deadline = time.monotonic() + script["timeout"]
            while process.poll() is None:
                if time.monotonic() > deadline:
                    raise StoryboardError(f"Script exceeded its {script['timeout']}-second timeout.")
                if self.service.get("jobs", job_id)["status"] == "cancelled":
                    raise StoryboardError("Run cancelled by the user.")
                total = 0
                count = 0
                for file in (work / "output").rglob("*"):
                    count += 1
                    if file.is_symlink():
                        raise StoryboardError("Script output contains a symbolic link.")
                    if file.is_file():
                        total += file.stat().st_size
                    if count > 128 or total > script.get("max_output_bytes", MAX_OUTPUT_BYTES) + 1024*1024:
                        raise StoryboardError("Script exceeded the working output file or size limit.")
                time.sleep(0.1)
            for thread in threads:
                thread.join(timeout=2)
            if process.returncode:
                raise StoryboardError(f"Script exited with code {process.returncode}. Review stderr before retrying.")
            result_path = safe_path(work / "output", "result.json", must_exist=True)
            if result_path.stat().st_size > 1024*1024:
                raise StoryboardError("Result manifest exceeds 1 MiB.")
            result = self._validate_outputs(work / "output", json.loads(result_path.read_text()), script.get("max_file_bytes", MAX_FILE_BYTES), script.get("max_output_bytes", MAX_OUTPUT_BYTES))
            (storage / "output").mkdir()
            for output in result["outputs"]:
                source = safe_path(work / "output", output["path"], must_exist=True)
                name = output["key"] + FORMATS[output["format"]]
                shutil.copyfile(source, storage / "output" / name)
                output["stored_path"] = (storage / "output" / name).relative_to(self.service.root).as_posix()
            result.update({"script": script["name"], "attempt": row["attempt"], "started_at": started, "finished_at": now(), "request_sha256": hashlib.sha256(dumps(request).encode()).hexdigest(), "return_code": process.returncode, "review": "pending"})
            json_file(storage / "result.json", result)
            return self._finish(job_id, "succeeded", result)
        except (StoryboardError, OSError, ValueError) as exc:
            if process:
                self._stop(process)
                stopped = True
            result = {"script": script["name"], "attempt": row["attempt"], "started_at": started, "finished_at": now(), "error": str(exc), "return_code": process.returncode if process else None, "outputs": []}
            if storage.exists():
                json_file(storage / "result.json", result)
            return self._finish(job_id, "failed", result)
        finally:
            if process and not stopped:
                self._stop(process)
            if storage.exists():
                for name, data in (("stdout.log", stdout), ("stderr.log", stderr)):
                    # Credentials explicitly supplied through env are redacted from saved logs.
                    decoded = bytes(data).decode("utf-8", errors="replace")
                    for key in script["env_keys"]:
                        value = os.environ.get(key)
                        if value:
                            decoded = decoded.replace(value, "[REDACTED]")
                    (storage / name).write_text(decoded, encoding="utf-8")
            shutil.rmtree(work, ignore_errors=True)

    def preview(self, job_id):
        row = self.service.get("jobs", job_id)
        result = dict(row)
        result["logs"] = {}
        if row["attempt"]:
            for filename in ("stdout.log", "stderr.log"):
                file = safe_path(self.service.root, f".storyboarder/jobs/{job_id}/attempt-{row['attempt']}/{filename}")
                result["logs"][filename] = file.read_text() if file.is_file() else ""
        result["outputs"] = row["result"].get("outputs", [])
        return result

    def approve(self, job_id, revision):
        row = self.service.get("jobs", job_id)
        if row["approved"]:
            with self.repo.transaction(False) as conn:
                return {"job_id": job_id, "already_imported": True, "outputs": [dict(r) for r in conn.execute("SELECT * FROM job_outputs WHERE job_id=? ORDER BY output_key", (job_id,))]}
        self.repo.check(row, revision)
        if row["status"] != "succeeded":
            raise StoryboardError("Only successful, validated results can be approved for import.")
        # Validate the complete set before registering anything. Failed partial imports
        # remain recoverable intake, while job_outputs provides per-output idempotency.
        prepared = []
        for output in row["result"].get("outputs", []):
            source = safe_path(self.service.root, output["stored_path"], must_exist=True)
            if inspect_image(source)["sha256"] != output["sha256"]:
                raise StoryboardError("Pending output changed after validation. Refuse import; create a fresh job.")
            prepared.append((output, source))
        for output, source in prepared:
            with self.repo.transaction(False) as conn:
                existing = conn.execute("SELECT 1 FROM job_outputs WHERE job_id=? AND output_key=?", (job_id, output["key"])).fetchone()
            if existing:
                continue
            imported = self.service.import_file(source, original_path=f"external-job:{job_id}/{output['key']}")
            provenance = {"job_id": job_id, "script": row["script"], "provider": row["result"]["provider"], "model": row["result"]["model"], "attempt": row["attempt"], "request_sha256": row["result"]["request_sha256"], "output_sha256": output["sha256"], "started_at": row["result"]["started_at"], "finished_at": row["result"]["finished_at"], "prompt_snapshot": row["request"]["prompt"]}
            with self.repo.transaction() as conn:
                if conn.execute("SELECT 1 FROM job_outputs WHERE job_id=? AND output_key=?", (job_id, output["key"])).fetchone():
                    # A concurrent approval won. Accept the duplicate intake only.
                    self.repo.update(conn, "intake", imported["intake"]["id"], 1, {"state": "accepted"})
                    continue
                entity_id, frame_id = None, None
                if row["target"] == "frame":
                    frame = self.service.attach_frame(row["shot_id"], imported["media"]["id"], output["notes"], provenance, conn=conn)
                    frame_id = frame["id"]
                else:
                    asset = self.repo.insert(conn, "entities", {"id": uid(), "kind": "asset", "title": title(output["title"] or row["title"]), "description": output["notes"], "fields": validate_fields("asset", {"type": row["asset_type"], "notes": "Imported from an image tool result."}), "created_at": now(), "updated_at": now()})
                    entity_id = asset["id"]
                    self.service.attach_media(entity_id, imported["media"]["id"], conn=conn)
                conn.execute("INSERT INTO job_outputs VALUES (?,?,?,?,?)", (job_id, output["key"], imported["media"]["id"], entity_id, frame_id))
                self.repo.update(conn, "intake", imported["intake"]["id"], 1, {"state": "accepted"})
                self.repo.event(conn, "job.output_imported", job_id, provenance)
        with self.repo.transaction() as conn:
            current = self.repo.get(conn, "jobs", job_id)
            if not current["approved"]:
                self.repo.update(conn, "jobs", job_id, current["revision"], {"approved": 1, "result": {**current["result"], "review": "imported"}})
            return {"job_id": job_id, "already_imported": False, "outputs": [dict(r) for r in conn.execute("SELECT * FROM job_outputs WHERE job_id=? ORDER BY output_key", (job_id,))]}
