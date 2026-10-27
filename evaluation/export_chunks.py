"""Export actual chunk IDs and text for human relevance annotation. Keep private."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

from core.service import CorpusService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/annotation_chunks.jsonl"))
    args = parser.parse_args()
    service = CorpusService()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(json.dumps(asdict(c), ensure_ascii=False) for c in service.db.chunks()), encoding="utf-8")
    print(f"Exported actual chunk IDs and passages to {args.output}. This file contains private document text.")


if __name__ == "__main__":
    main()
