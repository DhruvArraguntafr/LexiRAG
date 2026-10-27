import re
from dataclasses import dataclass

from core.models import GroundedAnswer


def normalize(text):
    return " ".join(text.split())


@dataclass(frozen=True)
class QuoteMatch:
    start: int
    end: int
    text: str


_TYPOGRAPHY = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
    "…": "...", "\u00ad": "",
})
_PUNCTUATION = set(".,;:!?()[]{}\"'-")


def _quote_form(text, dehyphenate=False):
    """Canonical typography with a reversible map to original source offsets.

    Word separators, punctuation symbols, digits and letter identities remain.
    No edit-distance matching, spelling repair, case folding or O/0 substitution.
    """
    ignored = set()
    if dehyphenate:
        # Only long alphabetic words broken across an actual source newline.
        # Numeric ranges and short prefixes such as re-/e- are not dehyphenated.
        for m in re.finditer(r"[^\W\d_]{3,}([-‐])[ \t]*\r?\n[ \t]*(?=[^\W\d_]{3,})", text):
            ignored.update(range(m.start(1), m.end()))
    chars, spans = [], []
    for index, char in enumerate(text):
        if index in ignored:
            continue
        for value in char.translate(_TYPOGRAPHY):
            value = " " if value.isspace() else value
            if value == " " and (not chars or chars[-1] == " "):
                continue
            chars.append(value)
            spans.append((index, index + 1))
    # A space around punctuation is layout, not a missing word. Spaces between
    # letters remain significant ("nowhere" must not match "now here").
    keep = [i for i,c in enumerate(chars) if c != " " or (
        i > 0 and i + 1 < len(chars) and chars[i-1] not in _PUNCTUATION and chars[i+1] not in _PUNCTUATION)]
    return "".join(chars[i] for i in keep), [spans[i] for i in keep]


def match_quote(quote, text):
    """Match within ONE supplied passage; return the exact original substring."""
    if len(quote.strip()) < 12 or not any(c.isalnum() for c in quote):
        return None
    for wrapped in (False, True):
        needle, _ = _quote_form(quote, wrapped)
        haystack, offsets = _quote_form(text, wrapped)
        position = haystack.find(needle) if needle else -1
        while position >= 0:
            stop = position + len(needle)
            if (needle[0].isalnum() and position and haystack[position - 1].isalnum()) or (
                needle[-1].isdigit() and stop < len(haystack) and haystack[stop].isalnum()) or (
                needle[0].isdigit() and position and haystack[position - 1] in "+-−"):
                position = haystack.find(needle, position + 1)
                continue
            if (position and offsets[position - 1][0] == offsets[position][0]) or (stop < len(offsets) and offsets[stop - 1][0] == offsets[stop][0]):
                position = haystack.find(needle, position + 1)
                continue
            start, end = offsets[position][0], offsets[position + len(needle) - 1][1]
            return QuoteMatch(start, end, text[start:end])
    return None


def verify_ref(ref, sources):
    source = sources.get(ref.source_id)
    return source is not None and match_quote(ref.quote, source.chunk.text) is not None


def validate_answer(answer: GroundedAnswer, sources):
    """Fail closed: remove a whole finding if any cited ID/quote is invalid.

This validates provenance and verbatim quotation, not semantic entailment.
The latter remains subject to Ragas and human review.
"""
    kept, invalid, attempts, valid = [], 0, 0, 0
    for finding in answer.findings:
        matches = [match_quote(ref.quote, sources[ref.source_id].chunk.text) if ref.source_id in sources else None for ref in finding.evidence]
        checks = [match is not None for match in matches]
        attempts += len(checks)
        valid += sum(checks)
        # Inline model-written source markers are disallowed: only the validated
        # evidence references are rendered as citations.
        inline = re.search(r"\[(?:S\d+|\d+)\]", finding.statement)
        if checks and all(checks) and not inline:
            # Display/save the original OCR spelling and punctuation, so every
            # accepted citation remains an exact stored-passage quotation.
            refs = [ref.model_copy(update={"quote": match.text}) for ref,match in zip(finding.evidence, matches)]
            kept.append(finding.model_copy(update={"evidence": refs}))
        else:
            invalid += 1
    limitations = list(answer.limitations)
    if invalid:
        limitations.append(f"{invalid} finding(s) were withheld because source validation failed.")
    if not kept:
        limitations.append("The uploaded documents do not contain enough verifiable evidence to answer this question.")
    return GroundedAnswer(insufficient_evidence=answer.insufficient_evidence or not kept,
                          findings=kept, limitations=list(dict.fromkeys(limitations))), attempts, valid


def citation_label(source_id, hit):
    chunk = hit.chunk
    suffix = f" · {chunk.locator}" if chunk.locator else ""
    return f"[{source_id}] {chunk.document_name} · PDF page {chunk.page}{suffix}"

