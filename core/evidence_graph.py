"""Graph edges come from saved citations or explicit user annotations only."""
def build_graph(evidence_service, workspace_id):
    nodes, edges = {}, []
    findings = {f["id"]: f for f in evidence_service.findings(workspace_id) if f["valid_sources"]}
    for item in evidence_service.list(workspace_id):
        doc_node, evidence_node = "doc:" + item["document_id"], "evidence:" + item["id"]
        nodes[doc_node] = {"id": doc_node, "name": item["document_name"], "category": 0, "detail": "Original indexed document", "document_id": item["document_id"], "page": item["page"]}
        nodes[evidence_node] = {"id": evidence_node, "name": f"p.{item['page']} · {item['quote'][:36]}", "category": 2,
                                 "detail": item["quote"], "evidence_id": item["id"], "document_id": item["document_id"], "page": item["page"], "quote": item["quote"]}
        edges.append({"source": evidence_node, "target": doc_node, "name": "quoted from", "basis": f"Indexed chunk {item['chunk_id']}, original page {item['page']}"})
        finding = findings.get(item["finding_id"])
        if finding:
            finding_node = "finding:" + finding["id"]
            nodes[finding_node] = {"id": finding_node, "name": finding["title"][:55], "category": 1,
                                   "detail": finding["statement"] + " · " + finding["verification"]}
            edges.append({"source": evidence_node, "target": finding_node, "name": item["relation"], "basis": "Saved citation; interpretation still requires review"})
        if item["question"]:
            import hashlib
            question_node = "question:" + hashlib.sha256(item["question"].encode()).hexdigest()[:12]
            nodes[question_node] = {"id": question_node, "name": item["question"][:60], "category": 3, "detail": item["question"]}
            edges.append({"source": question_node, "target": "finding:" + finding["id"] if finding else evidence_node,
                          "name": "researched with", "basis": "Saved research question"})
    with evidence_service.db.connect() as con:
        for link in con.execute("SELECT * FROM evidence_links WHERE workspace_id=?", (workspace_id,)):
            source, target = "evidence:" + link["source_id"], "evidence:" + link["target_id"]
            if source in nodes and target in nodes:
                edges.append({"source": source, "target": target, "name": link["relation"], "basis": "User annotation: " + link["note"]})
    return {"nodes": list(nodes.values()), "links": edges}
