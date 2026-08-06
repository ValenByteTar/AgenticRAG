---
id: RES-012
category: research
status: accepted
created: 2026-08-06
updated: 2026-08-06
author: human
components: [evaluation, benchmark, legacy-rag, knowledge-builder, knowledge-consumer, retrieval, evidence, verify, corpus, warm-artifacts]
tags: [benchmark, evaluation, migration, historical-baseline, canonical-benchmark, evidence, claim-coverage, corpus-versioning, builder, consumer, regression]
related: [RES-001, RES-002, RES-003, RES-010, RES-011, RES-013, ADR-0006, ADR-0018, ADR-0019, ADR-0020, ADR-0022, DEC-009, BM-001, BM-005, BM-006]
supersedes: null
superseded_by: null
---

# RES-012 — Migración del benchmark histórico hacia evaluación canónica por evidencia

## Topic

Definir cómo evolucionar el benchmark actual de 75 preguntas hacia una evaluación compatible con el Builder nuevo, el Consumer actual y el futuro Agentic RAG, preservando sin modificaciones las métricas históricas del RAG híbrido anterior.

## Sources

- `tests/eval/cybersec_eval_questions.json`: suite actual de 75 preguntas con expected sources/pages.
- `tests/eval/run_cybersec_eval.py`: harness actual y métricas legacy.
- `tests/eval/README.md`: distribución, ejecución e interpretación del benchmark.
- `tests/eval/baselines/baseline_pre_agentic_phase0/`: baseline histórico congelado.
- `knowledge/benchmarks/BM-001-baseline-pre-agentic-phase0.md`: baseline pre-Agentic.
- `knowledge/benchmarks/BM-005-consumer-warm-artifacts.md`: evaluación Consumer con Warm Artifacts.
- `knowledge/benchmarks/BM-006-baseline-post-canonical-migration.md`: baseline posterior a migración canónica.
- `data/corpus_exclusions.json`: registro de documentos excluidos, incluyendo duplicados.
- RES-001: contrato Warm como centro arquitectónico.
- RES-002: Knowledge Builder / Knowledge Compiler.
- RES-003: Knowledge Consumer / evolución del runtime.
- RES-010: contrato canónico de documento.
- RES-011: auditoría Consumer basada en evidencia.
- ADR-0006: Evaluation transversal.
- ADR-0018: separación Builder / Consumer.
- ADR-0019: contrato epistémico y VERIFY a nivel de claims.
- ADR-0020: ownership y contrato de ejecución observable.
- ADR-0022: contrato canónico de documento.
- DEC-009: métricas de producto frente a métricas de ingeniería.

---

## 1. Motivación

El benchmark actual fue construido para evaluar el RAG híbrido en un modelo centrado en chunks:

```text
Query -> chunks -> contexto -> LLM -> métricas de documento/página
```

La suite contiene 75 preguntas con `expected_sources`, `expected_pages`, keywords y reglas de rechazo. El harness mide recuperación de documentos/páginas, MRR, precision@K, recall multi-documento, keywords, citas, groundedness, alucinación y latencia.

Este diseño conserva un valor histórico importante: permite saber cómo se comportaba el RAG híbrido anterior. Sin embargo, no debe seguir siendo el único instrumento de evaluación cuando el sistema evoluciona hacia:

```text
Query
  -> QueryIR operacional
  -> RetrievalPlan
  -> EvidenceSet
  -> Evidence Evaluation
  -> EvidenceSelection
  -> ContextPackage
  -> Reasoning
  -> VERIFY
```

El problema no es únicamente que algunas fuentes hayan sido eliminadas. Algunas exclusiones corresponden a duplicados y el conocimiento puede permanecer en otro archivo. Por lo tanto:

```text
archivo excluido != conocimiento eliminado
```

La migración del benchmark debe preservar la historia y, al mismo tiempo, dejar de usar el nombre exacto del documento como único proxy de calidad.

---

## 2. Estado actual

### 2.1 Suite legacy

El dataset actual está en:

```text
tests/eval/cybersec_eval_questions.json
```

Contiene 75 casos y utiliza:

- `query`;
- `category`;
- `difficulty`;
- `is_answerable`;
- `expected_sources`;
- `expected_pages`;
- `answer_keywords`;
- `must_not_contain`;
- `notes`.

El harness actual está en:

```text
tests/eval/run_cybersec_eval.py
```

