#!/usr/bin/env python3
"""Real-service regressions for the Observation Contract browser client.

Run only against a disposable local Storyboarder workspace: this helper adds a
shot and contract, then revises an existing contract. Playwright routes only
hold requests/responses to reproduce races; every API call reaches the actual
local service unchanged.
"""
from pathlib import Path
import argparse
import asyncio
import json
import traceback
import uuid

from playwright.async_api import async_playwright


PENDING = "A save for this shot is still in progress. Its draft is preserved and editing is paused until it finishes."


def new_id():
    return str(uuid.uuid4())


async def run(args):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    cases = [
        "saved_validation_is_explicitly_scoped_when_draft_is_dirty",
        "real_revise_survives_a_to_b_to_a_and_shows_accepted_revision_validation",
        "held_old_initial_load_cannot_overwrite_accepted_revision",
        "real_create_survives_a_to_b_to_a_and_syncs_contract_selector",
        "clean_saved_validation_is_restored_after_reload",
        "mismatched_show_and_validate_tuple_reconciles_without_losing_draft_or_pins",
    ]
    report = {
        "url": args.url,
        "transport": "actual loopback app origin and actual observation service; Playwright only delays real requests/responses and does not stub or rewrite API payloads",
        "api_scope": "session, state, shot.create, shot.link-source, shot.sources, observation.list/show/validate/create/revise all served by the local backend",
        "passed": [], "failed": [], "never_run": list(cases), "requests": [],
        "page_errors": [], "console_errors": [], "screenshots": [],
    }
    browser = None
    release_revise = asyncio.Event()
    release_old_validation = asyncio.Event()
    release_create = asyncio.Event()
    revise_started = asyncio.Event()
    old_validation_held = asyncio.Event()
    create_started = asyncio.Event()
    arm_old_validation = {"value": False}
    arm_old_empty_list = {"value": False}
    old_empty_list_held = asyncio.Event()
    release_old_empty_list = asyncio.Event()
    hold_create = {"value": False}
    arm_tuple_show = {"value": False}
    capture_tuple_validation = {"value": False}
    tuple_show_held = asyncio.Event()
    release_tuple_show = asyncio.Event()
    try:
        async with async_playwright() as playwright:
            launch = {"headless": True, "args": ["--no-sandbox"]}
            if args.chromium:
                launch["executable_path"] = args.chromium
            browser = await playwright.chromium.launch(**launch)
            context = await browser.new_context(viewport={"width": 1440, "height": 1024})
            page = await context.new_page()
            page.set_default_timeout(15000)
            api = context.request
            page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
            page.on("console", lambda message: report["console_errors"].append(message.text)
                    if message.type == "error" and "409 (Conflict)" not in message.text else None)

            session_response = await api.get(args.url.rstrip("/") + "/api/v1/session")
            assert session_response.ok, await session_response.text()
            session = await session_response.json()
            project_id = session["active_project_id"]
            headers = {"X-Storyboarder-Token": session["token"]}
            api_root = args.url.rstrip("/") + f"/api/v1/projects/{project_id}"
            command_url = api_root + "/commands/"

            async def command(name, payload):
                response = await api.post(command_url + name, data=payload, headers=headers)
                assert response.ok, (name, response.status, await response.text())
                return await response.json()

            state_response = await api.get(api_root + "/state", headers=headers)
            assert state_response.ok, await state_response.text()
            state = await state_response.json()
            shots = [row for row in state["entities"] if row["kind"] == "shot" and not row.get("archived")]
            assert len(shots) >= 2, "Disposable workspace needs at least two active shots."

            chosen = None
            for shot in shots:
                listing = await command("observation.list", {"shot_id": shot["id"], "limit": 100, "offset": 0})
                for item in listing.get("items", []):
                    record = await command("observation.show", {"contract_id": item["id"]})
                    checked = await command("observation.validate", {
                        "contract_id": record["id"], "version_id": record["selected_version_id"]
                    })
                    requirement = next((row for row in record["contract"].get("requirements", [])
                                        if row["priority"] in ("must", "prefer")), None)
                    if checked["status"] == "consistent" and requirement:
                        chosen = (shot, record, checked, requirement)
                        break
                if chosen:
                    break
            assert chosen, "Disposable workspace needs a consistent saved contract with a must/prefer requirement."
            shot_a, record, validation, requirement = chosen
            shot_b = next(row for row in shots if row["id"] != shot_a["id"])

            existing_sources = await command("shot.sources", {"id": shot_a["id"]})
            source_rows = existing_sources.get("items", [])
            assert source_rows, "Disposable workspace needs at least one screenplay source link."
            usable_source = next((row for row in source_rows if not row.get("stale")), source_rows[0])
            created_shot = await command("shot.create", {
                "title": f"Observation client real-service {new_id()[:8]}",
                "parent_id": shot_a["parent_id"],
            })
            await command("shot.link-source", {"shot_id": created_shot["id"], "node_id": usable_source["node_id"]})
            created_sources = await command("shot.sources", {"id": created_shot["id"]})
            assert created_sources.get("items"), "The newly created test shot must have an actual linked source."
            report.update({
                "project_id": project_id,
                "existing_shot_id": shot_a["id"], "other_shot_id": shot_b["id"],
                "existing_contract_id": record["id"], "existing_revision": record["revision"],
                "requirement_id": requirement["id"], "new_shot_id": created_shot["id"],
                "mutations": {"shot.create": created_shot["id"], "shot.link-source": usable_source["node_id"]},
            })

            async def delay_only(route):
                path = route.request.url.split("/commands/")[-1]
                payload = route.request.post_data_json or {}
                report["requests"].append({"name": path, "method": route.request.method})
                if route.request.method == "POST" and path == "observation.revise" and not revise_started.is_set():
                    report["held_revise_payload"] = payload
                    revise_started.set()
                    await release_revise.wait()
                    await route.continue_()
                    return
                if (route.request.method == "POST" and path == "observation.validate"
                        and arm_old_validation["value"] and payload.get("contract_id") == record["id"]):
                    arm_old_validation["value"] = False
                    response = await route.fetch()
                    report["held_validation_response"] = await response.json()
                    old_validation_held.set()
                    await release_old_validation.wait()
                    await route.fulfill(response=response)
                    return
                if (route.request.method == "POST" and path == "observation.show"
                        and arm_tuple_show["value"] and payload.get("contract_id") == record["id"]):
                    arm_tuple_show["value"] = False
                    response = await route.fetch()
                    report["held_tuple_show_response"] = await response.json()
                    tuple_show_held.set()
                    await release_tuple_show.wait()
                    await route.fulfill(response=response)
                    return
                if (route.request.method == "POST" and path == "observation.validate"
                        and capture_tuple_validation["value"] and payload.get("contract_id") == record["id"]):
                    response = await route.fetch()
                    report.setdefault("tuple_validation_responses", []).append(await response.json())
                    await route.fulfill(response=response)
                    return
                if (route.request.method == "POST" and path == "observation.list"
                        and arm_old_empty_list["value"] and payload.get("shot_id") == created_shot["id"]):
                    arm_old_empty_list["value"] = False
                    response = await route.fetch()
                    report["held_empty_list_response"] = await response.json()
                    old_empty_list_held.set()
                    await release_old_empty_list.wait()
                    await route.fulfill(response=response)
                    return
                if route.request.method == "POST" and path == "observation.create" and hold_create["value"]:
                    report["held_create_payload"] = payload
                    hold_create["value"] = False
                    create_started.set()
                    await release_create.wait()
                    await route.continue_()
                    return
                await route.continue_()

            await page.route("**/api/v1/projects/*/commands/*", delay_only)

            async def open_shot(shot_id):
                card = page.locator(f'.graph-node[data-node-id="{shot_id}"]')
                await card.wait_for()
                await card.focus()
                await card.press("Enter")
                await page.get_by_role("tab", name="Shot intent", exact=True).click()
                return page.get_by_role("region", name="Shot intent contract", exact=True)

            def mark_passed(case):
                report["passed"].append(case)
                report["never_run"].remove(case)

            await page.goto(args.url, wait_until="networkidle")
            await page.get_by_role("button", name="Story canvas", exact=True).click()
            panel = await open_shot(shot_a["id"])
            clean_label = f'Current saved revision {record["revision"]}: consistent'
            await panel.get_by_text(clean_label, exact=True).wait_for()

            await page.get_by_label(f'Priority {requirement["id"]}', exact=True).select_option("unknown")
            await page.get_by_label(f'Requirement basis {requirement["id"]}', exact=True).select_option("unknown")
            dirty_label = f'Saved revision {record["revision"]} validation: consistent'
            await panel.get_by_text(dirty_label, exact=True).wait_for()
            await panel.get_by_text(
                f'This status covers saved revision {record["revision"]} only; the current local draft has not been checked.',
                exact=True,
            ).wait_for()
            # Keep in sync with the production copy; the full paragraph starts with “This”.
            mark_passed(cases[0])

            await page.get_by_role("button", name="Save draft", exact=True).click()
            await asyncio.wait_for(revise_started.wait(), timeout=12)
            card_b = page.locator(f'.graph-node[data-node-id="{shot_b["id"]}"]')
            await card_b.focus(); await card_b.press("Enter")
            await page.get_by_role("tab", name="Shot intent", exact=True).click()
            arm_old_validation["value"] = True
            card_a = page.locator(f'.graph-node[data-node-id="{shot_a["id"]}"]')
            await card_a.focus(); await card_a.press("Enter")
            await page.get_by_role("tab", name="Shot intent", exact=True).click()
            panel = page.get_by_role("region", name="Shot intent contract", exact=True)
            await panel.get_by_text(PENDING, exact=True).wait_for()
            await asyncio.wait_for(old_validation_held.wait(), timeout=15)
            held_validation = report["held_validation_response"]
            assert held_validation["revision"] == record["revision"] and held_validation["status"] == "consistent", held_validation
            release_revise.set()

            async def wait_record_revision():
                for _ in range(150):
                    current = await command("observation.show", {"contract_id": record["id"]})
                    if current["revision"] > record["revision"]:
                        return current
                    await asyncio.sleep(0.1)
                raise AssertionError("Actual observation.revise did not commit.")

            updated = await wait_record_revision()
            updated_validation = await command("observation.validate", {
                "contract_id": updated["id"], "version_id": updated["selected_version_id"]
            })
            assert updated_validation["status"] == "unresolved", updated_validation
            expected_current = f'Current saved revision {updated["revision"]}: unresolved'
            await panel.get_by_text(expected_current, exact=True).wait_for()
            release_old_validation.set()
            await asyncio.sleep(0.6)
            await panel.get_by_text(expected_current, exact=True).wait_for()
            assert await page.get_by_label("Observation contract", exact=True).input_value() == record["id"]
            assert await page.get_by_label(f'Priority {requirement["id"]}', exact=True).input_value() == "unknown"
            report["revise_result"] = {
                "revision": updated["revision"], "validation": updated_validation["status"],
                "label_after_released_old_get": expected_current,
                "selected_contract": await page.get_by_label("Observation contract", exact=True).input_value(),
                "priority_draft": "unknown",
            }
            assert sum(item["name"] == "observation.revise" for item in report["requests"]) == 1
            mark_passed(cases[1]); mark_passed(cases[2])

            await page.reload(wait_until="networkidle")
            await page.get_by_role("button", name="Story canvas", exact=True).click()
            panel = await open_shot(shot_a["id"])
            await panel.get_by_text(expected_current, exact=True).wait_for()
            mark_passed(cases[4])

            panel = await open_shot(created_shot["id"])
            await panel.get_by_role("button", name="Create observation contract", exact=True).wait_for()
            await panel.locator(".shot-source-option input").first.check()
            await panel.get_by_role("button", name="Add purpose", exact=True).click()
            intent_card = panel.locator(".shot-intent-card[data-intent-id]").first
            await intent_card.locator('input[aria-label^="Purpose "]').fill("Keep the source intent on the shot.")
            await intent_card.locator('textarea[aria-label^="Communication "]').fill("Real service create remount regression.")
            hold_create["value"] = True
            await panel.get_by_role("button", name="Create observation contract", exact=True).click()
            await asyncio.wait_for(create_started.wait(), timeout=12)
            await card_b.focus(); await card_b.press("Enter")
            await page.get_by_role("tab", name="Shot intent", exact=True).click()
            arm_old_empty_list["value"] = True
            card_new = page.locator(f'.graph-node[data-node-id="{created_shot["id"]}"]')
            await card_new.focus(); await card_new.press("Enter")
            await page.get_by_role("tab", name="Shot intent", exact=True).click()
            panel = page.get_by_role("region", name="Shot intent contract", exact=True)
            await panel.get_by_text(PENDING, exact=True).wait_for()
            await asyncio.wait_for(old_empty_list_held.wait(), timeout=15)
            assert not report["held_empty_list_response"].get("items"), "Held create must still be before real service dispatch."
            release_create.set()

            async def wait_created_contract():
                for _ in range(150):
                    listing = await command("observation.list", {"shot_id": created_shot["id"], "limit": 100, "offset": 0})
                    if listing.get("items"):
                        return listing["items"][0]
                    await asyncio.sleep(0.1)
                raise AssertionError("Actual observation.create did not commit.")

            created_item = await wait_created_contract()
            release_old_empty_list.set()
            await panel.get_by_label("Observation contract", exact=True).wait_for()
            await page.wait_for_function(
                "id => document.querySelector('select[aria-label=\\\"Observation contract\\\"]')?.value === id",
                arg=created_item["id"],
            )
            created_record = await command("observation.show", {"contract_id": created_item["id"]})
            create_label = f'Current saved revision {created_record["revision"]}: {created_record["validation"]["status"]}'
            await panel.get_by_text(create_label, exact=True).wait_for()
            assert await page.get_by_label("Observation contract", exact=True).input_value() == created_item["id"]
            assert sum(item["name"] == "observation.create" for item in report["requests"]) == 1
            report["create_result"] = {"contract_id": created_item["id"], "revision": created_record["revision"], "label": create_label}
            mark_passed(cases[3])

            # Hold the actual old show response on the remounted owner while an
            # independent real writer advances the contract. The old version's
            # validate response then carries the new header revision and must be
            # rejected/reconciled by the client, without clearing its draft/pins.
            panel = await open_shot(shot_a["id"])
            await panel.get_by_text(expected_current, exact=True).wait_for()
            await page.get_by_label(f'Priority {requirement["id"]}', exact=True).select_option("must")
            await panel.get_by_text(
                f'This status covers saved revision {updated["revision"]} only; the current local draft has not been checked.',
                exact=True,
            ).wait_for()
            await card_b.focus(); await card_b.press("Enter")
            await page.get_by_role("tab", name="Shot intent", exact=True).click()
            arm_tuple_show["value"] = True
            card_a = page.locator(f'.graph-node[data-node-id="{shot_a["id"]}"]')
            await card_a.focus(); await card_a.press("Enter")
            await page.get_by_role("tab", name="Shot intent", exact=True).click()
            await asyncio.wait_for(tuple_show_held.wait(), timeout=15)
            panel = page.get_by_role("region", name="Shot intent contract", exact=True)
            held_show = report["held_tuple_show_response"]
            assert held_show["revision"] == updated["revision"]
            assert held_show["selected_version_id"] == updated["selected_version_id"]

            external_body = json.loads(json.dumps(updated["contract"]))
            external_body["notes"] = (external_body.get("notes") or "") + " External tuple-race writer."
            external = await command("observation.revise", {
                "contract_id": updated["id"], "revision": updated["revision"], "contract": external_body,
            })
            assert external["revision"] == updated["revision"] + 1, external
            capture_tuple_validation["value"] = True
            release_tuple_show.set()
            await page.get_by_text(
                f'The editor still uses header revision {updated["revision"]}; latest is revision {external["revision"]}. Your local draft and exact pins are retained.',
                exact=True,
            ).wait_for()
            selected_option = await page.get_by_label("Observation contract", exact=True).locator("option:checked").inner_text()
            assert selected_option.startswith(f'Revision {external["revision"]} · {record["id"]}'), selected_option
            latest_label = f'Saved revision {external["revision"]} validation: {external["validation"]["status"]}'
            await panel.get_by_text(latest_label, exact=True).wait_for()
            metadata = await panel.locator(".shot-intent-meta").inner_text()
            assert f'Checked header revision {external["revision"]}' in metadata, metadata
            assert f'Checked version {external["selected_version_id"]}' in metadata, metadata
            assert f'Editor CAS revision {updated["revision"]}' in metadata, metadata
            assert f'Draft base version {updated["selected_version_id"]}' in metadata, metadata
            await panel.get_by_label(f'Priority {requirement["id"]}', exact=True).wait_for()
            assert await page.get_by_label(f'Priority {requirement["id"]}', exact=True).input_value() == "must"
            assert await page.get_by_label("Observation contract", exact=True).input_value() == record["id"]
            checked_edges = await panel.locator(".shot-source-option input:checked").evaluate_all(
                "inputs => inputs.map(input => input.closest('label').innerText.match(/Edge ([0-9a-f-]+)/)?.[1]).filter(Boolean)"
            )
            expected_edges = sorted(pin["edge_id"] for pin in updated["contract"]["source_pins"])
            assert sorted(checked_edges) == expected_edges, {"actual": checked_edges, "expected": expected_edges}
            assert await page.get_by_role("button", name="Save draft", exact=True).is_disabled()
            assert len(report.get("tuple_validation_responses", [])) >= 1
            mismatch = report["tuple_validation_responses"][0]
            assert mismatch["revision"] == external["revision"]
            assert mismatch["version_id"] == held_show["selected_version_id"]
            assert any(result["revision"] == external["revision"]
                       and result["version_id"] == external["selected_version_id"]
                       for result in report["tuple_validation_responses"])
            report["tuple_race_result"] = {
                "held_show": {"revision": held_show["revision"], "version_id": held_show["selected_version_id"]},
                "external_revision": external["revision"],
                "stale_validation": {"revision": mismatch["revision"], "version_id": mismatch["version_id"]},
                "reconciled_validation": report["tuple_validation_responses"][-1],
                "visible_label": latest_label,
                "selector_option": selected_option,
                "validation_metadata": metadata,
                "local_priority_draft": "must",
                "header_cas": updated["revision"],
                "draft_pins": checked_edges,
            }
            mark_passed(cases[5])
            if report["page_errors"] or report["console_errors"]:
                raise AssertionError("Browser recorded page or console errors.")
            await page.screenshot(path=str(output / "final.png"), full_page=True)
            report["screenshots"].append(str(output / "final.png"))
    except Exception:
        report["failed"].append({"error": traceback.format_exc()})
    finally:
        # A failed assertion must not strand a paused browser request.
        release_revise.set(); release_old_validation.set(); release_create.set(); release_old_empty_list.set(); release_tuple_show.set()
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Actual local Storyboarder app origin; use a disposable workspace.")
    parser.add_argument("--output", default="/tmp/storyboarder-observation-real-service-e2e")
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    args = parser.parse_args()
    result = asyncio.run(run(args))
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result["failed"] or result["never_run"] else 0)


if __name__ == "__main__":
    main()
