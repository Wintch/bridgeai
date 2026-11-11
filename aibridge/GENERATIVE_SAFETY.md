# Generative safety: models, law and a guard plan

Status: research note. The guard plan is not built yet. The author is not a lawyer. Legal points marked **[LAWYER]** must be confirmed by one before they are relied on. Tags: **[V]** checked against a primary page, **[S]** from news or law-firm summaries only, **[M]** from memory of the law, **[E]** estimate. Figures not measured here are marked as estimates.

Scope: the generative media stack in `gpu-host/imggen/server.py`, `gpu-host/vidgen/server.py`, `gpu-host/mosher`, the upscaler and interpolation steps, and the planned voice cloning and lip sync. Personal-data law (Ley 25.326) is covered in `aibridge/DATA_LAW_AND_KEYS.md` and is not repeated.

## 1. Repo versus production: who is responsible for what

bridgeai is two different things.

| | (1) The public MIT repo | (2) Our own production, free for a few testers |
|---|---|---|
| Who runs it | Anyone, on their own network | The operator, for third parties (one stack each) |
| Legal role | The self-hoster is the operator of their own install. They take on every duty below for their own users, or none if it is only themselves | A service provider, even without charging **[LAWYER]** |
| Model licences | Their own downloads, their own acceptance | We hold them and must flow terms down to testers (MiniMax H3 section 2.1) |
| Personal data | Their duty | Ley 25.326 duties, see `DATA_LAW_AND_KEYS.md` |
| MIT "AS IS" | Shields the authors from the self-hoster's use | Does not shield us from criminal, civil, consumer or licence duties |
| What the repo must do | Ship safe defaults and say plainly that the guard is the installer's job | Run the guard, publish terms, keep an abuse trail, answer reports |

Consequences:

- Everything in this note that is a **policy** (tester terms, country gate, takedown contact, who may be edited) belongs to production (2) and lives in private operator config, not in the repo.
- Everything that is a **mechanism** (prompt gate, output classifier, provenance mark, audit record) is code and ships in the repo, off or on by a documented setting, so a self-hoster can adopt it. Defaults should be on, because the stack has no other generative filter.
- The repo docs should state: "If you run this for other people, you are the provider. Read `GENERATIVE_SAFETY.md`."

## 2. The models

Licences were read where a text was available. Everything else is labelled.

| Model | Used for | Licence | Safety built into the weights | Risk for us |
|---|---|---|---|---|
| MiniMax H3 | Video with sound (`vidgen/server.py:90-94`) | MiniMax H3 Community License, excludes EU, UK, South Korea, USA | None documented for the open weights. The card says suspected unlawful or pornographic content "may be blocked", tied to MiniMax's hosted service | **High.** Licence imposes deployer duties, flow-down terms and a territory limit |
| FLUX.2 klein 4B | Images, reference edit of a person's photo (`imggen/server.py:80`) | Apache-2.0 | Most documented: NSFW-filtered training data, CSAM filtered with the IWF, post-training suppression, external red-teaming. The repo's input and output filters and the watermark do not run in our ComfyUI path | **High on `--ref`** (real faces). Medium otherwise |
| Z-Image Turbo | Image tier "photo" (`:81`) | Apache-2.0 per HF metadata | Nothing documented on safety, data or misuse | Medium. Community sources say it renders recognisable people and adult content |
| SDXL-Lightning 4-step | Image tier "fast" (`:79`) | OpenRAIL++ (from SDXL base 1.0) | No safety checker. Base card says "research purposes only" | Medium. Licence passes use restrictions to users, see 2.4 |
| Real-ESRGAN, RIFE | Upscale, frame interpolation | BSD-3 and MIT per third-party listings, unverified | Not generative, but they enhance whatever a person supplies | Low, follows the source media |
| MoshUp | Datamosh of a person's video | Our own tool | No generative model | Low, follows the source media |
| Chatterbox (planned) | Voice cloning, TTS (`tts/server_chatterbox.py`) | MIT | Output carries a PerTh watermark. "Don't use this model to do bad things." No consent language | **High** (voiceprint, impersonation) |
| Lip sync (planned) | Mouth motion on a face | Not chosen | Unknown | **High**, same class as `--ref` |

### 2.1 MiniMax H3 licence

Source: https://huggingface.co/MiniMaxAI/MiniMax-H3/raw/main/LICENSE **[V]** (excerpted, section numbers from the excerpt).

