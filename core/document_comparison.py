"""Shared multi-document analysis used by AI Research.

There is no dedicated comparison page or service endpoint. Keep independent
retrieval, paired citation checks and the result shape for saved-run exports.
"""
from time import perf_counter
import re

from core.models import LexiRAGError
from core.rag_pipeline import RAGPipeline
from core.comparison_retriever import ComparisonRetriever, balanced_sources


def comparison_coverage(result, document_ids):
    requested=set(document_ids)
    cited=set()
    paired=0
    invalid=[]
    for finding in result.answer.findings:
        docs={result.sources[r.source_id].chunk.document_id for r in finding.evidence}
        cited.update(docs)
        if len(docs)>=2:
            paired+=1
        elif re.search(r"(?i)\b(both|whereas|while|meanwhile|unlike|contrast|compared|differ\w*|similar\w*|broader|narrower|respectively|instead|versus|parallel|comparable)\b",
                       finding.heading+" "+finding.statement):
            invalid.append(finding)
    complete=(requested<=cited and paired>0 and not invalid and
              not result.answer.insufficient_evidence and result.citation_valid==result.citation_attempts)
    return complete,cited,paired,invalid


class DocumentComparator:
    def __init__(self, service, generator=None):
        self.service, self.pipeline=service,RAGPipeline(service,generator)
        self.retrieval=ComparisonRetriever(service)

    def compare(self, document_ids, topic, k=4, rerank=None, filters=None):
        document_ids=list(dict.fromkeys(document_ids))
        if not 2<=len(document_ids)<=8:
            raise LexiRAGError("Choose between two and eight documents for a comparison.")
        start=perf_counter()
        evidence=self.retrieval.retrieve(document_ids,topic,k,rerank,filters=filters)
        sources=balanced_sources(evidence,self.service.settings.context_chars)
        names=[self.service.db.document(i)["name"] for i in document_ids]
        instruction=("Compare only these selected PDFs: "+"; ".join(names)+". "
                     "Organize findings by the SAME legal issue in each document. State similarities and differences "
                     "in joint findings and cite each document being compared within that finding. "
                     "Separate summaries of each PDF alone do not constitute a completed comparison. "
                     "A finding with only one document cited must only describe that document; put missing "
                     "evidence in limitations, not in unsupported comparisons. Describe only the supplied "
                     "excerpts' coverage; never infer what an entire PDF lacks from retrieved passages. "
                     "Do not manufacture agreement, conflict, overruling or absence of a provision. "
                     "If evidence for a requested issue is missing in a document, state the limitation. "
                     "Questions to address: "+"; ".join(evidence.plan.concepts))
        result=self.pipeline.from_sources(topic,sources,instruction,mode="comparison")
        complete,_,_,_=comparison_coverage(result,document_ids)
        if not complete and sources:
            expanded=self.retrieval.retrieve(document_ids,topic,max(k,6),rerank,expanded=True,filters=filters)
            retry_sources=balanced_sources(expanded,self.service.settings.context_chars)
            if set(document_ids)<={h.chunk.document_id for h in retry_sources.values()}:
                sources=retry_sources
                result=self.pipeline.from_sources(topic,sources,instruction+
                    " This is a bounded recovery attempt. Review the expanded evidence. Provide joint, "
                    "source-supported comparisons instead of separate document summaries. Retain uncertainty "
                    "when a document does not support a requested point.",mode="comparison")
        complete,cited,paired,invalid=comparison_coverage(result,document_ids)
        limits=list(result.answer.limitations)
        if invalid:
            limits.append(f"{len(invalid)} comparative claim(s) were withheld because citations covered only one document.")
            # Valid paired findings can still answer the question after an
            # unsupported extra claim is withheld. Do not turn that into an
            # unnecessary refusal of all the independently verified findings.
            result.answer=result.answer.model_copy(update={
                "findings":[f for f in result.answer.findings if f not in invalid]})
            complete,cited,paired,_=comparison_coverage(result,document_ids)
        if not set(document_ids)<=cited:
            limits.append("A complete comparison is unavailable: verified citations do not cover every selected document.")
        if not paired:
            limits.append("The supported findings do not yet establish a paired comparison of the selected documents.")
        if result.citation_valid<result.citation_attempts:
            limits.append("Some requested findings failed quotation verification; the comparison is incomplete.")
        result.answer=result.answer.model_copy(update={
            "findings":result.answer.findings,
            "insufficient_evidence":not complete,"limitations":list(dict.fromkeys(limits))})
        rows=[]
        for finding in result.answer.findings:
            row={"Issue":finding.heading,"Finding":finding.statement,"Type":finding.kind}
            for identifier,name in zip(document_ids,names):
                refs=[r for r in finding.evidence if sources[r.source_id].chunk.document_id==identifier]
                row[f"{name} [{identifier[:6]}]"]="; ".join(f"[{r.source_id}] p. {sources[r.source_id].chunk.page}: {r.quote}" for r in refs) or "No supporting passage cited for this finding"
            rows.append(row)
        result.comparison_rows=rows
        result.latency_seconds=perf_counter()-start
        self.service.db.record_activity("comparison",result.latency_seconds,"hybrid",result.answer.insufficient_evidence)
        return result
