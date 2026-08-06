---
id: RES-011
category: research
status: proposed
created: 2026-08-06
updated: 2026-08-06
author: human
components: [consumer, kernel, capabilities, retrieval, evidence, evidence-evaluation, evidence-selection, context-package, planner, reasoning, verify, warm-artifacts]
tags: [architecture, consumer, agentic-rag, evidence-contract, evidence-quality, claim-scope, context-package, query-ir, retrieval, verification, non-goals]
related: [RES-001, RES-003, RES-008, RES-010, ADR-0015, ADR-0018, ADR-0019, ADR-0020, ADR-0022, DEC-008, DEC-009, DEC-010, BM-005]
supersedes: null
superseded_by: null
---

# RES-011 — Auditoría y evolución de la arquitectura Consumer basada en evidencia

## Topic

Auditar el Consumer actual y definir una evolución incremental desde retrieval de chunks hacia un pipeline contractual de evidencia, manteniendo la autoridad en los contratos y sin convertir Query IR, EvidenceSet o ContextPackage en un segundo Knowledge Builder.

## Sources

- RES-001: El contrato Warm como centro arquitectónico.
- RES-003: Knowledge Consumer / evolución del Agentic RAG runtime.
- RES-008: Capability-Oriented Execution Model.
- RES-010: Contrato canónico de documento.
- ADR-0015: Knowledge System como subsistema, no store.
- ADR-0018: Knowledge Builder / Consumer split con Artifact Registry.
- ADR-0019: Contrato epistémico y VERIFY a nivel de claims.
- ADR-0020: Ownership de decisiones y contrato de ejecución observable.
- ADR-0022: Contrato canónico de documento, Single Producer, Downward-Only Flow y Materialized Views.
- DEC-008: Planner determinista, entity expansion y tunings de retrieval.
- DEC-009: Métricas de producto frente a métricas de ingeniería.
- DEC-010: Modo de entidades en retrieval: boost acotado frente a filtro duro.
- BM-005: Consumer con Warm Artifacts frente a baseline Kernel.
- Código inspeccionado: `rag_hybrid.py`, `retrieval_engine.py`, `context_builder.py`, `query_classifier.py`, `src/bootstrap.py`, `src/kernel/state.py` y `src/capabilities/*`.

---

## 1. Motivación

El Consumer ya posee una separación inicial entre Kernel, capabilities, policies, retrieval, generación, evaluación y Warm Artifacts. Sin embargo, las interfaces internas no tienen el mismo nivel de formalidad que el contrato de ejecución.

El flujo actual todavía se aproxima a:

```text
Query -> chunks -> contexto textual -> LLM -> VERIFY
```

Los resultados de retrieval se transportan como `dict`, el contexto como `str` y múltiples decisiones se pasan por `ExecutionState.metadata`. Esto permite que retrieval, ranking, selección de evidencia, construcción de contexto y razonamiento se compensen entre sí mediante heurísticas y prompts.

La hipótesis de esta investigación es:

> El Consumer mezcla responsabilidades de retrieval, interpretación operacional de consulta, selección de evidencia, construcción de contexto y razonamiento final, haciendo que el LLM compense contratos incompletos.

La hipótesis queda **parcialmente validada y arquitectónicamente confirmada**. Existen boundaries válidos, pero el output de retrieval todavía no es una representación contractual de evidencia y no existe una fase explícita de evaluación de suficiencia antes de razonar.

---

## 2. Arquitectura actual observada

```text
CLI / Web / Harness
        |
        v
HybridRAG.execute()
        |
        +--> Kernel path
        |      |
        |      +--> ExecutionState
        |      +--> classify
        |      +--> memory_read
        |      +--> planner
        |      +--> entity_expansion
        |      +--> retrieval adapter
        |      |      +--> hybrid search
        |      |      +--> reranking
        |      |      +--> candidate/entity boosts
        |      +--> build_context
        |      +--> assess
        |      +--> generation
        |      +--> verify
        |      +--> policies: retry / repair / decline
        |      +--> ExecutionResult
        |
        +--> Linear path / LinearStateAdapter

query() permanece como fachada dict de compatibilidad.
```

### 2.1 Responsabilidades y límites actuales

