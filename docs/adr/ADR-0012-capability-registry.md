# ADR-0012 - Capability Registry

- **Estado:** Propuesto
- **Fecha:** 2026-07-21

## Contexto

Se hablaba de capacidades pero no aparecian; el Controller las conocia directamente (viola P6).

## Decision

Existe un **Capability Registry** en el Kernel. Las capabilities se **registran** (nombre / contrato / metadata); el Controller pide al Registry **resolver** una referencia.

El Registry **resuelve, no decide**.

## Consecuencias

Agregar una capacidad = registrar un modulo (P15); el Control nunca conoce Retrieval / Memory / Planner / Verify por nombre concreto.

## Alternativas

Imports directos en el Controller (rechazado: acoplamiento y crecimiento del nucleo).
