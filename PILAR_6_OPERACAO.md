# Pillar 6 — Operations (Operação)

> Reference spec for the Operations pillar. It describes **what** a complete version
> of this pillar is responsible for and the capabilities it should expose. The
> product decisions here are already made; what is left to you is technical — how the
> scheduler is wired, how events chain, how the failure-response engine is
> structured, where execution state is persisted. Choose those consistent with the
> project's conventions.
>
> Operations is the only pillar that produces nothing visible and owns no content
> knob: it is what makes the other five run by themselves, 24/7, unattended, on the
> home server. It is **cross-cutting by nature** — it runs the jobs that Discovery,
> Generation, Publishing, and Feedback *define* but do not run themselves. Two
> principles govern it. **Resilient by design** — it assumes APIs fail, the machine
> reboots, and resources run out, and it keeps running anyway. **Configurable** — the
> schedules, the retry policy, and the job enablement are panel-editable, while the
> limits it enforces stay owned by the pillars that define them.

## Responsibility (one sentence)

Operations keeps the system alive and running on its own: it schedules and
orchestrates the jobs the other pillars define, runs them resiliently through an
intelligent failure-response engine, enforces at runtime the limits the pillars set,
emits the events that become notifications, collects the health signals the dashboard
shows, and recovers cleanly after a crash. It owns everything about *running* the
system — and nothing about what to make, how to make it, where to ship it, or how it
performed.

## Input / output model