El harness consulta `HybridRAG.execute()` en modo directo o `/api/chat` en modo HTTP. La suite histórica debe permanecer inmutable.

### 2.2 Limitaciones del modelo legacy

1. `expected_sources` puede penalizar una respuesta correcta basada en una fuente equivalente.
2. `expected_pages` acopla el benchmark a una representación particular del corpus.
3. `doc_hit@K` mide un diagnóstico de retrieval, no necesariamente suficiencia de evidencia.
4. La fuente exacta puede desaparecer aunque su contenido siga en un duplicado activo.
5. La suite no expresa explícitamente claims requeridos, alcance de claims o cobertura.
6. La evaluación de generación y retrieval están relacionadas en un mismo caso, pero no tienen contratos independientes.
7. No representa Evidence Evaluation ni decisiones pre-reasoning de insuficiencia, ampliación, decline o aclaración.

---

## 3. Principio de preservación histórica

El benchmark legacy debe congelarse como una fotografía del sistema anterior.

No se debe:

- editar retroactivamente las 75 preguntas;
- cambiar sus expected sources/pages;
- reemplazar sus métricas por nuevas métricas;
- recalcular sus resultados históricos con el corpus nuevo;
- eliminar casos porque un archivo ya no tiene el mismo nombre;
- mezclar pass rates legacy y canónicos en una única cifra.

El reporte histórico debe declarar siempre:

```text
benchmark_version: legacy-v1
contract: legacy_chunk_retrieval
corpus_version: <identificador histórico>
knowledge_builder_version: <si aplica>
consumer_version: <si aplica>
```

La métrica histórica responde:

> ¿Cómo funcionaba el RAG híbrido anterior bajo su contrato y corpus originales?

---

## 4. Benchmark canónico propuesto

Debe crearse una segunda representación del benchmark, sin destruir la primera:

```text
tests/eval/legacy/cybersec_eval_questions_v1.json
tests/eval/canonical/cybersec_eval_questions_v2.json
```

La suite canónica deja de considerar las fuentes exactas como identidad primaria. Las fuentes siguen siendo importantes, pero se representan mediante `canonical_doc_id` y `accepted_evidence_sources`; el filename histórico queda como referencia de compatibilidad, no como verdad.

Cada caso debe separar:

```text
Question Case
    +-- Query Contract
    +-- Evidence Requirements
    +-- Answer Requirements
```

### 4.1 Estructura propuesta

```json
{
  "id": "q-003",
  "legacy_id": 3,
  "category": "conceptual",
  "difficulty": "low",
  "query": {
    "raw": "¿Qué significa CIA en ciberseguridad?",
    "required_evidence": ["cia-confidentiality", "cia-integrity", "cia-availability"],
    "constraints": [],
    "execution_budget": {
      "max_retrieval_rounds": 2,
      "max_context_tokens": 5000
    }
  },
  "expected_claims": [
    {
      "claim_id": "cia-confidentiality",
      "subject": "CIA triad",
      "required_relation": "includes",
      "object": "confidentiality",
      "human_description": "La respuesta debe expresar que confidentiality es un componente de CIA.",
      "canonical_form": "Confidentiality protects information against unauthorized access or disclosure.",
      "acceptable_variants": [
        "Prevents unauthorized disclosure",
        "Protects information from unauthorized access"
      ],
      "created_by": "external_human_evaluator"
    },
    {
      "claim_id": "cia-integrity",
      "canonical_form": "Integrity protects information from unauthorized alteration.",
      "acceptable_variants": [
        "Maintains accuracy and completeness",
        "Prevents unauthorized modification"
      ],
      "created_by": "external_human_evaluator"
    },
    {
      "claim_id": "cia-availability",
      "canonical_form": "Availability ensures authorized access when needed.",
      "acceptable_variants": [
        "Information is accessible to authorized users",
        "Ensures timely access to systems and data"
      ],
      "created_by": "external_human_evaluator"
    }
  ],
  "evidence_requirements": {
    "required_claims": 3,
    "minimum_claim_coverage": 1.0,
    "minimum_evidence_quality": 0.7,
    "minimum_independent_sources": 1,
    "require_documentary_support": false,
    "allow_general_domain_knowledge": true
  },
  "answer_requirements": {
    "required_claims": [
      "confidentiality",
      "integrity",
      "availability"
    ],
    "must_not_contain": ["central intelligence agency"],
    "citation_required": false
  },
  "legacy_reference": {
    "expected_sources": [
      "02 ISOIEC 27001 Implementation Guide.pdf",
      "Hack The Cybersecurity Interview .pdf",
      "Introduction To Cybersecurity.pdf",
      "ISO 27001 Introduction.pdf"
    ],
    "expected_pages": [1, 43, 11, 5]
  }
}
```

