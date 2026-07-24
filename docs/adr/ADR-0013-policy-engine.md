# ADR-0013 - Policy Engine (policies de primera clase)

- **Estado:** Propuesto
- **Fecha:** 2026-07-21

## Contexto

Retry, budget, routing, fallback, verification-gating, confidence, memory/learning gating estaban dispersos como `if/else`.

## Decision

Las **Policies** son ciudadanos de primera clase: funciones puras que interpretan `EvaluationSignal` + `ExecutionState` y devuelven una **decision** (que hacer a continuacion).

El **Policy Engine** (Kernel) las evalua. Las policies **deciden, no ejecutan**; no producen efectos, no llaman capabilities.

Restriccion anti-monolito: una policy = una decision; pequenias, puras, componibles y con scope.

## Consecuencias

El comportamiento del sistema se ajusta cambiando policies, no el Controller ni las capabilities; policies testeables en aislamiento.

## Alternativas

Logica de control en el Controller (rechazado: god object). Policy Engine que envuelve al Registry (rechazado: concentra decision+resolucion).
