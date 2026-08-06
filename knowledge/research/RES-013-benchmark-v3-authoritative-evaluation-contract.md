---
id: RES-013
category: research
status: proposed
created: 2026-08-06
updated: 2026-08-06
author: human
components: [evaluation, benchmark, knowledge-builder, knowledge-consumer, retrieval, generation, policies, observability, facade]
tags: [benchmark-v3, evaluation-contract, agentic-rag, deterministic-evaluation, compliance, evidence-policy, decision-policy, runtime-observation, claim-coverage, provenance, negative-capability]
related: [RES-001, RES-002, RES-003, RES-011, RES-012, ADR-0006, ADR-0018, ADR-0019, ADR-0020, ADR-0022, DEC-009, BM-005]
supersedes: null
superseded_by: null
---

# RES-013 — Benchmark v3 como contrato autoritativo de evaluación para Agentic RAG

## Topic

Diseñar `benchmark-v3` como un contrato externo, determinista y auditable que valide si un sistema Agentic RAG ejecutó una tarea cognitiva respetando contratos, políticas, evidencia, provenance y límites explícitos.

## Sources

- RES-012: Migración del benchmark histórico hacia evaluación canónica por evidencia.
- RES-011: Auditoría y evolución de la arquitectura Consumer basada en evidencia.
- RES-001: Contrato Warm como centro arquitectónico.
- RES-002: Knowledge Builder / Knowledge Compiler.
- RES-003: Knowledge Consumer / evolución del runtime.
- ADR-0006: Evaluation transversal.
- ADR-0018: Knowledge Builder / Consumer split.
- ADR-0019: Contrato epistémico y VERIFY a nivel de claims.
- ADR-0020: Ownership de decisiones y contrato de ejecución observable.
- ADR-0022: Contrato canónico de documento.
- DEC-009: Métricas de producto frente a métricas de ingeniería.
- Código actual: `tests/eval/canonical/`, `knowledge_builder/kir/`, `knowledge_builder/model/`, `contract/warm-v1/`, `src/kernel/state.py`, `src/evaluation/verify_groundedness.py`.

---

## 1. Contexto

El sistema evoluciona desde:

```text
Query -> chunks -> context -> answer
```

hacia:

```text
Query
  -> QueryIR
  -> RetrievalPlan
  -> EvidenceSet
  -> Evidence Evaluation
  -> EvidenceSelection
  -> ContextPackage
  -> Reasoning
  -> VERIFY
```

El benchmark histórico `legacy-v1` queda congelado. `canonical-v2`, documentado en RES-012, es una migración basada en claims y evidencia, pero todavía depende de adapters porque el Consumer actual no produce todos los artifacts contractuales.

`benchmark-v3` no debe ser simplemente un benchmark más sofisticado. Debe ser un **Evaluation Contract** que funcione como un sistema de compliance y evalúe estados de ejecución:

```text
Benchmark Contract
        |
        v
Policy Set
        |
        v
Runtime Observation
        |
        v
Deterministic Evaluator
        |
        v
PASS / FAIL / INVALID
```

La unidad principal de evaluación no es la respuesta textual. Es el estado producido por la ejecución respecto al contrato. La respuesta es una proyección final que puede expresarse como texto, voz, API, acción de herramienta o código generado sin cambiar el núcleo del benchmark.

---

## 2. Objetivo

Benchmark v3 debe responder determinísticamente:

> ¿El sistema ejecutó una tarea cognitiva respetando los contratos, políticas y límites definidos?

No pretende decidir si el modelo es inteligente. Pretende comprobar si la ejecución cumple una especificación externa.

---

## 3. Principio de autoridad

```text
La autoridad son los contratos.
```

El benchmark debe:

- definir contratos explícitos;
- definir claims esperados estructurados;
- definir políticas de evidencia;
- definir decisiones permitidas;
- validar trazabilidad y provenance;
- validar límites y condiciones de invalidez;
- producir `PASS`, `FAIL` o `INVALID` de forma determinista.

El benchmark no debe:

- usar un LLM como juez final;
- decidir si una respuesta “parece correcta”;
- inferir equivalencias semánticas libremente;
- evaluarse contra artifacts generados por el mismo Builder;
- aceptar respuestas por similitud textual global;
- mezclar generación probabilística con el criterio de aceptación.

