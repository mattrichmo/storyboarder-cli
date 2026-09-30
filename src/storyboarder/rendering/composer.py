"""Deterministic composition with visible, top-down context provenance."""
from pathlib import Path
from storyboarder import EXPORT_VERSION
from storyboarder.domain.errors import NotFound, StoryboardError
from storyboarder.media.files import safe_path

SCALARS = ("location_id", "time", "framing", "camera")
DIRECTIONS = ("premise", "visual_style", "constraints", "arc", "tone", "summary", "continuity")
COPY_LABELS = {
    "location_id": "Location", "visual_style": "Visual style", "premise": "Story premise",
    "arc": "Sequence direction", "tone": "Tone", "framing": "Framing", "camera": "Camera plan",
    "time": "Time of day", "constraints": "Production notes", "continuity": "Continuity",
    "summary": "Summary", "action": "Action", "dialogue": "Dialogue", "notes": "Notes",
    "subject": "Subject", "setting-reference": "Location", "costume": "Wardrobe",
    "prop": "Prop", "reference": "General reference", "append": "Add to earlier notes",
    "replace": "Replace earlier notes", "exclude": "Hide earlier notes here",
}
OPERATION_NOTES = {"replace": "Earlier direction replaced here", "exclude": "Earlier direction hidden here"}


def copy_label(value):
    return COPY_LABELS.get(str(value), str(value).replace("_", " ").replace("-", " ").title())


def display_title(value):
    text = str(value or "Untitled")
    if text.isupper() and "_" in text and all(part.isalnum() for part in text.split("_")):
        return " ".join(part if part.isdigit() else part.title() for part in text.split("_"))
    return text


def context(snapshot, owner_id):
    entities = {r["id"]: r for r in snapshot["entities"]}
    if owner_id not in entities:
        raise NotFound("This part of the story is no longer available. Refresh the project and try again.")
    chain, seen = [], set()
    current = entities[owner_id]
    while current:
        if current["id"] in seen:
            raise StoryboardError("The story order contains a loop. Review the affected items or restore a recent backup.")
        seen.add(current["id"])
        chain.insert(0, current)
        current = entities.get(current["parent_id"])
    if chain[0]["kind"] != "project":
        project = next(r for r in entities.values() if r["kind"] == "project")
        chain.insert(0, project)
    scalars, blocks, history = {}, {}, []
    for owner in chain:
        source = {"id": owner["id"], "kind": owner["kind"], "title": owner["title"], "revision": owner["revision"]}
        for key in SCALARS:
            value = owner["fields"].get(key)
            if value not in (None, ""):
                scalars[key] = {"value": value, "source": source}
                if key == "location_id":
                    scalars[key]["label"] = entities.get(value, {}).get("title", "Missing location")
        for key in DIRECTIONS:
            value = owner["fields"].get(key)
            if value:
                blocks.setdefault(key, []).append({"text": value, "source": source, "authored_field": key})
        authored = sorted((b for b in snapshot["context_blocks"] if b["owner_id"] == owner["id"]), key=lambda b: (b["key"], b["id"]))
        for block in authored:
            key, operation = block["key"], block["operation"]
            before = list(blocks.get(key, []))
            if operation in ("replace", "exclude"):
                blocks[key] = []
            if operation != "exclude" and block["text"]:
                blocks.setdefault(key, []).append({"text": block["text"], "source": source, "block_id": block["id"], "revision": block["revision"]})
            history.append({"key": key, "operation": operation, "source": source, "block_id": block["id"], "removed_sources": [r["source"] for r in before] if operation in ("replace", "exclude") else []})
    return {"scalars": scalars, "blocks": {k: v for k, v in sorted(blocks.items()) if v}, "history": history, "chain": [{"id": r["id"], "kind": r["kind"], "title": r["title"], "revision": r["revision"]} for r in chain]}


def media_public(media):
    # Source paths and launch credentials never enter portable scene exports.
    return {k: media[k] for k in ("id", "sha256", "original_name", "format", "width", "height", "size", "tags")}


