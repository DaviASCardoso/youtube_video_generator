# Pillar 1 — Discovery (Descoberta)

> Reference spec for the Discovery pillar. It describes **what** a complete
> version of this pillar is responsible for and the capabilities it should
> expose. It does not prescribe implementation details — choose mechanisms
> consistent with the conventions this project already uses. Where a capability
> implies a technical choice (which extra signal services to wire up, how to
> store the single decided theme, how many candidates to evaluate, the shape of
> the settings, what becomes of the existing `temas.json`), that choice is yours.
>
> Two principles run through everything below: **efficiency** (spend the
> expensive step only where it changes the decision) and **configurability**
> (every behavior is a panel-editable setting, never hardcoded).

## Responsibility (one sentence)

Discovery decides **what to make next**: it gathers topic candidates from one or
more signals, judges how well each fits a given video type, removes anything the
channel has effectively already done, and settles on the **single theme** the
next video of that type will be made from. Discovery owns everything up to "a
single, well-chosen theme, decided and ready to be produced" — and nothing after
it. *When* a discovery run happens is an Operations concern; *what* the run does
is Discovery's.

## Output model: one decided theme externally, configurable retention internally

The **output** this pillar hands to the rest of the system is exactly one thing
per video type: the next theme to produce, with the metadata that justifies the
choice (which signal it came from, why it was judged a fit, the priority it won
on). Downstream pillars (Generation, Publishing) read that one decided theme —
they never see or drain a multi-item backlog. That external contract is fixed.

**Internally**, whether Discovery keeps the non-selected candidates of a cycle or
throws them away is a **configurable policy**, not an architectural commitment:
- *Discard* (efficiency-first): each cycle re-decides from fresh signals; the
  previous cycle's losers are dropped. Best when signals are trend-heavy and
  decay fast.
- *Retain*: Discovery keeps an internal buffer of prior candidates and considers
  them alongside fresh ones in the next selection.

This is exactly the discard-vs-keep toggle the panel must expose. Crucially, even
in *retain* mode a retained candidate is **not re-evaluated** by the LLM each
cycle — it keeps its earlier fit score, and freshness decay (capability 5) makes
stale candidates sink and age out on their own. Retention therefore never
reintroduces batch re-scoring; it only changes whether old candidates linger.

## The flow this pillar is responsible for

```
signal source(s) → raw candidates → cheap ranking → fit evaluation of top contenders (per type) → dedup → ONE decided theme
                                                                                                              │
                                                                                              (optional) human review gate
```

## Efficiency principle

Gathering candidates from a source is cheap and can be batched; judging fit with
an LLM is the expensive step. A complete Discovery pillar spends the expensive
step only where it changes the decision: it ranks candidates by the cheap signals
first (raw signal strength, freshness, dedup) and only runs the costly per-
candidate evaluation on enough top contenders to settle on one theme. It never
fit-scores a whole batch to fill a store it drains one item at a time, and it
never re-scores a candidate it has already scored.

## Configurability principle

Nothing about Discovery's behavior is hardcoded. Every threshold, weight, window,
ratio, mode, and on/off switch is read from configuration and editable from the
admin panel, so behavior can change without touching code. Discovery's job is to
be **fully config-driven** and to define that config's schema; rendering the
editing controls is the Control pillar's job (thin forms over Discovery's config).
Configurability must not become a foot-gun: everything ships with sensible
defaults so the system runs correctly out of the box, and the panel is for tuning,
not a precondition for working. See "What must be panel-configurable" below.

## Capabilities of a complete Discovery pillar

### 1. Pluggable signal sources
A signal is any source that can propose topic candidates. Today there is one (the
Trends MCP feed). The complete pillar treats "signal source" as a **role** any
number of concrete sources can fill behind a common contract — each takes the
run's parameters and returns raw candidates, and a new source can be added without
touching the rest of the pillar. **Each source has its own enable/disable toggle
in the panel**, so a source can be turned off without removing it. A source that
fails returns nothing and is skipped, never crashing the run. The curated/manual
list and the evergreen pool are **input-side sources** — cheap raw ideas that
don't decay and are fine to persist, unlike processed trend themes. The external
sources to build are **decided, not open**: the existing Trends MCP feed stays as
one source, and four more are added, all free — the YouTube Data API v3 (what
people search on YouTube plus recent uploads from same-niche channels), Google
Trends via the maintained `pytrends-modern` fork (the original `pytrends` was
archived in April 2025 and is unmaintained), Reddit's public `.rss` feeds
(keyless, community/niche demand), and the Wikimedia Pageviews "top articles"
endpoint for pt.wikipedia (keyless, attention proxy). Of these, only the YouTube
Data API needs a credential; the other three are keyless. Because
`pytrends-modern` and the Reddit feeds are unofficial and fragile, they follow the
degrade-instead-of-crash posture and are never a lone dependency.

