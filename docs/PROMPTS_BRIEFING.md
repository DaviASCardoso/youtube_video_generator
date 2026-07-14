# Prompt author briefing — "Sem Guru" / Cético Prático

This document is for whoever writes the actual prompts for this channel. You do
**not** need to understand the system that runs them. You only need to know, for
each prompt, what it is for, exactly what shape its answer must take, and the few
hard rules that — if broken — stop a video from being produced. Everything you
need is here.

Write in whatever way makes the channel sound right. Just stay inside the fixed
formats described below.

---

## 1. Orientation — what you are writing for

**Sem Guru** is a faceless, fully automated YouTube channel. There is no on-camera
host; the "face" of the channel is its **voice and its opinions**, and that voice
is a persona called **"O Cético Prático"** (the Practical Skeptic): informed,
ironic but never cruel, direct, treats the viewer as intelligent, and dismantles
self-help clichés with logic and evidence instead of hype.

For every topic the channel decides to cover, a machine builds one video in four
steps, with no human in between:

1. **Script** — a narrator persona writes a continuous voice-over.
2. **Scenes** — each sentence of the script becomes one on-screen visual.
3. **Narration** — the script is read aloud by a synthetic voice.
4. **Assembly** — the visuals and the audio are stitched into the final video.

**The prompts are what give all of this its voice and taste.** The machine handles
timing, rendering, and stitching; your prompts decide *what it says* and *how it
looks and feels*. Your job is voice and quality **within fixed formats** — the
formats are non-negotiable because the machine reads the answers literally.

**Video format / canvas.** The videos are **vertical, 1080×1920 pixels (9:16,
YouTube Shorts shape)**. Every on-screen frame is that tall, narrow rectangle.
Keep this in mind wherever a prompt influences imagery: important elements should
sit in the **centre**, because backgrounds are scaled and cropped to fill this
vertical frame, and the **lower part of the frame is a "safe zone"** kept clear
for on-screen buttons/captions and (when used) a character figure. (The one
exception is the thumbnail, which is a separate landscape image — see §7.)

**Language.** The audience is Brazilian. Read each section for its exact language
rule — some outputs must be **Portuguese (pt-BR)**, some must be **English**, and
a couple mix the two. Getting the language wrong is a real defect, not a style
choice.

---

## 2. Where you edit these prompts

Every prompt below is a plain-text file that you edit in the **web panel**: open
the video type, go to the **Prompts tab**, edit the box for that prompt, and save.
You never touch anything else. Each section names the exact file so you know which
box is which.

---

## 3. The learned-guidance block — READ THIS ONCE, IT APPLIES TO EVERY PROMPT

Several of these prompts have a **second, machine-maintained section** that the
system may add on its own, *underneath* what you write. It is separated from your
text by a clearly marked delimiter line that looks like this:

```
--- Diretrizes aprendidas (geridas pelo Feedback) ---
```

Everything **below that line** is written and maintained automatically based on how
past videos performed. Two rules, always:

- **You write only the base prompt — the part above that line.** Do not write,
  edit, reword, or delete the delimiter line or anything beneath it. If you see it,
  leave it exactly as it is. If you don't see it, don't add it — it appears on its
  own when the system has something to add.
- **Your base prompt must stand completely on its own.** The guidance block is
  often **empty**, so never rely on it being there. Write each prompt as if it were
  the only instruction the machine will ever get — because most of the time it is.

That's the whole rule. It's the same for every prompt that has this block, so it
won't be repeated in each section.

---

## 4. Script / narration prompt — `system_prompt_script.txt`

**Role.** This is the heart of the channel: the persona and writing instructions
for the **voice-over script** of the whole video. When the machine has a topic, it
sends this prompt plus the topic to a writer, and whatever comes back *is* the
narration that gets read aloud. This is where the Cético Prático voice lives.

**Required output.** **Plain narration text in Portuguese (pt-BR)** — just the
words the narrator will speak, start to finish. Nothing else: no title, no labels,
no scene directions, no lists or bullet points, no headings, no stage notes, no
commentary about the script. Just the spoken text.

**Hard technical constraints — these break the video if ignored:**

- **The script is automatically chopped into short "periods" (roughly one
  sentence each), and every period becomes exactly one on-screen visual.** So the
  rhythm of your sentences directly controls the pacing of the images.
