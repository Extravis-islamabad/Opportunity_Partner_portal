"""
Customer-name normalization for duplicate detection.

Used by:
  - opportunity_service when writing/updating opportunities
  - duplicate_service when querying for matches
  - The 008 alembic migration to backfill existing rows

The exact algorithm MUST match the inline copy in
backend/alembic/versions/008_duplicate_prevention.py — if you change one,
change both, otherwise existing data won't match new lookups.
"""
import re
from typing import Optional
from urllib.parse import urlparse

# Common company suffixes stripped during normalization. Lowercase, no
# punctuation. "the" is included because it's noise at the start of names.
COMPANY_SUFFIXES = {
    # English
    "inc", "incorporated", "corp", "corporation", "co",
    "ltd", "limited", "llc", "llp", "lp", "plc",
    # European
    "gmbh", "ag", "sa", "sas", "srl", "spa", "bv", "nv", "ab", "as",
    # Asian / Pacific
    "pty", "pte", "pvt", "private",
    # Generic
    "company", "group", "holdings", "international", "intl",
    "the",
}

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def normalize_customer_name(name: Optional[str]) -> str:
    """Normalize a customer name for duplicate matching.

    Steps:
      1. Lowercase + strip
      2. Replace all punctuation with spaces
      3. Drop tokens in COMPANY_SUFFIXES
      4. Collapse whitespace

    Examples:
      "Atlas Manufacturing Inc."   -> "atlas manufacturing"
      "ATLAS MFG, LLC"             -> "atlas mfg"
      "The Atlas Company"          -> "atlas"
      "Atlas Mfg GmbH & Co. KG"    -> "atlas mfg kg"
    """
    if not name:
        return ""
    n = name.lower().strip()
    n = _PUNCT_RE.sub(" ", n)
    tokens = [t for t in _WS_RE.split(n) if t and t not in COMPANY_SUFFIXES]
    return " ".join(tokens)


# --- Domain extraction -----------------------------------------------------

_DOMAIN_RE = re.compile(r"\b((?:[a-z0-9-]+\.)+[a-z]{2,})\b", re.IGNORECASE)


def extract_domain(value: Optional[str]) -> Optional[str]:
    """Extract a likely domain from a free-text field (URL, email, plain text).

    Returns the apex domain in lowercase, or None if nothing recognizable
    is found. Used to auto-fill `Opportunity.customer_domain` from the
    contact email or website URL the partner provides.
    """
    if not value:
        return None
    text = value.strip().lower()

    # If it looks like an email, take the part after @
    if "@" in text:
        try:
            domain = text.split("@", 1)[1]
            return _strip_www(domain.split()[0]) if domain else None
        except IndexError:
            return None

    # If it looks like a URL, parse it
    if text.startswith(("http://", "https://", "//")):
        try:
            parsed = urlparse(text)
            if parsed.netloc:
                return _strip_www(parsed.netloc)
        except Exception:
            return None

    # Otherwise scan for a domain-like substring
    match = _DOMAIN_RE.search(text)
    if match:
        return _strip_www(match.group(1))
    return None


def _strip_www(domain: str) -> str:
    return domain[4:] if domain.startswith("www.") else domain