| Componente | Responsabilidad actual | Riesgo observado |
|---|---|---|
| `HybridRAG.execute()` | Fachada y selección de camino | Aún conserva parámetros históricos de estrategia |
| `ClassifyCapability` / `QueryClassifier` | Clasificación y extracción parcial | No producen un Query Contract operacional único |
| `PlannerCapability` | Tipo de consulta, roles, candidate docs y peso semántico | Plan representado como `dict`; mezcla varias decisiones |
| `EntityExpansionCapability` | Expansión de entidades | Canal lateral mediante metadata |
| `RetrievalEngine` | Embeddings, BM25, fusión y reranking | Retrieval y ranking comparten representaciones ad-hoc |
| `RetrievalCapability` | Retrieval, expansión de query, boosts y retry state | Mezcla ejecución de retrieval con scoring y housekeeping |
| `ContextBuilder` | Selección implícita, truncamiento y armado de prompt/contexto | Convierte evidencia en string sin contrato intermedio |
| `GenerationCapability` | Razonamiento/redacción y reparación | El modelo recibe un contexto sin evidencia estructurada |
| `Assess` / `VERIFY` | Evaluación antes/después de generación | Falta una evaluación explícita de suficiencia pre-reasoning |
| Policies | Retry, repair y termination | Boundary correcto; debe conservar ownership único |

---

## 3. Principio de autoridad

La autoridad debe residir en contratos y policies, no en el LLM.

El LLM no debe decidir:

- qué conocimiento existe;
- qué evidencia es válida;
- qué fuente tiene autoridad;
- qué claims están soportados;
- si una evidencia puede generalizarse;
- qué estrategia de retrieval se ejecuta;
- cuándo se publica o modifica conocimiento.

El LLM puede interpretar o redactar dentro de los límites del contrato, pero las decisiones epistémicas y operacionales pertenecen a componentes deterministas y versionados.

---

## 4. Pipeline Consumer objetivo

```text
QueryRequest
    |
    v
Query Understanding
    |
    v
QueryIR operacional
    |
    v
Retrieval Planning
    |
    v
Evidence Retrieval
    |
    v
Evidence Evaluation
    |
    +--> insuficiente: más retrieval / decline / aclaración
    |
    v
EvidenceSet
    |
    v
EvidenceSelection
    |
    v
ContextPackage
    |
    v
Reasoning Engine
    |
    v
Answer / Claims
    |
    v
VERIFY + Policy
    |
    v
Final Answer / Decline / Repair dirigido
```

### 4.1 Evidence Evaluation no es VERIFY

Son contratos y momentos distintos:

| Etapa | Pregunta | Salida |
|---|---|---|
| Evidence Evaluation | ¿Tengo suficiente evidencia para responder? | `coverage`, `confidence`, `sufficiency`, `decision` |
| VERIFY | ¿La respuesta generada respeta la evidencia? | claims soportados, no soportados, contradichos y decisión de policy |

Ejemplo:

```text
Retrieval: 5 documentos
Evidence Evaluation:
  coverage: 40%
  confidence: low
  decision: insufficient

Siguiente acción:
  ampliar retrieval, declinar o pedir aclaración

No se llama al LLM mientras la evidencia sea insuficiente según la policy.
```

Evidence Evaluation no reemplaza VERIFY y VERIFY no debe compensar un `retrieval_doc_miss`, conforme ADR-0019 y DEC-009.

---

## 5. Evidence Contract

### 5.1 EvidenceItem

El contrato mínimo de una evidencia debe incluir:

```text
evidence_id
canonical_doc_id
chunk / span
quote / text
source_reference
retrieval_signals
rank
provenance
artifact_identity / build_identity
claim_scope
```

`EvidenceItem` es una adaptación contractual del `dict` actual. La primera migración no requiere reescribir embeddings, BM25 ni el almacenamiento vectorial.

### 5.2 Claim scope

Una evidencia no solo tiene origen; también tiene alcance. `claim_scope` expresa qué afirma la evidencia y bajo qué condiciones, evitando generalizaciones indebidas.

Ejemplo:

```json
{
  "claim_scope": {
    "subject": "OAuth access token",
    "condition": "configured expiration policy"
  }
}
```

El texto:

> OAuth tokens expiran después de 1 hora

no debe interpretarse automáticamente como:

> Todo token expira después de 1 hora

`claim_scope` conecta el Evidence Contract con el contrato epistémico de ADR-0019 y permite que la evaluación de claims considere sujeto, condiciones y alcance, no solo overlap textual o procedencia documental.

### 5.3 EvidenceSet

`EvidenceSet` representa el conocimiento disponible en la ejecución después de retrieval y Evidence Evaluation. Puede contener evidencias que todavía no serán enviadas al modelo.

Ejemplo:

```text
30 evidencias recuperadas
coverage preliminar: 80%
confidence agregada: medium
fuentes: 6
estado: suficiente para selección
```

No es conocimiento nuevo, no modifica Warm Artifacts y no tiene lifecycle de Builder. Es un artefacto hot, temporal y Consumer-owned.

---

## 6. EvidenceSelection y ContextPackage

Estas representaciones deben permanecer separadas.

```text
EvidenceSet
    |
    v
EvidenceSelection
    |
    v
ContextPackage
```