La suite canónica define el conocimiento esperado y conserva la referencia histórica, pero no obliga a que el Consumer recupere el mismo filename si existe evidencia equivalente validada.

### 4.2 Independencia del benchmark respecto del Builder

El benchmark canónico debe ser una especificación externa al Builder. Los claims esperados no deben generarse automáticamente desde KIR, Knowledge Model o Warm Artifacts del mismo build que luego se evalúa.

```text
Human / evaluator
        |
        v
Expected claims + accepted variants
        |
        v
Canonical benchmark
        |
        v
Observed evidence from runtime
```

El Builder produce conocimiento operativo. El benchmark define el criterio externo contra el cual ese conocimiento se evalúa. Si el mismo proceso genera el Knowledge Model y los expected claims, el sistema puede terminar evaluándose contra sí mismo.

Los claims del benchmark deben tener:

- `created_by: external_human_evaluator` o procedencia independiente equivalente;
- `ground_truth_source: human_reviewed`;
- `review_status: approved|pending|rejected`;
- `reviewer` y `review_date`;
- fecha y versión de revisión;
- justificación o referencia externa;
- separación de `expected_claims` respecto de artifacts generados por Builder;
- revisión humana cuando se agreguen o modifiquen variantes aceptables.

El Builder puede ayudar a descubrir candidatos para revisión, pero no debe ser la autoridad final para crear o aprobar el ground truth.

### 4.3 Canonical form como ayuda humana

`canonical_form` no es la verdad computable ni debe convertirse en una sentencia textual que el evaluator deba hacer coincidir. Es una descripción legible para facilitar revisión.

La evaluación computable debe apoyarse principalmente en:

```text
claim_id
subject
required_relation
object
claim_scope
```

La equivalencia debe tolerar relaciones semánticamente compatibles, por ejemplo `includes` y `contains`, según una política externa revisada. Esto evita que el benchmark se convierta en un mini Knowledge Graph manual o dependa de frases específicas.

---

## 5. Separación de verdades

El benchmark debe distinguir tres cosas.

### 5.1 Expected knowledge

Lo que el sistema debe poder resolver:

```text
CIA incluye confidentiality, integrity y availability.
```

### 5.2 Accepted evidence

La evidencia y equivalencias aceptadas para soportar esos claims. La identidad primaria es `canonical_doc_id`; los filenames legacy se conservan como aliases históricos:

```json
{
  "accepted_evidence_sources": [
    {
      "canonical_doc_id": "doc:introduction-to-cybersecurity",
      "legacy_aliases": ["Introduction To Cybersecurity.pdf"],
      "accepted_claims": [
        "cia-confidentiality",
        "cia-integrity",
        "cia-availability"
      ]
    }
  ]
}
```

### 5.3 Equivalencia de claims

La equivalencia no es solo documental ni requiere texto idéntico. Dos fuentes pueden expresar el mismo claim con paráfrasis distintas:

```text
Fuente A: "La confidencialidad evita acceso no autorizado."
Fuente B: "Confidentiality protects information from unauthorized disclosure."
```

El benchmark debe conservar un catálogo externo de claims con:

```json
{
  "claim_id": "cia-confidentiality",
  "canonical_form": "Confidentiality protects information against unauthorized access.",
  "acceptable_variants": [
    "Prevents unauthorized disclosure",
    "Protects information from unauthorized access",
    "Maintains secrecy of information"
  ],
  "equivalence_policy": "semantic_claim_match",
  "created_by": "external_human_evaluator"
}
```

La equivalencia debe evaluarse respecto del significado, sujeto, condición y alcance (`claim_scope`), no solamente mediante coincidencia textual.

### 5.4 Observed evidence

Lo que el runtime recuperó y utilizó realmente:

```json
{
  "evidence_id": "ev-...",
  "canonical_doc_id": "doc:introduction-to-cybersecurity",
  "claim_scope": {
    "subject": "CIA triad",
    "condition": null
  },
  "coverage": [
    "cia-confidentiality",
    "cia-integrity",
    "cia-availability"
  ],
  "confidence": 0.94,
  "validated": true
}
```