- **Sentence length matters in both directions.** The splitter merges any fragment
  that is too short into its neighbour, and very long run-on sentences become one
  visual that lingers too long. Aim for **normal, self-contained sentences** —
  neither clipped two-word fragments nor sprawling multi-clause paragraphs. Punchy
  short sentences are on-brand and fine; just don't make them so tiny they get
  glued together, and don't chain everything into one giant sentence.
- **Sentence count is one-to-one with images and icons.** Each sentence gets one
  visual (and possibly one icon). You don't count anything yourself — just know
  that the number of sentences you produce is the number of on-screen moments, so
  keep the narration a clean sequence of speakable sentences.
- **Keep it to the intended spoken length** (this channel targets roughly a
  60–90 second read). More sentences = more visuals to generate and a longer video.

**Do NOT change / do NOT do:**

- Don't output anything that isn't the spoken words (no metadata, no "Title:", no
  numbering, no markdown).
- Don't add scene markers, cut markers, camera directions, or "[pause]"-type notes.
- Don't switch the narration out of Portuguese.
- Don't use lists or bullets — it must be flowing spoken prose.
- Don't touch the learned-guidance delimiter or anything under it (see §3).

---

## 5. Image-prompt prompt (AI-image mode) — `system_prompt_prompt.txt`

**Role.** Used when the channel renders its backgrounds with **AI-generated
illustrations**. The machine gives this prompt the finished script as a **numbered
list of sentences**, and this prompt must turn each sentence into a short **image
description** that an image generator will draw. One image per sentence.

**Required output.** **Only a JSON array of strings — nothing else.** Each string
is one image description, in **English**, in the same order as the sentences.
Example of the exact shape:

```json
["first image description", "second image description", "third image description"]
```

**Hard technical constraints:**

- **Output must be the array and nothing else.** No sentence before it, no
  explanation after it, no numbering, no comments, no code-fence prose around it.
  The machine reads the whole answer as JSON; any stray text can break it.
- **One prompt per sentence, in the same order, same count.** The images are
  matched to sentences by position, so the number of items must equal the number
  of sentences and the order must line up. Don't merge, skip, or reorder.
- **Image descriptions are in English** (image generators expect English).
- Keep each description short and to a **single scene with one or two main
  elements** — remember the final frame is a **vertical 9:16** crop, so favour a
  simple, centred composition rather than a busy wide scene.

**Do NOT change / do NOT do:**

- Don't output anything outside the JSON array.
- Don't add, drop, or reorder items relative to the sentences.
- Don't write the descriptions in Portuguese.
- Don't put readable words/text inside the described image (on-image text
  generates badly).
- Don't touch the learned-guidance delimiter or anything under it (see §3).

---

## 6. Per-scene prompt (character mode) — `system_prompt_cena.txt`

**Role.** Used when the channel builds each frame from a **real stock photo
background** plus (optionally) a **recurring character** and a small **icon**. The
machine gives this prompt the finished script as a **numbered list of sentences**,
and for **each sentence** this prompt must decide three things at once: the
character's **emotion**, an English **photo search term** for the background, and
an **icon concept**.

**Required output.** **Only a JSON array of objects — nothing else.** One object
per sentence, in order, each with **exactly these three keys**: `"emocao"`,
`"busca"`, `"icone"`. Example of the exact shape:

```json
[{"emocao": "cetico", "busca": "person waking up early", "icone": "clock"},
 {"emocao": "serio", "busca": "empty gym", "icone": null}]
```

**Each field has strict rules:**

- **`"emocao"`** — the character's expression for that sentence. It **must be
  exactly one** of these seven values, lowercase, spelled exactly (do not invent
  or translate them):

  `neutro`, `feliz`, `serio`, `pensativo`, `surpreso`, `cetico`, `confiante`

  (Roughly: `neutro` = plain narration/transition · `feliz` = positive/relief ·
  `serio` = firm statement/warning · `pensativo` = reflection/honest doubt ·
  `surpreso` = revelation/unexpected fact · `cetico` = irony/dismantling a cliché ·
  `confiante` = conclusion/turning point.) Anything outside this list is discarded
  and quietly replaced with `neutro`, so a wrong or misspelled value silently loses
  your intended expression.

