# Development, installation and release

## Installed path versus source path

Python 3.11 or later is required. Normal users install the wheel or run `pip install .`
from the source folder. The wheel includes SQL migrations, HTML/CSS/JS, React runtime,
favicon and licenses. `storyboarder` is the console entry point. Node is never needed
for installed operation.

For contributors use `python -m pip install -e '.[dev]'`, then `npm ci` in `clients/web/`.
Node 20+ is recommended for recursive source watching. Build: `npm run build`.
Type checking: `npm run typecheck`. Canvas math tests: `npm test`. Python suite:
`python -m pytest`. Optional browser automation additionally requires
`python -m pip install playwright` and `python -m playwright install chromium`.

The internal `clients/web/build.mjs` runs TypeScript diagnostics, bundles compiled local modules,
and copies the checked-in licensed React runtime to `src/storyboarder/static/`.
It deliberately needs only TypeScript as a build dependency. Production asset filenames
include a content hash; build.json records versions/hash. Run `npm run dev` to watch,
start `storyboarder ui` in another terminal, and refresh after rebuild. There is no
runtime CDN request or separate frontend server.

## Fresh release

```sh
python -m pytest
cd clients/web
npm ci
npm run typecheck
npm test
npm run build
cd ../..
python scripts/build_release.py
```

The release helper builds a wheel and sdist, checking packaged static assets and
migrations. With the `build` development dependency available, `python -m build` is
also supported. The checked-in frontend is intentional so source installations do not
silently depend on Node. Change the Python and web version together, rebuild and update
the verification report. Keep released migrations immutable; append the next numbered
SQL file and increase SCHEMA_VERSION. Run a full project backup before upgrades.

## Fully offline installation preparation

On an internet-connected machine with the same platform/Python version as the target:

```sh
python -m pip download --dest wheelhouse ./dist/storyboarder_desk-1.0.0-py3-none-any.whl
```

Transfer the wheelhouse to the offline target, then:

```sh
python -m pip install --no-index --find-links wheelhouse storyboarder-desk==1.0.0
```

This release does not include all third-party Python dependency wheels. `pip install .`
is not a promise of an offline first install on an empty machine. Native dependency
wheels vary by platform; validate the prepared wheelhouse on the actual target.

## Browser acceptance

Create a fresh demo workspace; start the app against it; then run:

```sh
python clients/web/e2e/browser_acceptance.py --url http://127.0.0.1:7430 --output artifacts/browser
```

The test is intentionally destructive to its **demo fixture**: it creates an asset,
relationship, layout, frame candidate, export and second project. Do not run it against
valuable production data. `--chromium /path/to/chromium` selects an installed executable.
It normally uses real loopback navigation.

This build environment blocks all browser top-level navigation through administrator
policy. Its documented `--transport-bridge` test mode therefore mounts the *unchanged
compiled frontend* in about:blank and relays requests to the running loopback API. It
does not change browser policy or ship a production fetch bypass. That mode tests actual
UI interactions and HTTP effects, but not ordinary page navigation, browser CSP enforcement
or browser-download behavior. Independent API tests cover returned files and headers.
The normal-navigation test still needs to be run on an unrestricted target machine.

## Platform and operational caveats

Linux/Python 3.13 was executed here. The project includes platform-neutral Python paths
and Windows startup instructions. System image-viewer handoff depends on the host
desktop configuration. The TUI benefits from at least 110×35 terminal cells.
PDF core fonts do not guarantee arbitrary Unicode glyph coverage; full HTML/JSON is
available for international productions.

Large projects use filtered/capped graph views and library pagination, but metadata
snapshots still scale with project size. This release is not an unlimited-node or
multi-user database product. See TEST_REPORT for observed checks rather than inferred
capacity promises.

## Uninstall and upgrade

`python -m pip uninstall storyboarder-desk` removes the application, not portable
projects or `~/.config/storyboarder/scripts.json`. Remove the virtualenv separately
when no longer needed. Back up before deleting data. To upgrade, stop local servers,
back up projects, install the new wheel, then open and run doctor. Never delete a
project database as an application "reset" operation.

## Self-contained application acceptance

Run `python scripts/acceptance_walkthrough.py ./new-acceptance-folder` with a
nonexistent destination. The real application services create a story/reference/frame,
save a graph, move/reopen the project and produce portable scene/board exports. The
script leaves the result available to inspect in any of the three interfaces.
