---
id: RES-008
category: research
status: draft
created: 2026-07-31
updated: 2026-07-31
author: human
components: [policy-engine, capability-registry, execution-state, kernel, builder, consumer, artifact-registry]
tags: [architecture, capabilities, authority, execution-context, delegation, pola, capability-based-security, exploratory]
related: [ADR-0004, ADR-0009, ADR-0012, ADR-0013, ADR-0018, ADR-0019, ADR-0020, RES-001, RES-003, RES-004]
supersedes: null
superseded_by: null
---

# RES-008 - Capability-Oriented Execution Model (Exploratory)

## Topic

Modelar la autoridad de ejecucion como un concepto arquitectonico independiente, basado en Capabilities explicitas, preservando compatibilidad con la arquitectura actual para una posible evolucion futura.

## Sources

- ADR-0004: ExecutionState explicito y serializable
- ADR-0009: Contratos de Memory y Tool
- ADR-0012: Capability Registry (resuelve, no decide)
- ADR-0013: Policy Engine (policies de primera clase — deciden, no ejecutan)
- ADR-0018: Knowledge Builder / Consumer split (frontera inviolable, Registry como autoridad)
- ADR-0019: Contrato epistemico y VERIFY a nivel de claims (senales, no decisiones)
- ADR-0020: Ownership de decisiones y contrato de ejecucion observable (P16, P17)
- RES-001: El contrato Warm como centro arquitectonico (Publication/Resolution Protocol)
- RES-003: Knowledge Consumer / evolucion del Agentic RAG runtime
- RES-004: LLMSupport — observador paralelo (hipotesis, no decisiones)

---

## 1. Motivacion

### 1.1 El patron emergente

La arquitectura actual separa consistentemente el razonamiento de la autoridad. Este patron ha emergido de forma natural en multiples capas:

**Builder (index-time):**

- El LLM extractor produce KIR (entidades, aliases, relaciones) pero no decide que entra al Knowledge Model.
- El Compilador decide via IR Passes (Dedup, Canonicalize, Confidence Policy).
- Validation gatea: Structural + Evidence + Semantic Validation ocurren antes del codegen.
- El extractor no conoce el catalogo de predicados (ADR-0021.5); produce lenguaje natural y el compilador normaliza.
- El Artifact Registry decide si un build se promueve (Publication Protocol).

**Consumer (query-time):**

- El LLM no decide retrieval. El `PlannerCapability` planifica la consulta.
- El Policy Engine decide que capability ejecutar, en que orden, y si retry (ADR-0013).
- ASSESS y VERIFY producen `EvaluationSignal` (pass/fail); el Policy Engine interpreta la senal y decide (ADR-0019).
- El Consumer nunca publica; solo lee Warm Artifacts via Resolution Protocol.

**LLMSupport (observador paralelo, RES-004):**

- El LLM produce `Hypothesis` con confidence; el Policy Engine interpreta y decide si actua.
- Modo passive por defecto: solo loggea hipotesis. No influye en el pipeline hasta que haya evidencia.

### 1.2 La pregunta arquitectonica

Este patron — "el componente inteligente propone, la autoridad decide" — es uno de los principios fundamentales de la arquitectura. Sin embargo, actualmente la autorizacion esta centralizada principalmente en el **Policy Engine** (ADR-0013).

Surge la pregunta:

> **Puede modelarse la autoridad como un concepto independiente del Policy Engine, utilizando un sistema explicito de Capabilities?**

---

## 2. Problem Statement

### 2.1 Modelos actuales de Tool Calling

Los modelos actuales de Tool Calling suelen asumir que el agente posee autoridad implicita para invocar herramientas. Incluso cuando existe un Policy Engine, la autorizacion continua siendo principalmente una decision centralizada.

### 2.2 Modelo basado en Capabilities

Un modelo basado en Capabilities propone una alternativa:

- la autoridad deja de estar implicita;
- toda accion requiere una capacidad explicita;
- la autoridad puede ser delegada, limitada o revocada;
- las herramientas nunca verifican autoridad — reciben llamadas ya autorizadas por el Dispatcher.

### 2.3 Modelo de capas de autoridad

La autoridad fluye en una sola direccion. Las tools son el extremo mas ignaro de la cadena:

