class StoryboardError(Exception):
    """Expected error. The code is stable across CLI and HTTP interfaces."""
    code = "invalid"
    status = 422

    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}

    def as_dict(self):
        return {"code": self.code, "message": str(self), "details": self.details}


class NotFound(StoryboardError):
    code = "not_found"
    status = 404


class Conflict(StoryboardError):
    code = "revision_conflict"
    status = 409


class UnsafePath(StoryboardError):
    code = "unsafe_path"
    status = 403


class InUse(StoryboardError):
    code = "in_use"
    status = 409