- **Territory (§I.3, §I.5, §II).** Worldwide except the EU, UK, South Korea and USA. Exhibit A item 1 bans use outside the territory. The model card says outputs are covered too (recorded in `GPU_RENTAL_AND_MODELS.md:26`). A rented GPU in an excluded territory is also out.
- **Flow-down (§V.2).** We must "bind each recipient or user to enforceable terms at least as protective as the use restrictions" and tell them before access. §III.1 requires giving them the licence. No tester terms exist in the repo today, so this is not met.
- **Deployer safeguards (§V.5, paraphrased).** A service that can generate outputs must implement, maintain, test and review "reasonable and proportionate technical and organizational safeguards", must not weaken or let users circumvent them, must keep a reporting channel, and must act on good-faith reports (remove content, suspend repeat violators). This is the clause our setup meets least: prompts go straight through and the only barrier is skill text.
- **Exhibit A, most relevant.** Item 6 minors; item 7 false content to harm others or influence elections; item 9 defame or harass; item 11 personal data to harm; item 12 public machine-generated content without clear disclosure; item 13 "impersonate another person without that person's consent"; item 5 circumventing safeguards. There is no explicit sexual-content or deepfake item. Outputs may not train another model (§V.3).
- **Marking.** §III.3(b) only encourages an AI-generation identifier in files.
- **Termination (§VIII.2).** For breach MiniMax may terminate, and we must stop and notify downstream users.
- **Escape hatch.** A MiniMax staff reply (HF discussion 12) says it may authorise users in excluded regions once compliance controls are confirmed. Not relied on.

### 2.2 FLUX.2 klein 4B

Sources: https://huggingface.co/black-forest-labs/FLUX.2-klein-4B, https://bfl.ai/legal/usage-policy.

- Apache-2.0, no territory limit, no deployer duty in the licence. The card's out-of-scope list bars violating law, deceptive or harmful content, non-consensual intimate imagery, harassment and personal data used to harm. Whether that list binds a self-hoster is unclear **[LAWYER]**. BFL "encourages" deployers to apply its mitigations. Mandatory filters apply only to the non-commercial 9B.
- BFL's usage policy prohibits realistic depiction of a real person in a sexual, intimate, degrading or defamatory manner, requires documented consent for such depictions, and says its restrictions "also apply to derivatives".
- Safety reports go to safety@blackforestlabs.ai.
- `--ref` crops the supplied photo and feeds it as reference latent (`imggen/server.py:19-25`). The card says nothing about face editing. Our only protection is a skill sentence about whose face may be used (`SKILL_image_requests.md:83-84`).

### 2.3 Z-Image Turbo

https://huggingface.co/Tongyi-MAI/Z-Image-Turbo: no safety statement, no use restrictions found. Restrictions published elsewhere by the developer are unverified. Its text encoder is multilingual (Qwen3-4B), so a word list in English only is bypassed by writing in another language.

### 2.4 SDXL-Lightning and SDXL base

OpenRAIL++ (read from the SDXL base `LICENSE.md`, not a separate Lightning file) **[V, partial]**. It requires that use restrictions "MUST be included as an enforceable provision", that users are notified, and it says "You are accountable for the Output you generate". Restrictions include violating law, harming minors, false information to harm, personal data to harm, defamation and harassment. No clause on sexual content, impersonation or disclosure. Reading Lightning's own terms is still to do **[LAWYER]**.

### 2.5 Cross-cutting

- No weight is a control we can rely on. Only FLUX.2 klein has documented safety work, and its filters do not run in our path.
- Provenance is stripped on purpose: ComfyUI runs with `--disable-metadata` (`imggen/server.py:297`, `vidgen/server.py:368`), PNGs are re-saved without text chunks (`vidgen/server.py:190`), videos are remuxed with `-map_metadata -1` (`:221`, `:465`). Nothing marks an output as AI-made.
- Logs hold a short prompt SHA-256 and a result hash, never the `ref` photo (`imggen/server.py:25,30`). That protects privacy, but it means we cannot reconstruct abuse afterwards. `GPU_MEDIA_TOOLS.md:394` plans a broker record (stack, prompt SHA, result hash). It is not built.

## 3. Law: must, should, can skip

Argentina has no AI law in force and no AI-specific AAIP rule **[S]**. Existing law applies. Case law is early, mostly provincial. Re-check every item **[LAWYER]**.

### 3.1 Must (confirm with a lawyer, but plan on it)