El benchmark define el criterio. El runtime aporta la evidencia observada. El evaluator decide si esa evidencia satisface el criterio.

---

## 6. Auditoría de corpus y equivalencias

Antes de excluir preguntas por documentos removidos, se debe ejecutar una auditoría de equivalencia.

El registro actual indica `total_excluded: 208`, mientras que la reducción mencionada informalmente es de 203 documentos. Esta discrepancia debe resolverse mediante un manifest versionado antes de comparar resultados.

Para cada fuente histórica se debe clasificar:

```text
stable_exact
stable_duplicate
stable_alternative
uncertain_requires_review
knowledge_gap_introduced
invalidated
```

### 6.1 Regla de clasificación

```text
archivo exacto ausente
    |
    +--> duplicado activo con contenido equivalente -> stable_duplicate
    +--> fuente alternativa con claims suficientes -> stable_alternative
    +--> sin equivalente comprobado -> uncertain_requires_review
    +--> conocimiento antes disponible pero ahora ausente -> knowledge_gap_introduced
    +--> caso inválido del dataset o ground truth defectuoso -> invalidated
```

No se debe inferir equivalencia únicamente por nombre parecido. La verificación debe considerar:

- fingerprint o hash de contenido;
- similitud textual;
- claims cubiertos;
- páginas o spans donde corresponda;
- canonical document identity;
- provenance del Builder;
- contenido efectivo disponible en el corpus activo.

### 6.2 Manifest de corpus

Se necesitan manifests explícitos:

```text
tests/eval/manifests/corpus_legacy.json
tests/eval/manifests/corpus_reduced.json
```

Cada manifest debe declarar:

```json
{
  "corpus_id": "reduced-2026-08",
  "source_root": "data/extracted_texts",
  "excluded_root": "data/extracted_texts_excluded",
  "document_count": 0,
  "excluded_count": 0,
  "exclusion_registry": "data/corpus_exclusions.json",
  "content_fingerprint": "...",
  "canonical_id_version": "..."
}
```

---

## 7. Métricas del benchmark canónico

El benchmark canónico debe reportar métricas por capas.

### 7.1 Query execution

- Query Contract válido.
- QueryIR operacional válido.
- Constraints preservadas.
- Budget respetado.
- Ejecución completada.

### 7.2 Evidence retrieval

- `evidence_recall`;
- `claim_coverage`;
- `evidence_precision`;
- `source_diversity`;
- `evidence_sufficiency`;
- retrieval rounds;
- retrieval latency.

### 7.3 Evidence selection y contexto

- `selection_coverage`;
- claims cubiertos por `EvidenceSelection`;
- `context_budget_compliance`;
- diversidad de fuentes;
- citas y provenance preservados.

### 7.4 Answer y VERIFY

- `claim_supported_rate`;
- `claim_weakly_supported_rate`;
- `claim_unsupported_rate`;
- `claim_contradiction_rate`;
- `citation_fidelity`;
- `evidence_attribution_accuracy`;
- `evidence_overreach_rate`;
- `hallucination_rate`;
- `decline_correctness`;
- `verify_pass`.

`evidence_attribution_accuracy` mide la proporción de enlaces claim-evidence correctos respecto del total de enlaces declarados o inferidos por la respuesta. Una respuesta puede ser factualmente correcta y, aun así, citar evidencia que no soporta el claim.

`evidence_overreach_rate` mide cuándo la respuesta extiende el alcance de la evidencia: por ejemplo, transformar “puede reducir el riesgo” en “previene completamente los ataques”. Esta señal debe considerar `claim_scope` y no solo similitud textual.

`doc_hit@K`, `page_hit@K`, MRR y scores BM25/vector/reranker se conservan como métricas diagnósticas y de continuidad histórica. No deben seguir siendo el único gate de calidad.

---

## 8. Suites y categorías

La suite canónica debe conservar las 75 preguntas y añadir etiquetas de evaluación:

```text
core_factual
multi_source_synthesis
no_answer
ambiguous
artifact_dependent
retrieval_equivalence
```

### 8.1 Core factual

Definiciones, acrónimos, comandos y frameworks con claims simples.

### 8.2 Multi-source synthesis

Preguntas que requieren combinar documentos o claims.

### 8.3 No-answer / insufficient evidence

