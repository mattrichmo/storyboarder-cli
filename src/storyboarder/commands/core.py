"""Shared command catalog and form vocabulary; all handlers call application services.

HTTP exposes only this explicit allow-list, not arbitrary service methods or paths.
"""

from dataclasses import dataclass, field, asdict

from typing import Any, Callable

import json

from storyboarder.domain.errors import StoryboardError, NotFound

from storyboarder.domain.models import ASSET_TYPES, ROLES, RELATION_RULES, FRAME_STATES, FIELD_MODELS

from storyboarder.automation.registry import ScriptRegistry

@dataclass
class InputField:
    name: str
    label: str
    type: str = "text"
    required: bool = False
    options: list[str] = field(default_factory=list)
    source: str = ""
    help: str = ""
    default: Any = None

@dataclass
class Command:
    name: str
    label: str
    fields: list[InputField]
    handler: Callable
    page: str = ""
    destructive: bool = False
    browser: bool = True
    read_only: bool = False

    def public(self):
        return {"name": self.name, "label": self.label, "fields": [asdict(f) for f in self.fields], "page": self.page, "destructive": self.destructive, "browser": self.browser, "read_only": self.read_only}

COMMANDS: dict[str, Command] = {}

CHOICE_LABELS = {
    "assets": "Reference map", "scene": "Scene board", "story": "Story flow",
    "asset": "Library item", "frame": "Storyboard image", "append": "Add to earlier notes",
    "replace": "Replace earlier notes", "exclude": "Hide earlier notes here",
    "setting-reference": "Location", "subject": "Subject", "costume": "Wardrobe",
    "reference": "General reference", "same-person-as": "Same person as",
    "alternate-view-of": "Alternate view of", "appears-at": "Appears at",
    "part-of": "Part of", "inspired-by": "Inspired by", "related-to": "Related to",
    "wears": "Wears", "draft": "Draft", "selected": "Selected", "approved": "Approved",
    "archived": "Archived", "pending": "Needs review", "accepted": "Added",
    "discarded": "Removed from intake", "queued": "Ready to run", "running": "In progress",
    "succeeded": "Complete", "failed": "Needs attention", "cancelled": "Stopped",
}

def choice_label(value):
    value = str(value)
    return CHOICE_LABELS.get(value, value.replace("_", " ").replace("-", " ").title())

def F(name, label=None, type="text", required=False, options=(), source="", help="", default=None):
    return InputField(name, label or name.replace("_", " ").title(), type, required, list(options), source, help, default)

def register(name, label, fields, handler, **kwargs):
    COMMANDS[name] = Command(name, label, fields, handler, **kwargs)

def record_id(source="entities", name="id", label=None):
    labels = {"assets": "Library item", "media": "Image", "intake": "Imported image", "asset_media": "Library image", "frames": "Storyboard image", "assignments": "Shot reference", "context_blocks": "Direction note", "jobs": "Tool run", "layouts": "Saved arrangement", "links": "Connection", "story": "Story item"}
    return F(name, label or labels.get(source, "Choose item"), required=True, source=source)

ID = record_id

REV = F("revision", "Version check", "integer", True, help="Keeps a newer edit from being overwritten.")

OWNER = F("owner_id", "Apply direction to", required=True, source="story")

PARENT = {"scene": "sequences", "shot": "scenes"}

MULTILINE = {"description", "notes", "action", "dialogue", "continuity", "summary", "constraints", "premise", "visual_style", "arc", "tone", "camera"}

def authored_fields(kind):
    result = []
    for name in FIELD_MODELS[kind].model_fields:
        if name == "type":
            result.append(F(name, "Item type", "select", options=ASSET_TYPES, default="reference"))
        elif name == "location_id":
            result.append(F(name, "Location", source="locations", help="Leave blank to use the location set higher in the story."))
        elif name == "duration":
            result.append(F(name, "Duration (seconds)", "number"))
        else:
            result.append(F(name, type="textarea" if name in MULTILINE else "text"))
    return result

def create_handler(kind):
    def handler(s, p):
        known = FIELD_MODELS[kind].model_fields
        return s.create_entity(kind, p["title"], p.get("parent_id"), p.get("description", ""), {k: v for k, v in p.items() if k in known}, p.get("tags"), p.get("aliases"))
    return handler

def update_handler(kind):
    def handler(s, p):
        record = s.get("entities", p["id"])
        if record["kind"] != kind:
            raise StoryboardError(f"Choose a {kind} for this command, not a {record['kind']}.")
        known = FIELD_MODELS[kind].model_fields
        changes = {k: v for k, v in p.items() if k in ("title", "description", "tags", "aliases")}
        changes["fields"] = {k: v for k, v in p.items() if k in known}
        return s.update_entity(p["id"], p["revision"], changes)
    return handler