### LLM auxiliar, nunca autoridad

El LLM puede actuar como parser o asistente no autoritativo:

```text
LLM auxiliar:
  "Esta frase parece contener el claim X"
        |
        v
Policy Engine / evaluator determinista:
  valida estructura, evidencia y policy
        |
        v
PASS / FAIL / INVALID
```

Puede ayudar a:

- proponer claims candidatos;
- extraer relaciones candidatas de una respuesta;
- detectar spans candidatos;
- asistir a un revisor humano.

No puede:

- aprobar claims;
- decidir equivalencias;
- validar evidencia;
- decidir PASS, FAIL o INVALID;
- reemplazar la policy determinista.

La frontera es equivalente a:

```text
Extractor != Compiler
LLM parser != Policy Engine
```

---

## 4. Non-goals

Este research no busca:

- reemplazar `legacy-v1` ni `canonical-v2`;
- modificar las métricas históricas;
- crear un segundo Knowledge Model;
- generar el benchmark desde KIR, Knowledge Model o Warm Artifacts;
- usar un LLM como autoridad de aceptación;
- convertir `claim_id` en texto libre evaluado por matching;
- decidir cómo implementa internamente el Consumer sus capabilities;
- introducir agentes autónomos dentro del benchmark;
- sustituir VERIFY del runtime;
- hacer que el benchmark publique o modifique conocimiento;
- activar gates en producción antes de que existan Runtime Artifacts contractuales.

---

## 5. Separación de responsabilidades

### 5.1 Benchmark Contract

Define:

- conocimiento requerido;
- claims esperados;
- evidencia aceptable;
- provenance requerido;
- decisiones permitidas;
- condiciones de fallo;
- condiciones de invalidez;
- límites de ejecución relevantes.

No depende del Builder y no se genera automáticamente desde él.

### 5.2 Policy Set

Las policies no son el contrato de conocimiento. Son la exigencia operacional aplicada al contrato.

El `Benchmark Contract` define qué se requiere; el `Policy Set` define cómo se clasifica el incumplimiento.

Ejemplo:

```json
{
  "missing_required_claim": "FAIL",
  "missing_provenance": "FAIL",
  "unsupported_claim": "FAIL",
  "invalid_contract_version": "INVALID"
}
```

El mismo caso puede evaluarse con diferentes policies sin cambiar el conocimiento esperado:

```text
development-policy:
  require_provenance: false

production-policy:
  require_provenance: true
```

Las policies deben ser versionadas, puras, deterministas y separadas del contenido del caso.

### 5.3 Runtime Observation

El Consumer produce artifacts observables. El benchmark no modifica esa salida.

Ejemplo conceptual:

```json
{
  "answer": "...",
  "decision": {
    "type": "answer"
  },
  "evidence_set": [
    {
      "artifact_id": "doc:iso27001",
      "span_id": "doc:iso27001#c03",
      "provenance": {
        "source_doc_id": "doc:iso27001",
        "source_chunk_ids": ["doc:iso27001#c03"],
        "quote": "..."
      },
      "supports_claims": ["cia-confidentiality"]
    }
  ],
  "verification": {
    "status": "passed"
  }
}
```

El ejemplo describe el contrato objetivo, no el output actual. Actualmente el Consumer produce `answer`, `sources`, `context`, `results`, `signals` y `traces`; la transición debe utilizar adapters explícitos.

### 5.4 Deterministic Evaluator

El evaluator determinista aplica el `Policy Set` al `Benchmark Contract` y al `Runtime Observation`. No llama al LLM, no modifica el estado y no decide retrieval.

---

## 6. Estructura del contrato v3

```text
tests/eval/
|
├── legacy/
|
├── canonical-v2/
|
└── contract-v3/
    |
    ├── cases/
    ├── claim_contracts/
    ├── evidence_policies/
    ├── decision_policies/
    ├── manifests/
    └── reports/
```

Cada caso representa un contrato:

