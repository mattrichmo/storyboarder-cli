# Context and media semantics

## Context is authored, not an invisible prompt

The scope chain is project → sequence → scene → shot. Known scalar defaults are
`location_id`, `time`, `framing`, `camera`. The nearest non-empty value wins; its source
ID/title/kind is reported. Empty/None inherits. This release does not use a separate
"explicitly no location" scalar sentinel; write a named constraint when required.

Project premise/visual style, sequence arc/tone, summaries, continuity and constraints
enter resolved direction with their source. Reusable named text blocks have an owner,
key, content, operation, order and revision. `append` accumulates. `replace` removes
same-key inherited entries and adds the authored content. `exclude` removes same-key
inherited direction at that scope. History records both the operation and removed
sources, so opting out is visible. A lower scope can explicitly add new direction
after an exclusion. Shot action, dialogue, duration and notes remain structured fields
in composition; the adapter request includes an authored shot snapshot as well.

CLI example with actual IDs substituted:

```sh
storyboarder context put --owner-id PROJECT_ID --key lighting --content "Soft overcast daylight." --operation append
storyboarder context put --owner-id SHOT_ID --key lighting --content "Available practical light." --operation replace
storyboarder context resolve --owner-id SHOT_ID --json
```

The exact command fields and defaults are in [CLI.md](CLI.md). Use revisions returned
by read/list operations for subsequent block editing/removal.

## Three independent image roles

**Intake** is a review state for an import occurrence. Two occurrences can point to one
managed media record when their SHA-256 hashes match. Original paths/names remain
metadata. **Reference media** is attached through asset-media memberships and optional
exact-media shot assignments. **Frames** are output candidate records attached to shots
with separate versions/states. A managed file can support both roles without collapsing
their meaning; export labels distinguish them.

Create/attach/merge are common services used across interfaces. Selecting a primary
asset image only changes the library default. It never rewrites a shot's exact choice.
Changing/detaching a membership needed by a shot is guarded. Conceptual assignments
without an exact image stay explicit and do not receive hidden fallbacks. A location
asset set as a scalar default appears as a derived scene/shot-to-location connection
in Canvas and the TUI. It remains context, not a per-shot reference-image assignment.
Assign a particular location image with the `setting-reference` role when a shot needs
that exact file in its composition or export.

Approved frame history is protected. Demote explicitly before selecting/approving a
replacement. Archiving a reference asset or frame is not byte destruction. Intake
Discard similarly preserves shared files. Original managed bytes are immutable through
normal app actions; modifying them externally produces doctor/export integrity errors.

## Import safety and recovery

Decoding validates the actual image, not its extension alone. Animated/multi-frame,
oversized, malformed and unsupported images are rejected with reasons. Original names
are sanitized for managed storage and all stored paths are relative, resolved within
the project, and checked against symlink traversal. Folder recursion is explicit and
bounded; browser file selection transfers only selected bytes, never a server-local
arbitrary path.

Thumbnails use Pillow and live in `.storyboarder/cache`. They can be rebuilt or removed
without changing authored data or original files. Doctor distinguishes missing originals,
changed hashes, orphan files, migration faults and recoverable staging residue. Keep a
backup and review orphan/staging warnings; this release intentionally does not offer a
hazardous automatic "delete all unreferenced files" cleanup.
