# Third-party notices

New Storyboarder application code is distributed under the root MIT LICENSE.
The production browser runtime includes React 18.2.0, ReactDOM 18.2.0 and Scheduler
0.23.0, © Meta Platforms, Inc. and affiliates, under MIT. Complete notices accompany
both the source runtime (`web/vendor/THIRD_PARTY_LICENSES.txt`) and installed static app
(`src/storyboarder/static/THIRD_PARTY_LICENSES.txt`). The runtime is pinned, checked in,
and loaded locally; the frontend does not fetch it from a CDN.

TypeScript 5.8.3 is an Apache-2.0 development dependency, not a bundled runtime/compiler
in the installed application. The other Python dependencies are installed separately
by pip and retain their own licenses and notices in their distributions. This package
does not redistribute third-party Python dependency wheels.

No font files are included. The UI uses local system fonts; the PDF renderer uses
ReportLab's built-in font support. Demo reference art is created by the included
project-seeding script and is labelled fictional. No stock photograph rights or real
person/film affiliations are represented.