```
Policy Engine       (decide que hacer)
      |
      v
Capability Manager  (emite capabilities segun la decision)
      |
      v
Dispatcher          (verifica capabilities antes de invocar)
      |
      v
Tool                (recibe llamada autorizada, ejecuta, retorna)
```

La tool:
- **no sabe** por que fue invocada
- **no sabe** quien autorizo
- **no sabe** si hubo capabilities
- **no valida** nada relacionado con autoridad
- **recibe** input, **produce** output, **termina**

Esto preserva P6 (no acoplamiento concreto): las tools no conocen al Policy Engine, al Capability Manager, ni al Dispatcher. Solo conocen su contrato de input/output.

### 2.4 Analogia con la arquitectura actual

El sistema ya tiene conceptos cercanos:

| Concepto actual | Analogia con Capabilities |
|---|---|
| Capability Registry (ADR-0012) | Registro de capacidades disponibles |
| Policy Engine (ADR-0013) | Interprete de politicas que decide que ejecutar |
| ExecutionState (ADR-0004) | Contexto de ejecucion que transporta estado |
| Warm Artifacts contract (RES-001) | Contrato que define que esta permitido leer |
| Frontera Builder/Consumer (ADR-0018) | Limite de autoridad entre componentes |

La diferencia clave: hoy la autoridad **se decide en runtime** (Policy Engine evalua senales y decide). En un modelo de Capabilities, la autoridad **se porta en el contexto de ejecucion** y el Dispatcher la verifica antes de invocar a la tool. La tool nunca conoce el mecanismo de autorizacion.

---

## 3. Working Hypothesis

La arquitectura podria evolucionar hacia un modelo donde toda autoridad de ejecucion fluya mediante un **Execution Context**, sin asumir un mecanismo de autorizacion especifico.

### 3.1 Estado actual del Execution Context

Hoy `ExecutionState` (ADR-0004) contiene:

- Invocation ID
- Contracts (referencias al build activo del Registry)
- Policy (configuracion de policies activas)
- Metadata de ejecucion (senales, presupuesto, trazas)

### 3.2 Evolucion potencial

En el futuro podria incorporar:

- **Capabilities**: capacidades explicitas otorgadas a esta ejecucion
- **Delegation Chain**: cadena de delegacion de autoridad
- **Expiration**: tiempo de validez de las capacidades
- **Scope**: alcance de cada capacidad (que documentos, que entidades, que operaciones)
- **Provenance**: quien emitio cada capacidad y por que

...sin modificar las interfaces publicas de los componentes.

### 3.3 Hipotesis de compatibilidad

La adicion de Capabilities al Execution Context seria **compatible hacia atras**:

- Componentes que no conocen capacidades siguen funcionando (ignoran campos nuevos).
- El Dispatcher verifica capacidades antes de invocar; las tools no cambian.
- El Policy Engine puede coexistir como interprete de politicas que tambien emite capacidades.

---

## 4. Architectural Principle (Draft)

> **Los componentes inteligentes nunca poseen autoridad implicita.**
>
> **Toda autoridad debe ser proporcionada explicitamente por el entorno de ejecucion.**

### 4.1 Implicaciones

1. Ningun componente (LLM, extractor, planner, verifier) asume que puede invocar herramientas o mutar estado.
2. Toda accion requiere una Capability valida en el Execution Context.
3. Las Capabilities se emiten, se delegan y se revocan explicitamente.
4. Las herramientas nunca validan autoridad — reciben llamadas ya autorizadas por el Dispatcher.
5. El Dispatcher es el unico punto que verifica capacidades antes de invocar a una tool.

### 4.2 Relacion con principios existentes

| Principio actual | Extension con Capabilities |
|---|---|
| P5: No estado oculto | Las capacidades son explicitas en el contexto |
| P6: No acoplamiento concreto | Las herramientas no conocen ni al Policy Engine ni al modelo de autorizacion |
| P16: Ownership de decisiones | La autoridad tiene un dueno: el emisor de la Capability |
| P17: Observabilidad no cambia comportamiento | Las capacidades de observacion son read-only por definicion |

---

## 5. Potential Benefits

### 5.1 Separacion entre razonamiento y autoridad

El LLM nunca "posee permisos". Solo produce propuestas. La autoridad vive en el contexto, no en el componente.

