---
id: DEC-010
title: "Modo de entidades en retrieval: de filtro duro a boost acotado"
date: 2026-07-27
status: accepted
category: decisions
tags: [retrieval, entity_filter, entity_mode, boost, filter, adr-0020, bm-004]
related: [ADR-0020, DEC-009, BM-004]
---

# DEC-010 — Modo de entidades en retrieval: de filtro duro a boost acotado

## Contexto

ADR-0020 establece que la decision de **como recuperar** pertenece unica y exclusivamente al Retrieval Pipeline; ningun caller externo (benchmark, fachada, web) puede imponerle estrategia.

Historicamente, `HybridRAG.query()` expone el parametro `entity_filter: bool`. Cuando es `True`, el monolito lineal reduce los candidatos del retrieval a aquellos cuyo metadata `source` contiene alguna de las entidades detectadas. Este comportamiento:

- Mejora precision en queries con entidades de documento explicito.
- Degrada recall en queries conceptuales, de comparacion o donde la evidencia pertenece a documentos distintos a los esperados.
- Genera divergencia entre benchmark y produccion cuando el benchmark pasa `entity_filter=False` o fuerza el flag.

BM-004 debe medir el impacto de eliminar el filtro duro, pero no podemos hacerlo de un solo paso sin evidencia.

## Decision

El control externo `entity_filter` se reemplaza por el modo interno `retrieval.entity_mode` en `config.yaml`:

| Modo | Comportamiento |
|---|---|
| `filter` | Mantiene el filtro duro historico (solo para compatibilidad / rollback). |
| `boost` (default) | Las entidades se usan para expansion de candidatos y como senal de scoring; no se descartan documentos por no coincidir. |
| `off` | Se ignoran las entidades en la fase de retrieval. |

El modo `boost` es el nuevo default. El filtro duro solo puede activarse cambiando configuracion, no por parametro de fachada.

### Parametros `entity_filter` y `two_stage` congelados

`HybridRAG.execute()` y `HybridRAG.query()` aun aceptan `entity_filter` y `two_stage` por compatibilidad, pero:

- Emiten `DeprecationWarning`.
- No modifican la estrategia real; solo `entity_mode` en config decide.
- No son usados por nuevos consumidores (`web_app.py`, harnesses, `tools/benchmark_speed.py`).

### Condicion de cierre

La eliminacion del modo `filter` y de los parametros `entity_filter`/`two_stage` queda condicionada a:

- Publicacion de **BM-004**, que mida doc hit rate, recall y calidad de respuesta con `entity_mode = boost|off` vs `filter`.
- Aprobacion explicita de que `boost` no regresa las metricas de producto.

Hasta entonces, el modo `filter` sigue disponible como escape controlado.

## Consecuencias

- El Retrieval Pipeline vuelve a ser dueno unico de su estrategia.
- El benchmark y la web usan el mismo pipeline sin flags de estrategia adicionales.
- La degradacion es incremental: `filter` -> `boost` -> `off`, cada paso medible.
- Se elimina la clase de bug "parametro de fachada ignorado" entre `kernel.enabled=true` y `kernel.enabled=false`.

## Alternativas consideradas

1. Eliminar `entity_filter` de inmediato: rechazado porque no hay evidencia de BM-004 aun.
2. Dejar `entity_filter` como parametro de `execute()`: rechazado por ADR-0020 (ownership del retrieval).
3. Mover la decision a un `Policy` del kernel: posible en Fase 7+, pero el monolito lineal aun no consume el kernel, por lo que `config.yaml` es el punto unico intermedio.

## Criterios de aceptacion

- `retrieval.entity_mode` esta presente en `config.yaml` con default `boost`.
- Ningun harness o consumidor nuevo pasa `entity_filter` o `two_stage` a `execute()`/`query()`.
- Modo `filter` reproduce el comportamiento historico para rollback controlado.
- Modo `boost` no descarta documentos por ausencia de coincidencia exacta de entidad; aplica senal de scoring acotada.
- **BM-004 publicado antes de cualquier eliminacion del modo `filter` o de los parametros `entity_filter`/`two_stage`.**

## Por que no es ADR

Esta decision no altera una frontera arquitectonica: no define interfaces ni capas nuevas, solo ajusta una politica de implementacion del retrieval bajo el contrato `execute()` ya fijado por ADR-0020. Es reversible cambiando configuracion, por eso vive como DEC.