| Duty | Basis | Why it applies |
|---|---|---|
| Consent for a person's image or voice | Código Civil y Comercial arts. 51-53, 1770 **[V, excerpt]** | Art. 53 covers capturing or reproducing image or voice "de cualquier modo". Generating a likeness plausibly counts **[E]**. A tester can consent only for their own face and voice |
| Never produce sexual depictions of minors | Código Penal art. 128, Ley 27.436 **[V, snippet]** | 3-6 years for producing or distributing "representaciones". Courts so far treat simulated images as covered (Zárate-Campana appeals court, 2025 **[S]**), bills to settle it are pending. **Plan on the strict reading.** A real minor's photo through `--ref` or `--from` is the clearest case |
| Do not keep or forward suspected CSAM | Same | Delete at once, log metadata only. Do not send it even to report it |
| Obey takedown and preservation orders | Ley 27.736 "Ley Olimpia" (civil, adds digital violence to Ley 26.485, creates no crime) **[V]**; court orders **[S]** | Removal of specific URLs, data preservation reported at 90 days **[S, unverified]**. Protects women only per one commentary **[S]**, other victims use civil remedies |
| Remove manifestly illegal content after notice | Rodríguez v. Google (CSJN, 2014) **[M]** | The practical standard for intermediaries. CSAM is the named case |
| Pass MiniMax H3 terms to testers, keep safeguards and a reporting channel | H3 licence §V.2, §V.5 **[V]** | A contract duty. Breach lets MiniMax terminate |
| Keep H3 away from the EU, UK, South Korea and USA | H3 licence §I.5, §II **[V]** | Includes testers living there and rented GPUs located there |
| Personal-data duties for photos and voice | Ley 25.326, see `DATA_LAW_AND_KEYS.md` A.2 rows 1-4, 7, 11 | A third party's face in a tester's photo is that person's data. A cloned voice creates a voiceprint, plausibly biometric and sensitive (AAIP Res 4/2019). Reference files fall under delete-on-exit |

### 3.2 Should

- **Short tester terms** in es, ru and en with an "I accept" step (section 5.7). Keep them honest: Ley 24.240 (consumer law) covers free services too **[S]** and voids abusive clauses, but applies to a provider acting "de manera profesional, aun ocasionalmente" **[M]**. A free programme for a handful of people probably is not professional **[E]**. This is the main open legal question **[LAWYER]**.
- Provenance marks (section 5.6). Required by no Argentine law found. H3 item 12 requires disclosure when the user publishes. The EU AI Act art. 50 requires deepfake labelling by deployers and machine-readable marking, with dates moved by the Digital Omnibus **[S]**. A private non-professional tester is probably outside the deployer duty **[M]**.
- A named takedown contact, 18+ only, and a log of who accepted which terms version.
- Follow AAIP's non-binding AI guide as good practice.

### 3.3 Can skip (for now)

- A notified registration specific to AI: none exists.
- A reporting duty for private non-ISP services: none found **[M, not exhaustive]**. Confirm **[LAWYER]**.
- Grooming (art. 131, Ley 26.904) targets the adult, and matters only where the service connects people (community ad feature, public intake bot). Terms say 18+.
- Copyright: no Argentine rule on AI outputs **[S]**. We do not train. Keep the skill's "famous fictional characters for the person's own fun" as private use only.
- Defamation (arts. 109-110, 113): the publisher is the author. The skill already refuses false scenes of real people. Terms put publishing responsibility on the tester.
- Provincial deepfake laws (Chaco Ley 4250-J, Santa Fe and Buenos Aires "Ley Ema", Catamarca) target who creates or spreads, not tool providers **[S]**. Watch them. Sources conflict on status.

### 3.4 Testers abroad

- H3 is a hard gate by country of residence (sections 2.1 and 5.4).
- US: the TAKE IT DOWN Act (48-hour removal by "covered platforms") probably does not reach us **[E]**. H3 is excluded for US users anyway.
- EU: GDPR may apply on its own to EU residents. Not researched (`DATA_LAW_AND_KEYS.md` A.4).

### 3.5 A lawyer must confirm

