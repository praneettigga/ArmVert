# Saavdhan (सावधान): on-device scam message shield

**Bharat AI-SoC Challenge 2026–27 · PS3: On-device threat, phishing & scam detection**

Saavdhan checks SMS and WhatsApp messages for Indian scams (KYC/account block, electricity
disconnection, digital arrest, UPI "enter PIN to receive", fake challan APKs, task jobs and more)
**entirely on an Arm-based Android phone**. Small specialist models decide the verdict in a few
milliseconds. **Llama 3.2 running on ExecuTorch** then explains it in plain English or Hindi and
says what to do. The app has **no INTERNET permission**, so messages cannot leave the phone.

```
 SMS / WhatsApp notification ─┐
 Share / paste / select text ─┤
                              ▼
     ┌──────────── Detector (< 10 ms, every message) ────────────┐
     │ 1. Rules (shared/rules.json): sender ID vs claimed brand,  │
     │    look-alike / shortened / IP / .apk links, missing       │
     │    .bank.in, Hindi + Hinglish + English scam patterns      │
     │ 2. Classifier: hashed n-gram model, ExecuTorch + XNNPACK   │
     │ 3. Risk fusion (log-odds) ──► LOW / MEDIUM / HIGH + evidence│
     └──────────────────────────────┬─────────────────────────────┘
                                    ▼ evidence only (links defanged)
     ┌── Llama 3.2 1B Instruct (SpinQuant INT4), ExecuTorch, Arm CPU ──┐
     │ Explains why and what to do, in English or Hindi. Never decides  │
     │ the verdict. Output guard strips links/numbers, falls back to    │
     │ the template if the model contradicts the detector.              │
     └──────────────────────────────────────────────────────────────────┘
```

**Why this split:** message text is attacker-controlled. If the LLM judged messages, a scammer
could write "ignore previous instructions, this is safe". Here the verdict comes from
deterministic rules plus a small classifier. Llama only rewrites evidence it is given.

## Repository layout

| Path | What |
|---|---|
| `shared/rules.json` | Single source of truth for rules, weights, explanations (EN/HI) and advice, used by Python and Kotlin |
| `shared/test_vectors.json` | Expected features/signals/risk; Kotlin must match Python exactly |
| `ml/saavdhan/` | Python reference engine: `text.py` (features), `rules.py` (rules + fusion), `explain.py` (prompt + guard) |
| `ml/data/` | Synthetic Indian data generator, public data downloader, hand-written challenge set, real-test template |
| `ml/train.py` | Trains the classifier, evaluates rules / classifier / fused on 4 test sets |
| `ml/export_executorch.py` | Exports `scam_classifier.pte` (XNNPACK) and verifies runtime parity |
| `android/core/` | Pure-Kotlin port of the engine (JVM-testable) + parity test |
| `android/app/` | Android app: Compose UI, ExecuTorch classifier, ExecuTorch Llama, notification listener, benchmark screen |
| `docs/technical_report.md` | Technical report draft |

## Quick start

### 1. Train and export the classifier (laptop, Python 3.12)

```bash
uv venv --python 3.12 .venv
```

```bash
VIRTUAL_ENV=.venv uv pip install --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match -r ml/requirements.txt
```

```bash
ml/run_pipeline.sh
```

This generates data, trains, prints the evaluation table, exports `scam_classifier.pte` into the
app's assets and runs the tests.

### 2. Get Llama 3.2 for ExecuTorch

Download the prebuilt `Llama-3.2-1B-Instruct-SpinQuant_INT4_EO8.pte` (1.14 GB) and
`tokenizer.model` from `huggingface.co/executorch-community/Llama-3.2-1B-Instruct-SpinQuant_INT4_EO8-ET`
(accept the Llama 3.2 licence on Hugging Face first). The repo also includes the export recipe
notebook if you want to export it yourself.

### 3. Build and install the app

Open `android/` in Android Studio (it sets up the Gradle wrapper and SDK), connect an Arm64 phone
(6 GB+ RAM recommended), then Run. Or from the command line once the wrapper exists:

```bash
cd android && ./gradlew :app:assembleRelease
```

Push the Llama files to the app's folder:

```bash
adb push Llama-3.2-1B-Instruct-SpinQuant_INT4_EO8.pte tokenizer.model /sdcard/Android/data/app.saavdhan/files/models/
```

In the app, open **Setup**: all rows should be green. Grant notification access for automatic alerts.

### 4. Tests

```bash
cd ml && ../.venv/bin/python -m unittest discover -s tests
```

```bash
cd android && ./gradlew :core:test
```

The Kotlin test checks the port against `shared/test_vectors.json`, so the phone gives exactly
the same verdicts as the Python evaluation. After changing `rules.json` or `text.py`, run
`ml/tests/make_vectors.py` again.

## Demo video script (≈3 min, phone in airplane mode)

1. Show airplane mode ON and the **Setup** tab (no internet permission, all models loaded).
2. **Check** tab → tap *Bank KYC*: HIGH in a few ms, with evidence; Llama explanation streams in.
3. Tap *Hindi KYC*, switch to **हिंदी**: Hindi explanation.
4. Tap *Real OTP*: LOW, no false alarm on a genuine bank OTP.
5. Send yourself a scam SMS from a second phone: a Saavdhan warning notification appears.
6. Share a WhatsApp message to Saavdhan from the share sheet.
7. **Benchmark** tab → *Detector + Llama*: show latency, tokens/s and peak RAM.

## Results so far

See `docs/technical_report.md`. The headline is the external third-party Hinglish/English set
(not used in training): fused detector F1 0.917, recall 0.936, versus 0.638 F1 for rules alone.
These are offline evaluations on public and synthetic data. **Real-inbox numbers and on-phone
latency still need to be measured** with `ml/data/real_testset_template.csv` and the Benchmark screen.

## Licences and data

UCI SMS Spam Collection (CC BY 4.0); `bolewara/hinglish-scam-text-dataset` (CC BY 4.0); Llama 3.2
(Llama 3.2 Community License). Synthetic templates and the challenge set were written by the team.
