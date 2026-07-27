# ADR-0020 - Ownership de decisiones y contrato de ejecucion observable

- **Estado:** Aceptado
- **Fecha:** 2026-07-27
- **Relaciona con:** ADR-0004, ADR-0006, ADR-0010, ADR-0013, ADR-0019, DEC-009, DEC-010

## Contexto

La revision del benchmark del RAG hibrido expuso tres problemas de frontera:

1. El harness de evaluacion pasa `entity_filter` y `two_stage` a `query()`, es decir, el benchmark impone estrategia de retrieval. Ademas `query_via_kernel` descarta silenciosamente esos parametros: con `kernel.enabled=true` el caller cree controlar el pipeline y no lo controla.
2. El gate de groundedness que se quiere adoptar necesita `_assess_claim_support()`, un metodo privado de `VerifyGroundednessEvaluator`, porque `evaluate()` requiere un `ExecutionState` que el camino lineal no produce. La tentacion de usar el privado es sintoma de una pieza faltante en el contrato, no una decision de conveniencia.
3. `retrieval_doc_miss` como fallo duro optimiza un proxy (que llegue el documento esperado) en lugar del objetivo (que la respuesta este soportada por evidencia), presionando al sistema en contra de su propia arquitectura hibrida.

## Decision

### 1. Principio de ownership de decisiones

Toda decision del sistema tiene un unico dueno. Ningun otro componente la toma, la sobrescribe ni la replica:

| Decision | Dueno |
|---|---|
| Como recuperar | Retrieval Pipeline |
| Como rerankear | Reranker |
| Cuando escalar estrategia (two-stage, retry) | Policy Engine |
| Como verificar | Evaluation (VERIFY) |
| Como medir | Benchmark |

Corolario operativo: **el benchmark nunca decide retrieval.** Se registra como P16 en `docs/principles.md`.

### 2. La observabilidad no cambia el comportamiento

**La instrumentacion, el benchmarking, el tracing y la evaluacion pueden ampliar la informacion disponible, pero nunca modificar las decisiones del pipeline.**

Aplica a todo componente presente y futuro — Supervisor, Knowledge Consumer, Planner, Tracing:

- **Ampliar** (permitido): pedir mas informacion del mismo run (`return_prerank`, trazas, `ExecutionState` completo).
- **Truncar** (permitido): detener el pipeline antes (`use_llm=False`).
- **Alterar** (prohibido): cambiar estrategia, umbrales o rutas de decision para poder medir.

Corolario de configuracion: comparar variantes se hace con la misma configuracion que se despliega, inyectada en el Composition Root, nunca con argumentos exclusivos del harness. Se registra como P17 en `docs/principles.md`.

### 3. Un unico contrato de ejecucion

Se agrega `HybridRAG.execute(...) -> ExecutionResult` con `answer`, `sources` y `execution_state: ExecutionState`. **`execute()` es el contrato de ejecucion del sistema.**

`query()` no se elimina (P8) pero queda **congelado**: conserva firma y retorno dict, y pasa a implementarse como `execute(...).to_query_result()`. No admite parametros ni claves nuevas; su superficie solo puede encoger. Todo desarrollo nuevo usa `execute()`.

Se rechaza agregar `evaluation_signals` al dict de `query()`: `query()` responde; no emite diagnostico de calidad. Quien quiera evaluar toma el **estado** y se lo pasa al evaluator (P14). El contrato devuelve estado, no diagnostico.

### 4. Fidelidad de estado: transicion explicita, no estado permanente

`ExecutionState.metadata['state_fidelity']` es obligatorio:

- `'full'`: producido por el camino kernel; incluye `signals` de ASSESS y VERIFY.
- `'partial'`: reconstruido por adaptador desde el camino lineal; sin `signals`.

Ningun consumidor puede leer `signals` sin chequear fidelidad. Un estado parcial que se presente como completo es estado oculto (P5) y metrica que miente (P3).

Esta dualidad es transitoria y se declara como tal, con condicion de cierre verificable:

- **Cierra cuando** un benchmark de paridad (BM-005) demuestre equivalencia kernel vs. lineal en los gates de producto.
- **Al cerrar** se borran en un mismo commit `LinearStateAdapter`, `state_fidelity` y la rama de reevaluacion del harness, junto con el flip de `kernel.enabled` a default.
- **Mientras dure**, todo reporte de benchmark declara `state_fidelity` en cabecera y marca los runs `partial` como modo transitorio.

La reevaluacion offline del modo `partial` usa el mismo evaluator y la misma configuracion que el runtime (P17).

### 5. El benchmark usa solo API publica de Evaluation

El harness invoca `VerifyGroundednessEvaluator.evaluate(state)`. El acceso a `_assess_claim_support()` u otros internos queda prohibido.

### 6. Relacion con decisiones tecnicas

ADR-0020 fija el marco arquitectonico de propiedad, contrato y observabilidad. Las decisiones de implementacion concretas que dependen de ese marco viven en DECs especificas:

- **Estrategia de entidades en retrieval** (`entity_filter` -> `boost`, `retrieval.entity_mode`, BM-004): documentada en `DEC-010`.
- **Taxonomia de metricas en dos niveles** (gates de producto vs. metricas de ingenieria, `retrieval_doc_miss` como advertencia): documentada en `DEC-009`.

Esta separacion mantiene al ADR en el nivel de principios y fronteras, y a los DEC en el nivel de politicas reversibles de implementacion.

## Consecuencias

- El benchmark mide el sistema de produccion, no una variante.
- Desaparece la clase de bug "parametro de fachada ignorado por una implementacion".
- Evaluation puede cambiar su implementacion interna sin tocar el benchmark.
- P17 acota por adelantado a componentes futuros (Supervisor, Knowledge Consumer, Planner).
- Las decisiones concretas de retrieval (modo entidades) y metricas se rigen por DEC-010 y DEC-009, manteniendo ADR-0020 como frontera arquitectonica.
- Costo asumido y acotado: adaptador de estado y ruta de evaluacion doble, ambos con condicion de borrado definida.

## Alternativas consideradas

1. `query()` devuelve `evaluation_signals`: rechazado (P14).
2. Cambiar el tipo de retorno de `query()`: rechazado (P8).
3. `execute()` solo en kernel, error en camino lineal: rechazado por ahora (evolucion incremental).
4. `query()` y `execute()` como contratos paralelos de igual rango: rechazado (duplicacion sin direccion).
5. Cerrar la transicion por fecha limite: rechazado (P4).
6. Que el benchmark llame `_assess_claim_support()`: rechazado.

## Criterios de aceptacion

- `query()` devuelve exactamente el mismo dict que antes para un estado dado, derivado de `to_query_result()`.
- Ningun parametro ni clave nueva se agrega a `query()`.
- Ningun harness pasa `entity_filter` ni `two_stage`.
- `web_app.py` y el harness comparten `semantic_weight` desde config.
- Ninguna lectura de `signals` sin chequeo de `state_fidelity`.
- Todo reporte de benchmark declara `state_fidelity`.
- BM-005 publicado antes de cerrar la transicion de fidelidad.
- DEC-010 y DEC-009 documentan y aceptan las decisiones de retrieval y metricas respectivamente.
