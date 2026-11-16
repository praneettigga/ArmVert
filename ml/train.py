"""Train the on-device scam classifier (fastText-style hashed n-gram model).

Model: hashed word/char n-gram ids -> Embedding(65536, 32) -> masked mean -> MLP -> logit.
About 2.1M parameters (8.4 MB fp32), sub-millisecond on a phone CPU via ExecuTorch/XNNPACK.

Training data: synthetic Indian templates (train split) + UCI SMS (train split).
Reported test sets (never trained on):
  synthetic_test  - synthetic messages from templates held out of training
  uci_test        - UCI SMS Spam Collection test split
  hinglish_ext    - third-party Hinglish/English scam set (bolewara, CC BY 4.0), fully held out
  real            - data/real_testset.csv if the team has collected it (the number that matters)

Usage: python train.py  (after data/generate_synthetic.py and data/download_public.py)
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from saavdhan.rules import RuleEngine
from saavdhan.text import MAX_FEATURES, NUM_BUCKETS, feature_ids

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
MODELS = ROOT / "models"


class ScamClassifier(nn.Module):
    def __init__(self, buckets: int = NUM_BUCKETS, dim: int = 32, hidden: int = 32):
        super().__init__()
        self.emb = nn.Embedding(buckets, dim, padding_idx=0)
        self.fc1 = nn.Linear(dim, hidden)
        self.fc2 = nn.Linear(hidden, 1)
        nn.init.normal_(self.emb.weight, std=0.05)
        with torch.no_grad():
            self.emb.weight[0].zero_()

    def forward(self, ids: torch.Tensor) -> torch.Tensor:          # ids: [B, MAX_FEATURES] int64
        mask = (ids != 0).to(torch.float32).unsqueeze(-1)            # [B, L, 1]
        summed = (self.emb(ids) * mask).sum(dim=1)                   # [B, D]
        count = mask.sum(dim=1).clamp(min=1.0)                       # [B, 1]
        h = torch.relu(self.fc1(summed / count))
        return self.fc2(h)                                           # [B, 1] logit


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["label"] = int(r["label"])
        r.setdefault("sender", "")
    return rows


def encode(rows: list[dict]) -> torch.Tensor:
    return torch.tensor([feature_ids(r["text"]) for r in rows], dtype=torch.int64)


def metrics(y: np.ndarray, p: np.ndarray, thr: float = 0.5) -> dict:
    pred = (p >= thr).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum()); tn = int(((pred == 0) & (y == 0)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    auc = float("nan")
    if 0 < y.sum() < len(y):
        order = np.argsort(p)
        ranks = np.empty(len(p)); ranks[order] = np.arange(1, len(p) + 1)
        npos = y.sum(); nneg = len(y) - npos
        auc = (ranks[y == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg)
    return {"n": int(len(y)), "precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4),
            "false_positive_rate": round(fpr, 4), "auc": round(float(auc), 4), "tp": tp, "fp": fp, "fn": fn, "tn": tn}


@torch.no_grad()
def predict_logits(model: nn.Module, X: torch.Tensor) -> np.ndarray:
    model.eval()
    return torch.cat([model(X[i:i + 512]) for i in range(0, len(X), 512)]).squeeze(-1).numpy()


def evaluate_all(model: nn.Module, engine: RuleEngine, sets: dict[str, list[dict]]) -> dict:
    report = {}
    for name, rows in sets.items():
        if not rows:
            continue
        y = np.array([r["label"] for r in rows])
        logits = predict_logits(model, encode(rows))
        p_clf = 1 / (1 + np.exp(-logits))
        p_rules = np.array([engine.analyse(r["text"], r["sender"] or None, None).risk for r in rows])
        p_fused = np.array([engine.analyse(r["text"], r["sender"] or None, float(l)).risk for r, l in zip(rows, logits)])
        report[name] = {"classifier": metrics(y, p_clf), "rules_only": metrics(y, p_rules), "fused": metrics(y, p_fused)}
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--lr", type=float, default=3e-3)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--seed", type=int, default=13)
    a = ap.parse_args()
    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)

    synth = load_csv(DATA / "synthetic.csv")
    public = load_csv(DATA / "public" / "public.csv")
    if not synth or not public:
        raise SystemExit("Run data/generate_synthetic.py and data/download_public.py first.")
    uci = [r for r in public if r["source"] == "uci"]
    hinglish = [r for r in public if r["source"] == "hf_hinglish"]
    train = [r for r in synth if r["split"] == "train"] + [r for r in uci if r["split"] == "train"]
    val = [r for r in synth if r["split"] == "val"] + [r for r in uci if r["split"] == "val"]
    tests = {
        "synthetic_test": [r for r in synth if r["split"] == "test"],
        "uci_test": [r for r in uci if r["split"] == "test"],
        "hinglish_ext": hinglish,
        "challenge": load_csv(DATA / "challenge_set.csv"),
        "real": load_csv(DATA / "real_testset.csv"),
    }
    print(f"train {len(train)}  val {len(val)}  " + "  ".join(f"{k} {len(v)}" for k, v in tests.items()))

    Xtr, ytr = encode(train), torch.tensor([r["label"] for r in train], dtype=torch.float32)
    Xva, yva = encode(val), np.array([r["label"] for r in val])
    pos = ytr.mean().item()
    model = ScamClassifier()
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
    lossf = nn.BCEWithLogitsLoss(pos_weight=torch.tensor((1 - pos) / pos))
    best, best_state = -1.0, None
    for ep in range(a.epochs):
        model.train()
        perm = torch.randperm(len(Xtr))
        tot = 0.0
        for i in range(0, len(perm), a.batch):
            idx = perm[i:i + a.batch]
            xb = Xtr[idx]
            # feature dropout: randomly blank 25% of ids so the model can't rely on one n-gram
            xb = xb * (torch.rand(xb.shape) > 0.25)
            loss = lossf(model(xb).squeeze(-1), ytr[idx])
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item() * len(idx)
        pv = 1 / (1 + np.exp(-predict_logits(model, Xva)))
        m = metrics(yva, pv)
        print(f"epoch {ep + 1}: loss {tot / len(Xtr):.4f}  val f1 {m['f1']:.4f}  val fpr {m['false_positive_rate']:.4f}")
        if m["f1"] > best:
            best, best_state = m["f1"], {k: v.clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)

    engine = RuleEngine()
    report = evaluate_all(model, engine, tests)

    # latency of the PyTorch model on this machine (phone numbers come from the app's benchmark screen)
    x1 = encode([{"text": "Dear customer your SBI account will be blocked, update KYC now bit.ly/x"}])
    model.eval()
    with torch.no_grad():
        for _ in range(20):
            model(x1)
        t0 = time.perf_counter()
        for _ in range(200):
            model(x1)
    report["host_latency_ms"] = round((time.perf_counter() - t0) / 200 * 1000, 3)
    report["params"] = sum(p.numel() for p in model.parameters())

    MODELS.mkdir(exist_ok=True)
    torch.save(model.state_dict(), MODELS / "classifier.pt")
    (MODELS / "classifier_meta.json").write_text(json.dumps(
        {"buckets": NUM_BUCKETS, "max_features": MAX_FEATURES, "dim": 32, "hidden": 32, "hash": "fnv1a32",
         "train_rows": len(train), "seed": a.seed}, indent=2))
    (MODELS / "eval_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print("\n%-15s %-11s %6s %6s %6s %6s %6s" % ("set", "model", "prec", "rec", "f1", "fpr", "auc"))
    for name, r in report.items():
        if not isinstance(r, dict):
            continue
        for kind in ("rules_only", "classifier", "fused"):
            m = r[kind]
            print("%-15s %-11s %6.3f %6.3f %6.3f %6.3f %6.3f" % (name, kind, m["precision"], m["recall"], m["f1"],
                                                                m["false_positive_rate"], m["auc"]))
    print(f"\nparams {report['params']:,}  host latency {report['host_latency_ms']} ms  -> models/")


if __name__ == "__main__":
    main()