```json
{
  "case_id": "cia-triad-001",
  "query_contract": {
    "query": "¿Qué significa CIA en ciberseguridad?"
  },
  "knowledge_contract": {
    "required_claims": [
      "cia-confidentiality",
      "cia-integrity",
      "cia-availability"
    ]
  },
  "evidence_policy": {
    "minimum_claim_coverage": 1.0,
    "minimum_evidence_quality": 0.7,
    "require_provenance": true,
    "allow_unsupported_inference": false
  },
  "decision_policy": {
    "allowed_decisions": ["answer"]
  },
  "failure_policy": {
    "unsupported_claims": "fail",
    "missing_evidence": "fail",
    "fake_citation": "fail",
    "invalid_provenance": "fail"
  }
}
```

El contrato no debe exigir que una evidencia individual cubra todos los claims. La política evalúa el conjunto:

```text
required_claims ⊆ supported_claims
```

Y reporta:

```text
required_claims: 3
covered_claims: 3
claim_coverage: 1.0
evidence_quality: 0.82
```

---

## 7. Claims estructurados

Los claims no son texto computable.

No usar como autoridad:

```json
{
  "claim": "Confidentiality protects information"
}
```

Preferir:

```json
{
  "claim_id": "cia-confidentiality",
  "subject": "CIA_triad",
  "required_relation": "includes",
  "object": "confidentiality",
  "claim_scope": {
    "condition": null
  }
}
```

`human_description` y `canonical_form` pueden existir como ayuda de revisión, pero no deben ser la verdad computable. La evaluación debe operar sobre estructuras y policies de relación.

La autoridad de claims debe ser externa:

```text
Human evaluator
       |
       v
Benchmark Contract v3
       |
       v
Builder
       |
       v
Consumer
```

El Builder puede sugerir candidatos, pero no aprobar claims, equivalencias ni el resultado de evaluación.

Los contratos de claims deben incluir:

```json
{
  "ground_truth_source": "human_reviewed",
  "review_status": "approved",
  "reviewer": "...",
  "review_date": "2026-08-06",
  "contract_version": "3.0.0"
}
```

---

## 8. Políticas deterministas

### 8.1 Claim coverage

```text
required_claims ⊆ supported_claims
```

Si falta un claim requerido:

```text
FAIL: missing_required_claim
```

### 8.2 Unsupported claims

```text
generated_claims - supported_claims == empty
```

Si la respuesta contiene claims no soportados:

```text
FAIL: unsupported_claim
```

### 8.3 Evidence provenance

Cada claim aceptado debe tener evidencia trazable:

```text
claim
  -> evidence_item
      -> artifact_id
      -> source_doc_id
      -> source_chunk_id/span_id
      -> quote/provenance
```

Si falta provenance requerido:

```text
FAIL: missing_provenance
```

### 8.4 Evidence attribution

La evidencia debe soportar el claim al cual está vinculada:

```text
correct_claim_evidence_links
    /
total_claim_evidence_links
```

Si el estado declara un enlace claim-evidence incorrecto, aunque la proyección textual parezca correcta:

```text
FAIL: incorrect_evidence_attribution
```

Esta regla evita que una ejecución sea aceptada con una justificación de evidencia incorrecta.

### 8.5 Evidence overreach

La respuesta no puede ampliar el alcance de la evidencia.

Ejemplo:

```text
evidence: "puede reducir el riesgo"
answer:   "previene completamente los ataques"
```

Resultado:

```text
FAIL: evidence_overreach
```

La evaluación debe comparar `claim_scope`, sujeto, condición, modalidad y fuerza de la afirmación.

### 8.6 Decline policy

Si la política determina:

```text
evidence_sufficiency == false
```

la decisión esperada es:

```text
expected_decision = decline
```

Responder afirmativamente:

```text
FAIL: should_have_declined
```

Declinar cuando la evidencia es suficiente:

```text
FAIL: unjustified_decline
```

### 8.7 Invalid execution

`INVALID` no es lo mismo que `FAIL`.

Usar `INVALID` cuando no puede determinarse justamente el resultado, por ejemplo:

- falta el manifest del artifact build;
- el runtime artifact no tiene la versión de contrato declarada;
- la evidencia no tiene identidad resoluble;
- el caso benchmark no tiene ground truth aprobado;
- el reporte está incompleto o corrupto;
- el evaluator detecta una incompatibilidad de schema.

