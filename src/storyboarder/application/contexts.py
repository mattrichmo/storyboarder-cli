"""Contexts operations behind the shared Service facade.

Transactions remain in the application layer; UI adapters do not write SQL.
"""
from storyboarder.domain.errors import StoryboardError, Conflict
from storyboarder.domain.models import uid, text


class ContextOperations:
    def put_context(self, owner_id, key, operation="append", content="", revision=None):
        key = text(key, "Direction block name", 100)
        if not key:
            raise StoryboardError("Give this direction note a topic.")
        if operation not in ("append", "replace", "exclude"):
            raise StoryboardError("Choose whether to add to, replace, or hide earlier notes here.")
        with self.repo.transaction() as conn:
            owner = self.entity(conn, owner_id)
            if owner["kind"] == "asset":
                raise StoryboardError("Direction notes can be added to a project, sequence, scene, or shot.")
            existing = conn.execute("SELECT id FROM context_blocks WHERE owner_id=? AND key=?", (owner_id, key)).fetchone()
            if existing:
                result = self.repo.update(conn, "context_blocks", existing[0], revision, {"operation": operation, "text": text(content)})
            elif revision is not None:
                raise Conflict("This direction note is no longer available. Refresh the project and try again.")
            else:
                result = self.repo.insert(conn, "context_blocks", {"id": uid(), "owner_id": owner_id, "key": key, "operation": operation, "text": text(content)})
            self.repo.event(conn, "context.updated", owner_id, {"key": key, "operation": operation})
            return result