Casos donde el sistema debe declinar correctamente. Son esenciales para Evidence Evaluation.

### 8.4 Unsupported answer / negative capability

Categoría explícita para evaluar cuándo el sistema **no debe responder afirmativamente** porque el corpus no contiene evidencia suficiente.

Ejemplo:

```text
Pregunta: ¿Cuál es la contraseña por defecto de X producto?
Respuesta correcta: No existe evidencia suficiente en el corpus.
```

Estos casos deben tener peso alto: un sistema que responde siempre puede inflar su pass rate. La suite debe medir:

- decline cuando corresponde;
- ausencia de claims inventados;
- ausencia de citas falsas;
- calibración entre confianza y suficiencia;
- separación entre `unsupported_answer` y una respuesta incorrecta por mala generación.

### 8.5 Ambiguous

Casos donde el sistema debe pedir aclaración o declarar el alcance de su interpretación.

### 8.6 Artifact-dependent

Casos que dependen de canonical IDs, aliases, entities, relations o roles producidos por Builder.

### 8.7 Retrieval equivalence

Casos donde múltiples fuentes pueden soportar el mismo conocimiento y la eliminación de duplicados no debe penalizar una respuesta válida.

---

## 9. Matriz de comparación Builder / Consumer

Para medir la evolución sin mezclar variables, se proponen estos runs:

| Run | Corpus | Builder | Consumer | Objetivo |
|---|---|---|---|---|
| A | Histórico | Viejo | Viejo | Baseline histórico |
| B | Reducido | Nuevo | Viejo | Impacto del corpus y Builder consumido por Consumer legacy |
| C | Reducido | Nuevo | Nuevo | Evolución completa |
| D | Histórico | Nuevo | Viejo | Aislar impacto del Builder |
| E | Histórico | Nuevo | Nuevo | Aislar Consumer sobre corpus histórico |

Los runs D y E son experimentos conceptualmente obligatorios para la atribución causal, aunque no sean necesarios para cada ejecución operativa diaria. Si el corpus histórico no está disponible físicamente, la ausencia debe registrarse como una limitación experimental explícita y no tratarse como si el experimento hubiera sido ejecutado.

La matriz permite estimar:

```text
Builder artifact contribution
+ Consumer contribution
+ interaction effect
```

De forma conceptual:

```text
B - A = efecto conjunto de corpus reducido + Builder nuevo
D - A = efecto del Builder nuevo sobre corpus histórico
E - D = efecto del Consumer nuevo sobre conocimiento histórico compilado
C - B = efecto adicional del Consumer nuevo sobre corpus reducido
```

Cada reporte debe declarar:

```text
benchmark_version
corpus_version
builder_version
consumer_version
artifact_build_id
contract_version
evaluation_contract
```

---

## 10. Versionado recomendado

```text
tests/eval/
├── legacy/
│   ├── cybersec_eval_questions_v1.json
│   └── reports/
├── canonical/
│   ├── cybersec_eval_questions_v2.json
│   ├── claim_catalog.json
│   ├── evidence_equivalences.json
│   └── reports/
└── manifests/
    ├── corpus_legacy.json
    ├── corpus_reduced.json
    └── benchmark_runs.json
```

### v1 — Legacy

- Preguntas originales.
- Expected sources/pages originales.
- Métricas históricas.
- Contrato `HybridRAG.query`.
- Inmutable.

### v2 — Canonical evidence

- Claims externos al Builder.
- Evidence requirements.
- Equivalencias verificadas de documentos y claims.
- No-answer y `unsupported_answer` policy.
- Evaluación de cobertura y suficiencia.
- Evidence Evaluation simulada en el evaluator a partir de la salida actual del Consumer.
- Compatible con Builder nuevo y Consumer viejo mediante adapters.

### v3 — Agentic execution

La especificación de `benchmark-v3` fue separada en **RES-013 — Benchmark v3 como contrato autoritativo de evaluación para Agentic RAG**. Este documento solo conserva la referencia histórica de coexistencia y no define el contrato v3.

### 10.1 Benchmark migration status

Los tres instrumentos pueden coexistir, pero no son automáticamente comparables. Todo dataset, harness y reporte debe declarar explícitamente su versión y estado.