Un sistema que incumple una regla con artifacts válidos produce `FAIL`. Una ejecución que no puede evaluarse produce `INVALID`.

---

## 9. Decisiones permitidas

Cada caso debe declarar las decisiones válidas:

```text
answer
decline
clarify
retry_retrieval
partial_answer
```

La política del caso puede restringirlas:

```json
{
  "allowed_decisions": ["decline"]
}
```

El benchmark no debe decidir si el Consumer usa una capability concreta. Solo valida que la decisión observada pertenece al conjunto permitido y respeta las condiciones del contrato.

---

## 10. Violation severity

No todas las violaciones tienen el mismo impacto. El evaluator debe emitir violaciones estructuradas con severidad:

```json
{
  "violations": [
    {
      "type": "fake_provenance",
      "severity": "critical",
      "claim_id": "cia-confidentiality",
      "message": "Evidence provenance does not resolve to the observed artifact."
    }
  ]
}
```

Niveles iniciales:

```text
critical
  fake_provenance
  hallucinated_citation
  unauthorized_claim
  answer_without_required_evidence
  forbidden_transition

major
  missing_required_claim
  evidence_overreach
  incorrect_evidence_attribution
  unjustified_decline
  required_step_missing

minor
  missing_optional_metadata
  incomplete_non-authoritative trace detail
```

La severidad debe influir en la decisión mediante el `Policy Set`, no estar codificada de forma implícita en el evaluator. Una policy puede establecer:

```text
critical -> FAIL obligatorio
major    -> FAIL en producción, warning en desarrollo
minor    -> warning o PASS con diagnóstico
```

`INVALID` sigue reservado para imposibilidad de evaluar, schema incompatible o falta de artifacts mínimos; no es una severidad.

---

## 11. Execution Integrity Contract

Benchmark v3 no evalúa solamente conocimiento y evidencia. También valida la integridad de la ejecución: si el sistema llegó al estado observado siguiendo un camino autorizado.

El resultado correcto obtenido por un camino inválido no debe aprobar automáticamente.

Ejemplo de contrato:

```json
{
  "execution_policy": {
    "required_steps": [
      "query_analysis",
      "retrieval",
      "evidence_evaluation",
      "verification"
    ],
    "forbidden_transitions": [
      "answer_without_evidence",
      "answer_without_retrieval",
      "skip_evidence_evaluation"
    ],
    "required_artifacts": [
      "decision",
      "evidence_state",
      "verification"
    ]
  }
}
```

La ejecución debe poder demostrar, mediante `Runtime Observation` y traces verificables:

- qué pasos se ejecutaron;
- en qué orden o relación causal;
- qué capabilities fueron requeridas y cuáles se ejecutaron;
- qué presupuesto se consumió;
- qué decisión produjo cada policy;
- si se saltó una etapa obligatoria;
- si se respondió sin evidencia suficiente.

Casos:

```text
respuesta correcta + retrieval no ejecutado
  -> FAIL: required_step_missing

"No tengo suficiente evidencia" + evidence evaluation ejecutada y suficiente=false
  -> PASS si decline está permitido

"No tengo suficiente evidencia" + retrieval/evidence evaluation omitidos
  -> FAIL o INVALID según la disponibilidad de traces contractuales
```

`Execution Integrity Contract` no prescribe una implementación interna concreta. Valida que el camino observado cumpla las transiciones y pasos exigidos por el caso/policy.

---

## 12. Compatibilidad con Builder y Consumer

### 10.1 Builder actual

El Builder produce actualmente:

- KIR;
- Entity/Document/Alias/Relation claims;
- Warm Artifacts;
- confidence;
- validated;
- builder_version;
- generated_by;
- evidence parcial con `source_doc_id`, `source_chunk_ids` y `quote`.

Esto es suficiente para diseñar el contrato v3, pero no para activar todos sus gates. En particular, `claim_scope` y links completos entre claims de respuesta y evidencia todavía no son un contrato Warm v1 completo.

### 10.2 Consumer actual

El Consumer produce actualmente:

- `answer`;
- `sources`;
- `results` como dicts de retrieval;
- `context` como string;
- `ExecutionState`;
- `EvaluationSignal`;
- `TraceEvent`;
- VERIFY posterior a generación.