### 5.2 Delegacion explicita

Las capacidades podrian delegarse temporalmente entre componentes sin ampliar privilegios globales. Ejemplo:

- El Policy Engine delega `retrieve_docs` al PlannerCapability por una invocacion.
- El PlannerCapability delega `expand_entities` al EntityExpansionCapability.
- Cada delegacion reduce scope (menos documentos, menos entidades, menos tiempo).
- Al finalizar la invocacion, las capacidades delegadas expiran.

### 5.3 Menor acoplamiento

Las herramientas no conocen el mecanismo de autorizacion. El Dispatcher verifica capacidades antes de invocarlas. El Policy Engine y el Capability Manager pueden evolucionar independientemente sin tocar las tools.

### 5.4 Compatibilidad futura

La arquitectura permaneceria abierta a modelos de autorizacion mas sofisticados sin rediseñar Builder, Consumer o Registry:

- Capabilities firmadas criptograficamente (no solo presence checks)
- Delegacion entre componentes remotos (microkernel distribuido)
- Revocacion en caliente (capabilities con expiration)
- Auditoria completa (cadena de delegacion trazable)

### 5.5 Principio de menor autoridad (POLA)

Cada componente recibe **solo las capacidades que necesita** para su tarea. No hay privilegios globales. Si un componente se compromete, el impacto esta acotado por sus capacidades.

---

## 6. Mapeo a la arquitectura actual

### 6.1 Builder

| Componente | Autoridad actual | Con Capabilities |
|---|---|---|
| LLM Extractor | No tiene; produce KIR | `extract_entities` (scope: un chunk) |
| Compiler | Decide via IR Passes | `canonicalize`, `dedup`, `merge` |
| Validation | Gatea; rechaza o acepta | `validate_structural`, `validate_evidence` |
| Artifact Registry | Decide promote/rollback | `publish`, `promote`, `rollback` |

### 6.2 Consumer

| Componente | Autoridad actual | Con Capabilities |
|---|---|---|
| PlannerCapability | Planifica consulta | `plan_query` (scope: una query) |
| RetrievalCapability | Ejecuta retrieval | `retrieve_docs` (scope: top-K, filtros) |
| EntityExpansionCapability | Expande entidades | `expand_entities` (scope: aliases del build activo) |
| GenerationCapability | Genera respuesta | `generate_answer` (scope: contexto proporcionado) |
| VerifyCapability | Verifica claims | `verify_claims` (scope: respuesta generada) |
| WarmArtifactResolver | Lee artifacts | `read_warm_artifact` (scope: build activo, read-only) |

### 6.3 LLMSupport

| Componente | Autoridad actual | Con Capabilities |
|---|---|---|
| LLMSupport | Observa; produce hipotesis | `observe_execution` (read-only, no muta estado) |
| TraceSink | Registra trazas | `write_trace` (append-only) |

---

## 7. Non-Goals

Este documento **no propone**:

- implementar Capabilities;
- reemplazar el Policy Engine;
- modificar la arquitectura actual;
- introducir complejidad adicional en esta etapa.

El objetivo es **unicamente preservar compatibilidad arquitectonica** para una posible evolucion futura, registrando la direccion potencial para mantener abiertas futuras decisiones de diseño, evitando introducir dependencias que dificulten una eventual transicion hacia un modelo basado en Capabilities.

---

## 8. Open Questions

1. **Execution Context**: es el lugar correcto para transportar autoridad? Deberia ser un campo dentro de `ExecutionState` o un objeto paralelo?
2. **Representacion**: las Capabilities deberian ser objetos, tokens firmados o contratos tipados?
3. **Emision**: quien emite una Capability? El Composition Root? El Policy Engine? El Registry?
4. **Revocacion**: quien puede revocarla? En que momento? Con que efecto?
5. **Delegacion**: como se representa? Es una cadena inmutable? Se puede acotar scope al delegar?
6. **Contracts y Capabilities**: como interactuan? Un Warm Artifact contract implica capacidades de lectura automaticas?
7. **Policy Engine**: continua existiendo o pasa a ser un interprete de Capabilities?
8. **Validacion**: confirmar que las herramientas nunca validan capacidades — solo el Dispatcher lo hace. Como se garantiza que ninguna tool bypassa el Dispatcher?
9. **Propiedades formales**: que propiedades podrian demostrarse formalmente mediante un modelo basado en Capabilities? (safety, liveness, non-interference)
10. **Compatibilidad hacia atras**: como garantizar que componentes que no conocen capacidades sigan funcionando sin modificacion?