### 2. Candidate normalization
Whatever a source returns is normalized into one internal shape before the rest of
the pillar touches it, so fit/dedup/selection never care which source produced a
candidate. Each candidate carries its origin and whatever raw signal strength the
source can express (e.g. a trend's rank/interest), because selection depends on it.

### 3. Fit evaluation per video type
Trending is not the same as worth-making for *this* channel. The complete pillar
evaluates a candidate against the type's persona and returns a decision (fit or
not?) and a **fit score** (how strong), not just a converted theme — and it can say
"no." The existing Gemini step is the natural home; each type steers it with its
own prompt. The **criteria for a "good theme" are configurable**: the minimum fit
score to accept, and the persona/criteria prompt itself, are panel-editable. Per
the efficiency principle, run this only on the top contenders.

### 4. Deduplication
Discovery must not propose something the channel has effectively already done. It
dedupes a candidate against signals recently consumed and against themes already
produced/published, robustly enough to catch trivial rewordings rather than only
exact-name matches. Both the **dedup window and how strict the matching is** are
panel-configurable.

### 5. Selection
Selection turns many candidates into one. It combines the inputs Discovery has —
raw signal strength, fit score, freshness — into a ranking and takes the top. The
**relative weight of each factor is configurable**, so you can make the system
lean harder on trend strength or on fit from the panel. This ranking is computed
fresh each run to pick the winner and is not persisted as a standing order.
Freshness means a strong-but-old trend loses to a fresher one, which keeps the
decided theme current and drives the aging-out in retain mode.

### 6. Trending / evergreen balance
Decided per cycle, not stored as a queue property. Discovery reads the type's
recent produced history and decides whether this cycle's theme should be trending
or evergreen to hold a **configurable target ratio** over time, then draws from the
matching source. The evergreen pool is a persistent input source (capability 1).

### 7. Optional human review gate
Two modes **per type, panel-selectable**: auto (the decided theme goes straight to
production) or review-first (the decided theme sits in a single pending state and
only becomes the theme-to-produce once approved). One pending item, not a queue.
The pending state lives on Discovery's side; the surface that approves it is
Control's.

### 8. Observability of discovery itself
For a run: what was fetched, what was ranked, what was evaluated, what won and why,
what was rejected. Recording this is Discovery's; surfacing it is Control's. This
keeps discarded candidates auditable even when they aren't persisted.

## What must be panel-configurable (not hardcoded)

Per signal source: an enable/disable toggle, plus that source's own parameters
(feed, fetch limit, etc.). For fit: the minimum fit score to accept a candidate,
and the criteria/persona prompt. For dedup: the window length and the matching
strictness. For selection: the weights of signal strength vs fit vs freshness. For
the trending/evergreen mix: the target ratio. Per type: the review-gate mode
(auto vs review-first). The **internal retention policy: discard the previous
cycle's candidates vs keep them in Discovery's internal buffer**. And the
evaluation budget: how many top contenders get LLM-evaluated per cycle. (The run
cadence is an Operations setting, not Discovery's.) Everything here ships with a
sensible default.

## Hand-off contract

Discovery's only output to the rest of the system is the **single decided theme
per type** (with priority/fonte/justification metadata) plus its pending/approved
state when the review gate is on. Downstream reads that one decided theme instead
of popping a queue; its shape must be stable for consumers.

The existing per-type `temas.json` and its web tab are **repositioned**: what was a
drained output queue becomes, at most, a persistent **input pool** of manually
curated and evergreen candidate ideas Discovery draws from. Whether to keep,
rename, or restructure that file is your technical decision, as long as manual and
evergreen ideas keep a durable home and the single decided theme is what production
consumes.

## Integrations to fix (part of this work, not a follow-up)

Because the output model changes from a multi-item queue to a single decided theme,
every place that currently produces into or consumes from the old queue must move
to the new contract: the generation/production entry point that pops the next
theme, the scheduler and manual-trigger paths, the run-history records, and the web
surface that exposed the "Fila de Temas" tab. These must keep working and the test
suite must stay green.

## Explicitly out of scope for this pillar

Producing the video (Generation), uploading it or its metadata (Publishing), the
web forms that edit these settings or show discovery history (Control — Discovery
only defines the config they edit), measuring how a published theme performed
(Feedback), and the scheduling / error-handling / alerting machinery that *runs* a
discovery job (Operations). Discovery decides what to make; it does not run itself,
make it, ship it, or grade it.
