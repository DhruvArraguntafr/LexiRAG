"""Conservative legal structure recognition, also usable on legacy chunks.

No text or IDs are rewritten. Parent numbers are carried between PDF pages;
page-local text remains the citation authority. Numbered judgment paragraphs
are never silently classified as sections of an Act.
"""
from collections import defaultdict
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
import re

from core.citation_manager import normalize

NUMBER = r"\d{1,4}[A-Za-z]?(?:\s*\(\s*[\da-zivx]+\s*\))*"
REFERENCES = re.compile(r"(?i)\b(section|sec\.?|s\.|rule|r\.|article|art\.?)\s*(" + NUMBER + r")")
EXPLICIT = re.compile(r"(?im)^\s*(section|rule|article|clause|paragraph|para\.?)\s+(" + NUMBER + r")[.:\s—-]*([^\n]*)")
BARE = re.compile(r"(?m)^[ \t]*(?:[A-Z][A-Za-z ,/-]{0,60}\.?[ \t]+)?(\d{1,3}[A-Za-z]?)[ \t]*\.[ \t]*(?=[^\d\s.])")
SUB = re.compile(r"(?m)^[ \t]*\((\d+[A-Za-z]?)\)[ \t]*(?=\S)")
STOP = set("a an the is are was were what which who how many much one two three four five six seven eight nine ten eleven twelve all under of in and or to for by from this that these those explain simple language cite relevant section sections act article rule please give list tell me about does do with as them their provisions provide citations citation uploaded documents document sources source pdf".split())


def canonical(kind, number):
    kind = {"sec": "section", "s": "section", "r": "rule", "art": "article", "para": "paragraph"}.get(kind.lower().rstrip("."), kind.lower())
    return kind + ":" + re.sub(r"\s", "", number).lower()


def references(text):
    return list(dict.fromkeys(canonical(m[1], m[2]) for m in REFERENCES.finditer(text)))


def display(reference):
    kind, number = reference.split(":", 1)
    return kind.title() + " " + number


def query_variants(question):
    # Remove task boilerplate and statute titles, without inventing an answer.
    focal = re.sub(r"(?i)\bunder\s+(?:the\s+)?[^?\n]{0,160}?\b(?:act|rules|regulations|code|constitution|order)\b(?:,?\s*\d{4})?", " ", question)
    terms = [t for t in re.findall(r"[\w'-]+", focal.lower()) if t not in STOP]
    concise = " ".join(dict.fromkeys(terms))[:1500]
    variants = [concise, " ".join(display(r) for r in references(question))]
    if re.search(r"(?i)\b(define|definition|meaning)\b", question):
        variants.append(concise + " definition")
    return list(dict.fromkeys(q for q in variants if q.strip()))


def asks_definition_of(question, term):
    """'What is a consumer?' differs from 'What is the time limit ... consumer'."""
    escaped = re.escape(term).replace(r"\ ", r"\s+")
    return bool(re.search(
        r"(?i)\b(?:define\s+|(?:definition|meaning)\s+of\s+|what\s+is\s+(?:meant\s+by\s+)?)"
        r"(?:(?:a|an|the)\s+)?[\"“']?" + escaped + r"[\"”']?(?=\s*(?:[?.,;:]|$)|\s+(?:under|in)\b)", question))


def named_documents(question, documents):
    """Prefer explicitly named files without relaxing or narrowing filters."""
    words = set(re.findall(r"\w+", question.casefold()))
    matches = set()
    for document in documents:
        title = re.sub(r"(?i)\.pdf$", "", document["name"])
        terms = {t for t in re.findall(r"[^\W_]+", title.casefold()) if t not in {"the", "of", "and"}}
        # A generic file named 'Act.pdf' must not match every legal question.
        if len(terms) >= 3 and terms <= words:
            matches.add(document["id"])
    return matches


@dataclass
class Span:
    start: int
    end: int
    reference: str | None
    heading: str = ""


class SectionTracker:
    def __init__(self, kind=None):
        self.kind, self.parent, self.child = kind, None, None

    def spans(self, text):
        if self.kind is None and re.search(r"(?i)\b(?:in this act|be it enacted)\b", text):
            self.kind = "section"
        if self.kind is None and re.search(r"(?i)\b(?:these rules|following rules)\b", text):
            self.kind = "rule"
        events = []
        for m in EXPLICIT.finditer(text):
            # 'Section 101 of the Act...' is a reference, not a heading.
            if re.match(r"(?i)(of|under|referred)\b", m[3].strip()):
                continue
            ref = canonical(m[1], m[2])
            events.append((m.start(), "parent", ref, m[3].strip()))
        for m in BARE.finditer(text):
            if re.match(r"(?i)(?:subs\.|ins\.|omitted|substituted|added|amended|see\b|vide\b)", text[m.end():]):
                continue  # Amendment footnotes must not reset the parent section.
            if not any(start <= m.start() < start + 30 for start, *_ in events):
                events.append((m.start(), "parent", canonical(self.kind or "paragraph", m[1]), ""))
        for m in SUB.finditer(text):
            events.append((m.start(), "child", m[1], ""))
        events.sort(key=lambda e: (e[0], e[1]))
        spans, start, heading = [], 0, ""
        for position, event, value, title in events:
            reference = self.parent + (f"({self.child})" if self.child else "") if self.parent else None
            if position > start:
                spans.append(Span(start, position, reference, heading))
            if event == "parent":
                # Explicit headings can themselves contain e.g. Section 2(9).
                self.parent, self.child = value, None
            elif self.parent:
                # Arabic numbered subclauses; roman/alphabetic list items stay
                # attached to their numbered parent, including across pages.
                root = self.parent.split("(")[0]
                self.parent, self.child = root, value
            start = position
            first_line = text[position:].split("\n", 1)[0].strip()
            quoted = re.search(r'["“]([^"”]{2,90})["”]', first_line)
            heading = quoted[1] if quoted else title
        reference = self.parent + (f"({self.child})" if self.child else "") if self.parent else None
        if start < len(text):
            spans.append(Span(start, len(text), reference, heading))
        return spans


