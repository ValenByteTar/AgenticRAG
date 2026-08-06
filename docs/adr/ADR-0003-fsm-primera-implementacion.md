# ADR-0003 - FSM como primera implementacion del Controller

- **Estado:** Propuesto
- **Fecha:** 2026-07-21

## Contexto

Se necesita una implementacion concreta, reproducible y con terminacion garantizada, hoy.

## Decision

Implementar el Controller-runtime como maquina de estados finita con presupuesto acotado.

Es una decision **revocable** bajo ADR-0002; cuando el razonamiento iterativo abierto lo exija, se puede superseder por otra implementacion sin cambiar el contrato.

## Consecuencias

Simple, auditable, medible.

**Riesgo:** que se agreguen capacidades como estados cableados. Mitigado por ADR-0001 y ADR-0012 (capacidades detras de contratos y Registry, no como estados del Controller).

## Alternativas

Grafo LLM-dirigido (rechazado hoy: no reproducible). ReAct libre (rechazado: latencia e impredecibilidad).
