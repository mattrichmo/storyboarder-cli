# Storyboarder — a calm editorial production desk

This is the interface design contract, established before the React shell. The app
is a working desk, not a cinematic landing page. Story and media carry the emphasis.

## Tokens

Warm paper `#f6f5f0`; surface `#fffefa`; ink `#292f2a`; muted ink `#656c63`;
rule `#d9ddd3`; selected forest `#405b48`; character surface `#e8ece6`; location
surface `#e6efed`; prop surface `#eee8df`; reference surface `#eae7ef`. Error ink
`#913c36`; warning ink `#875c25`; approved ink `#405b48`. Text labels accompany every state.

UI typography: local system sans, 14px base / 1.5 line height. Editorial headings:
Georgia, regular, 32–46px. IDs, counts and shot numbers: local monospace. No remote
fonts, bundled font files, gradients, decorative shadows or ornamental motion.

## Layout specimens

Dashboard: 238px navigation rail | 40px inset work surface. A small uppercase
WORKSPACE label, generous serif title, one clear create action, then simple project
rows with title, counts, last update and a short folder path. An empty workspace
explains the next action rather than displaying fictional statistics.

Asset node: 238px wide, labelled type header, text type badge, 92px image area when an image
is present, title and compact tags/counts. Reference media can be inspected without
turning the canvas node into another nested page.

Shot node: 238px wide, shot number and SHOT badge, preferred frame or neutral
placeholder, short title/action, framing, reference count. Draft/selected/approved
is written out; it is never implied only by a green border.

Edges: containment uses a solid line and visible 01/02 order labels; asset
relationships use a dashed line and the relationship verb; shot assignments use
a dotted line, role and exact-image indicator. All edge actions also exist in
keyboard-accessible lists/forms. No arbitrary or dangling endpoint creation.

Inspector: a 330px right column on large desktops. The canvas remains visible.
Type and title, compact reference previews, authored fields, context provenance,
then related records. Editing uses labelled controls and one clearly labelled action.
On small screens it becomes a dismissible, focus-managed dialog.

Scene board: separate presentation vocabulary. Large 16:9 panels, shot number,
framing, action, dialogue/notes, and labelled reference strips. Reference-only
panels explicitly say they are not storyboard frames. HTML retains complete text;
PDF/image sheets abbreviate only where documented and point to the complete JSON.

## Interaction vocabulary

Intake: Pending / Accepted / Discarded; duplicates mean equal SHA-256, not visually
similar. Frame: Draft / Selected / Approved / Archived. Save: Saving / Saved /
Changed elsewhere—reload. Destructive action: Hide in this layout / Archive record /
Delete unreferenced record. Hiding is presentation state, not data deletion.

Keyboard: visible focus, native inputs/buttons, Escape closes dialogs, Tab is
trapped only inside modal dialogs, arrow keys can reposition canvas selection,
Enter opens the inspector, L starts a valid connection. Reduced-motion removes
transitions. Library/project management reflow to narrow windows; the canvas is a
focused desktop surface with controls that wrap rather than clip.

TUI uses identical nouns and action order. Sidebar pages, searchable record table,
context/detail pane, action forms and confirmation dialogs remain reachable by
keyboard. Compact ANSI thumbnails are optional aids; viewer handoff is explicit.
