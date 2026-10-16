# AIPI demo video

The final MP4 is a captioned edit of a real local Docker fault and browser session.
It uses the deterministic mock, generated lab traffic and the existing application.
There are no substituted API responses, fabricated scores or seeded report screens.
Explanatory title/architecture cards and condensed **actual** CLI output are clearly
separate from the application capture. Baseline/setup/waiting periods are shortened;
this is not a real-time latency benchmark. No narration or music is included.

- [Watch or download the MP4](aipi-demo.mp4)
- [Thumbnail](aipi-demo-thumbnail.png)
- [Optional subtitle file](aipi-demo.srt)
- [Actual run and edit provenance](capture-manifest.json)
- [Playback verification](video-verification.json)

The README uses a clickable thumbnail linked to the MP4 file. GitHub/browser
playback varies; downloading the MP4 is supported. A local file link in Markdown
does not establish a hosted deployment or an inline README video player.

## What is demonstrated

1. Bounded host-only checkout SIGKILL, observable die(137) → start and verified recovery.
2. Incident creation through the UI with explicit checkout/gateway scope and times.
3. Six-stage LangGraph investigation, real persisted tool/node events and mock usage.
4. Frozen runtime evidence and competing hypotheses with FOR/AGAINST citations.
5. An outside-bundle citation resolved through the incident-scoped evidence API.
6. Separate report Facts / Hypotheses / Recommendations and actual Markdown export.
7. Recorded-live evaluation by the separate scorer, followed by its terminal truth reveal.

The displayed scores describe that one recovered run. The separate six-run historical
experiment remains in [Results](../docs/results/README.md). Neither is an LLM accuracy
measurement. Replica lag is implemented and tested; this short video follows the
service-kill scenario only. No autonomous incident detection or remediation is claimed.

## Reproduce the application

