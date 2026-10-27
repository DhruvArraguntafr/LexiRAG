"""Conservative dates from exact text spans; no inferred commencement dates."""
from datetime import datetime
import re

DATE_PATTERN = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{4})\b", re.I)


def extract_events(chunks):
    seen = set()
    for chunk in chunks:
        for match in DATE_PATTERN.finditer(chunk.text):
            date_value = None
            for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
                try:
                    date_value = datetime.strptime(re.sub(r"\bSept\b", "Sep", match.group(), flags=re.I), fmt).date().isoformat()
                    break
                except ValueError:
                    pass
            if date_value is None:
                continue
            prior_sentence = chunk.text.rfind(". ", 0, match.start())
            start = max(prior_sentence + 2 if prior_sentence >= 0 else 0, chunk.text.rfind("\n", 0, match.start()) + 1, 0)
            stop = chunk.text.find(". ", match.end())
            quote = chunk.text[start:stop + 1 if stop >= 0 else len(chunk.text)].strip()
            # Bind the role to words immediately adjacent to THIS date, not
            # another date in the same sentence.
            prefix = chunk.text[max(start, match.start() - 60):match.start()].lower()
            event_type = "Mentioned date"
            for pattern, label in ((r"(?:commences?|effective|comes into force)\s+(?:on\s+)?$", "Commencement (text label)"),
                                   (r"(?:notified|notification dated)\s+(?:on\s+)?$", "Notification (text label)"),
                                   (r"(?:judgment delivered|decided|pronounced)\s+(?:on\s+)?$", "Judgment (text label)"),
                                   (r"(?:amended|amendment dated)\s+(?:on\s+)?$", "Amendment (text label)"),
                                   (r"(?:enacted|enactment dated)\s+(?:on\s+)?$", "Enactment (text label)"),
                                   (r"(?:dated)\s+$", "Document date (text label)"),
                                   (r"(?:begins|starts|ends|expires)\s+(?:on\s+)?$", "Contract milestone (text label)")):
                if re.search(pattern, prefix):
                    event_type = label
                    break
            key = chunk.document_id, chunk.page, date_value, quote
            if key in seen:
                continue
            seen.add(key)
            yield {"title": (chunk.locator or "Date mentioned in source")[:180], "event_date": date_value,
                   "event_type": event_type, "chunk_id": chunk.id, "quote": quote, "origin": "extracted explicit date"}
