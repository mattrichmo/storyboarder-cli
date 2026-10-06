#!/usr/bin/env python3
"""Browser-client contract editor acceptance with deterministic API fixtures.

The app itself is served normally from a loopback origin. Only the not-yet-
integrated observation commands and screenplay source selectors are stubbed.
"""
from pathlib import Path
import argparse
import asyncio
import json
import re
import sys
import traceback
import uuid

from playwright.async_api import async_playwright


def uid():
    return str(uuid.uuid4())


def validation_for(record, sources):
    current = {item["edge_id"] for item in sources}
    return {"status": "unresolved" if any(pin["edge_id"] not in current for pin in record["contract"]["source_pins"]) else "consistent",
            "findings": [],
            "requirements": [],
            "source_pins": [{**pin, "stale": pin["edge_id"] not in current} for pin in record["contract"]["source_pins"]],
            "references": [], "basis_current": True}


def make_record(contract_id, shot_id, body, revision, version_number, sources):
    version_id = uid()
    version = {"id": version_id, "number": version_number, "parent_version_id": None if version_number == 1 else "parent-version",
               "schema_version": 1, "content_sha256": uid().replace("-", ""), "basis_sha256": uid().replace("-", ""),
               "operation": "create" if version_number == 1 else "revise", "created_at": "2026-10-05T00:00:00Z"}
    return {"id": contract_id, "shot_id": shot_id, "revision": revision, "current_version_id": version_id,
            "selected_version_id": version_id, "version": version, "contract": json.loads(json.dumps(body)),
            "source_pins": [{"edge_id": pin["edge_id"], "source_scope": pin["source_scope"],
                             "document_id": next((row["document_id"] for row in sources if row["edge_id"] == pin["edge_id"]), "document"),
                             "source_version_id": next((row["version_id"] for row in sources if row["edge_id"] == pin["edge_id"]), "version"),
                             "node_id": next((row["node_id"] for row in sources if row["edge_id"] == pin["edge_id"]), "node"),
                             "source_sha256": next((row["content_sha256"] for row in sources if row["edge_id"] == pin["edge_id"]), "sha256-unavailable"),
                             "scope_sha256": uid().replace("-", "") * 2}
                            for pin in body["source_pins"]],
            "history": [version], "validation": {"status": "consistent", "findings": [], "requirements": [],
                                                     "source_pins": [{**pin, "stale": False} for pin in body["source_pins"]],
                                                     "references": [], "basis_current": True}}