---

## 9. Related Concepts

- **Capability-Based Security**: modelo de seguridad donde la autoridad se representa como capacidades portables
- **Object Capabilities**: capacidades como referencias no forjables a objetos
- **Principle of Least Authority (POLA)**: cada componente recibe solo la autoridad que necesita
- **Microkernel Architecture**: separacion entre mecanismo (kernel) y politica (servidores)
- **Capability Systems**: KeyKOS, EROS, seL4 — sistemas operativos basados en capacidades
- **Design by Contract**: contratos tipados como precondiciones de ejecucion
- **Execution Context**: patron de contexto de ejecucion que transporta autoridad
- **Policy-Based Authorization**: autorizacion basada en politicas (modelo actual)

---

## 10. Current Position

**No existe evidencia suficiente para justificar una implementacion.**

La arquitectura actual resulta adecuada para el estado del proyecto:

- El Policy Engine (ADR-0013) centraliza las decisiones de ejecucion de forma efectiva.
- El Capability Registry (ADR-0012) resuelve referencias sin decidir.
- El ExecutionState (ADR-0004) transporta estado sin transportar autoridad.
- La frontera Builder/Consumer (ADR-0018) limita la autoridad por diseno.

Este documento registra una **direccion potencial de evolucion** cuyo objetivo es mantener abiertas futuras decisiones de diseno, evitando introducir dependencias que dificulten una eventual transicion hacia un modelo basado en Capabilities.

---

## 11. Riesgos

| Riesgo | Probabilidad | Impacto | Mitigacion |
|---|---|---|---|
| Sobre-ingenieria prematura | Alta | Alto | Mantener status draft; no implementar sin evidencia |
| Acoplamiento de componentes a formato de Capability | Media | Alto | Capabilities como campo opcional en Execution Context |
| Duplicacion con Policy Engine | Media | Medio | Definir claramente: Policy Engine decide, Capabilities autorizan |
| Complejidad de delegacion | Baja | Medio | Postergar delegacion hasta que haya caso de uso real |
| Incompatibilidad con Warm Artifacts | Baja | Bajo | Warm Artifacts son read-only; capacidades de lectura son triviales |

---

## 12. Takeaways

1. **El patron "razonamiento propone, autoridad decide" es fundamental** en la arquitectura actual y ha emergido consistentemente en Builder, Consumer y LLMSupport.
2. **La autoridad podria modelarse como un concepto independiente** del Policy Engine, utilizando Capabilities explicitas.
3. **El Execution Context (ExecutionState) es el candidato natural** para transportar autoridad, sin modificar interfaces publicas.
4. **La compatibilidad hacia atras es preservable**: componentes que no validan capacidades siguen funcionando.
5. **No hay evidencia suficiente para implementar**. La arquitectura actual es adecuada para el estado del proyecto.
6. **El valor de este documento es preventivo**: registrar la direccion para evitar introducir dependencias que dificulten la evolucion futura.

---

## 13. Criterio de promocion a ADR

Este research podria promoverse a ADR cuando:

- exista un caso de uso real que requiera delegacion de autoridad entre componentes;
- el Policy Engine demuestre limitaciones de escalabilidad o flexibilidad;
- se requiera auditoria formal de cadena de autoridad;
- se evaluen arquitecturas distribuidas o microkernel;
- se demuestre que las Capabilities resuelven un problema que el Policy Engine no puede resolver.

Hasta entonces permanece como research exploratorio de arquitectura de largo plazo.

---

Ver tambien:
- **RES-001** para el contrato Warm como centro arquitectonico
- **RES-003** para el detalle del Knowledge Consumer
- **RES-004** para LLMSupport como observador paralelo
- **ADR-0013** para el Policy Engine actual
- **ADR-0012** para el Capability Registry actual
- **ADR-0004** para ExecutionState
- **ADR-0020** para ownership de decisiones y contrato de ejecucion observable
