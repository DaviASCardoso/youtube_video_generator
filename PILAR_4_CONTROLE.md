# Pillar 4 — Control (Controle)

> Reference spec for the Control pillar. It describes **what** a complete version
> of this pillar is responsible for and the capabilities it should expose. The
> product decisions here are already made; what is left to you is technical — the
> rendering mechanism, how forms are generated from a schema, the auth mechanism,
> how ntfy is called, where the panel routes live. Choose those consistent with
> the project's existing panel stack (FastAPI + SSE); do not rewrite the frontend
> framework.
>
> Control is special: it is the surface where the configurability the other
> pillars built becomes a real UI, and it is how the system reaches you both when
> you are at the panel and when you are not. Two principles govern it. First, it is
> a **thin, schema-driven surface** — it holds no business logic of its own, it
> reads the config schemas and the records the other pillars define and renders
> forms and views over them, so a knob a pillar adds later appears in the panel
> without hand-editing Control. Second, it keeps **options simple and
> well-defaulted** — organized, progressively disclosed, every field showing its
> default — so the panel is approachable rather than a wall of fields.

## Responsibility (one sentence)

Control is the human-facing surface for **configuring, triggering, observing,
inspecting, and notifying**: it renders editable forms over every pillar's
configuration, lets a human start and re-run and cancel work, exposes run history
and live logs and the finished artifacts, surfaces health and cost at a glance,
hosts the human-approval gate, and pushes notifications to the phone. It owns the
interface and nothing behind it — no discovery, generation, publishing, scheduling,
analytics, or policy logic lives here.

## Input / output model

**Input:** the config schemas and the records (run history, published-records,
per-stage cost and quota, pending-approval items, health signals) that Discovery,
Generation, Publishing, Feedback, and Operations define and write. **Output:** human
actions — edited configuration written back to the right layer, triggered or
cancelled runs, and approve/reject/edit decisions — plus push notifications
delivered to the phone. Control produces no media and computes no analytics; it
renders what the pillars expose, relays what the human decides, and forwards the
events the human chose to be notified about.

## Governing principles

**Thin and schema-driven.** Control contains no pillar logic. It renders forms from
each pillar's config schema and views from each pillar's records. Adding a
configurable knob is done in the owning pillar's schema, and Control surfaces it
automatically rather than requiring a hand-built form per field.

**Simple and well-defaulted.** Options are organized by pillar and by type, advanced
knobs are collapsed behind progressive disclosure, and every field shows its
default. Nothing must be changed for the system to run; the panel is for tuning. The
same restraint applies to notifications: you can be notified about anything, but the
default is deliberately quiet.

**Responsive.** Configuration changes take effect without a restart wherever the
config layering allows it, and the human is never made to repeat work the panel
could remember.

## Capabilities of a complete Control pillar

### 1. Configuration surface (forms over every pillar's config)
Control renders editable forms for all the configuration the pillars define —
Discovery's source toggles and fit criteria and selection weights and retention and
review-gate mode, Generation's per-stage providers and prompts and voice and format
and variation and budget, Publishing's destinations and metadata templates and
thumbnail styling and timing and visibility and quota cap. Forms are generated from
the pillars' schemas rather than hand-coded per knob. The config layering is
visible: which value is a default and which is a per-type override, and which layer
a shown value comes from.

### 2. Prompt editing
The persona and criteria prompts are the highest-leverage configuration in the
system, so Control exposes them as first-class editable text with clear per-type
scoping, the way the existing prompt editors already do — generalized to cover every
prompt the pillars now use (script, visual, metadata, thumbnail, fit criteria).

### 3. Triggering & control actions
Control is the play/stop surface: manually trigger a run — discovery, generation,
publish, or the full pipeline — for a chosen type, re-run a single failed stage, and
cancel a running job. It respects the one-run-per-type invariant and never itself
runs the work; it asks Operations to.

### 4. Review & approval gate
Discovery's pending-candidate state and Publishing's review-first state both leave a
seam for human approval, and Control is where that seam becomes a UI: a list of items
awaiting approval, with approve, reject, and edit actions. Approving a pending theme
releases it to production; approving a review-first video releases it to publish.

### 5. Run history
A browsable history of runs — what ran, when, the outcome, the per-stage timing and
cost, the decided theme, and the published IDs and URLs — read from the records the
pillars write. No computation here; it displays what already exists.

### 6. Live logs, artifact inspection & playback
Real-time log streaming (the existing SSE) so a run can be watched as it happens,
plus inspection of a run's artifacts: read the script, hear the narration, see the
thumbnail, and play the finished video in the browser (the existing playback),
generalized so every stage's artifact is inspectable and a stage can be re-run from
here.

