# In-house canvas and accessible interactions

`clients/web/src/canvas/Canvas.tsx` renders React node cards and native SVG paths.
`geometry.ts` owns screen/world conversion, hit testing, fit/zoom, edge paths,
deterministic tidy placement and collapsed descendants. No React Flow or third-party
graph editing package is installed.

## Focused views

**Story flow** derives sequence → scene → shot edges from canonical parent/order
fields. **Asset network** shows filtered asset types/tags and typed relationships.
**Scene board** shows an ordered scene's shot cards, the references they use, and its
effective default-location connection. The edge reports which scope supplied the
location. That contextual link does not choose a shot's exact image; assign a location
image as `setting-reference` when a shot needs that exact file in its composition or
export. All three render the same project records. A 250-node view limit is explicit;
refine filters rather than treating a truncated view as the complete project.

Each asset card labels its type, title, primary thumbnail and counts. Each shot card
shows its number/order, framing, short authored action and reference count; the
inspector exposes full authored fields, exact images, context and related records.
Sequence and scene cards show order and child counts. Expand/collapse is presentation.

## Pointer and keyboard

Drag the background to pan; scroll pans; Ctrl/Command+scroll zooms around the cursor.
Toolbar zoom and Fit view are available without a gesture. Dragging selected cards,
including shift multi-selection, changes only positions. Arrow keys arrange focused
cards in ten-unit steps; Shift+arrows uses fifty units. Tab reaches cards and edge
controls. Enter selects/inspects. L starts a connection; focus an eligible destination
and press Enter, then complete the typed form. Escape cancels link/edge selection.

Order edges are solid, numbered and labelled. Asset links are dashed with their verb.
Shot assignments are dotted with their role and exact-image indication. Location
defaults use a dash-dot line and open the owning story scope for editing. Select an
edge to remove a stored relationship/assignment or reorder a story child; derived
location edges are changed by editing the context field, and there is no arbitrary
edge record independent of the domain model. Invalid endpoint/role
combinations return explanatory validation, and `part-of` rejects cycles.

The new-record toolbar has a type selector followed by a labelled form. New records
are persisted before appearing in the graph. Reparent/reorder uses explicit controls;
visual proximity or a drag never changes narrative order.

## Named layouts and deletion

Save a name for each view. Positions, hidden/collapsed IDs, filters and viewport are
stored independently from story records with their own revision. Tidy is deterministic
and does not rewrite canonical order. Unsaved arrangements are kept per project for
the open app session: navigating to another page or project and returning restores
positions, viewport, filters, hidden/collapsed cards and the selected layout's save
revision. Save the arrangement to keep it across app sessions. Switching canvas
modes/loading another layout warns before replacing unsaved positions. Closing or
reloading the app warns if any project has a dirty arrangement, even on another page.

Delete/Backspace opens usage review. **Hide** changes this layout only. **Archive**
changes the record's lifecycle across all interfaces. **Delete** is available only
when no canonical references prevent it, and requires confirmation. Stale presentation
positions for removed/filtered IDs may remain in a layout; they never create nodes or
relationships on their own.

## Accessibility and responsive behavior

Native labelled controls, visible focus outlines, textual state labels, keyboard
selection/linking and separate line styles avoid color-only meaning. Modals trap focus
and return it on close. The mobile inspector becomes a named, focus-managed dialog;
Escape closes it. Hidden mobile navigation is inert. Reduced-motion preferences remove
transitions. Management/library pages reflow; canvas controls wrap and the canvas itself
remains a desktop-oriented work surface.

Automated browser verification includes real keyboard link creation and presentation-only
dragging, plus a 390px library/inspector check. This is not a claim of formal WCAG or
screen-reader certification; test your chosen assistive technology before adopting it
for an accessibility-critical production workflow.