def execute(service, name, payload=None, browser=False):
    if name not in COMMANDS:
        raise StoryboardError("That action is no longer available. Refresh the project and try again.")
    command = COMMANDS[name]
    if browser and not command.browser:
        raise StoryboardError("This file or folder action is available from the command line or TUI. In the app, use image upload instead.")
    payload = payload or {}
    if not isinstance(payload, dict):
        raise StoryboardError("The action could not be completed. Refresh the project and try again.")
    allowed = {f.name for f in command.fields}
    if set(payload) - allowed:
        raise StoryboardError("Some action details are out of date. Refresh the project and try again.")
    values = {}
    for f in command.fields:
        if f.name not in payload:
            if f.required:
                raise StoryboardError(f"{f.label} is required.")
            if f.default is not None and not name.endswith(".update"):
                values[f.name] = f.default
            continue
        value = payload[f.name]
        if value is None or value == "":
            if f.default is not None and not f.required and not name.endswith(".update"):
                values[f.name] = f.default
                continue
            if f.required and f.type != "tags":
                raise StoryboardError(f"{f.label} is required.")
            if f.type in ("integer", "number") or f.source:
                values[f.name] = None
                continue
        if f.type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            raise StoryboardError(f"{f.label} must be an integer.")
        if f.type == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
            raise StoryboardError(f"{f.label} must be a number.")
        if f.type == "boolean" and not isinstance(value, bool):
            raise StoryboardError(f"{f.label} must be true or false.")
        if f.type == "json" and not isinstance(value, dict):
            raise StoryboardError(f"{f.label} has an invalid format. Review it and try again.")
        if f.type in ("text", "textarea", "select") and value is not None and not isinstance(value, str):
            raise StoryboardError(f"{f.label} must be text.")
        if f.options and value not in (None, "") and value not in f.options:
            raise StoryboardError(f"{f.label} must be one of: {', '.join(f.options)}.")
        values[f.name] = value
    return command.handler(service, values)

_PAGED_SOURCES = {
    "documents", "document_nodes", "versions", "provenance_edges", "annotations",
    "provenance_endpoints", "provenance_source", "provenance_target", "provenance_typed_endpoint",
}


def _source_page(items, total, limit, offset):
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
        "next_offset": offset + len(items) if offset + len(items) < total else None,
        "truncated": offset + len(items) < total,
    }


def _source_label(record):
    return str(record.get("label") or record.get("title") or record.get("original_name") or record.get("id", ""))


def _document_nodes_page(service, *, query, limit, offset, document_id=None, version_id=None,
                         include_archived=False, all_versions=False):
    """Return one indexed page from the current source trees without materializing a snapshot."""
    from storyboarder.storage.repository import unpack

    clauses, params = (["1=1"] if include_archived else ["d.archived=0"]), []
    if document_id:
        clauses.append("d.id=?")
        params.append(document_id)
    if version_id:
        clauses.append("v.id=?")
        params.append(version_id)
    elif not all_versions:
        clauses.append("d.current_version_id=v.id")
    if query:
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        clauses.append("(n.title LIKE ? ESCAPE '\\' OR n.text LIKE ? ESCAPE '\\')")
        params.extend([pattern, pattern])
    where = " AND ".join(clauses)
    query_sql = """FROM document_nodes n
        JOIN document_versions v ON v.id=n.version_id
        JOIN documents d ON d.id=v.document_id
        WHERE """ + where
    with service.repo.transaction(False) as conn:
        total = conn.execute("SELECT count(*) " + query_sql, params).fetchone()[0]
        rows = conn.execute("""SELECT n.id,n.version_id,n.logical_id,n.parent_id,n.node_type,n.position,n.title,
            substr(n.text,1,500) AS text,n.source_pointer,n.content_sha256,n.identity,
            d.id AS document_id,d.title AS document_title,d.kind AS document_kind,d.revision AS document_revision,
            v.label AS version_label
            """ + query_sql + " ORDER BY d.title,d.id,v.number,n.source_pointer,n.id LIMIT ? OFFSET ?",
            (*params, limit, offset)).fetchall()
    items = []
    for row in rows:
        item = unpack(row)
        item["revision"] = item["document_revision"]
        item["label"] = f"{item['document_title']} · {item.get('title') or item['node_type']} · {item['source_pointer']}"
        items.append(item)
    return _source_page(items, total, limit, offset)


