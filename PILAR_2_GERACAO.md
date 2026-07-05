# Pillar 2 — Generation (Geração)

> Reference spec for the Generation pillar. It describes **what** a complete
> version of this pillar is responsible for and the capabilities it should
> expose. It does not prescribe implementation details — choose mechanisms
> consistent with the conventions this project already uses. Where a capability
> implies a technical choice (which provider to wire per stage, how to store
> checkpointed artifacts, how to record cost, how captions are rendered), that
> choice is yours.
>
> The same two principles from the Discovery spec run through everything below:
> **efficiency** (this is where money is spent, so never pay for the same work
> twice and never pay for a stage until the previous one is validated) and
> **configurability** (every provider, parameter, and toggle is panel-editable,
> never hardcoded).

## Responsibility (one sentence)

Generation turns the **single decided theme** into a finished video file ready to
publish: it writes the script, produces the visuals and the narration, and
assembles them locally into the final video. It owns everything from "a decided
theme" to "a finished video file plus the sidecar metadata describing it" — and
nothing about deciding the theme, optimizing it for the platform, uploading it, or
measuring how it did.

## Input / output model

**Input:** exactly one decided theme per run — Discovery's output contract.
**Output:** one finished video file plus a sidecar record (duration, the script
that was used, the theme, and which providers/models/versions produced it), placed
where Publishing picks it up. Generation never uploads and never touches
platform-facing metadata; the finished file and its sidecar are the boundary.

## The flow this pillar is responsible for

```
decided theme → script → per-scene visual prompts → visuals  ┐
                      → narration (audio) ───────────────────┤→ assembly → finished video file (+ sidecar)
                      → captions (optional) ─────────────────┘
              (each stage validated before the next runs; each stage's output checkpointed)
```

## Efficiency principle

Generation is where the money is spent — every stage is one or more paid API calls
(LLM, image, TTS). Spend the expensive step only when the cheap checks pass:
validate each stage's artifact before paying for the next, checkpoint every stage's
output so a failed or re-run job never re-pays for work already done, and never
regenerate an artifact that already exists and still validates.

## Configurability principle

Nothing about how a video is generated is hardcoded. The provider for each stage,
the model names, the persona prompts, the voice, the visual mode and style, the
video format, the captions, the music — all read from configuration and editable
from the admin panel, with sensible defaults so a video generates correctly with
no tuning. Generation defines the config schema; the Control pillar renders the
forms over it. See "What must be panel-configurable" below.

## Capabilities of a complete Generation pillar

### 1. Staged pipeline with inspectable artifacts
Each stage — script, visual prompts, visuals, narration, captions, assembly —
produces a named, inspectable artifact rather than passing opaque data straight
through. Stages are isolated so any one can be re-run or swapped without redoing
the others, and a human (through Control) can read the script or hear the
narration of a given run.

### 2. Pluggable provider per stage
Like Discovery's sources, each stage's provider sits behind a common contract so it
can be swapped without rewiring the pipeline: the script LLM (Groq today), the
image generator (Together/FLUX today, with the stock-composite mode as an
alternate), and the TTS voice (Google Cloud TTS today, with room for an alternate
such as ElevenLabs, which you've already priced). Which provider a stage uses is a
panel setting, and adding a provider means implementing the contract, not touching
the pipeline. Providers already in use reuse the project's existing credentials —
nothing new is set up.

### 3. Quality gates between stages
Before spending on the next stage, validate the current artifact against
stage-appropriate checks: the script is coherent, on-persona, and within the
target length; the narration is audible, non-silent, and of the expected duration;
the visuals are the right count and not obviously broken. This generalizes the
fail-fast-before-spend instinct already in the codebase (the pre-flight validation
that refuses before burning API budget). A gate that fails retries or stops — it
never lets a broken artifact reach an expensive downstream stage.

### 4. Resumability / checkpointing
Every stage's output is persisted, so a run that fails at assembly resumes from the
last good artifact instead of restarting and re-paying stages one through n-1. A
re-run reuses still-valid artifacts and regenerates only what changed or what
failed. This is the single biggest cost and time saver in the pillar.

### 5. Deliberate variability / anti-repetition
Identical intros, pacing, phrasing, music, and visual treatment every day are both
a quality problem (the channel feels robotic) and a platform-survival problem —
this is exactly the mass-produced pattern the platform's inauthentic-content policy
targets. The complete pillar varies its output on purpose: configurable variation
in openings, structure, music, and visual style, so no two videos are cut from a
visibly identical template. Variation is a first-class, configurable behavior, not
an accident.

### 6. Cost & budget awareness
Because this is where spend happens, each stage records what it cost, and the
pillar can enforce a per-video and per-day budget: if a run would exceed the cap it
degrades (cheaper provider, fewer images) or stops, rather than blowing the budget.
The measurement originates here; the enforcement policy is configurable, and the
numbers feed Operations and the panel.

### 7. Graceful degradation per stage
A failed stage degrades instead of crashing the run, matching the posture already
used across the codebase: retry with backoff, fall back to an alternate provider
(FLUX fails → stock composite; primary TTS fails → secondary), or fall back to a
placeholder where acceptable. A single flaky API never takes down the whole
generation.

### 8. Observability of generation
For a run: which stages ran, what each produced, how long each took, what each
cost, what failed and why, and which providers, models, and versions were used.
Recording this is Generation's job; surfacing it (and letting a human inspect
artifacts or re-run a stage) is Control's. This makes both cost and failures
auditable per video.

## What must be panel-configurable (not hardcoded)

Per stage: which provider is used and its model name. For the script: the
persona/criteria prompt and the target length and tone knobs. For visuals: the
visual mode (AI images vs stock composite), the style, the aspect ratio, and how
many images per scene. For narration: the voice, and speed/pitch. For captions:
on/off and style. For assembly: resolution, fps, codec, background music on/off and
selection, and any intro/outro. For variation: how much the openings, structure,
music, and visual style are allowed to vary. For budget: the per-video and per-day
caps and what to do when they would be exceeded. Everything ships with a sensible
default.

## Hand-off contract

Generation's only output to the rest of the system is the finished video file plus
its sidecar record, placed where Publishing consumes it. Its only input is the
single decided theme from Discovery. Neither boundary changes shape in a way that
breaks the neighbor.

## Integrations to fix (part of this work, not a follow-up)

Everything the current code does to produce a video must move onto the staged,
checkpointed, config-driven model **without changing behavior for a default
configuration**: the entry point that consumes the decided theme, the existing
script / visual / TTS / assembly calls (now wrapped behind the per-stage provider
contract and the quality gates), the run-history records (now including per-stage
cost and provider info), and the handoff to Publishing (now the finished file plus
sidecar). The test suite stays green and the default-config output stays equivalent
to today's.

## Explicitly out of scope for this pillar

Deciding the theme (Discovery), optimizing the title / description / thumbnail for
the platform and uploading (Publishing), scheduling and running the job and firing
alerts (Operations), and measuring how the finished video performed (Feedback). The
variability that helps a video survive platform policy is implemented here, but the
policy judgment itself lives in Compliance. Generation makes the video; it doesn't
choose it, ship it, run itself, or grade it.
