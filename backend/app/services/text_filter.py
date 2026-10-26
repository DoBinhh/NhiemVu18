"""Logic match từ viết tắt — mirror đúng hành vi bên frontend."""
import re
from typing import Optional


_HAS_LINK = re.compile(r"https?://|www\.", re.IGNORECASE)


def build_regex(words: list[str], mode: str = "word") -> Optional[re.Pattern]:
    """
    'word' → chỉ khớp khi từ đứng biệt lập (ngta, m, cx, ...).
             Tránh 'm' khớp trong 'mày', 'làm', 'mua'.
    'part' → khớp một phần (dùng khi muốn tìm cả trong hashtag, biến thể).
    Từ dài ưu tiên trước để alternation không bắt nhầm.
    """
    if not words:
        return None
    ordered = sorted({w.strip() for w in words if w.strip()}, key=len, reverse=True)
    if not ordered:
        return None
    alternation = "|".join(re.escape(w) for w in ordered)
    pattern = rf"(?<!\w)({alternation})(?!\w)" if mode == "word" else f"({alternation})"
    return re.compile(pattern, re.IGNORECASE | re.UNICODE)


def find_words(text: str, regex: Optional[re.Pattern]) -> list[str]:
    if regex is None or not text:
        return []
    return list({m.group(0).lower() for m in regex.finditer(text)})


def has_link(text: str) -> bool:
    return bool(_HAS_LINK.search(text or ""))