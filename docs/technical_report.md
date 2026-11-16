# Saavdhan: Technical Report (Phase 1 draft)

> Draft. Sections marked **TODO (device)** must be filled with numbers from the phone's Benchmark
> screen and the real-message test set before submission.

## 1. Problem and use case

India recorded ₹22,845 crore in reported cyber-fraud losses in 2024 (MHA reply to Parliament), and
the National Cybercrime Reporting Portal receives around 8,000 complaints a day (SIH 2026, PS 26184).
Existing SIH problem statements address fraud on the institution side: I4C analytics, crypto
tracing, email forensics, voice-clone detection. Saavdhan protects the citizen at the moment a
message arrives, on their own phone, in their own language, with nothing sent to the cloud.

Following the mentoring guidance to pick one use case and do it well, Phase 1 targets
**Option A: SMS and chat scam detection** (with phishing-link analysis as part of it). The code is
modular so URL checks at click time and call-scam detection can be added in Phase 2.

## 2. System design

| Stage | Runs on | Model / method | Purpose |
|---|---|---|---|
| Input | Android | NotificationListenerService, share sheet, text selection, paste | Get SMS/WhatsApp text and sender |
| Rules | Arm CPU (Kotlin) | `shared/rules.json`: 19 keyword rules (EN/Hinglish/Hindi), 11 structural signals | Explainable evidence; India-specific checks |
| Classifier | Arm CPU via **ExecuTorch + XNNPACK** | Hashed word + char n-gram embedding bag + MLP, 2.1M params, 8.4 MB | Catch scams phrased in new ways |
| Fusion | Arm CPU | Log-odds sum, thresholds 0.5 / 0.85 | LOW / MEDIUM / HIGH |
| Explanation | Arm CPU via **ExecuTorch** (XNNPACK) | **Llama 3.2 1B Instruct**, SpinQuant INT4 | Plain-language why + what to do, EN/HI |
| Guard | Arm CPU | Regex post-filter | Remove links/numbers, block overclaiming, fall back to template |

India-specific signals include:
- an SMS that names a bank or government office but comes from a 10-digit mobile number instead of
  a registered sender ID (for example `AX-HDFCBK-S`);
- bank-themed links that are not on `.bank.in`, which RBI made mandatory for banks from 31 Oct 2025;
- brand look-alike domains, shorteners, raw-IP links and `.apk` links;
- the UPI "enter PIN to receive money" trick;
- digital-arrest scripts and the electricity-disconnection scam;
- negation handling, so "Do not share this OTP" is not flagged.

**Security choice.** The LLM never sees an instruction to judge the message. The message is defanged,
truncated, fenced as untrusted, and only the detector's evidence is given to Llama. If Llama
contradicts the detector (for example it calls a HIGH-risk message "safe"), the app shows the
deterministic template instead. The app has no `INTERNET` permission.

## 3. Data

| Set | Size | Use | Notes |
|---|---|---|---|
| Synthetic Indian templates | 4,360 rows, 94 templates | train / val / test **split by template** | Written by the team from public advisories; EN, Hinglish, Hindi; includes hard negatives (real OTPs, bank alerts, Hinglish chats) |
| UCI SMS Spam Collection | 5,574 | train / val / test | Old UK/Singapore English; mostly promotional spam |
| Hinglish scam set (bolewara, HF) | 87 non-UCI rows | **external test only** | Third-party, never trained on |
| Hand-written challenge set | 36 | test only | Phrased differently from the templates |
| Real inbox set | **TODO** | test only | Collect 100+ real messages from team and family phones (`ml/data/real_testset_template.csv`) |

## 4. Detection quality (offline, laptop)

Threshold 0.5. FPR = false-positive rate on genuine messages.

| Test set | Model | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|
| External Hinglish (n=87) | Rules only | 1.000 | 0.468 | 0.638 | 0.000 |
| | Classifier only | 0.909 | 0.851 | 0.879 | 0.100 |
| | **Fused** | 0.898 | **0.936** | **0.917** | 0.125 |
| Challenge set (n=36) | Rules only | 1.000 | 0.700 | 0.824 | 0.000 |
| | Classifier only | 0.900 | 0.900 | 0.900 | 0.125 |
| | **Fused** | 0.950 | 0.950 | **0.950** | 0.062 |
| UCI test (n=837) | **Fused** | 0.937 | 0.963 | 0.950 | 0.010 |
| Synthetic, unseen templates (n=660) | **Fused** | 0.875 | 1.000 | 0.933 | 0.105 |

The two parts complement each other. On the Hindi message "आपका खाता आज बंद हो जाएगा। तुरंत केवाईसी
अपडेट करें", the classifier gives p = 0.12 while the rules flag KYC + account threat + urgency, so the
fused verdict is HIGH. On paraphrased English scams with no keyword hit, the classifier supplies the recall.

**Honest caveats.**
- Rules-only scores on the synthetic test set are near-perfect only because the same team wrote both.
  They are excluded from the headline.
- The fused false-positive rate (6–12%) is too high for automatic alerts and is the main item for Phase 2.
- **TODO (device):** report results on the real inbox set; this is the number judges should trust.

## 5. On-device performance — TODO (device)

Measured with the in-app Benchmark screen (airplane mode on, phone at room temperature). Paste the JSON.

| Metric | Value |
|---|---|
| Device / SoC / RAM | |
| Classifier load time | |
| Detector latency per message (mean / p95) | |
| Llama model file | Llama-3.2-1B-Instruct-SpinQuant_INT4_EO8.pte, 1.14 GB |
| Llama load time | |
| Time to first token | |
| Prefill tokens/s | |
| Decode tokens/s | |
| Peak RSS (VmHWM) | |
| Guard fallback rate (Llama output replaced) | |

Host reference: classifier forward 0.025 ms on x86 laptop CPU (PyTorch eager); ExecuTorch runtime output
matches eager to 2×10⁻⁶.

## 6. User effectiveness — TODO

Plan: 8–10 non-technical participants (family members), 10 messages each (5 scams, 5 genuine), first
without the app, then with it. Record correct decisions, and whether they can repeat the recommended
action in their own words. Compare English and Hindi explanations.

## 7. Engineering notes

- **Parity:** the Kotlin core reproduces the Python reference exactly (shared rules JSON, FNV-1a
  feature hashing, ICU→ASCII regex normalisation), checked by `CoreParityTest` against
  `shared/test_vectors.json`.
- **Versions:** ExecuTorch 1.5.1 for both export (`pip executorch==1.5.1`) and runtime
  (`org.pytorch:executorch-android:1.5.1`).
- **Where each model runs:** both models run on the Arm CPU. The classifier is delegated to XNNPACK.
  Llama uses ExecuTorch's XNNPACK backend with INT4 weights (check whether the Maven AAR build enables Arm KleidiAI kernels; if not, a custom AAR built with `EXECUTORCH_XNNPACK_ENABLE_KLEIDI=ON` is a Phase 2 optimisation to benchmark). No NPU is used on Android.
  On Raspberry Pi 5 + AI HAT+, the classifier could move to the Hailo NPU as a separate pipeline (Phase 2).

## 8. Phase 2 roadmap

1. Cut false positives using the real inbox set (calibrated fusion weights learnt on real data).
2. Check links at click time through a local VPN/DNS service (still on-device).
3. Voice output of the advice for low-literacy users; more Indian languages.
4. Fine-tune Llama 3.2 1B (QAT+LoRA) on explanation style and Hindi quality.
5. Call-scam detection from live captions.