Todavía no produce de forma nativa:

- `EvidenceSet` contractual;
- `EvidenceEvaluationResult`;
- `EvidenceSelection`;
- `ContextPackage`;
- claim-evidence links estructurados;
- decision artifact completo.

### 10.3 Adapter temporal

Mientras el Consumer migra:

```text
legacy Consumer output
        |
        v
Runtime Observation Adapter v0
        |
        v
Benchmark v3 evaluator en shadow mode
```

El adapter debe declarar explícitamente sus limitaciones:

```json
{
  "observation_contract": "adapter-v0",
  "provenance_status": "partial",
  "claim_link_status": "unavailable",
  "evaluation_status": "shadow-only"
}
```

No debe inventar `supports_claims`, `claim_scope` o provenance que el runtime no produjo.

---

## 13. Estados de activación

```text
benchmark-v3
STATUS: specification-only
GATES: disabled
```

Estados posteriores:

```text
specification-only
adapter-shadow
contract-observation
hard-gates-enabled
```

La activación debe ser monotónica y explícita:

1. `specification-only`: contrato definido, sin ejecución normativa.
2. `adapter-shadow`: evaluator compara resultados, no cambia pass/fail de producción.
3. `contract-observation`: runtime produce artifacts contractuales y evaluator valida schema.
4. `hard-gates-enabled`: PASS/FAIL/INVALID afecta el criterio oficial del run.

---

## 14. Roadmap

### Fase 1 — Definir contrato v3

- Crear schemas de cases, claims, evidence policies, decision policies y runtime observation.
- Definir estados `PASS`, `FAIL`, `INVALID`.
- Definir reglas de provenance, attribution, overreach y decline.
- Sin ejecución normativa.

### Fase 2 — Alinear Consumer

Agregar artifacts observables:

- EvidenceSet;
- claim links;
- provenance;
- decision artifact;
- verification result estructurado.

El Consumer sigue siendo read-only respecto del conocimiento Builder.

### Fase 3 — Implementar evaluator determinista

- Validar schemas.
- Evaluar policies puras.
- Generar razones estructuradas de PASS/FAIL/INVALID.
- No usar LLM como juez.
- No modificar la ejecución observada.

### Fase 4 — Activar gates duros

Solo después de:

- casos con ground truth aprobado;
- artifacts runtime completos;
- paridad del evaluator shadow;
- reporte de incompatibilidades;
- aprobación explícita de la transición.

---

## 15. Criterios de éxito

- El benchmark no depende de artifacts del Builder evaluado para crear ground truth.
- El evaluator produce `PASS`, `FAIL` o `INVALID` determinísticamente.
- Los claims se evalúan estructuralmente, no por texto libre.
- Cada claim aceptado tiene provenance verificable.
- Las atribuciones claim-evidence incorrectas fallan.
- El evidence overreach falla aunque la respuesta sea parcialmente correcta.
- Las respuestas afirmativas sin evidencia suficiente fallan.
- Las ejecuciones no evaluables se distinguen como `INVALID`.
- La integridad del camino de ejecución se valida además del conocimiento y la evidencia.
- Las violaciones incluyen severidad y policy explícita.
- El LLM nunca decide la aceptación final.
- El adapter temporal no inventa campos ausentes.
- Los hard gates permanecen desactivados hasta que el runtime produzca el contrato necesario.

---

## Takeaways

1. Benchmark v3 es un contrato de compliance, no un juez de inteligencia.
2. La autoridad está en el contrato externo y en policies deterministas.
3. El Builder produce artifacts; no produce el ground truth del benchmark.
4. El Consumer produce runtime observations; el benchmark no modifica esa salida.
5. `PASS`, `FAIL` e `INVALID` tienen semánticas diferentes y no deben mezclarse.
6. Claim coverage, provenance, attribution, overreach y decline son políticas separadas.
7. El benchmark puede especificarse ahora, pero no activarse completamente hasta alinear el Consumer.
8. La transición correcta es `specification-only -> adapter-shadow -> contract-observation -> hard-gates-enabled`.
9. El resultado final no responde si el modelo es inteligente; responde si cumplió un contrato explícito.