**Input:** the jobs the pillars define (a discovery run, a generation run, a publish,
a feedback poll), the limits they set (Generation's cost budget, Publishing's quota
cap, Feedback's sample floor), and the checkpoints they persist. **Output:** executed
runs in the right order and at the right time, runtime enforcement of those limits,
emitted events for Control to deliver, collected health signals for Control to
display, and recorded execution logs. Operations runs the work and coordinates it; it
produces no content and computes no analytics.

## The flow this pillar is responsible for

```
schedule / event → orchestrate (right order, one-run-per-type) → run job through the failure-response engine → enforce limits → emit events + collect health → record execution
                                                                              │ on reboot: recover state and resume from checkpoints
```

## Governing principles

**Resilient by design.** Every external call can fail, the machine can reboot, and
disk can fill; Operations treats these as normal, not exceptional. The intelligent
failure-response engine (below) is the core of the pillar, not an add-on.

**Configurable, but limits stay with their owners.** Schedules, retry policy, and job
enablement are panel-editable here. The *values* of the cost, quota, and sample limits
live in the pillars that define them (Generation, Publishing, Feedback); Operations
reads and enforces them, it does not own them.

## Capabilities of a complete Operations pillar

### 1. Scheduler / timing
The clock of the system: what runs, when, how often, per type and per timezone —
discovery once a day, generation in sequence, feedback re-polling at its maturation
intervals. This is the existing APScheduler, generalized to orchestrate every pillar's
jobs, with each job's schedule and frequency panel-editable.

### 2. Reactive orchestration
Runs the pipeline in the correct order — discovery, then generation, then publishing —
and chains stages **by event**, not only by clock: when generation finishes,
publishing is triggered; when a video reaches 24h old, its feedback poll is scheduled.
It respects the one-run-per-type invariant so a type never has two runs in flight, and
it asks the pillars to do the work — it never contains their logic. The scheduler is
the trigger source; events carry the pipeline forward from there.

### 3. Intelligent failure-response engine (retry + error handling)
This is the heart of the pillar, and it is deliberately **not** "retry N times with
exponential backoff." It is a policy engine that first **classifies** every error and
then chooses the right response, because different failures need opposite reactions.

**Error taxonomy (decided).** Every error is classified into one of:
- **Transient** — timeouts, dropped connections, 5xx, rate-limit 429. The only truly
  retryable class.
- **Permanent** — 4xx other than auth and quota, malformed input, validation failures.
  Retrying wastes time and money; fail fast and record.
- **Auth** — 401/403, expired or invalid credential (the 7-day refresh-token case).
  Retrying the same call is useless; trigger a credential refresh if possible,
  otherwise halt that destination and escalate.
- **Quota / budget exhausted** — a quota 429 or one of the pillars' own caps hit.
  Don't retry-spam; **defer** the job to the next window when the resource resets
  (e.g. tomorrow's quota) and escalate.
- **Resource** — disk or NAS full, out of memory. Retrying won't help until it's
  freed; halt the affected work and escalate.

**Response strategies (matched to the class, not blanket).**
- *Honored, jittered backoff.* For transient errors, back off — but honor a
  `Retry-After` header when the API sends one instead of guessing, and add jitter so
  retries don't synchronize into a thundering herd.
- *Cost-aware retry budgets.* A retry on an expensive stage (image, TTS) costs real
  money, so cap retries tighter there than on cheap calls, and never let retries push a
  run past the cost budget Generation set — retrying is not exempt from the budget.
- *Idempotency-aware resume, not restart.* On retry, resume from the last good
  checkpoint Generation persisted rather than redoing paid stages, and for
  non-idempotent operations like an upload, reconcile first (did it actually complete?)
  so a retry after a partial upload never double-publishes. Retry at the granularity of
  the failed stage, not the whole pipeline.
- *Retry-then-failover.* After a bounded number of transient failures on a provider,
  fail over to the alternate the pillar defined (FLUX → stock, primary TTS →
  secondary) instead of retrying a provider that's clearly not answering.
- *Provider circuit breaker.* If a provider fails repeatedly, open a circuit — stop
  sending it requests for a cooldown so quota and time aren't wasted hammering a dead
  service — then send a single half-open probe after the cooldown to test recovery
  before closing it again. (This is distinct from the budget limits in capability 4;
  this breaker is about a failing dependency, that one is about spend.)
- *Adaptive to recent health.* Track each provider's recent failure pattern; a provider
  that's been flaky all day gets more conservative treatment (fewer retries, faster
  failover) than a normally-reliable one hitting a one-off blip.
- *Defer-to-window.* For quota and budget classes, "retry" becomes "reschedule to when
  the resource resets," not an immediate re-attempt.
- *Dead-letter and escalate.* When the matched strategies are exhausted, the job lands
  in a recorded dead-letter state — never silently dropped — carrying its **classified
  reason**, and escalates as an event (which Control delivers via ntfy), and can be
  manually re-run from Control once the cause is fixed.

**Error handling around all of it.** Every error is recorded with full context — which
stage, which provider, which theme or video, and its class — so failures are
diagnosable rather than opaque, and the escalation carries that context so an alert
reads "Generation failed at TTS for theme X: provider quota exhausted, deferred to
tomorrow" rather than "error." Partial failures (say 3 of 5 images fail) resolve by a
configurable policy — proceed degraded or fail — rather than crashing. Nothing fails
silently: every failure is recovered, deferred, or escalated.

### 4. Limit enforcement
The cost budget Generation defines, the quota cap Publishing defines, and the sample
floor Feedback defines are *defined* by those pillars but *enforced at runtime here*:
Operations is the guard that actually stops or defers a job when the day's budget or
quota is spent. The pillars set the limit; Operations makes it real.

### 5. Alerting / event emission
Operations detects the conditions worth a notification — a job dead-lettered after the
engine gave up, a credential expiring, disk or NAS filling, the scheduler failing to
run when expected, a budget or quota hit — and emits the event. Control delivers it to
the phone via ntfy per the user's notification config. Operations generates the event;
Control delivers it.

### 6. Health signal collection
It collects the signals the dashboard shows: the scheduler heartbeat, credential
validity and expiry, disk and NAS space, and when each type last ran and published
successfully. Operations collects; Control displays.

### 7. State & crash recovery
24/7 has to mean surviving reboots, not "until the first power cut or update." On
restart, Operations recovers its state — what was scheduled, what was mid-flight — and
resumes from the checkpoints Generation persisted, so an interrupted run continues
rather than restarting or vanishing.

### 8. Observability of execution
A record of every job: when it started and finished, whether it succeeded, how long it
took, how many retries and of what class, and whether it failed over or was deferred.
Recording this is Operations' job; surfacing it is Control's.

## What must be panel-configurable (not hardcoded)

The schedule and frequency per type and per pillar, and each job's enablement; the
failure-response policy — per error class and per stage the retry counts and caps, the
backoff base and ceiling, the circuit-breaker failure threshold and cooldown, and the
partial-failure policy of proceed-degraded versus fail; and the defer windows. The
cost, quota, and sample **limits themselves stay configured in their owning pillars**;
Operations only reads and enforces them. Everything ships with sensible defaults.

## Hand-off contract

Operations' inputs are the jobs and limits and checkpoints the other pillars define;
its outputs are executed runs, runtime limit enforcement, emitted events, collected
health signals, and execution records. It runs the pillars' work and coordinates it;
it holds none of their logic and produces no content. It reuses everything already in
the project (APScheduler, the service runner, the ntfy channel Control owns) and
introduces no new credential.

## Integrations to fix (part of this work, not a follow-up)

Generalize the existing APScheduler and run paths into the scheduler and reactive
orchestration described here; wrap the existing per-pillar external calls with the
failure-response engine so their in-pillar degrade-instead-of-crash posture is
coordinated rather than duplicated; wire limit enforcement to the caps Generation,
Publishing, and Feedback expose; emit events into the notification path Control's ntfy
tab already consumes; feed the health signals into the dashboard Control renders; and
resume from Generation's checkpoints on restart. Behavior for a default configuration
stays equivalent, and the test suite stays green with the failure-response engine's
classification, backoff, failover, circuit breaker, and dead-lettering all tested
against mocked failing clients. Keep CLAUDE.md and the README accurate, including that
Operations now schedules and reactively orchestrates every pillar and runs them through
an intelligent, classified failure-response engine.

## Explicitly out of scope for this pillar

Deciding themes (Discovery), making videos (Generation), shipping them (Publishing),
measuring performance (Feedback), the panel and notification delivery (Control —
Operations emits and collects, Control delivers and displays), and the policy rules
(Compliance). Operations is the conductor, not the musicians: it runs the work on time
and keeps it running, and it plays nothing itself.
