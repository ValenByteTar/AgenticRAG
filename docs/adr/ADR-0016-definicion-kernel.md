# ADR-0016 - Definicion del Kernel

- **Estado:** Propuesto
- **Fecha:** 2026-07-21

## Contexto

Sin frontera explicita, todo termina en el nucleo y el nucleo deja de ser estable.

## Decision

El Kernel contiene solo:

- Contratos
- `ExecutionState`
- Controller-runtime
- Capability Registry
- Policy Engine
- Hooks de Observability / Evaluation / Configuration
- Composition Root

Toda implementacion concreta vive afuera. El Kernel conoce contratos, jamas implementaciones (P2).

Criterio de entrada: ¿es un contrato o un mecanismo estable? entra. ¿es una implementacion? afuera.

Codigo: `src/kernel/`.

## Consecuencias

Superficie de cambio del nucleo casi nula; criterio objetivo para decidir si algo entra al Kernel.

## Alternativas

Kernel monolitico con implementaciones (rechazado: recrea el status quo).
