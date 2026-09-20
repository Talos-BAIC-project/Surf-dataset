"""Label 注册表与查询文本解析（无 LLM，纯词表 + 规则）。

上游（dfc-language-harness）产出标准 label_id + selector；
本模块兼容两种输入：
1. 结构化：label_id（dfc.substructure.*）+ Selector；
2. 自由文本：工程师原话（"中间两道筋" / "chamber_2" / "第二个腔"）。
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import PROJECT_ROOT

LABELS_CONFIG = PROJECT_ROOT / "configs" / "labels.yaml"

_LETTER_ORDINAL = {c: i + 1 for i, c in enumerate("abcdefgh")}


@dataclass
class LabelProfile:
    label_id: str
    caption_zh: str
    caption_en: str
    entity_type: str                    # face | curve
    functions: list[str] = field(default_factory=list)
    name_patterns: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)

    @property
    def short(self) -> str:
        return self.label_id.rsplit(".", 1)[-1]


@dataclass
class Selector:
    """查询限定：第几个 / 期望数量 / 相对位置。"""
    ordinal: int | None = None
    count: int | None = None
    position: str | None = None         # center/top/bottom/left/right

    def is_empty(self) -> bool:
        return self.ordinal is None and self.count is None and self.position is None


@dataclass
class ResolvedQuery:
    profile: LabelProfile
    selector: Selector
    matched_alias: str
    evidence: str                       # exact_label_id / region_name / exact_alias / fuzzy_alias
    score: float                        # 文本匹配置信度 0..1


class LabelRegistry:
    def __init__(self, profiles: list[LabelProfile], position_words: dict[str, list[str]],
                 ordinal_words: dict[int, list[str]]):
        self.profiles = profiles
        self.by_id = {p.label_id: p for p in profiles}
        self.by_short = {p.short: p for p in profiles}
        self.position_words = position_words
        self.ordinal_words = ordinal_words
        self._alias_index: list[tuple[str, LabelProfile]] = []
        for p in profiles:
            for alias in [*p.aliases, p.caption_zh, p.caption_en, p.short]:
                self._alias_index.append((alias.lower(), p))
        # 长别名优先匹配（避免"外轮廓"命中"轮廓"前先命中"廓"之类的短词）
        self._alias_index.sort(key=lambda kv: -len(kv[0]))

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: Path | None = None) -> "LabelRegistry":
        data = yaml.safe_load((path or LABELS_CONFIG).read_text(encoding="utf-8"))
        profiles = [
            LabelProfile(
                label_id=item["label_id"],
                caption_zh=item.get("caption_zh", ""),
                caption_en=item.get("caption_en", ""),
                entity_type=item.get("entity_type", "curve"),
                functions=item.get("functions") or [],
                name_patterns=item.get("name_patterns") or [],
                aliases=item.get("aliases") or [],
            )
            for item in data.get("labels", [])
        ]
        return cls(
            profiles,
            {k: list(v) for k, v in (data.get("position_words") or {}).items()},
            {int(k): list(v) for k, v in (data.get("ordinal_words") or {}).items()},
        )

    # ------------------------------------------------------------------
    def profile_for_function(self, function: str) -> LabelProfile | None:
        for p in self.profiles:
            if function in p.functions:
                return p
        return None

    def profile_for_region_name(self, name: str) -> LabelProfile | None:
        low = name.lower()
        for p in self.profiles:
            for pat in p.name_patterns:
                if low.startswith(pat):
                    return p
        return None

    # ------------------------------------------------------------------
    def parse_selector(self, text: str) -> Selector:
        sel = Selector()
        low = text.lower()
        # region 风格后缀：chamber_2 / stiffener_a / 第2腔
        m = re.search(r"[_\-\s](\d+)\b", low)
        if m:
            sel.ordinal = int(m.group(1))
        else:
            m = re.search(r"[_\-\s]([a-h])\b", low)
            if m:
                sel.ordinal = _LETTER_ORDINAL[m.group(1)]
        if sel.ordinal is None:
            for k, words in self.ordinal_words.items():
                if any(w.lower() in low for w in words):
                    sel.ordinal = k
                    break
        # 数量："两道/两条/2根/3个"
        m = re.search(r"([一两二三四五六七八九\d]+)\s*[道条根个处段]", text)
        if m:
            token = m.group(1)
            zh_num = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
            sel.count = zh_num.get(token) or (int(token) if token.isdigit() else None)
        for pos, words in self.position_words.items():
            if any(w.lower() in low for w in words):
                sel.position = pos
                break
        return sel

    # ------------------------------------------------------------------
    def resolve(self, query: str) -> ResolvedQuery | None:
        """自由文本 / label_id / region 名 -> LabelProfile + Selector。"""
        text = query.strip()
        low = text.lower()
        selector = self.parse_selector(text)

        # 1. 标准 label_id
        if low in self.by_id:
            return ResolvedQuery(self.by_id[low], selector, low, "exact_label_id", 1.0)
        # 2. region 名风格（chamber_2 / stiffener_a / main_wall_b）
        base = re.sub(r"[_\-\s]*([a-h]|\d+)$", "", low).strip("_- ")
        p = self.profile_for_region_name(base) or self.by_short.get(base)
        if p is not None:
            return ResolvedQuery(p, selector, base, "region_name", 1.0)
        # 3. 别名包含匹配（长词优先）
        for alias, prof in self._alias_index:
            if alias and alias in low:
                return ResolvedQuery(prof, selector, alias, "exact_alias", 0.95)
        # 4. 模糊匹配（difflib）
        aliases = [a for a, _ in self._alias_index]
        got = difflib.get_close_matches(low, aliases, n=1, cutoff=0.6)
        if got:
            prof = next(pr for a, pr in self._alias_index if a == got[0])
            ratio = difflib.SequenceMatcher(None, low, got[0]).ratio()
            return ResolvedQuery(prof, selector, got[0], "fuzzy_alias", round(0.5 + 0.4 * ratio, 3))
        return None