- **`"busca"`** — an **English search term (about 2–4 words)** used to find a real
  **stock photo** for the background. It must be **concrete and photographable** —
  a place, object, or situation — not an abstract idea. Good: `messy office desk`,
  `person waking up early`, `empty gym`, `coffee and laptop`. Bad: `success`,
  `motivation`, `productivity concept` (abstract terms return poor photos).

- **`"icone"`** — one **concrete English icon concept as a single noun** (or a
  two-word noun), **or `null`** when no icon fits that sentence. This is **not** a
  search phrase — give one plain concept word. Good: `money`, `warning`, `clock`,
  `brain`, `growth`, `target`, or `null`. Bad: `a person thinking about money` (a
  phrase, not a concept), `""` (use `null` instead), `success` (too abstract).
  Only include an icon when it genuinely reinforces the sentence; otherwise use
  `null`. Not every sentence needs an icon.

**Hard technical constraints:**

- **Output must be the JSON array and nothing else** — no prose, no numbering, no
  comments before or after.
- **One object per sentence, same order, same count** as the sentences you were
  given.
- **The three keys must be spelled exactly** `emocao`, `busca`, `icone`. `emocao`
  must be one of the seven exact values; `busca` must be English; `icone` must be a
  short English noun **or the literal `null`** (never an empty string, never a
  sentence).

**Do NOT change / do NOT do:**

- Don't rename, add, or drop keys.
- Don't invent new emotions or translate the emotion values.
- Don't write the search term or icon in Portuguese.
- Don't return an empty string for the icon — use `null`.
- Don't output anything outside the JSON array.
- Don't touch the learned-guidance delimiter or anything under it (see §3).

---

## 7. Visual style prompt (AI-image mode) — `style_prompt.txt`

**Role.** A short block of **visual-style instructions that is automatically added
in front of every AI image description** from §5. It's how you lock the whole
channel into one consistent look (for Sem Guru today: a deliberate crude "MS Paint"
flat-color aesthetic). You set the art direction once here; every image inherits it.

**Required output.** **Free text — a set of English style descriptors**, typically
a comma-separated list of look-and-feel phrases (art style, color palette, texture,
what to avoid). It is not JSON and has no rigid structure; it is prepended verbatim
to each image description, so write it as reusable style fragments, not as a
sentence about one specific scene.

**Hard technical constraints:**

- **Write it in English** (it joins the English image descriptions).
- **Keep it about style only** — colors, linework, texture, overall aesthetic,
  and things to avoid. Do **not** describe any specific scene or subject here; the
  per-image descriptions handle subjects, and this text applies to *all* of them.
- Keep it reasonably short and consistent — this is the channel's visual signature.

**Do NOT change / do NOT do:**

- Don't put scene-specific content here (it would leak into every image).
- Don't write it in Portuguese.
- Don't touch the learned-guidance delimiter or anything under it (see §3).

---

## 8. Metadata prompt — `system_prompt_metadados.txt`

**Role.** After a video is built, this prompt turns the topic and the finished
script into the video's **YouTube title, description, and tags**, optimized for
clicks and search (the raw topic is *not* used as the title). The machine sends
this prompt the topic and the script and expects packaged metadata back.

**Required output.** **Only a JSON object — nothing else — with exactly these three
keys:** `"titulo"` (a string), `"descricao"` (a string), and `"tags"` (an array of
strings). Example shape:

```json
{"titulo": "…", "descricao": "…", "tags": ["…", "…"]}
```

The title, description, and tags content should be in **Portuguese (pt-BR)** — it's
what Brazilian viewers read.

**Hard technical constraints:**

- **Output must be that JSON object and nothing else** — no text around it.
- **The three keys must be exactly** `titulo`, `descricao`, `tags`; `tags` must be
  a **list of strings**.
- Keep the **title short** — YouTube caps it and overly long titles get cut off
  (aim well under ~100 characters).
- Produce a **reasonable number of tags** (roughly a dozen or so; the system may
  trim extras and drop duplicates).

**Do NOT change / do NOT do:**

- Don't rename, add, or drop keys.
- Don't output anything outside the JSON object.
- Don't make `tags` anything other than a plain list of short strings.
- Don't touch the learned-guidance delimiter or anything under it (see §3).

---

## 9. Thumbnail-text prompt — `system_prompt_thumbnail.txt`

