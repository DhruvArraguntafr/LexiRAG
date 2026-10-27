"""Question-driven comparison planning; no legal answers or inferred authorities."""
from dataclasses import dataclass
import re

from core.legal_sections import query_variants, references, named_documents

_COMPARE = re.compile(r"(?i)\b(compare[ds]?|comparisons?|contrast(?:s|ing)?|versus|vs\.?|differences?|similar(?:ities|ity)?|differ(?:s|ent)?|distinguish|both\s+(?:documents|pdfs|agreements|acts))\b")
_META = re.compile(r"(?i)\b(compare|comparison|contrast|similarities|differences|shared|specific|stated|selected|uploaded|documents?|pdfs?|act|rules|advisory|explain|distinguish|between|across|each|both|what|how|their|the|with|under|more|contain)\b")
# Retrieval vocabulary, never answer templates: these expressions contain no
# statutory numbers, deadlines, legal conclusions or document-specific facts.
RELATED = {
    "scope": "extent applicability application", "extent": "scope applicability",
    "complaint": "grievance redress dispute", "redress": "grievance complaint remedy",
    "disclose": "information disclosure particulars", "disclosure": "information particulars informed",
    "information": "disclosure informed particulars", "refund": "return repayment consideration",
    "return": "refund defective goods consideration", "consent": "affirmative permission automatic",
    "privacy": "personal data consent", "cancellation": "termination notice charges",
    "liability": "responsibility obligation compensation", "audit": "review self-audit compliance",
    "pattern": "interface consent unfair practice",
    "procedure": "complaint filing proceedings hearing adjudication",
}


def is_comparison(question):
    return bool(_COMPARE.search(question))


def document_aliases(database, document):
    aliases = [re.sub(r"(?i)\.pdf$", "", document["name"])]
    # Older imports may have abbreviated filenames. Explicit instrument titles
    # in their first pages are metadata for reference resolution, not evidence.
    for page in (1, 2):
        record = database.page(document["id"], page)
        if not record:
            continue
        lines = record["text"].splitlines()
        for i,line in enumerate(lines):
            joined = " ".join(lines[i:i+2]).strip()
            if re.fullmatch(r"(?i)(?:the\s+)?[A-Za-z ()-]{6,120}\b(?:act|rules|regulations|code)\s*,?\s*\d{4}[’']?", joined):
                aliases.append(joined.strip("’'"))
    return list(dict.fromkeys(aliases))


def resolve_comparison_documents(database, allowed, question):
    docs=[d for d in database.documents() if d["id"] in allowed]
    expanded=[]
    for doc in docs:
        expanded.extend({"id":doc["id"],"name":alias} for alias in document_aliases(database,doc))
    matched=named_documents(question,expanded)
    matched.update(doc["id"] for doc in docs if re.search(
        r"(?<!\w)"+re.escape(doc["name"])+r"(?!\w)",question,re.I))
    # Resolve shorthand only when unambiguous within the allowed selection.
    # Never guess among two Acts or add a document outside that selection.
    for kind in ("act", "rules", "advisory", "agreement", "judgment"):
        candidates={doc["id"] for doc in docs if any(
            re.search(r"\b"+kind+r"\b",alias,re.I) for alias in document_aliases(database,doc))}
        if len(candidates)==1 and re.search(r"\b(?:the\s+"+kind+r"\b|"+kind.capitalize()+r"\b)",question):
            matched.update(candidates)
    return tuple(d["id"] for d in docs if d["id"] in matched) if len(matched)>=2 else tuple(allowed)


@dataclass(frozen=True)
class ComparisonPlan:
    question: str
    concepts: tuple[str, ...]
    expanded: tuple[str, ...]


def plan_comparison(question, aliases=()):
    if not question.strip() or len(question)>6000:
        from core.models import LexiRAGError
        raise LexiRAGError("Enter a comparison question of 1–6,000 characters.")
    clean=question
    for alias in sorted(aliases,key=len,reverse=True):
        # A one-word filename may also be the legal concept itself.
        if len(re.findall(r"\w+",alias))>=2:
            clean=re.sub(re.escape(alias)," ",clean,flags=re.I)
    # Split BEFORE keyword normalization, which deliberately removes words
    # such as 'and'. Otherwise every apparent subquery is the entire question.
    pieces=re.split(r"\s+(?:and|with|versus|vs|whereas|while|but)\s+|[?;.]",clean,flags=re.I)
    concepts=[]
    for value in [clean,*pieces]:
        focal=query_variants(value)
        value=_META.sub(" ",focal[0] if focal else value)
        value=" ".join(value.split()).strip(" ,:;?.")
        if len(re.findall(r"\w+",value))>=2 and value not in concepts:
            concepts.append(value[:450])
    if not concepts:
        concepts=[clean or question.strip()]
    concepts=concepts[:4]
    # References explicitly requested by the user remain searchable even when
    # instrument titles/boilerplate are removed from concept subqueries.
    if references(question):
        concepts=list(dict.fromkeys([*concepts,question]))[:5]
    expanded=[]
    # Short procedural alternatives avoid drowning the requested action in
    # names of institutions that also occur in their statutory definitions.
    if re.search(r"\b(procedur\w*|filing|file|apply|application)\b",question,re.I):
        expanded.append("complaint filing procedure proceedings hearing")
    for concept in concepts:
        terms=[]
        for trigger,related in RELATED.items():
            if re.search(r"\b"+trigger+r"\w*\b",concept,re.I):
                terms.extend(related.split())
        if terms:
            expanded.append(concept+" "+" ".join(dict.fromkeys(terms)))
    return ComparisonPlan(question,tuple(concepts),tuple(expanded[:4]))
