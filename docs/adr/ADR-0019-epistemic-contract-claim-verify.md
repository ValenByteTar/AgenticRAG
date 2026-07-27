# ADR-0019 - Contrato epistémico y VERIFY a nivel de claims

- **Estado:** Aceptado
- **Fecha:** 2026-07-27
- **Relaciona con:** ADR-0006, ADR-0013, DEC-006, EXP-005, BM-002

## Contexto

DEC-006 aceptó VERIFY determinista post-generación basado en overlap léxico, hedge detection y citation fidelity, con REPAIR presupuestado (`max_repairs=1`). EXP-005 validó el mecanismo en tests unitarios y BM-002 mostró 100% groundedness y 0 alucinaciones en una muestra estratificada de 11 preguntas.

Sin embargo, durante la evaluación completa de 75 preguntas se observó un efecto no deseado:

- La primera respuesta suele ser correcta y concisa (p. ej., expandir el acrónimo SOAR o definir CIA triad).
- VERIFY interpreta la baja coincidencia léxica entre la respuesta y el contexto como falta de soporte factual.
- REPAIR fuerza una regeneración con instrucciones "solo contexto", lo que induce hedging, respuestas más extensas y, frecuentemente, peor calidad.
- El problema se agrava porque muchos fallos son `retrieval_doc_miss`: el documento correcto no llegó al contexto, por lo que REPAIR no puede arreglar la respuesta y solo la degrada.

Esto indica que **el contrato epistémico entre generación y verificación es inconsistente**. El prompt general permite usar conocimiento general del dominio marcado como `[Conocimiento general]`, pero REPAIR prohíbe explícitamente todo conocimiento externo. Además, VERIFY confunde "soporte factual" con "coincidencia de tokens".

## Decisión

### 1. Separar dos tipos de conocimiento en la respuesta

Toda respuesta puede contener:

- **Evidencia documental (E)**: hechos, números, versiones, citas, procedimientos. Debe provenir del contexto recuperado, con cita `[Doc N - nombre p.X]`.
- **Conocimiento de fondo del dominio (B)**: definiciones canónicas, expansión de acrónimos ampliamente aceptados, taxonomías generales. Puede complementar la evidencia, pero debe estar marcado explícitamente como `[Conocimiento general]` y nunca debe incluir citas documentales falsas ni hechos específicos no verificables.

El contrato del prompt y de REPAIR deben ser idénticos: si se permite B, ambos lo permiten; si el modo es estricto, ambos lo son.

### 2. VERIFY evalúa soporte de claims, no similitud léxica global

`VerifyGroundednessEvaluator` evoluciona de un score léxico global a una señal estructurada por claims:

- `Supported`: el claim está directamente respaldado por el contexto.
- `WeaklySupported`: el claim es una paráfrasis o conocimiento de fondo consistente con el contexto.
- `Unsupported`: un claim factual específico no tiene evidencia en el contexto.
- `Contradicted`: el claim contradice el contexto o es un hedge injustificado cuando ASSESS pasó.

La métrica de overlap léxico pasa a ser un **diagnóstico**, no un gate duro. El gate duro solo se activa cuando hay claims `Unsupported` o `Contradicted`, citas inventadas, o contradictions explícitas.

### 3. REPAIR se dispara solo ante riesgo factual real

`VerifyRepairPolicy` decide `retry` únicamente si:

- Existe al menos un claim `Contradicted` (incluye hedge injustificado).
- Existe al menos un claim `Unsupported` que contenga un token de alto riesgo (números, versiones, nombres propios de controles/frameworks, citas numéricas no válidas).
- Todas las citas documentales son inválidas.
- El answer está vacío o es demasiado corto.

Si el problema es solo bajo overlap léxico con claims `Supported` o `WeaklySupported`, VERIFY pasa con warning y no se repara.

### 4. REPAIR dirigido

Cuando se repara, el hint no ordena "reescribir todo solo con contexto". En su lugar:

- Se identifican los claims problemáticos.
- Se indica al generador: "Elimina o reformula los siguientes claims no soportados; preserva el resto de la respuesta".
- Se preserva la estructura de la respuesta original si es correcta.

### 5. No reparar fallos de retrieval

Si ASSESS/retrieval no trajo evidencia suficiente (`retrieval_doc_miss`), REPAIR no se usa como compensación. El sistema debe aceptar con warning o declinar, según la política de riesgo del modo.

## Consecuencias

- Se reduce la degradación de respuestas correctas y concisas (caso Q13 SOAR, CIA, etc.).
- Se mantiene la protección anti-alucinación para hechos específicos y citas.
- Se alinea el contrato del prompt con el contrato de verificación.
- `VerifyGroundednessEvaluator` produce señales más ricas (`metadata["claim_support"]`) que pueden consumirse por otras policies o mostrarse en trazas.
- `VerifyRepairPolicy` requiere inspeccionar `metadata` de la señal `verify` en lugar de depender únicamente de `passed`.
- Los tests unitarios existentes deben actualizarse para reflejar el nuevo contrato.

## Alternativas consideradas

1. **Ajustar solo el `groundedness_floor`**: rechazado. Sigue midiendo lo incorrecto y es frágil por dominio/idioma.
2. **Context-only global**: rechazado. Baja utilidad para definiciones conceptuales y no arregla retrieval.
3. **LLM-as-judge para VERIFY**: rechazado. Costo, latencia y conflicto con principio local-first (ADR-0011).
4. **Eliminar VERIFY/REPAIR**: rechazado. Se pierde la barrera anti-alucinación que EXP-005 y BM-002 validaron.

## Criterios de aceptación futuros

- Una respuesta conceptual correcta y concisa (expansión de acrónimo, definición canónica) no dispara REPAIR si no contiene hechos específicos no soportados.
- Un claim con número, versión o cita falsa sí dispara REPAIR o decline.
- El contrato del prompt y REPAIR son idénticos respecto al uso de `[Conocimiento general]`.
- `retrieval_doc_miss` no se intenta reparar mediante regeneración.

## Notas de implementación

- Fase A: cambiar `VerifyRepairPolicy` para usar metadatos de claim support y no reparar por overlap puro.
- Fase B: implementar `_assess_claim_support` en `VerifyGroundednessEvaluator` con segmentación local-first (oraciones + heurísticas de riesgo + matching léxico/semántico ligero).
- Actualizar `repair_hint` para ser dirigido por claims problemáticos.
- Alinear el prompt general de `rag_hybrid.py` para reflejar el contrato E/B.