1. Whether a free service for a few testers is "professional" under Ley 24.240, and the legal status of the operator under Ley 25.326 art. 24.
2. Whether art. 128 covers AI-simulated images, and what the operator must do on finding a suspected case. Which authority to contact and how to hand over without copying the file.
3. Whether a face photo edited without extracting a template is "biometric data", and whether a cloned voice is.
4. Whether BFL's out-of-scope list binds an Apache-2.0 self-hoster, and SDXL-Lightning's own terms.
5. Whether tester terms that mirror H3 are "enforceable" under Argentine adhesion-contract rules, and whether acceptance in a chat is enough.
6. Retention: how long metadata of a refused or reported job may be kept.
7. Whether lingerie on a real adult's photo is acceptable risk (see 5.2).

## 4. The gap today

1. **No generative filter.** `imggen` and `vidgen` check length (800 chars), control characters and the `embedding:` string, nothing about meaning (`imggen/server.py:103-139`). The skills say so: "no content filter on the machine" (`SKILL_image_requests.md:52`), "The model has no content filter" (`SKILL_video_generation.md:124`).
2. **The refuse list is advice to an LLM**, which can be prompt-injected (web page, job posting) and which varies by router and model. `content_guard.py` is an injection guard, not a content filter. The repo's own principle applies: a switch the agent can influence "is NOT a security boundary" (`GPU_MEDIA_TOOLS.md:615`). Enforcement belongs on the host.
3. **Reference edits of real faces.** `--ref` and `makevideo --from` take any photo. Nothing checks how many faces, whose, or whether the photo is already sexual. Skills allow lingerie and underwear on adults (`SKILL_image_requests.md:55`, `SKILL_video_generation.md:124`), and no tool can tell age from a picture.
4. **Voice cloning (planned).** `tts/server_chatterbox.py` clones from a reference wav with no consent step.
5. **No terms, no country gate, no abuse trail, no reporting channel.** Four things the H3 licence expects.
6. **No provenance.** Metadata is stripped everywhere, and Telegram re-encodes images, so file metadata would not survive delivery anyway.

## 5. Guard plan

Principle: the LLM refusal stays as layer 0, but every real control is deterministic and lives on the host or gateway, where a prompt cannot reach it. Never keep flagged output. Never print or log a person's prompt, audio or key.

### 5.1 Layers and where each lives

| Layer | Where | v1 or v2 |
|---|---|---|
| L0 Skill text (existing) | `SKILL_image_requests.md`, `SKILL_video_generation.md`, new voice skill | v1 edit, see 5.2 |
| L1 Prompt gate: rules plus language check | New `gpu-host/guard/prompt_rules.py` plus data file, imported by `imggen` and `vidgen` | v1 |
| L2 Ref-input checks: one face, not nude | `imggen` (before `ReferenceLatent`), and gateway before sending a `--from` file | v1 |
| L3 Output gate: image and video frames | `imggen` and `vidgen` post step, in a separate classifier process | v1 |
| L4 Country and acceptance gate | Gateway (`aibridge/gateway.py`, `cmd_image` :497, `cmd_makevideo` :957) reading per-stack config | v1 |
| L5 Abuse record and takedown | Gateway writes it, runbook in operator docs | v1 |
| L6 Provenance | Output stage of `imggen`, `vidgen` | v1 visible mark, v2 signing |
| L7 Second-opinion prompt classifier on CPU | Host service | v2 |

### 5.2 Skills (L0)

- Remove lingerie and underwear from the allowed lists in both skills. Keep swimwear and sportswear. Age cannot be detected, so the safe line is no undress-adjacent output at all. This is an operator decision (section 6).
- Add: "a photo of another person needs that person's yes: ask once, and if the answer is unclear, do not edit". Add: refuse when the photo shows more than one person.
- Tell the person plainly when the machine refused, without explaining the filter, so no one learns how to evade it.

### 5.3 Prompt gate (L1)

- The service receives the LLM's English rewrite, so it can enforce **English-only**: reject a prompt with mostly non-Latin letters. Cheap, deterministic, and it closes the "write it in Russian" bypass for the multilingual encoders.
- A rules file (data, not code) with word and pattern lists, and one combination rule: an age term (child, minor, schoolgirl, teen, numbers under 18) together with a body or undress term, or any explicit sexual term, refuses. Add real-person impersonation patterns ("looks like", named public figures with sexual or violent terms).
- Refusal returns a fixed code (`content_refused`), never the matched rule. The gateway translates it into one neutral sentence.
- Rules are a floor, easy to paraphrase around. They are not the whole plan.
- Test in a `*_selftest.py` with labelled safe and unsafe sets, in the style of `content_guard_corpus.json`. Measure false positives on benign prompts first.

