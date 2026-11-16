"""Export the trained classifier to an ExecuTorch .pte (XNNPACK delegate for Arm CPUs).

Usage: python export_executorch.py
Output: models/scam_classifier.pte (+ copied into android/app/src/main/assets/)

Also verifies that the ExecuTorch runtime output matches eager PyTorch on sample inputs.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import torch
from executorch.backends.xnnpack.partition.xnnpack_partitioner import XnnpackPartitioner
from executorch.exir import to_edge_transform_and_lower
from executorch.runtime import Runtime

from saavdhan.text import MAX_FEATURES, feature_ids
from train import ScamClassifier

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"
ASSETS = ROOT.parent / "android" / "app" / "src" / "main" / "assets"

SAMPLES = [
    "Dear customer your SBI account will be blocked today. Update KYC immediately http://sbi-kyc.xyz",
    "482913 is your OTP for txn of Rs 2,500 at Amazon. Do not share this OTP with anyone. - HDFC Bank",
    "bhai kal 5 baje milte hai, cricket khelne chalenge?",
    "आपका खाता आज बंद हो जाएगा। तुरंत केवाईसी अपडेट करें",
]


def main() -> None:
    model = ScamClassifier()
    model.load_state_dict(torch.load(MODELS / "classifier.pt"))
    model.eval()
    example = (torch.tensor([feature_ids(SAMPLES[0])], dtype=torch.int64),)
    assert example[0].shape == (1, MAX_FEATURES)

    exported = torch.export.export(model, example)
    program = to_edge_transform_and_lower(exported, partitioner=[XnnpackPartitioner()]).to_executorch()
    out = MODELS / "scam_classifier.pte"
    out.write_bytes(program.buffer)
    print(f"wrote {out} ({out.stat().st_size / 1e6:.2f} MB)")

    # verify runtime parity with eager PyTorch
    method = Runtime.get().load_program(out).load_method("forward")
    worst = 0.0
    vectors = []
    for s in SAMPLES:
        x = torch.tensor([feature_ids(s)], dtype=torch.int64)
        eager = model(x).item()
        et = method.execute([x])[0].item()
        worst = max(worst, abs(eager - et))
        vectors.append({"text": s, "logit": round(eager, 5)})
        print(f"eager {eager:+.4f}  executorch {et:+.4f}  | {s[:50]}")
    assert worst < 1e-3, f"runtime mismatch {worst}"
    print(f"max |eager - executorch| = {worst:.2e}")

    (MODELS / "classifier_vectors.json").write_text(json.dumps(vectors, ensure_ascii=False, indent=2))
    ASSETS.mkdir(parents=True, exist_ok=True)
    shutil.copy(out, ASSETS / "scam_classifier.pte")
    print(f"copied to {ASSETS / 'scam_classifier.pte'}")


if __name__ == "__main__":
    main()
