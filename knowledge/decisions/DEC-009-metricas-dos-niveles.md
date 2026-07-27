# DEC-009 - Taxonomia de metricas en dos niveles: producto vs ingenieria

- **Estado:** Aceptado
- **Fecha:** 2026-07-27
- **Relaciona con:** ADR-0006, ADR-0019, ADR-0020, BM-001, BM-002, BM-003

## Contexto

El harness de evaluacion historico trataba `retrieval_doc_miss` (que la lista de fuentes devueltas contenga el documento esperado) como fallo duro (`pass_retrieval = False`).

En un RAG hibrido/agéntico donde la evidencia puede provenir de multiples documentos o donde una pregunta se responde correctamente con evidencia equivalente de otro texto, forzar `retrieval_doc_miss` como fallo duro castiga respuestas correctas y presiona al sistema a usar filtrado duro por entidad, reduciendo el recall general.

## Decision

Se separa formalmente la evaluacion en dos niveles de metricas:

### 1. Metricas de Producto (Gates de evaluacion)

Deciden si el caso aprueba o falla (`passed = True | False`). Si un gate de producto falla, la ejecucion se considera fallida.

- **Soporte de respuesta por evidencia (`pass_groundedness`):** la respuesta esta respaldada por el contexto recuperado (VERIFY `supported` / `weakly_supported`).
- **Anti-alucinacion (`pass_hallucination`):** ausencia de afirmaciones factuales no soportadas o inventadas.
- **Declinacion correcta (`decline_pass`):** para preguntas no respondibles (`is_answerable = False`), el sistema reconoce la falta de evidencia y declina adecuadamente.
- **Sin contenido prohibido (`forbidden_pass`):** la respuesta no contiene frases prohibidas configuradas (`must_not_contain`).
- **Completitud minima (`pass_generation`):** presencia de palabras clave esenciales de la respuesta sin introducir hechos falsos.

### 2. Metricas de Ingenieria (Diagnostico de rendimiento)

Proporcionan senales de optimizacion para componentes especificos. **No causan fallo duro del caso de prueba**, pero se registran y monitorean mediante umbrales de alerta versionados en `tests/eval/baselines/`.

- `retrieval_doc_hit` / `retrieval_doc_miss`: indica si el documento esperado estuvo en el top-K.
- `retrieval_page_hit` / `retrieval_page_miss`: precision a nivel de pagina.
- `Recall@K`, `Precision@K`, `MRR`, `NDCG`.
- Scores intermedios (BM25 score, Reranker score, Hybrid score).
- Cobertura de fuentes y overlap lexico global.

`retrieval_doc_miss` se convierte oficialmente en una advertencia de diagnostico (`warning`) en lugar de un fallo duro.

## Consecuencias

- Evita optimizar el retrieval exclusivamente para complacer al benchmark.
- Permite que la arquitectura hibrida evolucione e incorpore nuevas fuentes sin romper tests existentes.
- Aumenta la exigencia sobre la calidad de la respuesta (gates de producto) mientras relaja supuestos rigidos sobre el origen exacto de la evidencia.
