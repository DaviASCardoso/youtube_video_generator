# Pillar 7 — Compliance (Conformidade)

> Reference spec for the Compliance pillar. It describes **what** a complete version
> of this pillar is responsible for and the capabilities it should expose. The product
> decisions here are already made; what is left to you is technical — how rules are
> stored and versioned, how the authenticity analysis is computed, where the audit
> record lives. Choose those consistent with the project's conventions.
>
> Compliance is the shortest pillar in code and the most existential in consequence:
> the other six make the channel *work*, this one decides whether it *survives*. It
> produces nothing and publishes nothing — it is the system's conscience, a set of
> rules and checks that cross the other pillars and answer one question: will this get
> the channel demonetized or taken down? It is **cross-cutting** like Operations, but
> instead of making things run it **vetoes** and **marks**. It has one property no
> other pillar has: its requirement changes from the outside — YouTube tightens a
> policy and yesterday's safe output is suddenly unsafe — so it must be easy to update
> when the rules move. Two principles govern it: **objective checks block, subjective
> checks advise** (a hard veto on machine judgment would flag good videos and get the
> pillar switched off), and its rules are **centrally versioned** so a policy shift is
> a one-place edit.

## Responsibility (one sentence)

Compliance keeps the channel on the right side of the platform's rules: it decides when
synthetic-media disclosure applies, flags when output is drifting into the
mass-produced pattern the platform penalizes, checks that assets are licensed, vetoes
inappropriate themes, and records an audit trail of every judgment. It owns the
policy verdict — and nothing about deciding, making, shipping, running, or measuring
the video, except the veto and the seal it places on those.

## Input / output model

**Input:** the theme from Discovery, the finished video and its inputs from Generation,
the assets and metadata from Publishing, and the variation and disclosure config those
pillars expose. **Output:** verdicts — a veto (block this theme or this publish), a
flag (advisory, surfaced for human decision at the review gate), the disclosure
decision Publishing sets on the upload, and an audit record. Compliance advises and
bars; it produces no content.

## Governing principles

**Objective blocks, subjective advises.** Checks with a clear right answer — does this
content require the disclosure flag, is this asset licensed — block automatically.
Checks that rest on judgment — is this drifting into slop, is this theme inappropriate,
is this claim false — flag by default and let the human decide at the review gate, so
false positives never silently kill good videos.

**Externally-changing rules, centrally versioned.** Because the platform's policy
changes without warning, the rules live in one versioned, editable place — a compliance
changelog — so tightening the channel to a new policy is a single edit, not a hunt
through scattered logic.

## Capabilities of a complete Compliance pillar

### 1. Synthetic-media disclosure judgment
Publishing *sets* the disclosure flag; Compliance *decides when it applies*. A video
with AI narration and AI or realistic stock visuals almost certainly needs YouTube's
altered/synthetic-content label, mandatory since January 2026. This capability owns the
rule — given this content's characteristics, is disclosure required — and hands the
decision to Publishing to apply. This is an objective check and blocks a publish that
would omit a required disclosure.

### 2. Authenticity / anti-slop
The most critical capability, because the platform renamed its policy to inauthentic
content in July 2025 and enforces it against mass-produced channels. It works in two
layers. The objective layer verifies the protective signals are present: Generation's
variation knob is active and sufficient, and the channel's persona and point of view
are in place. The ambitious layer uses Groq to compare the new video against recent
ones and estimate how template-identical the output is becoming — the exact "same thing
every day" pattern the algorithm targets — and flags when sameness climbs. Both are
**advisory**: they surface a warning at the review gate rather than hard-blocking,
since a machine judgment of "this feels like slop" will sometimes be wrong and an
auto-veto would get the whole pillar disabled.

### 3. Copyright / licensing check
Before a video ships, verify every asset it used has a licensed origin — music, bank
images (Pexels is licensed), voice, and any other asset. For Sem Guru the risk is low
(AI or licensed-stock visuals), but the rule must exist for the day music or a
dubious-origin asset enters, and it is essential if the skeleton is reused for the
stories channel where looping gameplay is copyrighted. This is objective and blocks an
asset without a clear license.

### 4. Brand safety / appropriateness
Because Discovery pulls themes from trends, the system could make a video about
something offensive, tragic, or sensitive purely because it was trending. This
capability vetoes inappropriate themes and angles at Discovery's edge, before
production spends anything. Clear-cut cases block; borderline ones flag for the human.

### 5. Factual accuracy (optional, advisory, off by default)
The persona is a skeptical pragmatist, so publishing a false claim hurts the brand and
flirts with the misinformation policy. An optional layer, using Groq, checks whether a
video asserts something verifiable and wrong. It is **off by default** and, when on,
**advisory** — it is the hardest check to automate well, so it exists as a switch
rather than an inflated always-on gate.

### 6. Versioned, centrally-editable rules
All of the above are rules, and because the platform's policy shifts externally the
rules sit in one versioned, editable place with a change history — a compliance
changelog — so tightening to a new policy is one edit. Editable through Control.

### 7. Audit record
For every video: which checks ran, what passed, what was vetoed or flagged and why,
and which disclosure was set and on what basis. If the platform ever questions the
channel, the history exists. Recording is Compliance's job; surfacing it is Control's.

## Application model

Objective checks — disclosure applicability and asset licensing — block automatically.
Subjective checks — authenticity, brand safety, factual accuracy — flag by default and
route to the human at the review gate, with each check's blocking-vs-advisory mode
configurable so the channel can tighten specific checks to hard blocks as it matures.

## What must be panel-configurable (not hardcoded)

Per check: whether it is blocking or advisory (with the decided defaults above), and its
thresholds — the minimum variation and the sameness ceiling for authenticity, the
brand-safety lists and sensitivity, whether factual accuracy is on. The disclosure
rules and the overall strictness (permissive vs strict). And the versioned rule set
itself, edited through Control. Everything ships with sensible defaults.

## Hand-off contract

Compliance reads the theme, the finished video and its inputs, the assets, and the
variation and disclosure config the other pillars expose; it emits verdicts — vetoes,
advisory flags, the disclosure decision Publishing applies — and an audit record Control
displays. It reuses the Groq integration already in the project for its judgment layers
and introduces no new credential. It advises and bars; it owns no content and no
production step.

## Integrations to fix (part of this work, not a follow-up)

Wire the theme veto into Discovery's edge so an inappropriate theme is stopped before
production; wire the authenticity flag to read Generation's variation config and the
recent-video set and surface at the review gate; wire the disclosure judgment to the
flag Publishing sets and the licensing check to the assets Publishing ships; route all
advisory flags into Control's review-and-approval view and the audit record into
Control's display; and place the versioned rule set where Control can edit it. Behavior
for a default configuration stays equivalent, and the test suite stays green with the
disclosure rule, the licensing check, the authenticity analysis, and the veto path
tested against mocked inputs and a mocked Groq. Keep CLAUDE.md and the README accurate,
including that Compliance now judges disclosure, flags authenticity drift, checks
licensing, vetoes unsafe themes, and keeps a versioned rule set and an audit trail.

## Explicitly out of scope for this pillar

Deciding the theme (Discovery — Compliance only vetoes), making the video (Generation),
uploading it or setting flags mechanically (Publishing — Compliance decides the
disclosure, Publishing applies it), running the checks on schedule (Operations),
measuring performance (Feedback), and the panel and its forms (Control — Compliance
defines the rules, Control edits and displays them). Compliance is the conscience and
the gate: it judges, flags, vetoes, and records, and it makes nothing.
