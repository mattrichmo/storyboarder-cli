"""Delivery operations behind the shared Service facade.

Transactions remain in the application layer; UI adapters do not write SQL.
"""
from storyboarder.domain.errors import StoryboardError
from storyboarder.media.files import thumbnail


class DeliveryOperations:
    def compose(self, owner_id):
        from storyboarder.rendering.composer import compose
        return compose(self.repo.snapshot(), owner_id, self.root)

    def export_bundle(self, owner_id, include_media=True):
        from storyboarder.rendering.exports import export_bundle
        return export_bundle(self, owner_id, include_media)

    def export_board(self, owner_id, format="html", approved_only=False):
        from storyboarder.rendering.boards import export_board
        return export_board(self, owner_id, format, approved_only)

    def doctor(self, hashes=False):
        from .recovery import doctor
        return doctor(self, hashes)

    def backup(self):
        from .recovery import backup
        return backup(self)

    def cache(self, rebuild=False):
        from storyboarder.media.files import clear_cache
        clear_cache(self.root)
        errors, count = [], 0
        if rebuild:
            for media in self.repo.snapshot()["media"]:
                try:
                    thumbnail(self.root, media)
                    count += 1
                except StoryboardError as exc:
                    errors.append({"media_id": media["id"], "message": str(exc)})
        return {"rebuilt": count, "cleared": True, "errors": errors}
