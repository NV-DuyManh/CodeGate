# Public dashboard demo

Live URL: **https://codegate-demo.vercel.app**. The real local runtime video is available at
**https://codegate-demo.vercel.app/recordings/codegate-runtime-vi.mp4** (Vietnamese synthetic male narration).

The public demo is a static build of the existing dashboard. It runs without a hosted API, database, GitHub
installation or AI credentials. A persistent banner labels every page as sample data.

## Interactive scope

- Switch between two sample workspaces and inspect repository, pull-request and analytics views.
- Search repositories and pull requests; filter policies, states and repositories; paginate results.
- Inspect illustrative findings, policy evidence, coverage and reviewer recommendations.
- Save testing settings, sample member changes and coaching progress in this browser, then reset the demo.
- Open the separately recorded real local runtime video through **Watch real runtime**.

GitHub connection/sync, sending invitations, AI analysis and executing tests are unavailable in the static demo.
Their controls explain that a configured live backend is required. Sample edits never modify a GitHub repository
or another viewer's data. The demo transport intercepts only the configured CodeGate API base; unknown CodeGate
endpoints return an explicit unavailable response instead of calling a viewer's local machine.

## Build and publish

The demo is opt-in. Normal development and production builds retain the existing live API behavior.

```powershell
cd dashboard
npm.cmd ci
$env:VITE_CODEGATE_DEMO = 'true'
npm.cmd run build
Remove-Item Env:VITE_CODEGATE_DEMO
```

Publish **only `dashboard/dist`** as a static site. `dashboard/vercel.demo.json` supplies SPA fallback and asset
headers for an already-built artifact; it deliberately contains no server build command. Copy it into the static
release directory as `vercel.json`, alongside `index.html`. For the Vercel CLI, select the dedicated demo project
and account scope explicitly. Do not upload the repository root, `.env`, runtime databases or recording controls.

Copy the verified narrated runtime MP4 to `dist/recordings/codegate-runtime-vi.mp4` before publishing. The binary is delivered
as a release artifact rather than committed to Git. Without this asset the demo's video link will not work.
The recording itself is described in [RUNTIME_RECORDING.md](RUNTIME_RECORDING.md).
The narrated version preserves the original recorded video stream and adds a generic Vietnamese male synthetic
voice aligned to the actual scenes. The narration does not represent a human recording or a named person's voice.

## Verification

```powershell
cd dashboard
npm.cmd run test:run
npm.cmd run lint
```

Demo contract tests check tenant isolation, coherent evidence, persistence/reset, unknown-endpoint handling,
and that disabling demo mode does not replace live fetch. UI tests check the banner, unavailable provider actions
and browser-local save wording. Verify the published site in a fresh browser, including a deep link, mobile
layout, workspace switching, filtering, local persistence/reset, and the MP4 response.
