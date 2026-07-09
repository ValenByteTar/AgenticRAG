import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
from run_cybersec_eval import (
    validate_retrieval, validate_response_keywords,
    evaluate_case, analyze_results,
)


def make_fake_result(i, lat, rank=1, recall=1.0, answerable=True,
                     pass_ret=True, pass_gnd=True, pass_gen=True, pass_hal=True):
    return {
        'id': i, 'category': 'simple', 'difficulty': 'low',
        'is_answerable': answerable,
        'passed': pass_ret and pass_gnd and pass_gen and pass_hal,
        'pass_retrieval': pass_ret,
        'pass_groundedness': pass_gnd,
        'pass_generation': pass_gen,
        'pass_hallucination': pass_hal,
        'failure_reasons': ([] if pass_ret else ['retrieval_doc_miss']),
        'warnings': [],
        'retrieval': {
            'skipped': False, 'hit_doc': pass_ret, 'hit_page': pass_ret,
            'recall': recall,
            'first_relevant_rank': rank if pass_ret else None,
            'mrr': (1.0/rank) if pass_ret else 0.0,
            'precision_at_k': 0.4, 'matched': [],
        },
        'response_validation': {
            'keyword_score': 0.8, 'present': ['x'], 'missing': [],
            'found_forbidden': [], 'keywords_pass': True, 'forbidden_pass': True,
        },
        'hallucination': {'applicable': not answerable, 'pass': pass_hal,
                          'declined': pass_hal, 'hallucinated': False},
        'citation_fidelity': {'score': None, 'cited': [], 'verified': [], 'unverified': []},
        'query': 'test query', 'answer_snippet': 'ok', 'sources_returned': [], 'latency_ms': lat,
    }


# --- Test 1: veredictos por capa en evaluate_case ---
q_answerable = {
    'id': 1, 'category': 'simple', 'difficulty': 'low', 'is_answerable': True,
    'query': 'test', 'expected_sources': ['CISSP.pdf'], 'expected_pages': [30],
    'answer_keywords': ['zero trust'], 'must_not_contain': [],
}
api_good = {
    'response': 'El modelo de zero trust verifica identidades',
    'sources': [{'name': 'CISSP.pdf', 'page': 30, 'score': 0.9}],
    'latency_ms': 500,
}
r = evaluate_case(q_answerable, api_good, tolerance=2)
assert r['pass_retrieval'] == True
assert r['pass_groundedness'] == True
assert r['pass_generation'] == True
assert r['passed'] == True
print("Test 1 PASS  4-layer verdicts OK para caso perfecto")

# --- Test 2: retrieval falla, generation OK -> Overall FAIL pero generacion PASS ---
api_bad_ret = {
    'response': 'El modelo de zero trust verifica identidades',
    'sources': [{'name': 'other_doc.pdf', 'page': 1, 'score': 0.5}],
    'latency_ms': 300,
}
r2 = evaluate_case(q_answerable, api_bad_ret, tolerance=2)
assert r2['pass_retrieval'] == False
assert r2['pass_generation'] == True   # keywords OK aunque retrieval falle
assert r2['passed'] == False
print("Test 2 PASS  retrieval FAIL, generation PASS, overall FAIL")

# --- Test 3: Recall@1/3/5 ---
fake5 = [
    make_fake_result(1, 200, rank=1),   # encontrado en rank 1 -> contribuye a @1,@3,@5
    make_fake_result(2, 200, rank=3),   # rank 3 -> contribuye a @3,@5
    make_fake_result(3, 200, rank=5),   # rank 5 -> solo @5
    make_fake_result(4, 200, pass_ret=False),  # miss -> no contribuye
    make_fake_result(5, 200, rank=2),   # rank 2 -> @3,@5
]
a3 = analyze_results(fake5)
s3 = a3['summary']
# retrieval_total=5 (todos skipped=False); ranks: 1,3,5,None,2
# @1: solo rank=1 -> 1/5
# @3: rank<=3 -> rank1,rank3,rank2 -> 3/5
# @5: rank<=5 -> rank1,rank3,rank5,rank2 -> 4/5  (rank=None no cuenta)
assert s3['recall_at_1'] == round(1/5, 3), f"recall@1={s3['recall_at_1']}"
assert s3['recall_at_3'] == round(3/5, 3), f"recall@3={s3['recall_at_3']}"
assert s3['recall_at_5'] == round(4/5, 3), f"recall@5={s3['recall_at_5']}"
print(f"Test 3 PASS  Recall@1={s3['recall_at_1']} @3={s3['recall_at_3']} @5={s3['recall_at_5']}")

# --- Test 4: latencia percentiles + rank_dist ---
fake_lat = [make_fake_result(i, lat) for i, lat in enumerate([100, 200, 300, 400, 950], 1)]
a4 = analyze_results(fake_lat)
s4 = a4['summary']
assert s4['latency_max_ms'] == 950
assert s4['latency_p95_ms'] >= 400
assert a4['rank_distribution'] == {1: 5}
assert s4['avg_mrr'] == 1.0
print(f"Test 4 PASS  p95={s4['latency_p95_ms']} max={s4['latency_max_ms']} rank_dist={a4['rank_distribution']}")

# --- Test 5: top_problems conteo correcto ---
fake_mix = [
    make_fake_result(1, 100, pass_ret=False),   # retrieval miss
    make_fake_result(2, 100, pass_ret=False),   # retrieval miss
    make_fake_result(3, 100, pass_gen=False),   # low kw
    make_fake_result(4, 100),                    # PASS
]
a5 = analyze_results(fake_mix)
tp = a5['top_problems']
assert tp['retrieval_miss'] == 2
assert tp['low_kw_score'] == 1
assert tp['forbidden'] == 0
print(f"Test 5 PASS  top_problems={tp}")

# --- Test 6: codigo muerto ausente (doc_errors/doc_miss_count) ---
import inspect
import importlib.util, pathlib
_spec = importlib.util.spec_from_file_location(
    "run_cybersec_eval",
    str(pathlib.Path(__file__).parent / "run_cybersec_eval.py")
)
_m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m)
src = inspect.getsource(_m.analyze_results)
import re as _re
assert 'doc_errors' not in src, "codigo muerto doc_errors sigue presente"
# doc_miss_count como variable standalone (no como substring de retrieval_doc_miss_count)
assert not _re.search(r'\bdoc_miss_count\b', src), "codigo muerto doc_miss_count sigue presente"
print("Test 6 PASS  sin codigo muerto")

print("\nALL TESTS PASSED")
