"""Agent-facing, JSON-safe observation-contract commands."""
from .core import F, ID, REV, register
from storyboarder.application.observation_contracts import ObservationContracts
from storyboarder.application.observation_planner import ObservationPlanner


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
register("observation.rebase", "Rebase a contract with explicit source pins", [
         ID("story", "contract_id", "Observation contract"), REV, BODY],
         lambda s, p: ObservationContracts(s).rebase(p["contract_id"], p["revision"], p["contract"]),
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