def _versions_page(service, query, limit, offset, document_id=None, active_only=False):
    from storyboarder.storage.repository import unpack

    clauses, params = (["d.archived=0"] if active_only else ["1=1"]), []
    if document_id:
        clauses.append("d.id=?")
        params.append(document_id)
    if query:
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        clauses.append("(d.title LIKE ? ESCAPE '\\' OR v.label LIKE ? ESCAPE '\\')")
        params.extend([pattern, pattern])
    where = " AND ".join(clauses)
    join = " FROM document_versions v JOIN documents d ON d.id=v.document_id WHERE " + where
    with service.repo.transaction(False) as conn:
        total = conn.execute("SELECT count(*)" + join, params).fetchone()[0]
        rows = conn.execute("SELECT v.id,v.document_id,v.parent_version_id,v.number,v.label,v.format_version,v.content_sha256,v.created_at,d.title AS document_title,d.revision AS document_revision" + join + " ORDER BY d.title,d.id,v.number DESC,v.id LIMIT ? OFFSET ?", (*params, limit, offset)).fetchall()
    items = []
    for row in rows:
        item = unpack(row)
        item["revision"] = item["document_revision"]
        item["title"] = f"{item['document_title']} · Draft {item['number']} · {item['label']}"
        item["label"] = item["title"]
        items.append(item)
    return _source_page(items, total, limit, offset)


def _table_page(service, table, query, limit, offset, *, where="1=1", args=(), order="id"):
    """Read a single explicit source table in bounded pages for source pickers."""
    from storyboarder.storage.repository import unpack

    allowed = {"frames", "media", "jobs", "provenance_edges", "annotations"}
    if table not in allowed:
        raise StoryboardError("That source selector is not available.")
    clauses, params = [where], list(args)
    if query:
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        if table == "provenance_edges":
            clauses.append("(source_snapshot LIKE ? ESCAPE '\\' OR target_snapshot LIKE ? ESCAPE '\\' OR relation LIKE ? ESCAPE '\\' OR notes LIKE ? ESCAPE '\\')")
            params.extend([pattern] * 4)
        elif table == "annotations":
            clauses.append("(text LIKE ? ESCAPE '\\' OR snapshot LIKE ? ESCAPE '\\' OR state LIKE ? ESCAPE '\\')")
            params.extend([pattern] * 3)
        elif table == "frames":
            clauses.append("(notes LIKE ? ESCAPE '\\' OR state LIKE ? ESCAPE '\\')")
            params.extend([pattern] * 2)
        elif table == "media":
            clauses.append("(original_name LIKE ? ESCAPE '\\' OR path LIKE ? ESCAPE '\\')")
            params.extend([pattern] * 2)
        else:
            clauses.append("(title LIKE ? ESCAPE '\\' OR script LIKE ? ESCAPE '\\' OR status LIKE ? ESCAPE '\\')")
            params.extend([pattern] * 3)
    condition = " AND ".join(clauses)
    with service.repo.transaction(False) as conn:
        total = conn.execute(f"SELECT count(*) FROM {table} WHERE {condition}", params).fetchone()[0]
        rows = conn.execute(f"SELECT * FROM {table} WHERE {condition} ORDER BY {order} LIMIT ? OFFSET ?", (*params, limit, offset)).fetchall()
    return [unpack(row) for row in rows], total


