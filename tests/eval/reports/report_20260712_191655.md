# Reporte de evaluacion RAG - Ciberseguridad

Fecha: 20260712_191655  |  Tiempo total: 1592.5s

## Resumen global

| Metrica | Valor |
|---------|-------|
| Total preguntas | 25 |
| Aprobadas | 16 (64.0%) |
| Fallidas | 9 |
| Tasa aprobacion (respondibles) | 69.6% |
| Tasa aprobacion (sin respuesta) | 0.0% |

### Veredictos por capa

| Capa | Tasa de exito |
|------|---------------|
| Retrieval | 80.0% |
| Groundedness (sin forbidden) | 96.0% |
| Generation (keyword score) | 80.0% |
| Anti-alucinacion | 0.0% |
| **Overall** | **64.0%** |

### Retrieval

| Metrica | Valor |
|---------|-------|
| Doc hit@K | 78.3% |
| Pag hit@K (+/-tol) | 43.5% |
| Recall@1 | 0.391 |
| Recall@3 | 0.696 |
| Recall@5 | 0.696 |
| Recall promedio (multi-doc) | 0.551 |
| MRR promedio | 0.528 |
| Precision@K promedio | 0.300 |
| Fallos retrieval (doc miss) | 5 |
| Advertencias pagina miss | 8 |

### Respuesta

| Metrica | Valor |
|---------|-------|
| Keyword score promedio (auxiliar) | 0.488 |
| Fallos por kw score bajo | 5 |
| Fidelidad citas promedio | N/A |
| Alucinaciones detectadas | 2 |

### Latencia

| Metrica | Valor |
|---------|-------|
| Promedio | 61341 ms |
| P50 | 54714 ms |
| P95 | 122248 ms |
| Maximo | 124341 ms |

### Breakdown por etapa (promedio)

| Etapa | Avg ms | % del total |
|-------|--------|------------|
| Embed query (BGE) | 754.5 | 1.2% |
| Busqueda semantica | 49.4 | 0.1% |
| BM25 keyword | 1947.4 | 3.2% |
| Fusion + ranking | 38.2 | 0.1% |
| Re-ranker | 5293.2 | 8.6% |
| LLM (estimado) | 57506.2 | 93.7% |

## Resultados por categoria

| Categoria | Total | Aprob | Tasa | DocHit | PagHit | Recall | MRR | KW |
|-----------|-------|-------|------|--------|--------|--------|-----|-----||
| complex | 12 | 8 | 67% | 8 | 4 | 0.389 | 0.403 | 0.399 |
| multi_document | 1 | 1 | 100% | 1 | 1 | 0.500 | 1.000 | 1.000 |
| no_answer | 2 | 0 | 0% | 0 | 0 | N/A | N/A | 1.000 |
| simple | 10 | 7 | 70% | 9 | 5 | 0.750 | 0.631 | 0.442 |

## Top problemas

| Problema | Casos |
|---------|-------|
| Page miss (doc correcto, pagina errada) | 8 |
| Retrieval miss (doc no encontrado) | 5 |
| Generation baja (keyword score bajo) | 5 |
| Alucinacion (no declino) | 2 |
| Forbidden phrase encontrada | 1 |

## Distribucion de rank del primer documento correcto

| Rank | Frecuencia |
|------|------------|
| 1 | 9 |
| 2 | 3 |
| 3 | 4 |
| 6 | 1 |
| 7 | 1 |

_Rank 1 = 9 casos  |  Rank 2-3 = 7 casos  |  Rank 4+ = 2 casos_

## Casos fallidos

- **ID 53**: Como se estructura un SOC de clase mundial segun el libro de 11 estrategias? Des
  - retrieval_doc_miss
  - kw_score=0 missing=['soc', 'tier', 'metrics', 'detection', 'strategy']
- **ID 56**: Como se aplica DevSecOps en un pipeline de CI/CD? Describe herramientas, puntos 
  - retrieval_doc_miss
  - kw_score=0 missing=['devsecops', 'ci/cd', 'pipeline', 'security', 'tool']
- **ID 58**: Describe los pasos del RMF de NIST y como cada paso contribuye a la gestion de r
  - retrieval_doc_miss
  - WARN: kw_partial=0.38 missing=['categorize', 'select', 'implement', 'assess', 'authorize']
- **ID 59**: Como se protege una infraestructura critica segun los marcos de ciberseguridad d
  - retrieval_doc_miss
  - kw_score=0 missing=['critical infrastructure', 'protection', 'framework', 'security']
- **ID 63**: Que es Wireshark y como se usa en forensia de red?
  - kw_score=0 missing=['wireshark', 'network', 'forensics', 'packet']
  - WARN: recall=0.33 (multi-doc incompleto)
- **ID 64**: Que cubre el dominio de seguridad en la nube del CCSP?
  - retrieval_doc_miss
  - WARN: kw_partial=0.33 missing=['cloud security', 'domain']
- **ID 68**: Que es la ingenieria social segun los documentos disponibles?
  - kw_score=0 missing=['social engineering', 'manipulation', 'human']
  - WARN: retrieval_page_miss
  - WARN: recall=0.67 (multi-doc incompleto)
- **ID 72**: Cual fue el impacto financiero exacto del ransomware NotPetya en Maersk en 2017?
  - found_forbidden: ['300 millones', 'maersk']
  - hallucination_forbidden_content
- **ID 74**: Cual es la contrasena por defecto del router Cisco ASA 5505?
  - hallucination_no_decline

## Diagnostico

**Prioridad de intervencion:**

1. Si `retrieval_doc_hit_rate` es bajo -> ajustar top_k, score_threshold o reranker.
2. Si `retrieval_page_hit_rate` es bajo pero `hit_doc` es alto -> chunking muy fino o metadata de pagina incorrecta.
3. Si `avg_mrr` < 0.5 y `hit_doc` es alto -> el doc correcto llega pero en posicion baja; mejorar reranker.
4. Si `avg_keyword_score` es bajo pero retrieval es bueno -> problema en LLM/prompt (no en retrieval).
5. Si `hallucination_count` > 0 -> revisar evidence gate y DECLINE_PHRASES.
6. `avg_precision_at_k` bajo con `hit_doc` alto -> el retriever trae mucho ruido junto con docs correctos.