class LegalIndex:
    """Map actual existing chunk IDs to verified page-local structure."""
    def __init__(self, database, chunks):
        self.by_reference, self.labels, self.headings = defaultdict(list), defaultdict(set), defaultdict(list)
        self.chunks = {c.id: c for c in chunks}
        grouped = defaultdict(list)
        for chunk in chunks:
            grouped[chunk.document_id].append(chunk)
        for doc_id, doc_chunks in grouped.items():
            doc = database.document(doc_id)
            kind = "rule" if re.search(r"(?i)\brules?\b", doc["name"]) else "section" if doc["document_type"] == "Act / Statute" else None
            tracker = SectionTracker(kind)
            pages = defaultdict(list)
            for chunk in doc_chunks:
                pages[chunk.page].append(chunk)
            if any(database.page(doc_id, number) is None for number in pages):
                from core.legacy_pages import restore_page_records
                restore_page_records(database, doc_id)
            for number, page_chunks in sorted(pages.items()):
                detail = database.page(doc_id, number)
                # Old v1 imports might not have page records; do not reconstruct
                # false offsets by concatenating overlapping chunk text.
                if not detail:
                    for chunk in page_chunks:
                        for ref in references(chunk.locator or ""):
                            self._attach(ref, chunk.id)
                    continue
                text = detail["text"]
                flat = normalize(text)
                spans = tracker.spans(text)
                positions = {}
                for chunk in page_chunks:
                    needle = normalize(chunk.text)
                    offset, length = flat.find(needle), len(needle)
                    if offset < 0:
                        # Legacy OCR may differ in punctuation. Only a long
                        # exact anchor on this page can supply structure.
                        match = SequenceMatcher(None, flat, needle, autojunk=False).find_longest_match()
                        if match.size >= max(60, len(needle) * 0.35):
                            offset, length = match.a, match.size
                    positions[chunk.id] = offset, length
                for span in spans:
                    if not span.reference:
                        continue
                    left = len(normalize(text[:span.start]))
                    right = len(normalize(text[:span.end]))
                    for chunk in page_chunks:
                        offset, length = positions[chunk.id]
                        if offset >= 0 and min(offset + length, right) > max(offset, left) + 8:
                            self._attach(span.reference, chunk.id)
                            if span.heading:
                                self.headings[span.heading.casefold()].append(chunk.id)

    def _attach(self, reference, identifier):
        if identifier not in self.by_reference[reference]:
            self.by_reference[reference].append(identifier)
        self.labels[identifier].add(reference)

    def enrich(self, chunk):
        refs = sorted(self.labels.get(chunk.id, ()))
        if not refs:
            return chunk
        return replace(chunk, locator="; ".join(display(r) for r in refs))

    def lookup(self, question):
        exact, definitions = [], []
        for wanted in references(question):
            for ref, ids in self.by_reference.items():
                if ref == wanted or ref.startswith(wanted + "("):
                    exact.extend(ids)
            # Citations inside judgments are useful evidence of discussion,
            # but are not promoted to statutory heading metadata.
            exact.extend(c.id for c in self.chunks.values() if wanted in references(c.text))
        focal = query_variants(question)
        question_words = " " + " ".join(re.findall(r"\w+", (focal[0] if focal else question).casefold())) + " "
        for heading, ids in sorted(self.headings.items(), key=lambda item: -len(item[0])):
            phrase = " ".join(re.findall(r"\w+", heading))
            if len(phrase.split()) == 1 and not asks_definition_of(question, phrase):
                continue  # A common party label must not dominate every query.
            if phrase and len(phrase) > 3 and " " + phrase + " " in question_words:
                definitions.extend(ids)
                question_words = question_words.replace(" " + phrase + " ", " ")
        definitions = list(dict.fromkeys(definitions))
        definitions.sort(key=lambda identifier: min(
            (self.chunks[identifier].text.casefold().find(h) / max(1, len(self.chunks[identifier].text))
             for h, ids in self.headings.items() if identifier in ids and h in self.chunks[identifier].text.casefold()), default=1))
        return list(dict.fromkeys(exact)), definitions

    def related(self, identifiers, limit=24):
        """Complete the same provision, then its numbered parent heading."""
        result = list(dict.fromkeys(identifiers))
        for identifier in list(result):
            for ref in sorted(self.labels.get(identifier, ())):
                # Avoid expanding an entire multi-page Definitions section.
                if "(" in ref:
                    result.extend(self.by_reference[ref])
                    root = ref.split("(")[0]
                    result.extend(self.by_reference.get(root, [])[:1])
        return list(dict.fromkeys(result))[:limit]