```text
legacy-v1
STATUS: frozen
PURPOSE: preservar la medición histórica del RAG híbrido anterior
COMPARABILITY: comparable únicamente con runs legacy-v1 bajo corpus/configuración equivalente

canonical-v2
STATUS: migration-in-progress
PURPOSE: migrar desde document/page matching hacia claims, evidencia y suficiencia
COMPARABILITY: no comparable directamente con pass rate legacy-v1

agentic-v3
STATUS: planned
PURPOSE: evaluar QueryIR, RetrievalPlan, Evidence Evaluation runtime, EvidenceSelection, ContextPackage y policies
COMPARABILITY: no comparable directamente con v1 ni v2 salvo mediante métricas puente documentadas
```

Reglas de interpretación:

1. Un resultado `canonical-v2` nunca debe presentarse como mejora o regresión directa de `legacy-v1`.
2. La comparación entre versiones requiere métricas puente, casos compartidos y un reporte de diferencias.
3. `legacy-v1` no se modifica para facilitar la comparación.
4. `canonical-v2` puede cambiar durante la migración, pero cada cambio debe incrementar su versión menor o registrar un changelog.
5. `agentic-v3` no se considera activo hasta que sus contratos y evaluator estén aprobados.
6. Todo reporte debe incluir `benchmark_version`, `benchmark_status`, `evaluation_contract` y `comparability_notes`.

Ejemplo mínimo de metadata de reporte:

```json
{
  "benchmark_version": "canonical-v2",
  "benchmark_status": "migration-in-progress",
  "evaluation_contract": "evidence-v1",
  "comparability_notes": "No comparar pass_rate directamente con legacy-v1",
  "bridge_metrics": [
    "answerable_pass_rate",
    "claim_coverage",
    "groundedness",
    "decline_correctness",
    "doc_hit_at_k_diagnostic"
  ]
}
```

---

## 11. Non-goals

Este research no busca:

- borrar o reescribir el benchmark histórico;
- hacer que el benchmark nuevo sea artificialmente comparable con el antiguo;
- eliminar inmediatamente la evaluación por documento/página;
- asumir que dos documentos son equivalentes por nombre;
- introducir una ontología de consultas;
- convertir el benchmark en un Knowledge Model;
- generar expected claims desde KIR, Knowledge Model o Warm Artifacts del mismo Builder que se evalúa;
- evaluar el sistema contra sus propios artifacts;
- usar el LLM como juez único de evidencia;
- cambiar el Builder o el Consumer en este documento;
- publicar un nuevo ADR sin validar primero la equivalencia del corpus y los contratos de evaluación.

---

## 12. Plan incremental de trabajo

### Fase 0 — Congelar historia

1. Copiar o identificar formalmente el dataset legacy actual como `v1` sin modificar su contenido.
2. Congelar y documentar los reportes históricos existentes.
3. Registrar corpus, commit, configuración, modelo y Consumer usados en cada baseline.

### Fase 1 — Manifest y auditoría de corpus

1. Resolver la diferencia entre 203 y 208 documentos excluidos.
2. Generar manifest del corpus histórico y corpus reducido.
3. Comparar expected sources contra archivos activos, excluidos y candidatos duplicados.
4. Crear clasificación de cobertura por pregunta.

### Fase 2 — Canonicalización del dataset

1. Crear `v2` a partir de las 75 preguntas, conservando `legacy_id`.
2. Extraer claims y requisitos de evidencia.
3. Registrar equivalencias verificadas.
4. Separar expected knowledge, accepted evidence y observed evidence.
5. No eliminar casos inciertos; marcarlos como `uncertain_requires_review`.

### Fase 2.5 — Benchmark shadow mode

Antes de utilizar la evaluación canónica como métrica de decisión, ejecutar legacy evaluator y canonical evaluator sobre los mismos resultados, sin cambiar comportamiento ni gates.

Registrar:

- casos `legacy_fail -> canonical_pass`;
- casos `legacy_pass -> canonical_fail`;
- preguntas sin claims suficientemente definidos;
- diferencias por fuente equivalente;
- diferencias entre coincidencia de keywords y soporte real de evidencia.

Interpretación inicial:

```text
legacy_fail -> canonical_pass
  posible falso negativo por recuperar evidencia equivalente

legacy_pass -> canonical_fail
  posible keyword match con evidencia débil, incorrecta o sobreextendida
```

El shadow mode es observacional: no toma decisiones de producto, no modifica el pass rate y no altera el pipeline.

### Fase 3 — Evaluator canónico compatible

