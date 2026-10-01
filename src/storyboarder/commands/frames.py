"""Frames command registrations; handlers use the application facade."""
from .core import F, FRAME_STATES, ID, REV, register


register("frame.add", "Add storyboard image from file", [F("shot_id", "Shot", required=True, source="shots"), F("path", "Image file", required=True), F("notes", "Notes", type="textarea")], lambda s, p: s.add_frame(p["shot_id"], p["path"], p.get("notes", "")), page="frames", browser=False)

register("frame.attach", "Use project image as storyboard frame", [F("shot_id", "Shot", required=True, source="shots"), F("media_id", "Image", required=True, source="media"), F("notes", "Notes", type="textarea")], lambda s, p: s.attach_frame(p["shot_id"], p["media_id"], p.get("notes", "")), page="frames")

register("frame.state", "Update storyboard image status", [ID("frames", label="Storyboard image"), REV, F("state", "Status", "select", True, FRAME_STATES)], lambda s, p: s.set_frame_state(p["id"], p["revision"], p["state"]), page="frames")
