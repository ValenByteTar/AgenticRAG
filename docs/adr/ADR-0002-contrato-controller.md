# ADR-0002 - Contrato de Controller: solo ejecuta acciones decididas

- **Estado:** Propuesto
- **Fecha:** 2026-07-21

## Contexto

El Controller sabia demasiado (conocia Retrieval / Memory / Verify). Eso viola P6 y P15.

## Decision

El Controller **solo ejecuta la accion decidida por el Policy Engine** y garantiza terminacion. NO conoce capacidades concretas; para actuar, pide al Capability Registry resolver la referencia de la decision.

El contrato no prescribe FSM, grafo ni ReAct.

Cadena de runtime:

> Evaluation produce senales; Policy interpreta; Controller ejecuta; Registry resuelve; Capability trabaja.

## Consecuencias

El Controller no crece al agregar capacidades (P15); implementacion del orquestador reemplazable.

## Alternativas

Controller que enruta (rechazado: recrea el monolito).