def compose(snapshot, owner_id, root=None):
    entities = {r["id"]: r for r in snapshot["entities"]}
    owner = entities.get(owner_id)
    if not owner:
        raise NotFound("Choose a project, sequence, scene, or shot to build a board.")
    if owner["kind"] == "asset":
        raise StoryboardError("Choose a project, sequence, scene, or shot to build a board.")
    project = next(r for r in entities.values() if r["kind"] == "project")
    media = {r["id"]: r for r in snapshot["media"]}
    warnings, required = [], {}

    def use_media(media_id, shot_id):
        if not media_id:
            return None
        record = media.get(media_id)
        if not record:
            warnings.append({"severity": "error", "code": "missing_media_record", "shot_id": shot_id, "media_id": media_id, "message": "A chosen image is no longer in the project library. Add it to the library again before exporting."})
            return None
        public = media_public(record)
        required[media_id] = public
        if root:
            try:
                safe_path(root, record["path"], must_exist=True)
            except StoryboardError as exc:
                warnings.append({"severity": "error", "code": "missing_media_file", "shot_id": shot_id, "media_id": media_id, "message": "Storyboarder couldn’t open this image in the project folder. Restore the original file or import it again."})
        return public

    def compose_shot(shot):
        assignments = []
        for assignment in sorted((a for a in snapshot["assignments"] if a["shot_id"] == shot["id"]), key=lambda a: (a["role"], a["asset_id"], a["id"])):
            asset = entities[assignment["asset_id"]]
            selected = use_media(assignment["media_id"], shot["id"])
            if not assignment["media_id"]:
                warnings.append({"severity": "warning", "code": "reference_not_selected", "shot_id": shot["id"], "assignment_id": assignment["id"], "message": f"{asset['title']}: choose a specific image for this {copy_label(assignment['role']).lower()} reference if the shot needs one."})
            if asset["archived"]:
                warnings.append({"severity": "warning", "code": "archived_asset", "shot_id": shot["id"], "message": f"{asset['title']} is archived but still appears in this shot. Restore it or choose another reference."})
            assignments.append({**assignment, "asset": asset, "media": selected})
        frames = []
        for frame in sorted((f for f in snapshot["frames"] if f["shot_id"] == shot["id"] and f["state"] != "archived"), key=lambda f: (f["version"], f["id"])):
            frames.append({**frame, "media": use_media(frame["media_id"], shot["id"])})
        if not shot["fields"].get("action"):
            warnings.append({"severity": "warning", "code": "action_empty", "shot_id": shot["id"], "message": f"{display_title(shot['title'])}: add a short description of the action."})
        return {**shot, "context": context(snapshot, shot["id"]), "assignments": assignments, "frames": frames}

    if owner["kind"] == "shot":
        scenes = [entities[owner["parent_id"]]]
    elif owner["kind"] == "scene":
        scenes = [owner]
    elif owner["kind"] == "sequence":
        scenes = [r for r in entities.values() if r["kind"] == "scene" and r["parent_id"] == owner_id and not r["archived"]]
    else:
        scenes = [r for r in entities.values() if r["kind"] == "scene" and not r["archived"] and not entities[r["parent_id"]]["archived"]]
    scenes.sort(key=lambda s: (entities[s["parent_id"]]["position"], s["position"], s["id"]))
    composed_scenes = []
    for scene in scenes:
        shots = [r for r in entities.values() if r["kind"] == "shot" and r["parent_id"] == scene["id"] and not r["archived"] and (owner["kind"] != "shot" or r["id"] == owner_id)]
        shots.sort(key=lambda r: (r["position"], r["id"]))
        composed_scenes.append({**scene, "sequence": {k: entities[scene["parent_id"]][k] for k in ("id", "title", "position")}, "context": context(snapshot, scene["id"]), "shots": [compose_shot(s) for s in shots]})
    return {"schema": EXPORT_VERSION, "project": {k: project[k] for k in ("id", "title", "revision", "fields")}, "owner": owner, "context": context(snapshot, owner_id), "scenes": composed_scenes, "media": [required[k] for k in sorted(required)], "validation": warnings, "valid": not any(w["severity"] == "error" for w in warnings)}


def markdown(document):
    lines = [f"# {display_title(document['owner']['title'])}", "", f"{display_title(document['project']['title'])} · Storyboard", ""]
    def add_context(ctx):
        result = ["#### Story direction", ""]
        for key, value in ctx["scalars"].items():
            result.append(f"- **{copy_label(key)}**: {value.get('label', value['value'])} — {copy_label(value['source']['kind'])}: {display_title(value['source']['title'])}")
        for key, values in ctx["blocks"].items():
            result += ["", f"**{copy_label(key)}**"]
            for value in values:
                result += ["", value["text"], "", f"_{copy_label(value['source']['kind'])}: {display_title(value['source']['title'])}_"]
        for step in ctx["history"]:
            if step["operation"] in ("replace", "exclude"):
                result += ["", f"{OPERATION_NOTES[step['operation']]} for **{copy_label(step['key']).lower()}** · {copy_label(step['source']['kind'])}: {display_title(step['source']['title'])}."]
        return result + [""]
    if not document["scenes"]:
        lines += add_context(document["context"])
    for scene in document["scenes"]:
        lines += [f"## {display_title(scene['sequence']['title'])} / {display_title(scene['title'])}", "", scene["fields"].get("summary", ""), ""]
        if not scene["shots"]:
            lines += ["No shots in this scene yet.", ""]
        for shot in scene["shots"]:
            lines += [f"### {shot['fields'].get('number') or str(shot['position'] + 1).zfill(2)} · {display_title(shot['title'])}", ""]
            for key in ("action", "dialogue", "framing", "camera", "duration", "continuity", "notes", "constraints"):
                value = shot["fields"].get(key)
                if value not in (None, ""):
                    lines += [f"**{copy_label(key)}**", "", str(value), ""]
            lines += add_context(shot["context"])
            lines += ["#### Images used in this shot", ""]
            for assignment in shot["assignments"]:
                media = assignment["media"]
                lines += [f"- {copy_label(assignment['role'])}: **{display_title(assignment['asset']['title'])}**" + (f" — {media['original_name']}" if media else " — no specific image selected")]
                if media and media.get("bundle_path"):
                    lines += ["", f"![Reference image: {display_title(assignment['asset']['title'])}]({media['bundle_path']})", ""]
            lines += ["", "#### Storyboard images", ""]
            for frame in shot["frames"]:
                lines += [f"- Image {frame['version']}: **{copy_label(frame['state'])}** · {frame['notes']}"]
                if frame["media"] and frame["media"].get("bundle_path"):
                    lines += ["", f"![Storyboard image {frame['version']}]({frame['media']['bundle_path']})", ""]
            lines += [""]
    if document["validation"]:
        lines += ["## Production checks", ""]
        for issue in document["validation"]:
            lines += [f"- {copy_label(issue['severity'])}: {issue['message']}"]
    return "\n".join(lines).rstrip() + "\n"
