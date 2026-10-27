from dataclasses import asdict
import json

from core.models import Chunk, GroundedAnswer, ResearchResult, SearchHit


def encode_result(result):
    data = asdict(result)
    data["answer"] = result.answer.model_dump()
    return json.dumps(data, ensure_ascii=False)


def decode_result(value):
    data = json.loads(value)
    data["answer"] = GroundedAnswer.model_validate(data["answer"])
    data["sources"] = {sid: SearchHit(Chunk(**hit["chunk"]), hit["scores"]) for sid, hit in data["sources"].items()}
    return ResearchResult(**data)