1. Mantener el harness legacy intacto.
2. Añadir un evaluator canónico que inicialmente opere sobre la salida actual del Consumer.
3. Simular Evidence Evaluation dentro del evaluator, sin esperar a que exista `EvidenceEvaluationCapability` en runtime.
4. Mapear chunks actuales a `EvidenceItem` mediante adapter.
5. Calcular `required_claims`, `obtained_claim_coverage` y `minimum_evidence_quality` sobre la evidencia observada.
6. Mantener doc/page metrics como diagnósticos.
7. Añadir decisiones de suficiencia, `unsupported_answer`, decline y aclaración según el contrato canónico.

### Fase 4 — Builder y Consumer actuales

1. Ejecutar Run B: Builder nuevo + Consumer viejo sobre corpus reducido.
2. Ejecutar Run C cuando el Consumer contractual esté disponible.
3. Comparar siempre por benchmark version, corpus version, builder version y consumer version.
4. No presentar el nuevo pass rate como mejora histórica directa.

### Fase 5 — Benchmark v3

La definición y roadmap de `benchmark-v3` fueron separados en RES-013. RES-012 termina en la migración y evaluación canónica de `v2`.

---

## 13. Criterios de éxito

- Los resultados legacy siguen siendo reproducibles y no se modifican.
- Cada run nuevo declara corpus, Builder, Consumer y contrato de evaluación.
- Ninguna pregunta se elimina solo porque desapareció un filename.
- Las equivalencias se verifican por contenido/provenance y no solo por nombre.
- El benchmark canónico puede aceptar evidencia equivalente sin perder trazabilidad.
- `doc_hit@K` permanece disponible como diagnóstico histórico.
- Evidence Evaluation y VERIFY se reportan como problemas distintos.
- El mismo conjunto de 75 preguntas puede ejecutarse en legacy, canonical y futuro Agentic benchmark.
- El benchmark puede determinar si un cambio proviene del corpus, Builder o Consumer.

---

## Comparativa

| Aspecto | Benchmark legacy | Benchmark canónico | Benchmark futuro Agentic |
|---|---|---|---|
| Unidad principal | Documento/página | Claim/evidencia | Query + plan + evidencia + decisión |
| Fuente de verdad | Expected sources/pages | Expected claims + accepted evidence | Contracts + policies + observed trace |
| Retrieval gate | Doc/page hit | Evidence/claim coverage | Evidence sufficiency y policy decision |
| Generación | Keywords y forbidden content | Claims soportados | Claims, provenance y VERIFY |
| No-answer | Frases de decline | Suficiencia insuficiente | Evidence Evaluation + decline policy |
| Corpus | Implícito o histórico | Manifest explícito | Artifact/corpus/build versionado |
| Compatibilidad | RAG híbrido anterior | Builder nuevo + Consumer actual | Agentic Consumer |
| Estado | Congelado | Evolutivo | Objetivo futuro |

---

## Takeaways

1. El benchmark histórico debe conservarse sin cambios.
2. La nueva evaluación debe migrar de documentos esperados hacia claims y evidencia aceptada.
3. La desaparición de un archivo no demuestra pérdida de conocimiento; hay que auditar duplicados y equivalencias.
4. La suite canónica debe conservar las 75 preguntas y añadir `legacy_id`, claims y requisitos de evidencia.
5. `doc_hit@K` debe mantenerse como diagnóstico y continuidad histórica, no como único gate.
6. Los manifests son necesarios para separar impacto de corpus, Builder y Consumer.
7. El Builder nuevo + Consumer viejo es un experimento válido y debe ser el primer run de migración.
8. La evaluación futura debe medir Evidence Evaluation antes de Reasoning y VERIFY después de Generation.
9. El benchmark canónico no debe convertirse en un segundo Knowledge Model.
10. Los claims esperados deben ser externos, humanos y auditables; el Builder no puede generar el ground truth final.
11. `canonical_form` es una ayuda humana; la verdad computable debe apoyarse en estructura semántica y policies de equivalencia.
12. `evidence_attribution_accuracy` y `evidence_overreach_rate` complementan groundedness y citation fidelity.
13. D y E son experimentos conceptualmente obligatorios para atribuir Builder artifact contribution y Consumer contribution.
14. El shadow mode debe preceder cualquier uso normativo del benchmark canónico.
15. Antes de congelar contratos nuevos, se debe proponer un ADR específico de evaluación canónica y equivalencia de evidencia.
