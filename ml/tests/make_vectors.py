"""Write shared/test_vectors.json: expected feature ids, rule signals and risk for sample
messages. The Kotlin core test (android/core) must reproduce these exactly."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from saavdhan.rules import RuleEngine  # noqa: E402
from saavdhan.text import extract_urls, feature_ids, feature_strings, fnv1a32, model_tokens, nfkc_lower  # noqa: E402

CASES = [
    ("Dear customer your SBI account will be blocked today. Update KYC immediately: http://sbi-kyc-update.xyz/login", "9876543210", 6.0),
    ("482913 is your OTP for txn of Rs 2,500 at AMAZON. Do not share this OTP with anyone. - HDFC Bank", "AX-HDFCBK-S", -4.0),
    ("Dear consumer your electricity power will be disconnected tonight at 9:30 pm. Please call electricity officer 9123456780", "+91 9123456780", None),
    ("Congratulations! You won Rs 25 lakh in KBC lucky draw. Claim: bit.ly/kbc-claim", "8899001122", None),
    ("Aapka traffic challan pending hai. RTO Challan.apk download kare turant", None, None),
    ("bhai kal 5 baje milte hai, cricket khelne chalenge?", "9812345678", -8.0),
    ("Rs.500 credited to your a/c XX1234 by UPI ref 4321. If not done by you call bank. https://www.icicibank.com/x", "JD-ICICIT-S", None),
    ("Enter your UPI PIN to receive Rs 2000 cashback from PhonePe", None, 1.5),
    ("आपका खाता आज बंद हो जाएगा। तुरंत केवाईसी अपडेट करें", None, -2.6),
    ("आपको PhonePe से ₹500 कैशबैक मिला है। पैसे पाने के लिए अपना पिन डालें।", None, None),
    ("Do not share your OTP with anyone. SBI never asks for PIN.", "VM-SBIINB-T", None),
    ("Visit http://sbi.co.in@203.0.113.9/login now, account suspended!!", "+447700900123", None),
    ("Install AnyDesk so our customer care can process your refund", "9000000001", None),
    ("Hi mum this is my new number, I lost my phone", None, None),
    ("Mail me at someone@gmail.com tomorrow", None, None),
    ("ＦＵＬＬＷＩＤＴＨ ＴＥＸＴ ＫＹＣ update ₹１０００", None, None),
]


def all_cases() -> list:
    import csv
    root = Path(__file__).resolve().parents[1] / "data"
    cases = list(CASES)
    for f in [root / "challenge_set.csv", root / "public" / "public.csv"]:
        if f.exists():
            for r in csv.DictReader(f.open(encoding="utf-8")):
                if f.name == "challenge_set.csv" or r["source"] == "hf_hinglish":
                    cases.append((r["text"], r["sender"] or None, None))
    return cases


def main() -> None:
    eng = RuleEngine()
    out = []
    for text, sender, logit in all_cases():
        v = eng.analyse(text, sender, logit)
        out.append({
            "text": text, "sender": sender, "classifier_logit": logit,
            "normalized": nfkc_lower(text),
            "urls": [{"host": u.host, "scheme": u.scheme, "path": u.path} for u in extract_urls(nfkc_lower(text))],
            "tokens": model_tokens(text),
            "num_features": len(feature_strings(text)),
            "feature_ids": feature_ids(text),
            "signals": [s.id for s in v.signals],
            "risk": round(v.risk, 6), "level": v.level,
        })
    hashes = {s: fnv1a32(s) for s in ["", "a", "w:kyc", "c:<ky", "b:your account", "w:खाता", "c:₹00"]}
    path = Path(__file__).resolve().parents[2] / "shared" / "test_vectors.json"
    path.write_text(json.dumps({"fnv1a32": hashes, "cases": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {len(out)} cases to {path}")


if __name__ == "__main__":
    main()
