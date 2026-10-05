"""Agent-facing, JSON-safe observation-contract commands."""
from .core import F, ID, REV, register
from storyboarder.application.observation_contracts import ObservationContracts


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
