# User-facing language

Storyboarder should read like a calm editorial production desk. Copy should help a filmmaker make the next decision without exposing storage, API, or implementation terms.

## Voice

- Use plain, direct sentences and familiar production language.
- Name the work the person is doing: story direction, reference images, storyboard images, scenes, shots, and project backups.
- Keep labels short. Use supporting text to explain what a control changes.
- When something fails, say what happened and give the next useful step.
- Keep technical identifiers, raw responses, logs, and version details inside a collapsed **Technical details** section.
- Do not rewrite text authored in a project. App interface copy and project story content have different owners.

## Shared vocabulary

| Internal concept | User-facing term |
| --- | --- |
| Asset | Library item |
| Media | Image |
| Assignment | Shot reference |
| Context / context block | Story direction / direction note |
| Append / replace / exclude | Add to earlier notes / replace earlier notes / hide earlier notes here |
| Graph / canvas mode | Story flow / reference map / scene board |
| Layout | Saved canvas arrangement |
| Composition | Storyboard or board preview |
| Automation job | Image request or image tool run |
| Doctor / integrity report | Project health / Project care |

Use the command catalog for action and form labels shared by the React app and TUI. Keep display mappings alongside their client when the underlying value is an API or storage enum.

## Copy pass plan

1. **Shared terms:** align navigation, form choices, command names, statuses, and connection labels across the React app and TUI.
2. **Page copy:** give every page a plain title, a short description, and empty states that explain a useful next step.
3. **Action copy:** name controls by their result; explain destructive or unusual changes before they are saved.
4. **Problem states:** replace raw network, server, and storage errors with a short explanation and a recovery action.
5. **Technical detail:** keep IDs, saved versions, logs, raw tool inputs, and project-format data available only when someone opens technical details.
6. **Review:** build the web client and inspect the Guide, Outline, Inspector, forms, and other pages; review the TUI labels and exported boards for terminology drift.

## Review checklist

- Does the copy describe the user's task instead of the data structure?
- Is each action clear before it is selected?
- Does a blank state say what to do next?
- Does an error explain a recovery step without asking the user to interpret a stack trace?
- Are image references clearly distinguished from storyboard images?
- Are raw IDs, enum values, and implementation vocabulary hidden unless the user asks for technical detail?