**Role.** For a thumbnail (a **separate 1280×720 landscape image**, 16:9 — not the
vertical video frame), this prompt decides two things from the topic and script:
the **short punchy text overlaid on the thumbnail**, and a description/term for the
thumbnail's **background image**.

**Required output.** **Only a JSON object — nothing else — with exactly these two
keys:** `"texto"` and `"fundo"`.

- **`"texto"`** — a **very short, high-impact overlay line (around five words
  max)** that goes on top of the thumbnail. For this Brazilian channel this text is
  read by viewers, so write it in **Portuguese**.
- **`"fundo"`** — a description of the thumbnail's background, written in
  **English**. Depending on the channel's setting this is either an image-generator
  prompt **or** a stock-photo search term; either way, keep it **English and
  visual/concrete**.

Example shape:

```json
{"texto": "…", "fundo": "eye-catching english background description"}
```

**Hard technical constraints:**

- **Output must be that JSON object and nothing else.**
- **The two keys must be exactly** `texto` and `fundo`.
- Keep `texto` **short** (a few words) — it has to be legible at thumbnail size.
- Keep `fundo` in **English** and concrete (abstract terms produce weak images).

**Do NOT change / do NOT do:**

- Don't rename, add, or drop keys.
- Don't output anything outside the JSON object.
- Don't write `fundo` in Portuguese, and don't let `texto` run long.
- Don't touch the learned-guidance delimiter or anything under it (see §3).

---

## 10. Discovery fit-criteria prompt — `system_prompt_tendencia.txt`

**Role.** Before anything is produced, the channel scans trends and ideas and asks:
"does this make a good Sem Guru video, and if so, what's the actual topic?" This
prompt is the **judgment criteria and persona** used to answer that. It defines
what counts as a good fit for the channel and how to turn a raw trending item
(often unrelated English trends) into a concrete channel topic.

**How its answer is handled (important, and different from the others).** Unlike
the prompts above, you do **not** need to specify an output format here — the answer
shape (accept/reject, a fit score, a ready-to-use topic, and a short justification)
is enforced automatically by the system. Your job is purely to write the
**criteria and voice**: what makes a topic right for the Cético Prático persona, and
how to bridge an unrelated trend into an honest self-help angle.

**Required output / language:**

- Write this prompt as **instructions/criteria in Portuguese (pt-BR)**.
- Make clear that the **resulting topic must be in Portuguese (pt-BR)** and phrased
  as a real subject for a video (not a clickbait title, and not a news summary or
  gossip recap) — a genuine, concrete angle in the channel's skeptical, practical
  voice.
- Because the structure is enforced for you, **do not** try to force a JSON
  format or output examples here — just describe the standard for a good topic and
  the persona clearly.

**Do NOT change / do NOT do:**

- Don't turn this into a rigid output-format instruction — describe the *criteria*,
  not a data shape.
- Don't let the guidance drift off the channel's persona (skeptical, practical,
  anti-cliché).
- Don't ask for topics in a language other than Portuguese.
- Don't touch the learned-guidance delimiter or anything under it (see §3).

---

## Quick reference

| Prompt file | Its answer must be | Language of the answer |
| --- | --- | --- |
| `system_prompt_script.txt` | Plain narration text, one clean sentence after another, no markup | Portuguese |
| `system_prompt_prompt.txt` | **Only** a JSON array of strings (one image description per sentence) | English |
| `system_prompt_cena.txt` | **Only** a JSON array of `{emocao, busca, icone}` objects (one per sentence) | `emocao` = fixed value · `busca` English · `icone` English noun or `null` |
| `style_prompt.txt` | Free-text style descriptors (prepended to every image) | English |
| `system_prompt_metadados.txt` | **Only** a JSON object `{titulo, descricao, tags[]}` | Portuguese |
| `system_prompt_thumbnail.txt` | **Only** a JSON object `{texto, fundo}` | `texto` Portuguese · `fundo` English |
| `system_prompt_tendencia.txt` | Criteria/persona prose (answer shape is enforced for you) | Portuguese (and topics must be pt-BR) |

Three rules that apply everywhere:

1. **When a prompt must output JSON or an array, output ONLY that** — no words
   before or after, no numbering, no comments.
2. **Anything tied one-to-one with sentences must keep the same count and order** as
   the sentences given.
3. **Never edit the learned-guidance delimiter or anything below it**, and always
   write a base prompt that works on its own (see §3).
