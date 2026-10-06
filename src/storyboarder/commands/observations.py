"""Agent-facing, JSON-safe observation-contract commands."""
import json

from .core import F, ID, REV, register
from storyboarder.application.observation_contracts import ObservationContracts
from storyboarder.application.observation_planner import ObservationPlanner
from storyboarder.application.observation_transfer import (
    apply_observation_import,
    export_observation_plan,
    preview_observation_import,
)


SHOT = F("shot_id", "Storyboard shot", required=True, source="shots")
SHOT_REV = F("expected_shot_revision", "Last-read storyboard shot revision", "integer", True)
BODY = F("contract", "Versioned observation contract", "json", True)
register("observation.create", "Create a shot observation contract", [SHOT, SHOT_REV, BODY],
         lambda s, p: ObservationContracts(s).create(p["shot_id"], p["expected_shot_revision"], p["contract"]),
         browser=False, api_safe=True, page="coverage")
register("observation.show", "Show a shot observation contract", [ID("story", "contract_id", "Observation contract"),
         F("version_id", "Contract version")],
         lambda s, p: ObservationContracts(s).show(p["contract_id"], p.get("version_id")),
         browser=False, api_safe=True, read_only=True, page="coverage")
register("observation.list", "List shot observation contracts", [
         F("shot_id", "Storyboard shot", source="shots"),
         F("include_archived", "Include archived shots", "boolean", default=False),
         F("limit", "Page size", "integer", default=100), F("offset", "Offset", "integer", default=0)],
         lambda s, p: ObservationContracts(s).list(**p),
         browser=False, api_safe=True, read_only=True, page="coverage")
register("observation.revise", "Revise a shot observation contract", [
         ID("story", "contract_id", "Observation contract"), REV, BODY],
         lambda s, p: ObservationContracts(s).revise(p["contract_id"], p["revision"], p["contract"]),
         browser=False, api_safe=True, page="coverage")
register("observation.validate", "Check declared observation links and basis", [
         ID("story", "contract_id", "Observation contract"), F("version_id", "Contract version")],
         lambda s, p: ObservationContracts(s).validate(p["contract_id"], p.get("version_id")),
         browser=False, api_safe=True, read_only=True, page="coverage")


def _review_rebase(s, p):
    return ObservationContracts(s).review_rebase(p["contract_id"], p["contract"])


def _rebase(s, p):
    return ObservationContracts(s).rebase(p["contract_id"], p["revision"], p["contract"],
                                           p["expected_basis_sha256"])


register("observation.rebase-preview", "Review basis changes before rebasing a contract", [
         ID("story", "contract_id", "Observation contract"), BODY], _review_rebase,
         browser=False, api_safe=True, read_only=True, page="coverage")
register("observation.rebase", "Rebase a contract with explicit source pins", [
         ID("story", "contract_id", "Observation contract"), REV, BODY,
         F("expected_basis_sha256", "Reviewed basis token", required=True)], _rebase,
         browser=False, api_safe=True, page="coverage")
register("observation.diff", "Compare two observation contract versions", [
         ID("story", "contract_id", "Observation contract"),
         F("before_version_id", "Earlier version", required=True),
         F("after_version_id", "Later version", required=True)],
         lambda s, p: ObservationContracts(s).diff(p["contract_id"], p["before_version_id"], p["after_version_id"]),
         browser=False, api_safe=True, read_only=True, page="coverage")


def _coverage(s, p):
    request = p["request"]
    if set(request) - {"anchors"}:
        from storyboarder.application.observation_planner import ObservationPlannerError
        raise ObservationPlannerError("observation_plan_invalid", "Coverage requests accept only an anchors array.")
    return ObservationPlanner(s).coverage(request.get("anchors"), limit=p["limit"], offset=p["offset"])


def _create_group(s, p):
    request = p["request"]
    if set(request) != {"items"}:
        from storyboarder.application.observation_planner import ObservationPlannerError
        raise ObservationPlannerError("observation_plan_invalid", "Grouped plans require one items array.")
    return ObservationPlanner(s).create_group(request["items"])


register("observation.coverage", "Report exact observation coverage", [
         F("request", "Request-scoped exact anchors", "json", True,
           help='JSON object: {"anchors": [{"document_id", "version_id", "node_id", "source_sha256", "priority", "basis"}]}.'),
         F("limit", "Page size", "integer", default=500), F("offset", "Offset", "integer", default=0)],
         _coverage, browser=False, api_safe=True, read_only=True, page="coverage")
register("observation.create-group", "Create planned shots, source links, and contracts", [
         F("request", "Atomic grouped plan", "json", True,
           help='JSON object: {"items": [GroupItem, ...]}; include caller-generated shot_id, contract_id, edge_id, and expected_scene_revision.' )],
         _create_group, browser=False, api_safe=True, page="coverage")


def _plan_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _plan_export(s, _p):
    return {"plan": json.loads(export_observation_plan(s))}


def _plan_import_preview(s, p):
    return preview_observation_import(s, _plan_json(p["plan"]), p.get("choices"))


def _plan_import_apply(s, p):
    return apply_observation_import(s, _plan_json(p["plan"]), p["preview"])


register("observation.plan-export", "Export exact observation history plan", [], _plan_export,
         browser=False, api_safe=True, read_only=True, page="coverage")
register("observation.plan-import-preview", "Preview observation plan reconciliation", [
         F("plan", "Portable observation plan", "json", True),
         F("choices", "Explicit conflict choices by contract ID", "json")],
         _plan_import_preview, browser=False, api_safe=True, read_only=True, page="coverage")
register("observation.plan-import-apply", "Apply a reviewed observation plan import", [
         F("plan", "Portable observation plan", "json", True),
         F("preview", "Exact preview receipt", "json", True)],
         _plan_import_apply, browser=False, api_safe=True, page="coverage")
