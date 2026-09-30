# Exports, integrity and recovery

## Composition and portable bundles

Choose a project, sequence, scene or shot scope. The composer produces a versioned,
deterministic snapshot containing owner/project metadata, ordered scenes/shots,
authored fields, inherited values with provenance, exact assignments, separate frame
candidates, required media and validation messages. Missing selected media is an
error. An asset assignment without an exact image is a visible warning, not permission
to substitute a different image.

`export bundle --owner-id ID` creates a directory and a ZIP under `exports/scenes/`:

```text
manifest.json
scene.json
scene.md
context-provenance.json
media/<media-id>.<canonical-extension>
```

Default bundles copy the exact selected inputs, including relevant frame candidates,
and use bundle-relative paths in the data. Hashes and the file inventory enable
integrity checking. No project cache or absolute managed path is needed to use the
bundle. `--no-include-media` explicitly requests a data-only bundle; do not describe
that opt-out export as self-contained.

Stable JSON ordering and fixed ZIP entry timestamps make unchanged exports repeatable.
A deterministic content key identifies each export. Existing files are hash-verified
before reuse. If an existing export was edited externally, move it aside rather than
expecting a subsequent export to overwrite it. Concurrent identical exports are
serialized under a file lock and atomically committed from staging.

## Presentation boards

`export board --owner-id ID --format all` writes HTML, PDF and PNG sheets plus the
composition, manifest and exact media into a shareable directory/ZIP. Individual
`html`, `pdf`, `png` formats are supported. Scene and full-sequence exports work offline.

Presentation boards are intentionally not screenshots of the editing canvas. A large
panel prioritizes the approved frame, or selected candidate when permitted, otherwise
an explicitly labelled reference-only image. Reference strips retain exact selections.
Approved-only mode affects storyboard candidate choice; labelled references remain
available. Multi-page HTML/PDF and multiple PNG sheets preserve long sequences.

HTML carries full authored text. Fixed paper/image panels abbreviate lengthy fields
and point to the complete JSON/Markdown; never use a short panel as the only archival
script record. ReportLab uses portable built-in PDF fonts: full multilingual glyph
coverage is not guaranteed. For complex scripts use the full HTML in a suitable local
browser/print workflow. PNG contact sheets are visual summaries, not replacements for
the structured package. TIFF/BMP originals remain in the package, with derived JPEG
presentation previews for web compatibility.

## Doctor and cache

```sh
storyboarder doctor --project ./my-film --hashes --json
storyboarder cache rebuild --project ./my-film
storyboarder cache clear --project ./my-film
```

Doctor checks SQLite integrity/foreign keys, migration state, story hierarchy, typed
relationships/assignments, location defaults, context ownership, unsafe/missing paths,
optional full hashes and recoverable orphan/staging issues. Hash checking can take
longer on large originals. Cache clear removes only derived thumbnails. A corrupt or
missing database is not initialized over existing data: preserve the damaged folder
and restore a verified backup to a different location.

## Backups

`storyboarder backup --project ./my-film --json` reports the created ZIP path under
`exports/backups/`. SQLite's online backup API captures a consistent database with a
writer boundary while immutable managed media is collected. Project metadata and
stored job requests/pending results/logs are included. Cache, exports, staging and
previous backups are excluded, avoiding recursive archives.

Wait for or cancel external runs before an archival backup: a live script's in-progress
logs/output are not an independent quiescent artifact. Approved canonical media remains
covered by the database/managed-file boundary. Keep at least one backup outside the
project's disk; there is no cloud copy unless you make it.

```sh
storyboarder restore ./my-film/exports/backups/BACKUP.zip ./recovered-film
storyboarder doctor --project ./recovered-film --hashes --json
storyboarder project open ./recovered-film
```

Restore only targets a new/nonexistent destination. Archive entries, paths, symlinks,
counts, expanded size and every declared file hash are checked before making the
folder visible. Backup creation enforces the same limits before publishing an archive:
100,000 files, 10 GiB expanded data, and a 20 MiB manifest. Restore also limits archives
to 100,000 entries and 10 GiB expanded data. The browser restore upload additionally has a
1 GiB request ceiling. Use CLI for larger compressed archives within the expansion limits.

Moving a whole project preserves IDs. Close all writers before a plain folder move,
or use the backup API instead. Do not copy only `storyboard.sqlite3` while WAL writers
are active. Register the moved/restored path to update the workspace. When two copies
share an ID, the registered path is preferred and other paths are reported as duplicates;
the workspace does not present them as two independent stories.

## Upgrade / interrupted operation

Back up first. Install the new package and open the project. Numbered SQL migrations
apply in order and record checksums. Before upgrading an older database, the repository
creates a database-only `before-vN` backup. This is not a substitute for a media-inclusive
project backup. Never edit a released migration or manually alter `user_version`.

After a crash: preserve the folder; run doctor; confirm originals; review staging/orphan
warnings; clear/rebuild cache if needed. An interrupted running job can be cancelled and
explicitly retried after its process/lock is gone. Approval checks output hashes again,
so a damaged pending result cannot silently become an ordinary asset.