### 7. Health, cost & quota dashboard
The at-a-glance "is everything OK, and what is it costing" view — the thing that
means you never open a terminal to know the system's state. It surfaces what
Operations and the other pillars record: whether the scheduler is running, whether
any credential is expired or expiring (the 7-day refresh-token case), whether the
disk or NAS is filling, when each type last published successfully, and today's
spend against budget and quota against cap. It reads these signals; it does not
compute or enforce them.

### 8. Access protection
The panel is exposed on the network (bound to 0.0.0.0 on the home server) and can
trigger spend and publish, so it sits behind a simple single-admin auth gate — one
admin credential, configurable, not a multi-user identity system. The exact
mechanism (session, token, or basic auth) is your technical choice; the requirement
is that the network-exposed panel is not open.

### 9. Notifications (ntfy push)
The panel is how you reach the system; notifications are how it reaches you when
you're not looking at it. Control pushes notifications to the phone via **ntfy**, a
free, open-source HTTP pub-sub service where a plain POST to a topic reaches the
subscribed phone app, with no account or API key required on the public server. A
dedicated, configurable notifications tab controls what you receive across **every
pillar and process** — Discovery, Generation, Publishing, and the Operations/health
signals — so you *can* be notified about anything.

**Channel and config.** The channel is ntfy. Configuration is the server URL
(default `https://ntfy.sh`, overridable for a self-hosted instance — which fits the
home server later), the topic (chosen unguessable, since on the public server the
topic acts as the password), and an optional access token. Emission is a simple HTTP
POST; no heavy dependency is added.

**Boundary.** Control owns the notification configuration, the ntfy channel, and the
tab. Events originate in every pillar and in Operations; Control decides — per the
user's config — which of those actually reach the phone. In practice Control can
already fire from the signals and records it reads for the dashboard (a failed run, an
expiring credential, a cap hit, low disk, a pending approval), so notifications work
without modifying every pillar now; a lightweight notification interface lets pillars
emit finer events later.

**Default policy (decided — quiet, never spammy).** Notify by default, at high
priority, only for things that need attention: a run failed after retries, a
credential expired or is expiring, a budget or quota cap was hit, disk or NAS space is
low, the scheduler didn't run when expected, and an item is waiting in the review
gate (only when review-first is enabled). Stay silent by default — available to switch
on — for routine successes: a video published, a run completed, per-stage progress.
These would flood the phone (one or more per video per day) and the free tier is 250
messages/day, so they are off unless you turn them on. Quiet hours are available to
suppress non-critical notifications during set hours, and a "send test notification"
button confirms the phone is receiving.

## What the panel must expose (organized, not a wall)

Every configurable knob the other pillars define, grouped by pillar and by type,
with advanced options collapsed and defaults shown: Discovery's, Generation's, and
Publishing's full configurable sets as listed in their specs. Plus Control's own
settings: the admin credential and whether auth is required; the notifications tab
(the ntfy server, topic, and optional token; per-pillar and per-event toggles;
priority per category; quiet hours; and the test button); and any panel preferences
such as log retention or refresh rate. Everything reads from and writes to the
pillars' config layers; Control stores no configuration of its own beyond its panel,
auth, and notification settings.

## Hand-off contract

Control reads the config schemas and records the other pillars define and writes
configuration back to the correct layer; it emits human actions (trigger, cancel,
approve, reject, edit) that the pillars act on, and it delivers to the phone the
events the human chose to be notified about. It holds no pillar logic and owns no
records of its own beyond panel, auth, and notification settings. Each pillar owns
its schema and its records; Control renders, edits, and notifies.

## Integrations to fix (part of this work, not a follow-up)

The existing panel — the per-type config forms, the prompt editors, the SSE live
logs, the run history, and the in-browser playback — moves onto this model without
losing any current behavior: forms become schema-driven and cover the full
configurable sets from Discovery, Generation, and Publishing; the existing per-type
publish toggle and the pending states appear in the review-and-approval view; the
health/cost/quota dashboard, the auth gate, and the ntfy notifications tab are added,
with notifications wired to the signals Control already reads. The default panel
behavior stays at least as capable as today's, and the test suite stays green, with
tests covering the config read/write, the action endpoints, and the notification
dispatch (external clients including ntfy mocked).

## Explicitly out of scope for this pillar

Deciding themes (Discovery), making videos (Generation), shipping them (Publishing),
computing analytics (Feedback — Control displays them), running and scheduling the
work and enforcing budgets, quotas, and alerts (Operations — Control triggers,
displays, and notifies; Operations runs and enforces), and the policy rules
themselves (Compliance). Control is the window, the controls, and the messenger; the
machinery is behind the glass. It shows everything, tells you what matters, and runs
nothing.
