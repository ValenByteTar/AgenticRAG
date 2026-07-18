import chromadb
c = chromadb.PersistentClient(path='chroma_bge_m3')
col = c.get_collection('cybersec_docs_bge_m3')
r = col.get(where={"source": {"$eq": "NIST RISK MANAGEMENT FRAMEWORK.pdf"}}, include=['metadatas', 'documents'])
for m, d in zip(r['metadatas'], r['documents']):
    print(m.get('page'), (d or '')[:200])