### 5.4 Ref-input checks (L2) and country gate (L4)

- **One face.** A small CPU face detector (OpenCV YuNet, MIT **[UNVERIFIED]** at source) on every `--ref` and `--from` file. Zero or several faces for an "edit my face" request is refused. Blocks group photos of non-consenting people.
- **Not nude.** Run the nudity classifier (5.5) on the input. Refuse a sexual or nude source.
- **Limit**: suggest 5 reference edits per day per stack **[E]**.
- **Declaration.** One recorded acknowledgement per person ("photos I send are of me, an adult, or of someone who agreed"), stored with date, language and text version, reusing the consent record of `DATA_LAW_AND_KEYS.md` A.2 row 2.
- **Not now: identity matching** against a stored selfie. It needs a stored biometric template (sensitive data), most strong face models are non-commercial research only, and it proves nothing about the enrolment photo.
- **H3 country gate (planned, not in `gateway makevideo` yet).** Per-stack config holds `country` (private operator config, never in the repo). `makevideo` refuses when the stack is in the excluded list or the country is unknown. A rented GPU host must declare its location and the gateway refuses to use one in an excluded country.

### 5.5 Output gate (L3)

- **Image classifier.** Falconsai/nsfw_image_detection (Apache-2.0, ViT-B/16 about 86M parameters, CPU about 0.1-0.3 s per image **[E]**). Accuracy 98% is the authors' own figure on their own set, not an independent benchmark. NudeNet v3 has an unresolved licence conflict (AGPL in the repo, MIT in PyPI metadata), so skip it or run it as an unmodified separate service **[LAWYER]**. Do not use the SD safety checker (documented as obfuscated and easy to bypass), ShieldGemma (4B, does not fit beside H3) or Llama Guard 4 (12B, weak recall on its own card).
- **Video.** Extract frames with ffmpeg (first, last, about one per second, at most 8-10), classify each. Block if one is clearly over threshold or two are borderline. The audio track has no cheap local check, so only the prompt gate covers it.
- **Process.** Run the classifier outside the vidgen process (vidgen has no Pillow), on CPU so it never touches the 8 GB card.
- **Calibration.** Swimwear is allowed, so a binary classifier will flag some. Set the threshold from the false-positive rate on safe pictures (beach, sport, portraits), not from a positive set made with our own models.
- **Stricter threshold on `--ref` jobs.**
- **Flagged output is deleted immediately** and only a metadata line is kept. The operator does not review flagged items by eye.
- Minor detection is not solved: no listed model outputs age, and age estimators are unreliable on stylised or AI imagery **[UNVERIFIED]**. That is why section 5.2 removes undress-adjacent categories instead of trying to detect age.

### 5.6 Provenance (L6)

