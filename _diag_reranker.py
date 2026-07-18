import json

data = json.load(open('tests/eval/reports/retrieval_only_20260714_205418_sw60.json', 'r', encoding='utf-8'))
results = data['results']

empeorados = [11, 17, 21, 54, 56, 57, 60, 66, 67]

print("=== Diagnostico reranker: queries empeorados ===\n")

for r in results:
    if not r.get('is_answerable', True):
        continue
    if r['retrieval'].get('skipped'):
        continue
    if r['id'] not in empeorados:
        continue

    pre = r['prerank_retrieval']
    post = r['retrieval']
    
    print(f"ID {r['id']}: {r['query'][:70]}")
    print(f"  Pre:  hit={pre.get('hit_doc')}, rank={pre.get('first_relevant_rank')}, recall={pre.get('recall'):.3f}")
    print(f"  Post: hit={post.get('hit_doc')}, rank={post.get('first_relevant_rank')}, recall={post.get('recall'):.3f}")
    
    # Show prerank top-3 sources
    pre_sources = r.get('prerank_sources_returned', [])[:3]
    print(f"  Pre top-3:")
    for s in pre_sources:
        print(f"    {s['name'][:55]} (score={s['score']:.4f})")
    
    # Show postrank top-3 sources
    post_sources = r.get('sources_returned', [])[:3]
    print(f"  Post top-3:")
    for s in post_sources:
        print(f"    {s['name'][:55]} (score={s['score']:.4f})")
    
    # Show matched docs in prerank
    pre_matched = pre.get('matched', [])
    if pre_matched:
        print(f"  Pre matched (ground truth):")
        for m in pre_matched[:3]:
            print(f"    {m['source'][:55]} page={m.get('page')} rank={m.get('rank')}")
    
    post_matched = post.get('matched', [])
    if post_matched:
        print(f"  Post matched (ground truth):")
        for m in post_matched[:3]:
            print(f"    {m['source'][:55]} page={m.get('page')} rank={m.get('rank')}")
    
    print()

# Also check: what's the reranker score pattern for empeorados vs mejorados
print("\n=== Resumen: empeorados vs mejorados ===")
print(f"Empeorados: {len(empeorados)} queries")
print(f"Mejorados: 16 queries")
print(f"Net: -9 +16 = +7 (pero perdemos 9 docs que estaban hit en prerank)")
