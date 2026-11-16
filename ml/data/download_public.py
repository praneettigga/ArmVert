"""Download public datasets into data/public/ and normalise them to one CSV.

- UCI SMS Spam Collection (CC BY 4.0): English, UK/Singapore, 2011. "spam" is mostly
  promotional spam, not fraud, so it is down-weighted during training.
- bolewara/hinglish-scam-text-dataset (CC BY 4.0, Hugging Face): English + a few
  Hinglish financial-scam examples, largely derived from UCI.

Output: data/public/public.csv with columns text,sender,label,category,lang,template,split,source
"""
from __future__ import annotations

import csv
import io
import json
import random
import urllib.request
import zipfile
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "public"
UCI_URL = "https://archive.ics.uci.edu/static/public/228/sms+spam+collection.zip"
HINGLISH_URL = "https://huggingface.co/datasets/bolewara/hinglish-scam-text-dataset/resolve/main/data.json"


def fetch(url: str, dest: Path) -> bytes:
    if dest.exists():
        return dest.read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": "dataset-downloader/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    dest.write_bytes(data)
    return data


def split_for(i: int, r: random.Random) -> str:
    x = r.random()
    return "test" if x < 0.15 else "val" if x < 0.25 else "train"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    r = random.Random(11)
    rows: list[dict] = []

    z = zipfile.ZipFile(io.BytesIO(fetch(UCI_URL, OUT_DIR / "uci_sms.zip")))
    raw = z.read("SMSSpamCollection").decode("utf-8", "replace")
    for i, line in enumerate(raw.splitlines()):
        if "\t" not in line:
            continue
        lab, text = line.split("\t", 1)
        rows.append({"text": text, "sender": "", "label": int(lab == "spam"), "category": "uci_" + lab,
                     "lang": "en", "template": "", "split": split_for(i, r), "source": "uci"})

    try:
        data = json.loads(fetch(HINGLISH_URL, OUT_DIR / "hinglish_scam.json"))
        items = data if isinstance(data, list) else (data.get("rows") or data.get("data") or [])
        uci_texts = {x["text"].strip().lower() for x in rows}
        added = 0
        for i, it in enumerate(items):
            text = str(it.get("text") or it.get("message") or "").strip()
            lab = it.get("label")
            if not text or lab is None or text.lower() in uci_texts:
                continue          # skip rows that are copies of UCI
            label = int(str(lab).lower() in ("1", "scam", "spam", "fraud"))
            rows.append({"text": text, "sender": "", "label": label, "category": "hf_hinglish",
                         "lang": it.get("language", "mixed"), "template": "", "split": split_for(i, r), "source": "hf_hinglish"})
            added += 1
        print(f"hinglish dataset: added {added} non-UCI rows")
    except Exception as e:  # dataset is optional
        print("skipping hinglish dataset:", e)

    out = OUT_DIR / "public.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
