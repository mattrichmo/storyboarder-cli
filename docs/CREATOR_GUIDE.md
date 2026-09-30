# Creator walkthrough

## 1. Begin with an empty workspace

Run `storyboarder workspace init ./stories`, then `storyboarder ui --workspace
./stories`. Choose **New project**, enter a title and folder name. The browser may
create only under this workspace's `projects/` directory. An outside project requires
an explicit `storyboarder ui --project /path/to/project` launch.

The same project is visible to `storyboarder project list --workspace ./stories`
and `storyboarder tui --workspace ./stories`. Create a second project and switch
between them to see separate records and managed media.

## 2. Gather references

Open **Intake queue** and choose files or a folder. Browser selection grants only
those uploaded bytes; it does not grant arbitrary disk access. Recursive folder
selection is explicit. Alternatively: `storyboarder import /path/to/references
--project ./stories/projects/my-film --recursive`.

Each incoming still image has an intake record. Exact duplicates are labelled by
hash; they do not consume another copy of managed bytes. Review tags and choose
**Accept intake item** to attach to an existing asset or create a typed asset. Use
**Discard** for an intake item you do not need. This does not delete an image that
another asset/shot/frame uses.

In **Asset library**, edit names, descriptions, tags and aliases. Attach more images
to the same asset and mark a primary reference. The asset inspector's reference tab
lets you inspect its particular images; exact shot references are selected separately.
Use merge only after reviewing source/target assets; references are reassigned and
the source is archived rather than erased.

## 3. Build the story

Create a sequence in **Story outline**, a scene under it, then shots under the scene.
Edit location/time, scene summary and continuity. On each shot author the action,
dialogue, framing, camera direction, duration and notes as separate fields. IDs remain
stable when titles change. **Move / reorder** takes a parent and a zero-based index;
this is a canonical reorder, unlike canvas dragging.

Assign a character/location/prop/reference to a shot with an appropriate role.
Choose an exact image from that asset when the shot should depend on a particular
reference. Leaving it blank records a conceptual asset assignment and a visible
composition warning—not a silent primary-image substitution.

## 4. Make direction explicit

In **Story guide**, choose a scope. Author the project premise/visual style, sequence
arc/tone, scene continuity or shot constraints. Add reusable direction blocks with
keys such as `wardrobe`, `lighting` or `camera-rules`. Use append, replace or exclude.
Preview the resolved scope to see the source of each inherited value and any explicit
exclusions. A shot-level location overrides a scene default; clearing it inherits.

## 5. Explore and arrange

**Canvas & connections** has Story flow, Asset network and Scene board modes. Choose
**Fit view** after opening a large view. Search/focus and filters narrow the working
set. Select a card to inspect it without hiding the graph on desktop. Drag a card or
use its arrow keys; save the arrangement under a named layout.

Press **L** on a focused node, focus a destination and press **Enter** to create a
valid link through a typed form. Invalid endpoint combinations explain the rule.
Select a story-order edge to move/reorder its child. Deleting a card opens a usage
review: hide only this view, archive, or delete an unreferenced underlying record.

## 6. Add frame candidates

In **Frame comparison**, choose a shot. Upload an externally drawn image, or attach
an existing managed image as a candidate. It receives its own candidate version,
notes and state, even when it uses bytes already in the reference library. Compare
checkboxes show two or more candidates side by side. Select or approve deliberately;
approved candidates are protected from silent replacement. A newly generated
candidate is still a draft and does not replace an approved frame.

## 7. Preview and export

Open **Composition & exports**, choose a scene, sequence or project and resolve
missing inputs reported by validation. The preview identifies inherited context,
exact references, preferred frames and reference-only panels. Export a portable
scene bundle, or HTML + PDF + PNG boards. The self-contained ZIP is available through
the browser and remains on disk under the project's `exports/` folder.

For CLI exports, obtain an ID with `scene list --json`, then run:

```sh
storyboarder --project ./my-film compose SCENE_ID --json
storyboarder --project ./my-film export bundle --owner-id SCENE_ID --json
storyboarder --project ./my-film export board --owner-id SEQUENCE_ID --format all --json
```

`SCENE_ID` and `SEQUENCE_ID` are placeholders for IDs returned by your own project.

## 8. Back up, move and reopen

Run `storyboarder backup --project ./my-film --json`. Restore the reported archive
to a new path with `storyboarder restore /path/to/backup.zip ./recovered-film`.
Run `storyboarder doctor --project ./recovered-film --hashes`. Open it directly with
`storyboarder ui --project ./recovered-film`—registration is not required.

To move a folder instead, close the UI/TUI and all other writers first, then move the
entire project folder, not just the SQLite file. Reopen by its new path. Managed media
survives the move because its database paths are relative. Register the moved path to
repair an old workspace navigator entry. Do not delete the old copy until the new one
has passed doctor and your chosen exports have been checked.

## 9. Optional external-script exercise

The offline adapter demonstration and exact commands are in [AUTOMATION.md](AUTOMATION.md).
It creates a labelled test slate, records provenance and leaves results pending your
review. It does not call a provider or require credentials.
