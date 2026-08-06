# ADR-0010 - Fachada de consulta estable y versionada

- **Estado:** Propuesto
- **Fecha:** 2026-07-21

## Contexto

Web / CLI / benchmark dependen de `query()` y su dict de retorno.

## Decision

La fachada de consulta se versiona; su forma de entrada/salida es un contrato. Los cambios internos (FSM, capabilities) no alteran el contrato sin bump de version.

## Consecuencias

Protege el benchmark y consumidores; permite refactor interno agresivo.

## Alternativas

Cambiar la API libremente (rechazado: rompe evaluacion y clientes).