def source_options(service, source, values=None, query="", limit=100, offset=0):
    """Return a bounded, searchable page for document and provenance form selectors."""
    from storyboarder.application.documents import Documents
    from storyboarder.application.provenance import unpack as unpack_edge

    values = values or {}
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise StoryboardError("Page size must be an integer from 1 to 1,000.")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise StoryboardError("Page offset must be a nonnegative integer.")
    query = str(query or "")
    docs = Documents(service)

    if source == "documents":
        result = docs.list(kind=values.get("kind"), query=query, archived=True, limit=limit, offset=offset)
        items = [{**row, "label": f"{row['title']} · {row['kind']} · {'archived · ' if row['archived'] else ''}revision {row['revision']}"} for row in result["items"]]
        return result | {"items": items}
    if source == "document_nodes":
        return _document_nodes_page(service, query=query, limit=limit, offset=offset,
                                    document_id=values.get("document_id"), version_id=values.get("version_id"))
    if source == "versions":
        return _versions_page(service, query, limit, offset, values.get("document_id") or values.get("id"))
    if source == "provenance_edges":
        rows, total = _table_page(service, "provenance_edges", query, limit, offset, where="retired=0", order="created_at DESC,id")
        items = []
        for row in rows:
            edge = unpack_edge(row)
            source_label = edge.get("source_snapshot", {}).get("label") or f"{edge['source_type']}:{edge['source_id']}"
            target_label = edge.get("target_snapshot", {}).get("label") or f"{edge['target_type']}:{edge['target_id']}"
            items.append({**edge, "label": f"{source_label} → {choice_label(edge['relation'])} → {target_label}"})
        return _source_page(items, total, limit, offset)
    if source == "annotations":
        rows, total = _table_page(service, "annotations", query, limit, offset, order="updated_at DESC,id")
        items = [{**row, "label": f"{choice_label(row['state'])} · {row['text'][:90]} · {row['endpoint_type']}:{row['endpoint_id']}"} for row in rows]
        return _source_page(items, total, limit, offset)
    if source == "provenance_endpoints":
        kind = values.get("source_type") or values.get("target_type") or values.get("kind") or values.get("endpoint_type")
        active_only = values.get("active_only", True)
        if kind not in ("node", "entity", "frame", "media", "job", "version", "artifact"):
            return _source_page([], 0, limit, offset)
        if kind == "node":
            return _document_nodes_page(service, query=query, limit=limit, offset=offset,
                                        document_id=values.get("document_id"), version_id=values.get("version_id"),
                                        include_archived=not active_only, all_versions=not active_only)
        if kind == "version":
            return _versions_page(service, query, limit, offset, values.get("document_id") or values.get("id"), active_only)
        if kind == "entity":
            result = service.list_entities(query=query, archived=not active_only, limit=limit, offset=offset)
            items = [{**row, "label": f"{choice_label(row['kind'])} · {row['title']}"} for row in result["items"]]
            return result | {"items": items}
        if kind == "artifact":
            # Source artifacts are queried directly because they have no mutable project snapshot table.
            from storyboarder.storage.repository import unpack
            with service.repo.transaction(False) as conn:
                clauses, params = ["1=1"], []
                if query:
                    pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                    clauses.append("(original_name LIKE ? ESCAPE '\\' OR path LIKE ? ESCAPE '\\')")
                    params.extend([pattern, pattern])
                condition = " AND ".join(clauses)
                total = conn.execute(f"SELECT count(*) FROM source_artifacts WHERE {condition}", params).fetchone()[0]
                records = [unpack(row) for row in conn.execute(f"SELECT * FROM source_artifacts WHERE {condition} ORDER BY created_at DESC,id LIMIT ? OFFSET ?", (*params, limit, offset)).fetchall()]
            return _source_page([{**row, "label": f"{row['original_name']} · source artifact"} for row in records], total, limit, offset)
        table = {"frame": "frames", "media": "media", "job": "jobs"}[kind]
        frame_filter = "state!='archived' AND EXISTS(SELECT 1 FROM entities e WHERE e.id=frames.shot_id AND e.archived=0)" if kind == "frame" and active_only else "1=1"
        rows, total = _table_page(service, table, query, limit, offset, where=frame_filter, order="id")
        from storyboarder.storage.repository import unpack
        with service.repo.transaction(False) as conn:
            for row in rows:
                if kind == "frame":
                    shot = conn.execute("SELECT title FROM entities WHERE id=?", (row["shot_id"],)).fetchone()
                    row["title"] = f"{shot['title'] if shot else 'Shot'} · image {row['version']}"
                elif kind == "media":
                    row["title"] = row.get("original_name")
                row["type"] = kind
                row["label"] = row.get("title") or row.get("original_name") or row.get("id")
        return _source_page(rows, total, limit, offset)
    if source in ("provenance_source", "provenance_target", "provenance_typed_endpoint"):
        endpoint_source = source_options(service, "provenance_endpoints", values={
            "kind": values.get("source_type") if source == "provenance_source" else values.get("target_type") if source == "provenance_target" else values.get("kind") or values.get("endpoint_type"),
            "document_id": values.get("document_id"),
            "version_id": values.get("version_id"),
            "active_only": source != "provenance_typed_endpoint",
        }, query=query, limit=limit, offset=offset)
        return endpoint_source
    return _source_page([], 0, limit, offset)