Follow the [quick start](../README.md#quick-start), including isolated project/port
exports when the machine has retained lab volumes. Preserve matching `.env` and
volumes. Start Docker Desktop, then:

```sh
make setup
make up
make seed-traffic
```

Faults, demos, recording and live tests must run serially on each Compose project.
The capture command invokes `make chaos-kill` itself. It gathers 30 seconds of
baseline, injects/recovers a real fault, and creates a new incident through the UI.
Its end window rounds forward to a whole second, covering the runner's completion
when filling a `datetime-local` input. Existing incidents and protected run records
are not rewritten. The script fails if recovery, report generation, scoring,
citation resolution or evidence-ID stability does not pass.

## Recreate the video

Requires Node 25, the normal Python 3.12/uv lab, Chromium and an FFmpeg binary with
libx264. Recording dependencies are separate from the application lockfiles.

```sh
npm ci --prefix demo
npm exec --prefix demo -- playwright install chromium

# Either use a system FFmpeg, or this pinned native helper (verified on Apple Silicon):
export FFMPEG="$(UV_CACHE_DIR=/tmp/aipi-uv-cache uv run --no-project --python 3.12 \
  --with imageio-ffmpeg==0.6.0 python -c \
  'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"

node demo/capture.mjs
node demo/pickups.mjs    # read-only close-ups of the same saved result
node demo/render.mjs
node demo/verify.mjs
```

Keep any `COMPOSE_PROJECT_NAME` / `AIPI_*_PORT` exports active. The capture derives
API/web addresses from them. If the running lab belongs to a different checkout,
pass `--lab-root /absolute/path/to/that/checkout` to capture; its existing credentials
are used only by the normal host chaos utility. Optional `--api-url` and `--web-url`
overrides accept loopback HTTP addresses only; pass the same overrides to
`pickups.mjs` when using them. `PLAYWRIGHT_EXECUTABLE_PATH` can
select an already-installed compatible Chromium binary. No provider key is needed.

Outputs:

- `aipi-demo.mp4`: 1920×1080, H.264/yuv420p, 30 fps, faststart, captioned/silent.
- `aipi-demo-thumbnail.png`: actual UI capture in a designed title frame.
- `aipi-demo.srt`: matching optional captions; readable captions are already burned in.
- `capture-manifest.json`: observed run IDs, checks, actual scores, cited outside IDs,
  scene times and final video hash. It contains no environment credentials or host paths.
- `video-verification.json`: complete decode, browser playback/seek and dimensions.
- `.work/`: ignored raw browser recording, editorial cards, encoded segments and QA frames.

The close-up command reads the same saved incident, report and evaluation, without
starting another investigation or replacing a score. It gives completed metrics,
node events and the approval label readable dwell time.

The small cursor/ripple overlay helps follow genuine browser actions. It does not
modify application data or responses. The renderer uses short fades to dark between
scenes; no fabricated intermediate UI or results are generated. Native browser
capture is 1280×720 and is scaled to 1080p for readable text and captions.

The renderer enforces a conservative **25 MB** repository budget. If a later edit
exceeds it, encode a smaller version or upload it as a GitHub Release asset yourself
and replace the README link with its exact hosted URL. No upload or push is performed
by these scripts. Do not commit raw recordings, private environments or debug logs.

## Storyboard

| Time | Scene | Purpose |
|---|---|---|
| 00–06 s | Introduction | Explain the fragmented-signal investigation problem |
| 06–12 s | Architecture | Show observation → scoped investigation → isolated scoring |
| 12–20 s | Actual runner output | Establish the real fault, telemetry and recovery |
| 20–28 s | Create incident | Show explicit services and incident window |
| 28–36 s | Agent trace | Inspect the six nodes and real mock usage/latency |
| 36–43 s | Evidence | Inspect frozen runtime events |
| 43–50 s | Hypotheses | Compare support and counterevidence |
| 50–56 s | Outside-bundle lookup | Open a cited observation beyond the display cap |
| 56–63 s | Report/export | Separate facts, inferences and approval-required next checks |
| 63–73 s | Evaluation | Score this actual recovered incident, then reveal the label |
| 73–80 s | Engineering highlights | Read-only tools, immutable evidence and fabrication gates |
| 80–86 s | Conclusion | Reproduction command and honest scope/limitations |

## Verify before sharing

```sh
make test
make lint
make build-web
node demo/verify.mjs
```

`verify.mjs` decodes the entire MP4, checks SHA-256, resolution and duration, plays
it in real Chromium, then seeks through every chapter and saves QA screenshots.
Review those frames for legibility and sensitive data. The capture checks all
report citations against scoped by-ID lookup, reruns evidence retrieval for identical
IDs, verifies all six nodes completed and requires a passing actual live scorecard.

The scripts serve playback on a temporary loopback-only port. They never record
the personal desktop, terminal configuration, `.env`, browser address bar or other
applications. CI remains the application's existing mock workflow; this optional
media toolchain does not claim a GitHub-hosted CI run.

## Verification of this recording

Verified locally on **2026-10-17 (IST)** using Apple Silicon, Docker Desktop,
Python 3.12, Node 25 and mock reasoning:

| Check | Observed result |
|---|---|
| Final MP4 | 86 s; 1920×1080; H.264/yuv420p; 30 fps; 2,580 frames; 4,173,025 bytes |
| Media integrity | Complete FFmpeg decode; real Chromium playback; seek through every chapter; SHA-256 matches manifest |
| Streaming layout | MP4 moov atom precedes mdat (faststart) |
| Actual recorded report | 349/349 supported citation pairs; 0 unsupported/critical unsupported claims |
| Scoped provenance | All 321 unique cited IDs resolved; repeated bundle IDs identical |
| Workflow | Six node completions, FOR/AGAINST evidence, approval-required unexecuted recommendations |
| Application tests | 140 Python passed in 437.21 s (24 live Docker tests, none skipped); 26 UI tests passed |
| Quality/build | Ruff, strict mypy (66 source files), ESLint, tsc, Vite build and demo-script syntax checks passed |
| Secrets/links | Gitleaks candidate scan: 22.88 MB, no leaks; local Markdown links valid; final chapter frames visually reviewed |

The initial capture attempt exposed whole-second end-time truncation; the scorer
rejected that window. The final capture uses a new incident with the full recovery
window. Scoring/data were not altered to make it pass. Completed-result close-ups
come from that same final incident/evaluation, and the renderer rejects mismatched
close-up IDs. The initial attempt and raw intermediates remain ignored locally.

No functional application source, fixtures, CI or existing application lockfiles were changed. The
existing root .env and original Docker volumes were preserved; a separate local
project supplied the demonstration. GitHub-hosted CI was not run, and no push or
external media upload was performed.
