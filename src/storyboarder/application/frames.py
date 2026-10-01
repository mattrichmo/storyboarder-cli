"""Frames operations behind the shared Service facade.

Transactions remain in the application layer; UI adapters do not write SQL.
"""
from storyboarder.domain.errors import StoryboardError, InUse
from storyboarder.domain.models import uid, now, text, FRAME_STATES


class FrameOperations:
    def attach_frame(self, shot_id, media_id, notes="", provenance=None, conn=None):
        if conn is None:
            with self.repo.transaction() as current:
                return self.attach_frame(shot_id, media_id, notes, provenance, current)
        self.entity(conn, shot_id, "shot")
        self.repo.get(conn, "media", media_id)
        version = conn.execute("SELECT coalesce(max(version),0)+1 FROM frames WHERE shot_id=?", (shot_id,)).fetchone()[0]
        result = self.repo.insert(conn, "frames", {"id": uid(), "shot_id": shot_id, "media_id": media_id, "version": version, "state": "draft", "notes": text(notes), "provenance": provenance or {}, "created_at": now()})
        self.repo.event(conn, "frame.attached", shot_id, {"frame_id": result["id"], "version": version})
        return result

    def add_frame(self, shot_id, path, notes=""):
        with self.repo.transaction(False) as conn:
            self.entity(conn, shot_id, "shot")
        imported = self.import_file(path, frame_folder=uid())
        frame = self.attach_frame(shot_id, imported["media"]["id"], notes)
        self.review_intake(imported["intake"]["id"], imported["intake"]["revision"], "accepted")
        return frame

    def set_frame_state(self, frame_id, revision, state):
        if state not in FRAME_STATES:
            raise StoryboardError("Choose Draft, Selected, Approved, or Archived.")
        with self.repo.transaction() as conn:
            row = self.repo.get(conn, "frames", frame_id)
            self.repo.check(row, revision)
            self.entity(conn, row["shot_id"], "shot")
            if state in ("selected", "approved"):
                # Approved work is never silently demoted by selecting a new draft.
                current = conn.execute("SELECT * FROM frames WHERE shot_id=? AND state='approved' AND id<>?", (row["shot_id"], frame_id)).fetchone()
                if current:
                    raise InUse("Another storyboard image is already approved. Archive it or mark it as a draft before approving this one.")
                conn.execute("UPDATE frames SET state='draft',revision=revision+1 WHERE shot_id=? AND state='selected' AND id<>?", (row["shot_id"], frame_id))
            result = self.repo.update(conn, "frames", frame_id, revision, {"state": state})
            self.repo.event(conn, "frame." + state, row["shot_id"], {"frame_id": frame_id})
            return result
