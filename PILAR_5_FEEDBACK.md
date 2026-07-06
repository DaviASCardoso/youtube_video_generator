# Pillar 5 — Feedback (Retorno)

> Reference spec for the Feedback pillar. It describes **what** a complete version
> of this pillar is responsible for and the capabilities it should expose. The
> product decisions here are already made; what is left to you is technical — how
> metrics are stored, how the re-poll schedule is wired, how aggregates are
> computed, how the learned-guidance block is stored and injected. Choose those
> consistent with the project's conventions.
>
> Feedback is the pillar that turns the system from a blind factory into a
> business, and it has two halves that matter equally: **collecting** performance
> (ingest, attribute, aggregate) and **applying** it (routing findings back into
> the pillars that produce videos). Collecting well without applying is a
> speedometer wired to nothing. Two principles govern it. **Efficiency** —
> analytics have quota and mature slowly, so re-poll on a maturation schedule and
> never re-pull or recompute unchanged data. **Configurability** — the metrics,
> the schedule, the sample floor, and how aggressively learnings are applied are
> all panel-editable, with conservative defaults.

## Responsibility (one sentence)

Feedback closes the loop with real-world performance: it pulls each published
video's analytics back in, relates the outcome to the inputs that produced it, rolls
those into per-dimension findings, and **applies** those findings back into
Discovery, Generation, and Publishing so the system makes more of what works. It owns
everything from "a video is live" to "a learning is applied to how the next video is
chosen, made, and shipped" — and nothing about the panel that displays it.

## Input / output model

**Input:** the published-records from Publishing (per-platform video ID and URL plus
the inputs that produced each video) and the platform analytics APIs. **Output:** two
kinds — stored performance data and findings (the collecting half), and applied
learnings: bounded numeric adjustments written to the target pillars' config and
LLM-translated guidance written into their prompts' learned-guidance blocks (the
applying half). Control displays both; the upstream pillars act on the applied
learnings.

## The flow this pillar is responsible for

```
published-record + sidecar → ingest → attribute → aggregate → FINDINGS
FINDINGS → deterministic router → ┌ numeric dimension → bounded config adjustment ┐→ [advisory: propose → human approves in Control | auto: apply] → Discovery / Generation / Publishing
                                  └ textual dimension → Groq translator → learned-guidance block ┘
```

## Data source (decided)

Owner metrics come from the **YouTube Analytics API** (channel-owner OAuth) —
retention, CTR, watch time, subscribers gained per video; basic counters from the
**Data API v3**. Both reuse the existing YouTube OAuth (same client, no new secret or
key file), with the credential setup the pillar needs: **enable the YouTube Analytics
API** in the Cloud Console (free, separate from the Data API v3 already enabled), add
the `yt-analytics.readonly` scope, and re-consent once.
The headline metrics are **retention** (average view percentage) and **CTR**.

## Capabilities of a complete Feedback pillar

### 1. Analytics ingestion
Pull each published video's metrics on a schedule, re-polling as the numbers mature —
decided default roughly 24h, 72h, 7 days, 30 days after publish, then stop. A
destination is a pluggable role as in Publishing: YouTube now, others a clean seam.

### 2. Attribution
Join each video's performance to the inputs that produced it, read from the
published-record and the generation sidecar — source, fit score, hook, voice, visual
mode, thumbnail, title, publish time, trending-vs-evergreen flag — so the system can
ask which of them performed. Attribution grows richer as upstream records carry more.

### 3. Retention curve
Ingest and store the audience-retention curve, not just the average, since for a
faceless channel where viewers drop off is the highest-signal thing available.

### 4. Aggregation & scoring (findings)
Roll raw per-video metrics up per input dimension into a score per video and per
dimension, producing structured **findings** (dimension, value, effect, sample size,
confidence). Scoring is **sample-size aware**: a dimension is not called a winner or
loser until it has a configurable minimum number of videos behind it (decided
default a small floor), so the system never over-fits on one lucky video.

### 5. Closing the loop — the application layer
This is the applying half, and it is as important as the collecting half. It has four
decided parts:

**Deterministic routing.** A decided dimension→destination map, not an LLM guess,
decides where each finding goes. Numeric dimensions — publish time, the
trending/evergreen ratio, source weights, voice/length/visual-mode defaults — become
**bounded numeric adjustments** to the target pillar's existing config. Textual
dimensions — hook style, intro length and pacing as guidance, title phrasing,
thumbnail text style, fit-criteria nuances — become **prompt guidance**. The LLM is
used only for translating the textual ones, never for routing.

**LLM translation into a maintained block.** For textual findings, Groq (already in
the project) is given the channel context, the target prompt's current
learned-guidance block, and the new finding, and it **reconciles and rewrites** the
block — resolving contradictions, keeping only the top-K highest-confidence items,
and staying under a size cap — rather than appending lines. Guidance **decays** with
confidence and freshness unless re-confirmed by new data, so the block never
accumulates stale cruft.

**The learned-guidance block as a first-class artifact.** Each relevant prompt
(Discovery's fit criteria, Generation's script and visual, Publishing's metadata and
thumbnail) gains a dedicated learned-guidance block that is **separate from the
human-authored base prompt**, versioned, inspectable, and human-vetoable line by line
through Control. The base prompt is never overwritten or polluted; a human always
sees exactly what the machine learned and injected and can pin or veto any line.

**Advisory by default, bounded, reversible.** The layer **proposes** changes — numeric
and prompt — and a human approves them in Control before they take effect; an
auto-apply toggle exists per target and ships **off**. Numeric adjustments are capped
per application and reversible; the guidance block is capped and clearable. The
reason for the human gate is honest and load-bearing: translation adds a failure mode
where the LLM over-interprets thin data and writes confident-but-wrong guidance that
would degrade every video, so on a young channel it stays gated until there's enough
data to trust auto-apply.

### 6. Experiments (optional frontier)
Run and evaluate simple experiments — variant titles, thumbnails, or hooks measured
against each other. Configurable, off by default, useful once volume makes a
comparison meaningful.

### 7. Surfacing to Control
Per-video performance, per-dimension findings, winners and losers, retention curves,
trends over time, and the proposed and applied learnings (numeric and the guidance
blocks) are computed and stored here and displayed by Control. Feedback computes and
stores; it never renders a dashboard.

### 8. Efficiency, quota-awareness & graceful degradation
Re-poll only on the maturation schedule, never re-pull unchanged data, cache what was
fetched, never recompute an aggregate whose inputs are unchanged, and translate only
when a finding actually changed the block. A failed analytics or translation call
degrades — retry later, leave the last good data and the last good block in place —
rather than crashing.

## What must be panel-configurable (not hardcoded)

Which metrics are ingested and which are headline; the re-poll schedule; the
sample-size floor; which dimensions are attributed and aggregated; the routing map's
per-dimension destination where it's sensibly adjustable; the application mode per
target (advisory vs auto, default advisory); the numeric-adjustment caps; the
learned-guidance block size cap and decay; whether experiments are enabled; and the
per-destination enable toggle. Everything ships with the conservative defaults above.

## Hand-off contract

Feedback's inputs are the published-records and the analytics APIs; its outputs are
stored performance and findings, plus applied learnings — bounded numeric adjustments
to the target pillars' config and translated guidance in their learned-guidance
blocks — all gated advisory by default. The upstream pillars consume the applied
learnings (numeric knobs they already read; guidance blocks injected into their
prompts); Control displays and approves. Credentials are reused; the only change is
the added `yt-analytics.readonly` scope.

## What the upstream pillars must gain (built as part of the application layer)

Discovery, Generation, and Publishing are only partly ready to receive learnings: the
numeric knobs (selection weights, evergreen ratio, voice/length/visual defaults,
publish time) already exist and can take bounded adjustments, but the prompts have no
machine-maintained slot. So this pillar's work includes adding a **learned-guidance
block** to the relevant prompts (Discovery fit, Generation script and visual,
Publishing metadata and thumbnail) — a distinct, versioned, injectable, human-vetoable
section separate from the base prompt — and confirming each numeric target accepts a
bounded, reversible adjustment. No other upstream behavior changes.

## Explicitly out of scope for this pillar

Deciding themes (Discovery consumes the learning but owns the decision), making videos
(Generation), shipping them (Publishing), displaying the learnings (Control), running
the ingestion and application schedule (Operations runs the job; Feedback defines what
it does), and the policy rules (Compliance). Feedback measures, learns, and applies;
it doesn't choose, make, ship, show, or run itself.