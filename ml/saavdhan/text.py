"""Text normalisation, URL extraction and feature hashing.

Mirrored line-for-line by android/core/src/main/kotlin/in/saavdhan/core/TextFeatures.kt.
Any change here must be made there too; tests/test_parity.py checks shared vectors.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

NUM_BUCKETS = 65536          # embedding rows; id 0 is reserved for padding
MAX_FEATURES = 512           # fixed model input length
CHAR_NGRAMS = (3, 4)

_URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>\"']+"
    r"|\b(?:[a-z0-9-]+\.)+(?:com|in|net|org|info|xyz|top|icu|click|live|shop|online|site|buzz|vip|cyou|rest|sbs|cfd|"
    r"monster|gq|tk|ml|cf|ga|ly|cc|co|me|io|app|link|club|fun|pw|work|support|help|loan|win|bond|gl|gd|to|at|ru|ws|it|sbi)"
    r"\b(?:/[^\s<>\"']*)?",
    re.ASCII | re.IGNORECASE,
)
_TRAIL = ".,;:!?)]}'\""


def nfkc_lower(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower()


@dataclass(frozen=True)
class Url:
    raw: str
    scheme: str      # "http", "https" or "" when missing
    host: str
    path: str


def extract_urls(norm_text: str) -> list[Url]:
    out: list[Url] = []
    for m in _URL_RE.finditer(norm_text):
        start = m.start()
        if start > 0 and norm_text[start - 1] == "@":   # e-mail address, not a link
            continue
        raw = m.group(0).rstrip(_TRAIL)
        rest = raw
        scheme = ""
        if rest.startswith("http://"):
            scheme, rest = "http", rest[7:]
        elif rest.startswith("https://"):
            scheme, rest = "https", rest[8:]
        cut = len(rest)
        for ch in "/?#":
            i = rest.find(ch)
            if i != -1 and i < cut:
                cut = i
        host = rest[:cut]
        at = host.rfind("@")                 # http://sbi.co.in@evil.xyz tricks
        if at != -1:
            host = host[at + 1:]
        colon = host.find(":")
        if colon != -1:
            host = host[:colon]
        if host.startswith("www."):
            host = host[4:]
        host = host.strip(".")
        if host:
            out.append(Url(raw=raw, scheme=scheme, host=host, path=rest[cut:]))
    return out


def _is_token_char(c: str) -> bool:
    o = ord(c)
    return ("a" <= c <= "z") or ("0" <= c <= "9") or (0x0900 <= o <= 0x097F) or c == "₹"


def _digit_placeholder(n: int) -> str:
    if n <= 2:
        return "0"
    if n <= 5:
        return "00"
    if n <= 9:
        return "000"
    return "0000"


def model_tokens(text: str) -> list[str]:
    """Tokens fed to the classifier. URLs are replaced by coarse placeholder tokens."""
    norm = nfkc_lower(text)
    urls = extract_urls(norm)
    pieces: list[str] = []
    pos = 0
    for u in urls:
        i = norm.find(u.raw, pos)
        if i == -1:
            continue
        pieces.append(norm[pos:i])
        tld = u.host.rsplit(".", 1)[-1] if "." in u.host else "none"
        pieces.append(f" xurl xtld{tld} ")
        pos = i + len(u.raw)
    pieces.append(norm[pos:])
    norm = "".join(pieces)

    tokens: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            tokens.append("".join(buf))
            buf.clear()

    i = 0
    n = len(norm)
    while i < n:
        c = norm[i]
        if "0" <= c <= "9":
            j = i
            while j < n and "0" <= norm[j] <= "9":
                j += 1
            buf.append(_digit_placeholder(j - i))
            i = j
            continue
        if _is_token_char(c):
            buf.append(c)
        else:
            flush()
        i += 1
    flush()
    return tokens


def feature_strings(text: str) -> list[str]:
    toks = model_tokens(text)
    feats = [f"w:{t}" for t in toks]
    feats += [f"b:{a} {b}" for a, b in zip(toks, toks[1:])]
    for t in toks:
        padded = f"<{t}>"
        for n in CHAR_NGRAMS:
            for k in range(len(padded) - n + 1):
                feats.append(f"c:{padded[k:k + n]}")
    return feats[:MAX_FEATURES]


def fnv1a32(s: str) -> int:
    h = 0x811C9DC5
    for byte in s.encode("utf-8"):
        h ^= byte
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def feature_ids(text: str) -> list[int]:
    """Fixed-length id vector (padded with 0) for the classifier."""
    ids = [fnv1a32(f) % (NUM_BUCKETS - 1) + 1 for f in feature_strings(text)]
    return ids + [0] * (MAX_FEATURES - len(ids))