- v1: a small visible "AI" corner mark on every delivered image and video (Pillow, ffmpeg overlay). It survives Telegram's re-encoding, which strips metadata and C2PA manifests. Add IPTC `DigitalSourceType=trainedAlgorithmicMedia` and an mp4 comment tag for files sent as documents.
- Mark removal must not be a model option: the gateway applies it, not the agent.
- v2: C2PA signing with c2patool (https://github.com/contentauth/c2pa-rs). A self-signed certificate shows as untrusted. A trusted one costs money **[E]**. Test an invisible watermark (TrustMark, MIT, images only) against Telegram's JPEG step. Chatterbox's PerTh watermark stays on, never stripped.

### 5.7 Terms for testers and takedown (L4, L5)

Short, es/ru/en, accepted once, version stored. Contents:

- Only your own face and voice, or the express yes of the person.
- No sexual, humiliating or deceptive content about a real person. Nothing involving minors. 18+ only.
- You must say "AI-generated" when you publish (H3 item 12).
- The H3 restrictions are passed down, the licence text is attached (§III.1, §V.2). Territory limit stated.
- The service is free and experimental, no promise about outputs, ownership of outputs is unsettled, you are responsible for what you publish.
- We refuse some requests, may stop the feature for a person after a report, and keep a metadata record (stack, time, hashes, never the prompt text or photo) of media jobs for a stated period.
- One contact address for reports.

Takedown runbook (operator, private): on a report stop the generative paths for that stack, delete the output and any reference, keep the metadata record, hand the record to the authorities on a legal order **[LAWYER]**. Record who, when, what.

Abuse record (gateway, v1): one line per job: stack id, time, tier or model, size, prompt SHA-256 (16 hex), result hash, ref present yes/no and a ref hash, outcome (`ok`, `refused_prompt`, `refused_ref`, `blocked_output`). No prompt text, no image, no audio. Keep for the quota period.

### 5.8 v2 (later)

- Qwen3Guard-Gen-0.6B (Apache-2.0, about 0.8B parameters, CPU **[E]** 1-2 GB RAM) as a second prompt opinion. Spanish and Russian are not named in its language list. Llama Guard 3 1B has a child-exploitation category but no Russian support and a gated licence. Measure RAM first, since H3 uses about 18 GB host RAM for staging.
- C2PA signing and invisible watermark.
- **Voice cloning gate before it ships:** a recorded consent per voice ("this is my voice"), a spoken-phrase check that the sample says a random sentence, the stored sample treated as sensitive data and deleted on exit, PerTh watermark left on, no cloning of a voice from a video of another person.
- **Lip sync** goes behind the same L2 and L3 gates as `--ref`.
- Per-stack rate limits on media jobs and an alert when refusals repeat.

### 5.9 Build order for v1

1. Tester terms and acceptance gate, country field and H3 gate in the gateway (L4). Smallest, and closes the licence flow-down.
2. Abuse record (L5).
3. Prompt gate with English-only check and rules (L1), with self-tests.
4. Output gate for images, then video frames (L3), with the ref-input checks (L2).
5. Visible mark (L6).
6. Skill edits (L0), docs for self-hosters.

## 6. Open decisions

1. **Lingerie and underwear on adults:** remove from both skills (recommended) or keep with the output gate only.
2. **Reference edits of real people:** keep only with the declaration plus one-face rule, or limit to selfies and drop `--from` on photos with another person. Is identity matching ever wanted?
3. **Testers in excluded territories:** drop H3 for them, or ask MiniMax for authorisation, or offer a different video model.
4. **Terms owner and contact address:** who signs, what address receives reports, and who is the person that handles one.
5. **Retention** of the abuse record, and whether `ref` hashes are acceptable under the delete-on-exit rule.
6. **Visible AI mark:** always on, or per person on request. Signed C2PA now or later, with the cost of a trusted certificate.
7. **Voice cloning and lip sync:** ship only after the v2 consent design, or not for testers at all.
8. **Classifier choice:** Falconsai alone, or add NudeNet after the licence is settled.
9. **Lawyer budget:** which of section 3.5 to confirm first. Suggested order: items 2, 1, 5.
10. **Self-hosters:** default the guard on in the repo and document how to relax it, or leave it opt-in.

## Sources

- MiniMax H3 licence and card: https://huggingface.co/MiniMaxAI/MiniMax-H3/raw/main/LICENSE, https://huggingface.co/MiniMaxAI/MiniMax-H3, discussion 12.
- FLUX.2 klein 4B: https://huggingface.co/black-forest-labs/FLUX.2-klein-4B, BFL usage policy https://bfl.ai/legal/usage-policy.
- Z-Image Turbo: https://huggingface.co/Tongyi-MAI/Z-Image-Turbo, https://github.com/Tongyi-MAI/Z-Image.
- SDXL-Lightning: https://huggingface.co/ByteDance/SDXL-Lightning, SDXL base https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0.
- Classifiers: https://huggingface.co/Falconsai/nsfw_image_detection, https://github.com/notAI-tech/NudeNet, https://huggingface.co/Qwen/Qwen3Guard-Gen-0.6B, https://huggingface.co/meta-llama/Llama-Guard-3-1B, https://huggingface.co/google/shieldgemma-2-4b-it, https://arxiv.org/abs/2210.04610.
- Provenance: https://github.com/contentauth/c2pa-rs, https://github.com/adobe/trustmark.
- Law: Argentine texts on https://www.argentina.gob.ar/normativa (Código Civil y Comercial, Código Penal, Leyes 25.326, 27.436, 27.736, 26.904, 24.240). Provincial and bill status from press and law-firm summaries only.
- Repo: `aibridge/GPU_MEDIA_TOOLS.md`, `aibridge/VIDEO_BENCH_RESULTS.md`, `aibridge/GPU_RENTAL_AND_MODELS.md`, `aibridge/DATA_LAW_AND_KEYS.md`, `aibridge/SKILL_image_requests.md`, `aibridge/SKILL_video_generation.md`, `aibridge/content_guard.py`.