def source_record(service, source, record_id, values=None):
    """Resolve one picker record and expose the revision token expected by its mutation."""
    from storyboarder.application.documents import Documents
    from storyboarder.application.provenance import Provenance
    from storyboarder.storage.repository import unpack

    values = values or {}
    docs = Documents(service)
    if source == "documents":
        return docs.show(record_id)
    if source == "document_nodes":
        record = docs.node(record_id)
        if values.get("document_id") and record["document_id"] != values["document_id"]:
            raise NotFound("This source element belongs to a different document. Refresh the selector.")
        if values.get("version_id") and record["version_id"] != values["version_id"]:
            raise NotFound("This source element belongs to a different draft. Refresh the selector.")
        record["revision"] = record["document_revision"]
        return record
    if source == "versions":
        record = docs.version(record_id)
        selected_document = values.get("document_id") or values.get("id")
        if selected_document and record["document_id"] != selected_document:
            raise NotFound("This draft belongs to a different document. Refresh the selector.")
        record["document_revision"] = docs.show(record["document_id"])["revision"]
        record["revision"] = record["document_revision"]
        return record
    if source == "provenance_edges":
        return Provenance(service).show(record_id)
    if source == "annotations":
        with service.repo.transaction(False) as conn:
            row = conn.execute("SELECT * FROM annotations WHERE id=?", (record_id,)).fetchone()
            if row is None:
                raise StoryboardError("This review note is no longer in the project. Refresh the selector.")
            return unpack(row)
    if source in ("provenance_endpoints", "provenance_source", "provenance_target", "provenance_typed_endpoint"):
        kind = values.get("source_type") or values.get("target_type") or values.get("kind") or values.get("endpoint_type")
        if source == "provenance_source": kind = values.get("source_type")
        elif source == "provenance_target": kind = values.get("target_type")
        elif source == "provenance_typed_endpoint": kind = values.get("kind") or values.get("endpoint_type")
        record = Provenance(service).endpoint(kind, record_id)
        if kind == "node":
            node = docs.node(record_id)
            if values.get("document_id") and node["document_id"] != values["document_id"]:
                raise NotFound("This source element belongs to a different document. Refresh the selector.")
            if values.get("version_id") and node["version_id"] != values["version_id"]:
                raise NotFound("This source element belongs to a different draft. Refresh the selector.")
            record["revision"] = node["document_revision"]
        elif kind == "version":
            selected_document = values.get("document_id") or values.get("id")
            if selected_document and record["document_id"] != selected_document:
                raise NotFound("This draft belongs to a different document. Refresh the selector.")
            record["revision"] = docs.show(record["document_id"])["revision"]
        return record
    return None


def options_for(source, state, values=None, service=None):
    values = values or {}
    if source in _PAGED_SOURCES and service is not None:
        page = source_options(service, source, values=values, limit=100, offset=0)
        return [(record["id"], _source_label(record)) for record in page["items"]]
    entities = state.get("entities", [])
    by_id = {r["id"]: r for r in entities}
    if source == "scripts":
        return [(r["name"], r["name"] + " — " + r.get("description", "")) for r in ScriptRegistry().list()]
    kinds = {"assets": "asset", "sequences": "sequence", "scenes": "scene", "shots": "shot", "projects": "project"}
    if source in kinds:
        records = [r for r in entities if r["kind"] == kinds[source] and not r["archived"]]
    elif source == "locations":
        records = [r for r in entities if r["kind"] == "asset" and r["fields"]["type"] == "location" and not r["archived"]]
    elif source in ("story", "parents"):
        records = [r for r in entities if r["kind"] in (("project", "sequence", "scene") if source == "parents" else ("project", "sequence", "scene", "shot")) and not r["archived"]]
    else:
        records = state.get(source, entities if source == "entities" else [])
    if source == "asset_images":
        records = state["media"]
    if source == "asset_images" and values.get("asset_id"):
        allowed = {m["media_id"] for m in state.get("asset_media", []) if m["asset_id"] == values["asset_id"]}
        records = [r for r in records if r["id"] in allowed]
    result = []
    for record in records:
        label = record.get("title") or record.get("original_name") or record.get("name") or record.get("key")
        if source == "asset_media":
            media = next((m for m in state.get("media", []) if m["id"] == record["media_id"]), {})
            label = f"{by_id.get(record['asset_id'], {}).get('title', 'Library item')} / {media.get('original_name', 'Image')}" + (" · cover image" if record["is_primary"] else "")
        if source == "frames":
            label = f"{by_id.get(record['shot_id'], {}).get('title', 'Shot')} / image {record['version']} · {choice_label(record['state'])}"
        if source == "links":
            label = f"{by_id.get(record['source_id'], {}).get('title', 'Item')} → {choice_label(record['relation'])} → {by_id.get(record['target_id'], {}).get('title', 'Item')}"
        if source == "assignments":
            label = f"{by_id.get(record['shot_id'], {}).get('title', 'Shot')} → {choice_label(record['role'])} → {by_id.get(record['asset_id'], {}).get('title', 'Library item')}"
        result.append((record["id"], str(label or "Untitled item")))
    return result