### 6.1 EvidenceSelection

Es una decisión temporal de ejecución que selecciona un subconjunto de `EvidenceSet` según:

- cobertura de `required_evidence`;
- `claim_scope` relevante;
- confianza y autoridad;
- diversidad de fuentes;
- deduplicación por identidad canónica;
- presupuesto de tokens;
- restricciones de latencia;
- modo de consulta.

Ejemplo:

```text
EvidenceSet: 30 evidencias
EvidenceSelection:
  8 evidencias seleccionadas
  3 claims cubiertos
  2 fuentes independientes
  5.000 tokens permitidos
```

### 6.2 ContextPackage

`ContextPackage` es un artefacto temporal de ejecución para el Reasoning Engine. No representa el conocimiento total y no debe convertirse en un JSON gigante con ownership ambiguo.

Debe contener únicamente:

- evidencia seleccionada;
- claims o requisitos cubiertos;
- citas y provenance necesarios para generación;
- presupuesto aplicado;
- límites de contexto;
- referencias a `EvidenceItem`.

El string de contexto actual puede mantenerse como una proyección compatible para el provider existente, pero no debe ser el contrato primario de la arquitectura futura.

---

## 7. QueryIR operacional

QueryIR debe expresar **qué necesita el sistema para resolver la consulta**, no explicar semánticamente qué significa la pregunta.

Contrato propuesto:

```text
QueryIR(
    raw_query,
    normalized_query,
    entities,
    constraints,
    required_evidence,
    retrieval_preferences,
    execution_budget
)
```

No se deben introducir campos como:

```json
{
  "intent": "explain_security_architecture",
  "domain": "cybersecurity",
  "answer_type": "technical"
}
```

Ese tipo de representación puede convertirse progresivamente en una ontología o Knowledge Model de consultas. QueryIR debe mantenerse como contrato operacional y no debe producir conocimiento de dominio.

---

## 8. Orden de migración

### Fase 0 — Observabilidad

- Trazar query, candidatos, scores, evidencia provisional, selección, contexto, claims y señales.
- Comparar Kernel y camino lineal con `state_fidelity` explícita.
- No cambiar el comportamiento para medir.

### Fase 1 — Evidence Contract y Evidence Quality

- Adaptar `dict` de retrieval a `EvidenceItem`.
- Añadir `claim_scope`.
- Introducir `EvidenceQuality`/`EvidenceEvaluation`.
- Separar suficiencia de evidencia de VERIFY.
- Permitir ampliar retrieval, decline o aclaración antes de llamar al LLM.

### Fase 2 — EvidenceSelection y ContextPackage

- Introducir selección explícita desde `EvidenceSet`.
- Mantener `EvidenceSelection` como decisión hot y temporal.
- Producir `ContextPackage` acotado desde la selección.
- Mantener el string como proyección de compatibilidad.

### Fase 3 — QueryIR operacional

- Formalizar `QueryIR` con campos operacionales mínimos.
- Sustituir gradualmente metadata lateral y dicts ambiguos.
- Evitar ontologías, dominios interpretativos y answer models.

### Fase 4 — Refinamiento de Planner

- Consumir QueryIR.
- Mantener planner determinista inicialmente.
- Separar preferencias de retrieval de decisiones de policy.
- Mantener entity mode y boosts bajo ownership del Retrieval Pipeline.

### Fase 5 — Reasoning y Verification

- Mantener Generation como redacción/razonamiento.
- Alinear prompts y REPAIR con E/B y claim scope.
- Mantener VERIFY como evaluación posterior de claims.
- No usar REPAIR para compensar insuficiencia de retrieval.

### Fase 6 — Migración y eliminación de duplicación

- Hacer Kernel la ruta de referencia cuando BM-005 y benchmarks de paridad lo permitan.
- Reducir `HybridRAG` a fachada/adapters.
- Retirar gradualmente lógica duplicada de la rama lineal, bootstrap, clasificadores y retrieval adapters.
- Versionar contratos y validarlos en Composition Root.

---

## 9. Archivos potencialmente afectados

