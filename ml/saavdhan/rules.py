"""Rule engine and risk fusion. Mirrors android/core RuleEngine.kt and RiskFusion.kt."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from .text import Url, extract_urls, nfkc_lower

RULES_PATH = Path(__file__).resolve().parents[2] / "shared" / "rules.json"
_FLAGS = re.ASCII | re.IGNORECASE
_SECOND_LEVEL = {"co", "gov", "nic", "bank", "fin", "org", "net", "ac", "edu", "res", "gen", "firm", "ind"}


@dataclass(frozen=True)
class Signal:
    id: str
    category: str
    weight: float
    en: str
    hi: str
    advice: tuple[str, ...]
    detail: str = ""          # e.g. the offending domain, shown to user and Llama


@dataclass
class Verdict:
    risk: float
    level: str                # "high" | "medium" | "low"
    classifier_prob: float | None
    signals: list[Signal] = field(default_factory=list)

    @property
    def top_category(self) -> str:
        pos = [s for s in self.signals if s.weight > 0]
        return max(pos, key=lambda s: s.weight).category if pos else "none"


def registered_domain(host: str) -> str:
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in _SECOND_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


_IPV4 = re.compile(r"^[0-9]{1,3}(\.[0-9]{1,3}){3}$")


def _is_ip(host: str) -> bool:
    """Strict dotted IPv4 (kept simple so RuleEngine.kt can match it exactly)."""
    return bool(_IPV4.match(host)) and all(int(p) <= 255 for p in host.split("."))


def _ends_with_domain(host: str, suffix: str) -> bool:
    return host == suffix or host.endswith("." + suffix)


class RuleEngine:
    def __init__(self, rules_path: Path = RULES_PATH):
        cfg = json.loads(Path(rules_path).read_text(encoding="utf-8"))
        self.cfg = cfg
        self.brands = cfg["brands"]
        self.brand_words = [re.compile(r"(^|[^a-z])" + re.escape(w) + r"($|[^a-z])", _FLAGS) for w in cfg["brand_words"]]
        self.official = cfg["official_domain_suffixes"]
        self.shorteners = set(cfg["url_shorteners"])
        self.risky_tlds = set(cfg["risky_tlds"])
        self.registered_sender = re.compile(cfg["registered_sender_pattern"], _FLAGS)
        self.mobile_sender = re.compile(cfg["mobile_sender_pattern"], _FLAGS)
        self.structural = cfg["structural_signals"]
        self.keyword_rules = []
        for r in cfg["keyword_rules"]:
            pats = [re.compile(p, _FLAGS) for p in r["patterns"]]
            negs = [re.compile(r"(" + n + r")\s*$", _FLAGS) for n in r.get("negations", [])]
            self.keyword_rules.append((r, pats, negs))
        self.advice = cfg["advice"]
        self.fusion = cfg["fusion"]

    # ---- helpers -------------------------------------------------------
    def _struct(self, sid: str, detail: str = "") -> Signal:
        s = self.structural[sid]
        return Signal(sid, s["category"], s["weight"], s["en"], s["hi"], tuple(s["advice"]), detail)

    def _is_official(self, host: str) -> bool:
        return any(_ends_with_domain(host, d) for d in self.official)

    def mentions_brand(self, norm: str) -> bool:
        return any(p.search(norm) for p in self.brand_words)

    # ---- main ----------------------------------------------------------
    def signals(self, text: str, sender: str | None = None) -> list[Signal]:
        norm = nfkc_lower(text)
        out: list[Signal] = []
        urls = extract_urls(norm)
        brand = self.mentions_brand(norm)
        out += self._url_signals(urls, brand)
        out += self._sender_signals(sender, brand)
        out += self._keyword_signals(norm)
        return out

    def _url_signals(self, urls: list[Url], brand_in_text: bool) -> list[Signal]:
        out: list[Signal] = []
        if not urls:
            return out
        seen: set[str] = set()
        all_official = True
        for u in urls:
            host = u.host
            official = self._is_official(host)
            all_official &= official
            rd = registered_domain(host)
            tld = host.rsplit(".", 1)[-1]

            def add(sid: str) -> None:
                if sid not in seen:
                    seen.add(sid)
                    out.append(self._struct(sid, host))

            if official:
                continue
            if _is_ip(host):
                add("URL_IP")
            if host in self.shorteners or rd in self.shorteners:
                add("URL_SHORTENER")
            if tld in self.risky_tlds:
                add("URL_RISKY_TLD")
            if "xn--" in host:
                add("URL_PUNYCODE")
            labels = rd.replace("-", ".").split(".") + host.replace("-", ".").split(".")
            compact = host.replace("-", "").replace(".", "")
            if any(b in labels or (len(b) >= 4 and b in compact) for b in self.brands):
                add("URL_BRAND_LOOKALIKE")
            if u.scheme == "http":
                add("URL_HTTP")
            if u.path.split("?")[0].endswith(".apk"):
                add("URL_APK")
            if brand_in_text and not host.endswith("bank.in") and "URL_NOT_BANK_IN" not in seen \
                    and not (host in self.shorteners or rd in self.shorteners):
                add("URL_NOT_BANK_IN")
        if all_official:
            out.append(self._struct("URL_OFFICIAL", ", ".join(u.host for u in urls)))
        return out

    def _sender_signals(self, sender: str | None, brand_in_text: bool) -> list[Signal]:
        if not sender:
            return []
        s = sender.strip()
        compact = s.replace(" ", "").replace("-", "") if s.startswith("+") or s[:1].isdigit() else s
        if self.mobile_sender.match(compact) and brand_in_text:
            return [self._struct("SENDER_MOBILE_IMPERSONATION", s)]
        if self.registered_sender.match(s.lower()):
            return [self._struct("SENDER_REGISTERED", s)]
        return []

    def _keyword_signals(self, norm: str) -> list[Signal]:
        out: list[Signal] = []
        for r, pats, negs in self.keyword_rules:
            for p in pats:
                hit = None
                for m in p.finditer(norm):
                    window = norm[max(0, m.start() - 20):m.start()]
                    if negs and any(n.search(window) for n in negs):
                        continue
                    hit = m
                    break
                if hit:
                    out.append(Signal(r["id"], r["category"], r["weight"], r["en"], r["hi"],
                                      tuple(r["advice"]), hit.group(0)[:60]))
                    break
        return out

    # ---- fusion --------------------------------------------------------
    def fuse(self, signals: list[Signal], classifier_logit: float | None) -> Verdict:
        f = self.fusion
        if classifier_logit is None:
            base, prob = f["no_classifier_prior"], None
        else:
            clip = f["classifier_clip"]
            base = f["classifier_scale"] * max(-clip, min(clip, classifier_logit))
            prob = 1.0 / (1.0 + math.exp(-classifier_logit))
        z = base + f["bias"] + sum(s.weight for s in signals)
        risk = 1.0 / (1.0 + math.exp(-z))
        level = "high" if risk >= f["high_threshold"] else "medium" if risk >= f["medium_threshold"] else "low"
        ordered = sorted(signals, key=lambda s: -s.weight)
        return Verdict(risk=risk, level=level, classifier_prob=prob, signals=ordered)

    def analyse(self, text: str, sender: str | None = None, classifier_logit: float | None = None) -> Verdict:
        return self.fuse(self.signals(text, sender), classifier_logit)