async def main(args):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    report = {"transport": "normal loopback app origin; observation/source/document command requests use deterministic Playwright fixtures",
              "api_scope": "stubbed observation.*, shot.sources, and document.show/versions/node; session, project state, frontend, inspector, and inspector navigation are served by the actual local app",
              "url": args.url,
              "passed": [], "failed": [], "never_run": [], "requests": [], "page_errors": [], "console_errors": [], "expected_conflicts": []}
    cases = ["draft_survives_tab_and_shot_switch", "delayed_save_is_owner_scoped", "create_revision_and_hidden_fields",
             "409_refresh_keeps_header_draft_and_exact_pins", "rebase_token_invalidates_and_retries", "keyboard_and_responsive_shot_intent"]
    async with async_playwright() as playwright:
        options = {"headless": True, "args": ["--no-sandbox"]}
        if args.chromium:
            options["executable_path"] = args.chromium
        browser = await playwright.chromium.launch(**options)
        page = await browser.new_page(viewport={"width": 1440, "height": 1024})
        page.set_default_timeout(10000)
        page.on("pageerror", lambda error: report["page_errors"].append(str(error)))

        def on_console(message):
            if message.type != "error":
                return
            if "409 (Conflict)" in message.text:
                report["expected_conflicts"].append(message.text)
            else:
                report["console_errors"].append(message.text)

        page.on("console", on_console)
        shot_sources = {}
        replacement_sources = {}
        records_by_shot = {}
        records_by_id = {}
        command_counts = {}
        mutation_payloads = {"create": [], "revise": [], "rebase": [], "preview": []}
        review_count = {"value": 0}
        revise_count = {"value": 0}
        rebase_count = {"value": 0}
        source_version_docs = {}
        source_node_map = {}
        create_committed = asyncio.Event()
        create_release = asyncio.Event()
        issued_review_tokens=[]
        diff_changes={"items":[{"path":"/script_intents/intent-communication","before":"Saved communication","after":"Changed elsewhere"}]}

        def source_row(shot_id, *, inherited=False, node_type="action", title="Linked action", suffix="source"):
            edge_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{shot_id}:{suffix}:edge"))
            document_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{shot_id}:{suffix}:document"))
            version_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{shot_id}:{suffix}:version"))
            node_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{shot_id}:{suffix}:node"))
            row = {"edge_id": edge_id, "target_id": shot_id if not inherited else str(uuid.uuid5(uuid.NAMESPACE_URL, shot_id + ":scene")),
                   "node_id": node_id, "version_id": version_id, "logical_id": suffix, "node_type": node_type,
                   "title": title, "document_id": document_id, "version_label": "Imported version",
                   "current_version_id": version_id, "content_sha256": uuid.uuid5(uuid.NAMESPACE_URL, suffix + ":sha256").hex * 2,
                   "stale": False, "inherited": inherited}
            source_version_docs[version_id] = document_id
            source_node_map[node_id] = row
            return row

        async def route_api(route):
            name = route.request.url.split("/commands/")[-1]
            payload = route.request.post_data_json or {}
            command_counts[name] = command_counts.get(name, 0) + 1
            report["requests"].append({"name": name, "payload": payload})
            if name == "shot.sources":
                await route.fulfill(json={"items": shot_sources.get(payload["id"], [])})
            elif name == "document.show":
                await route.fulfill(json={"id": payload["id"], "title": "The winter screenplay",
                                          "current_version_id": source_version_docs.get(payload["id"], "")})
            elif name == "document.versions":
                document_id = payload["document_id"]
                versions = [{"id": version_id, "document_id": document_id, "number": index + 1, "label": "Imported version"}
                            for index, version_id in enumerate(version for version, doc in source_version_docs.items() if doc == document_id)]
                await route.fulfill(json={"items": versions, "total": len(versions), "limit": payload.get("limit", 100), "offset": 0, "next_offset": None})
            elif name == "document.node":
                row = source_node_map[payload["id"]]
                await route.fulfill(json={"id": row["node_id"], "version_id": row["version_id"], "title": row["title"],
                                          "node_type": row["node_type"], "logical_id": row["logical_id"], "content_sha256": row["content_sha256"], "is_current": True})
            elif name == "observation.list":
                records = [record for shot_id, record in records_by_shot.items() if not payload.get("shot_id") or shot_id == payload["shot_id"]]
                items = [{"id": record["id"], "shot_id": record["shot_id"], "current_version_id": record["current_version_id"],
                          "revision": record["revision"], "shot_title": "Fixture shot", "version_number": record["version"]["number"]} for record in records]
                await route.fulfill(json={"items": items, "total": len(items), "limit": payload.get("limit", 100), "offset": payload.get("offset", 0), "next_offset": None, "truncated": False})
            elif name == "observation.show":
                record = records_by_id[payload["contract_id"]]
                await route.fulfill(json=record)
            elif name == "observation.validate":
                record = records_by_id[payload["contract_id"]]
                checked = validation_for(record, shot_sources.get(record["shot_id"], []))
                record["validation"] = checked
                await route.fulfill(json={"contract_id": record["id"], "shot_id": record["shot_id"], "revision": record["revision"],
                                          "version_id": record["current_version_id"], **checked})
            elif name == "observation.diff":
                await route.fulfill(json={"contract_id": payload["contract_id"], "before_version_id": payload["before_version_id"],
                                          "after_version_id": payload["after_version_id"], "content_changed": True,
                                          "changes": diff_changes["items"]})
            elif name == "observation.create":
                mutation_payloads["create"].append(payload)
                contract_id = uid()
                record = make_record(contract_id, payload["shot_id"], payload["contract"], 1, 1, shot_sources[payload["shot_id"]])
                records_by_shot[payload["shot_id"]] = record
                records_by_id[contract_id] = record
                create_committed.set()
                await create_release.wait()
                await route.fulfill(json=record)
            elif name == "observation.revise":
                mutation_payloads["revise"].append(payload)
                revise_count["value"] += 1
                record = records_by_id[payload["contract_id"]]
                if revise_count["value"] == 1:
                    external_body = json.loads(json.dumps(record["contract"]))
                    external_body["script_intents"][0]["communication"] = "Changed elsewhere"
                    new_current = source_row(record["shot_id"], inherited=True, node_type="action", title="Replacement current action", suffix="replacement")
                    replacement_sources[record["shot_id"]]=new_current
                    shot_sources[record["shot_id"]] = [new_current]
                    remote = make_record(record["id"], record["shot_id"], external_body, record["revision"] + 1,
                                         record["version"]["number"] + 1, [new_current])
                    records_by_shot[record["shot_id"]] = remote
                    records_by_id[record["id"]] = remote
                    await route.fulfill(status=409, json={"error": {"code": "revision_conflict", "message": "The contract changed elsewhere."}})
                else:
                    updated = make_record(record["id"], record["shot_id"], payload["contract"], record["revision"] + 1,
                                          record["version"]["number"] + 1, shot_sources[record["shot_id"]])
                    records_by_shot[record["shot_id"]] = updated
                    records_by_id[record["id"]] = updated
                    await route.fulfill(json=updated)
            elif name == "observation.rebase-preview":
                mutation_payloads["preview"].append(payload)
                review_count["value"] += 1
                revision = records_by_id[payload["contract_id"]]["revision"]
                token = f"opaque-review-token-{review_count['value']}"
                issued_review_tokens.append(token)
                await route.fulfill(json={"contract_id": payload["contract_id"], "shot_id": payload.get("shot_id"),
                    "revision": revision, "saved_basis_sha256": "saved-basis", "current_basis_sha256": f"basis-{review_count['value']}",
                    "expected_basis_sha256": token, "basis_changed": True,
                    "changes": [{"path": "/shot/fields/duration", "saved_value": 4, "current_value": 6}], "changes_truncated": False})
            elif name == "observation.rebase":
                mutation_payloads["rebase"].append(payload)
                rebase_count["value"] += 1
                record = records_by_id[payload["contract_id"]]
                if rebase_count["value"] == 1:
                    external_body = json.loads(json.dumps(record["contract"]))
                    external_body["notes"] = "External basis review arrived during rebase."
                    updated = make_record(record["id"], record["shot_id"], external_body, record["revision"] + 1,
                                          record["version"]["number"] + 1, shot_sources[record["shot_id"]])
                    records_by_shot[record["shot_id"]] = updated
                    records_by_id[record["id"]] = updated
                    diff_changes["items"]=[{"path":"/notes","before":"Keep this hidden note.","after":"External basis review arrived during rebase."}]
                    await route.fulfill(status=409, json={"error": {"code": "revision_conflict", "message": "The reviewed basis changed."}})
                else:
                    updated = make_record(record["id"], record["shot_id"], payload["contract"], record["revision"] + 1,
                                          record["version"]["number"] + 1, shot_sources[record["shot_id"]])
                    records_by_shot[record["shot_id"]] = updated
                    records_by_id[record["id"]] = updated
                    await route.fulfill(json=updated)
            else:
                await route.continue_()

        await page.route("**/api/v1/projects/*/commands/*", route_api)
        try:
            await page.goto(args.url, wait_until="networkidle")
            await page.get_by_role("button", name="Story canvas", exact=True).click()
            shots=page.locator('.graph-node[aria-label^="Shot:"]')
            await shots.first.wait_for()
            assert await shots.count()>=2,"The browser fixture needs two visible shots."
            shot_a=shots.nth(0);shot_b=shots.nth(1)
            shot_a_id=await shot_a.get_attribute("data-node-id");shot_b_id=await shot_b.get_attribute("data-node-id")
            assert shot_a_id and shot_b_id and shot_a_id!=shot_b_id
            shot_sources[shot_a_id]=[source_row(shot_a_id,title="First linked action",suffix="first")]
            direct_scene=source_row(shot_b_id,node_type="scene",title="Whole screenplay scene",suffix="direct-scene")
            scene_context=source_row(shot_b_id,inherited=True,node_type="action",title="Inherited scene action",suffix="scene-context")
            shot_sources[shot_b_id]=[direct_scene,scene_context]
            intent_id,requirement_id,continuity_id,reference_id=uid(),uid(),uid(),uid()
            initial_body={"schema":"storyboarder.observation-contract/v1","source_pins":[{"edge_id":direct_scene["edge_id"],"source_scope":"direct-element"}],
                "script_intents":[{"id":intent_id,"source_edge_id":direct_scene["edge_id"],"source_scope":"direct-element","purpose":"Establish the room","communication":"Saved communication","basis":"interpreted"}],
                "requirements":[{"id":requirement_id,"priority":"must","basis":"direct","source_edge_ids":[direct_scene["edge_id"]],"statement":"The key changes hands before the turn.","topic":None}],
                "references":[reference_id],"continuity":[{"id":continuity_id,"related_shot_ids":[shot_a_id],"statement":"The same key remains in Eli's hand."}],"notes":"Keep this hidden note."}
            contract_b=uid()
            preseed=make_record(contract_b,shot_b_id,initial_body,2,2,shot_sources[shot_b_id])
            records_by_shot[shot_b_id]=preseed;records_by_id[contract_b]=preseed

            async def select_shot(card):
                await card.focus();await card.press("Enter")
                await page.get_by_role("tab",name="Shot intent",exact=True).click()
                await page.locator(".shot-intent-panel").wait_for()

            async def fill_new_draft():
                await page.locator(".shot-source-option input").first.check()
                await page.get_by_role("button",name="Add purpose",exact=True).click()
                card=page.locator(".shot-intent-card[data-intent-id]").first
                intent=await card.get_attribute("data-intent-id")
                await card.locator('input[aria-label^="Purpose "]').fill("A purpose that survives navigation")
                await card.locator('textarea[aria-label^="Communication "]').fill("Keep this local draft visible after leaving the tab.")
                return intent

            await select_shot(shot_a)
            await page.get_by_role("button",name="Create observation contract",exact=True).wait_for()
            draft_a_intent=await fill_new_draft()
            await page.get_by_role("tab",name="Story direction",exact=True).click()
            unload_state=await page.evaluate("""()=>{const event=new Event('beforeunload',{cancelable:true});const allowed=window.dispatchEvent(event);return {blocked:!allowed,returnValue:event.returnValue}}""")
            assert unload_state["blocked"],unload_state
            async with page.expect_event("dialog") as dialog_info:
                reload_task=asyncio.create_task(page.reload(timeout=1800))
            unload_dialog=await dialog_info.value
            assert unload_dialog.type=="beforeunload",unload_dialog.type
            await unload_dialog.dismiss()
            try:
                await reload_task
            except Exception as reload_error:
                assert "Timeout" in str(reload_error),str(reload_error)
            await page.get_by_role("tab",name="Shot intent",exact=True).click()
            await page.locator(".shot-intent-card[data-intent-id]").wait_for()
            restored_tab_value=await page.locator(".shot-intent-card[data-intent-id] input[aria-label^='Purpose ']").input_value()
            restored_tab_pin=await page.locator(".shot-source-option input:checked").count()
            assert restored_tab_value=="A purpose that survives navigation" and restored_tab_pin==1,(restored_tab_value,restored_tab_pin)
            await shot_b.focus();await shot_b.press("Enter")
            await page.get_by_role("tab",name="Shot intent",exact=True).click()
            await page.get_by_label(f"Purpose {intent_id}",exact=True).wait_for()
            clean_shot_unload=await page.evaluate("""()=>{const event=new Event('beforeunload',{cancelable:true});return !window.dispatchEvent(event)}""")
            assert clean_shot_unload,"A dirty draft for shot A must guard unload while clean shot B is selected."
            await shot_a.focus();await shot_a.press("Enter")
            await page.get_by_role("tab",name="Shot intent",exact=True).click()
            await page.locator(".shot-intent-card[data-intent-id]").wait_for()
            restored_shot_value=await page.locator(".shot-intent-card[data-intent-id] input[aria-label^='Purpose ']").input_value()
            restored_shot_pin=await page.locator(".shot-source-option input:checked").count()
            assert restored_shot_value=="A purpose that survives navigation" and restored_shot_pin==1,(restored_shot_value,restored_shot_pin)
            report["draft_switch"]={"intent_id":draft_a_intent,"tab_return_value":restored_tab_value,"shot_return_value":restored_shot_value,
                                    "tab_return_pins":restored_tab_pin,"shot_return_pins":restored_shot_pin,
                                    "beforeunload_cancelled_after_tab_unmount":unload_state["blocked"],"real_reload_prompt_dismissed":True,
                                    "beforeunload_cancelled_from_clean_other_shot":clean_shot_unload}
            report["passed"].append(cases[0])

            await page.locator(".shot-intent-card[data-intent-id]").locator('input[aria-label^="Purpose "]').fill("Create from selected shot A")
            await page.locator(".shot-intent-card[data-intent-id]").locator('textarea[aria-label^="Communication "]').fill("The scene intent is shown clearly.")
            create_button=page.get_by_role("button",name="Create observation contract",exact=True)
            await create_button.click()
            await asyncio.wait_for(create_committed.wait(),5)
            await page.wait_for_function("document.querySelector('.shot-intent-fields')?.disabled===true")
            assert await page.locator('.shot-intent-card input[aria-label^="Purpose "]').is_disabled()
            await shot_b.focus();await shot_b.press("Enter")
            await page.get_by_role("tab",name="Shot intent",exact=True).click()
            await page.get_by_label(f"Purpose {intent_id}",exact=True).wait_for()
            assert await page.get_by_label(f"Purpose {intent_id}",exact=True).input_value()=="Establish the room"
            await page.locator(".shot-pin-comparison").get_by_text(direct_scene["content_sha256"],exact=True).first.wait_for()
            assert await page.locator(".shot-pin-comparison").get_by_text(direct_scene["content_sha256"],exact=True).count()>=2
            await shot_a.focus();await shot_a.press("Enter")
            await page.get_by_role("tab",name="Shot intent",exact=True).click()
            await page.get_by_label(f"Purpose {draft_a_intent}",exact=True).wait_for()
            assert await page.get_by_label(f"Purpose {draft_a_intent}",exact=True).input_value()=="Create from selected shot A"
            assert await page.locator(".shot-intent-fields input[type=checkbox]").first.is_disabled(),"A remounted editor must lock while its own write is pending."
            pending_unload=await page.evaluate("""()=>{const event=new Event('beforeunload',{cancelable:true});return !window.dispatchEvent(event)}""")
            assert pending_unload,"A pending write must guard page unload even after its submitting editor unmounted."
            await shot_b.focus();await shot_b.press("Enter")
            await page.get_by_role("tab",name="Shot intent",exact=True).click()
            create_release.set()
            await asyncio.sleep(.3)
            assert not await page.get_by_label(f"Purpose {intent_id}",exact=True).is_disabled()
            assert await page.get_by_label(f"Purpose {intent_id}",exact=True).input_value()=="Establish the room"
            assert len(mutation_payloads["create"])==1
            create_payload=mutation_payloads["create"][0]
            contract_a=records_by_shot[shot_a_id]["id"]
            assert create_payload["shot_id"]==shot_a_id and create_payload["expected_shot_revision"]>=1
            assert create_payload["contract"]["source_pins"]==[{"edge_id":shot_sources[shot_a_id][0]["edge_id"],"source_scope":"direct-element"}]
            assert create_payload["contract"]["script_intents"][0]["id"]==draft_a_intent
            assert create_payload["contract"]["script_intents"][0]["purpose"]=="Create from selected shot A"
            report["pending_owner"]={"created_shot_id":shot_a_id,"visible_shot_id":shot_b_id,"create_posts":len(mutation_payloads["create"]),
                                     "same_owner_remount_locked":True,"other_shot_purpose":await page.get_by_label(f"Purpose {intent_id}",exact=True).input_value()}
            report["passed"].append(cases[1]);report["passed"].append(cases[2])

            await shot_a.focus();await shot_a.press("Enter");await page.get_by_role("tab",name="Shot intent",exact=True).click()
            await page.get_by_label(f"Purpose {draft_a_intent}",exact=True).wait_for()
            assert await page.get_by_label(f"Purpose {draft_a_intent}",exact=True).input_value()=="Create from selected shot A"
            assert await page.get_by_label("Observation contract",exact=True).input_value()==contract_a
            assert await page.get_by_role("button",name="Create observation contract",exact=True).count()==0
            await shot_b.focus();await shot_b.press("Enter");await page.get_by_role("tab",name="Shot intent",exact=True).click()
            await page.get_by_role("button",name=re.compile(r"Save draft"),exact=True).wait_for()
            assert await page.locator(".shot-source-option").get_by_text("Direct shot link · Scene node · Whole screenplay scene").count()==1
            assert await page.locator(".shot-source-option").get_by_text("Scene context · action · Inherited scene action").count()==1
            await shot_b.focus();await shot_b.press("Enter");await page.get_by_role("tab",name="Shot intent",exact=True).click()
            await page.get_by_label(f"Communication {intent_id}",exact=True).fill("My local edit must survive the conflict.")
            await page.get_by_label(f"Requirement statement {requirement_id}",exact=True).fill("My local requirement after refresh.")
            await page.get_by_role("button",name="Save draft",exact=True).click()
            await page.get_by_role("alert").filter(has_text="A newer saved revision is available").wait_for()
            await page.get_by_text("Changed elsewhere",exact=True).wait_for()
            assert await page.get_by_label(f"Communication {intent_id}",exact=True).input_value()=="My local edit must survive the conflict."
            assert await page.get_by_label(f"Requirement statement {requirement_id}",exact=True).input_value()=="My local requirement after refresh."
            assert await page.locator(".shot-source-stale").get_by_text(direct_scene["edge_id"],exact=True).count()==1
            assert await page.locator(".shot-source-option input:checked").count()==0
            replacement=replacement_sources[shot_b_id]
            preview_retarget=page.get_by_role("button",name=re.compile(r"^Preview retarget from .*Replacement current action$"))
            await preview_retarget.click()
            await page.get_by_role("group",name="Retarget preview",exact=True).wait_for()
            retarget_panel=page.get_by_role("group",name="Retarget preview",exact=True)
            assert await retarget_panel.get_by_text(direct_scene["content_sha256"],exact=True).count()==1
            assert await retarget_panel.get_by_text(replacement["content_sha256"],exact=True).count()==1
            assert await page.get_by_label(f"Source for purpose {intent_id}",exact=True).input_value()==direct_scene["edge_id"]
            await retarget_panel.get_by_role("button",name="Retarget draft pin",exact=True).click()
            assert await page.get_by_label(f"Source for purpose {intent_id}",exact=True).input_value()==replacement["edge_id"]
            assert await page.locator(".shot-source-option input:checked").count()==1
            assert await page.locator(f'.shot-intent-card[data-requirement-id="{requirement_id}"] .shot-edge-select input:checked').count()==1
            assert await page.locator(".shot-source-stale").get_by_text(direct_scene["edge_id"],exact=True).count()==0
            assert len(mutation_payloads["revise"])==1
            revise_payload=mutation_payloads["revise"][0]
            assert revise_payload["revision"]==2 and revise_payload["contract_id"]==contract_b
            assert revise_payload["contract"]["source_pins"]==initial_body["source_pins"]
            report["conflict_preservation"]={"base_revision":2,"remote_revision":records_by_id[contract_b]["revision"],
                "saved_diff_visible":True,"local_communication":await page.get_by_label(f"Communication {intent_id}",exact=True).input_value(),
                "local_requirement":await page.get_by_label(f"Requirement statement {requirement_id}",exact=True).input_value(),
                "old_exact_pin_retained_in_failed_request":revise_payload["contract"]["source_pins"]==initial_body["source_pins"],
                "replacement_retained_unmodified_until_explicit_retarget":True,"explicit_retarget_edge":replacement["edge_id"],
                "retarget_source_sha256":replacement["content_sha256"],"new_source_selected_after_confirm":await page.locator(".shot-source-option input:checked").count()==1}
            report["passed"].append(cases[3])

            await page.get_by_role("button",name="Review rebase",exact=True).click()
            await page.get_by_role("heading",name="Reviewed basis changes",exact=True).wait_for()
            first_token=mutation_payloads["preview"][-1]
            assert first_token["contract"]["requirements"][0]["statement"]=="My local requirement after refresh."
            await page.get_by_label(f"Requirement statement {requirement_id}",exact=True).fill("A changed proposal invalidates the token.")
            assert await page.get_by_role("button",name="Confirm reviewed rebase",exact=True).count()==0
            assert await page.get_by_text(first_token.get("expected_basis_sha256","never-a-token"),exact=True).count()==0
            await page.get_by_role("button",name="Review rebase",exact=True).click()
            await page.get_by_role("button",name="Confirm reviewed rebase",exact=True).wait_for()
            assert mutation_payloads["preview"][-1]["contract"]["requirements"][0]["statement"]=="A changed proposal invalidates the token."
            await page.get_by_role("button",name="Confirm reviewed rebase",exact=True).click()
            await page.get_by_role("alert").filter(has_text="The reviewed basis changed").wait_for()
            assert await page.get_by_role("button",name="Confirm reviewed rebase",exact=True).count()==0
            assert await page.get_by_label(f"Requirement statement {requirement_id}",exact=True).input_value()=="A changed proposal invalidates the token."
            assert len(mutation_payloads["rebase"])==1 and mutation_payloads["rebase"][0]["expected_basis_sha256"]==issued_review_tokens[1]
            await page.locator(".inspector").get_by_text("External basis review arrived during rebase.",exact=True).wait_for(state="visible")
            assert "External basis review arrived during rebase." in await page.locator(".inspector").inner_text()
            await page.get_by_role("button",name="Review this draft again",exact=True).click()
            await page.get_by_role("button",name="Confirm reviewed rebase",exact=True).wait_for()
            fresh_token=mutation_payloads["preview"][-1]
            assert fresh_token["contract"]["requirements"][0]["statement"]=="A changed proposal invalidates the token."
            await page.get_by_role("button",name="Confirm reviewed rebase",exact=True).click()
            await page.get_by_role("status").filter(has_text="Shot intent saved as contract revision").wait_for()
            rebase_payloads=mutation_payloads["rebase"]
            assert len(rebase_payloads)==2
            assert rebase_payloads[0]["expected_basis_sha256"]!=rebase_payloads[1]["expected_basis_sha256"]
            assert rebase_payloads[1]["expected_basis_sha256"]==issued_review_tokens[-1]
            final_body=rebase_payloads[1]["contract"]
            assert final_body["references"]==[reference_id] and final_body["continuity"]==initial_body["continuity"] and final_body["notes"]==initial_body["notes"]
            assert final_body["script_intents"][0]["id"]==intent_id and final_body["requirements"][0]["id"]==requirement_id
            report["rebase_tokens"]={"attempts":len(rebase_payloads),"old_token_invalidated":True,"new_token_used":rebase_payloads[1]["expected_basis_sha256"],
                "stable_ids_preserved":[intent_id,requirement_id],"hidden_fields_preserved":True}
            report["passed"].append(cases[4])

            tab=page.get_by_role("tab",name="Shot intent",exact=True)
            await page.set_viewport_size({"width":390,"height":844})
            await tab.focus();await tab.press("End")
            assert await page.get_by_role("tab",name="Story direction",exact=True).get_attribute("aria-selected")=="true"
            await page.keyboard.press("Home");await page.get_by_role("tab",name="Details",exact=True).wait_for()
            await tab.focus();await tab.press("ArrowRight")
            assert await page.get_by_role("tab",name="Story direction",exact=True).get_attribute("aria-selected")=="true"
            direction_tab=page.get_by_role("tab",name="Story direction",exact=True)
            await direction_tab.press("ArrowLeft")
            assert await page.get_by_role("tab",name="Shot intent",exact=True).get_attribute("aria-selected")=="true"
            await tab.press("ArrowLeft")
            assert await page.get_by_role("tab",name="References",exact=True).get_attribute("aria-selected")=="true"
            snapshot=await page.locator(".inspector").evaluate("e=>({role:e.getAttribute('role'),modal:e.getAttribute('aria-modal'),activeInside:e.contains(document.activeElement),overflow:document.documentElement.scrollWidth>innerWidth})")
            assert snapshot=={"role":"dialog","modal":"true","activeInside":True,"overflow":False},snapshot
            report["responsive_keyboard"]=snapshot
            report["passed"].append(cases[5])
            report["passed_all"]=True
        except Exception as error:
            report["failed"].append({"case":cases[len(report["passed"])] if len(report["passed"])<len(cases) else "setup_or_browser",
                                     "error":f"{type(error).__name__}: {error}","traceback":traceback.format_exc()})
            await page.screenshot(path=str(output/"failure.png"),full_page=True)
            (output/"failure.txt").write_text(await page.locator("body").inner_text())
            report["never_run"]=cases[len(report["passed"])+1:]
            report["passed_all"]=False
        finally:
            await browser.close()
            (output/"browser-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    return 0 if report.get("passed_all") and not report["page_errors"] and not report["console_errors"] else 1


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--url",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--chromium")
    sys.exit(asyncio.run(main(parser.parse_args())))