- `src/kernel/state.py`: referencias tipadas a QueryIR, EvidenceSet, EvidenceSelection y ContextPackage.
- `src/capabilities/retrieval.py`: adaptación a EvidenceItem/EvidenceSet.
- `src/capabilities/evidence_evaluation.py`: nueva capability de suficiencia pre-reasoning.
- `src/capabilities/evidence_selection.py`: nueva capability de selección hot.
- `src/capabilities/build_context.py`: proyección desde EvidenceSelection hacia ContextPackage.
- `src/capabilities/classify.py`: producción de QueryIR operacional.
- `src/capabilities/planner.py`: consumo de QueryIR y producción de RetrievalPlan.
- `retrieval_engine.py`: mantener búsqueda híbrida, pero separar contratos de retrieval, scoring y ranking.
- `context_builder.py`: convertir la implementación actual en una proyección de ContextPackage.
- `src/bootstrap.py`: wiring explícito de las nuevas capabilities.
- `rag_hybrid.py`: reducción progresiva de responsabilidades, manteniendo `execute()` y `query()`.
- `query_classifier.py`: adapter o implementación de Query Understanding operacional.
- `tests/unit/*`: contratos, claim scope, suficiencia, selección y serialización.
- `tests/eval/*`: paridad, groundedness, anti-hallucination, decline, coverage y latencia.
- `docs/adr/`: ADR posterior para congelar Evidence Contract, Evidence Quality, EvidenceSelection, ContextPackage y QueryIR.

---

## 10. Invariantes propuestas

1. `EvidenceItem` siempre tiene identidad documental canónica.
2. Toda evidencia tiene provenance y `claim_scope` explícito o marcado como desconocido.
3. EvidenceSet no crea conocimiento nuevo ni modifica Warm Artifacts.
4. EvidenceSelection es temporal y no es una materialized view persistente.
5. ContextPackage es temporal y no es un Knowledge Model.
6. Evidence Evaluation ocurre antes de Reasoning.
7. VERIFY ocurre después de Generation.
8. Evidence Evaluation y VERIFY no se sustituyen entre sí.
9. El LLM no decide autoridad, suficiencia, validez o alcance de evidencia.
10. QueryIR expresa necesidades operacionales y no se convierte en una ontología.
11. Retrieval Pipeline mantiene ownership de estrategia y scoring.
12. Policies mantienen ownership de retry, escalado, decline y reparación.
13. Builder sigue siendo el único productor de conocimiento estructurado.
14. El Consumer no publica ni modifica Warm Artifacts.
15. `query()` permanece como fachada de compatibilidad; el desarrollo nuevo usa `execute()`.

---

## Non-goals

Este trabajo no busca:

- Reemplazar Chroma, BM25 ni los motores actuales de retrieval.
- Introducir agentes autónomos en retrieval.
- Hacer obligatorio el uso de un LLM para planificación.
- Crear una ontología de consultas.
- Convertir QueryIR en un Knowledge Model.
- Mover el Knowledge Model desde Builder hacia Consumer.
- Convertir EvidenceSet en una nueva base de conocimiento.
- Convertir EvidenceSelection en una materialized view persistente.
- Convertir ContextPackage en un segundo Builder o un almacén de conocimiento.
- Resolver la evaluación completa de respuestas; VERIFY permanece separado y posterior.
- Eliminar inmediatamente la ruta lineal ni romper la fachada `query()`.
- Congelar nuevas interfaces sin un ADR aceptado.

---

## Comparativa

| Aspecto | Estado actual | Evolución propuesta |
|---|---|---|
| Retrieval output | `list[dict]` de chunks y scores | `EvidenceItem` / `EvidenceSet` |
| Alcance factual | Implícito en texto | `claim_scope` explícito |
| Suficiencia | Inferida tarde por assess/generation | Evidence Evaluation antes de Reasoning |
| Selección | Implícita en retrieval/context builder | `EvidenceSelection` temporal |
| Contexto | `str` construido desde resultados | `ContextPackage` acotado, con proyección string |
| Query representation | Clasificadores y metadata dispersos | QueryIR operacional |
| Planificación | Dict con heurísticas y roles | RetrievalPlan consumiendo QueryIR |
| Verificación | VERIFY posterior | Se mantiene posterior y separado de Evidence Evaluation |
| Autoridad | Parcialmente distribuida | Contratos, Builder y Policies |
| Conocimiento | Riesgo de enriquecimiento local | Warm Artifacts read-only y flujo descendente |

---

## Takeaways

1. El cuello de botella conceptual inmediato está en el output de retrieval, no en crear una representación más sofisticada de la query.
2. Evidence Contract debe incluir alcance de claim, no solo origen y score.
3. Evidence Evaluation es una barrera pre-reasoning distinta de VERIFY.
4. EvidenceSet representa disponibilidad; EvidenceSelection representa una decisión; ContextPackage representa el paquete temporal de ejecución.
5. QueryIR debe permanecer operacional y pequeño para no convertirse en un segundo Knowledge Model.
6. El Consumer debe consumir conocimiento certificado, no reconstruirlo ni ampliarlo localmente.
7. La evolución debe ser incremental: adaptar `dict` a contratos, preservar interfaces públicas y medir cada transición.
8. Cualquier congelación de estas fronteras requiere un ADR posterior; este RES documenta la investigación y el plan, no sustituye la decisión arquitectónica.
