# ADR-0000 - Proceso y formato de ADR

- **Estado:** Aceptado
- **Fecha:** 2026-07-21

## Contexto

Un solo autor y evolucion a anios; sin proceso, la documentacion se pudre.

## Decision

Toda decision arquitectonica se registra como ADR atomico e inmutable en `docs/adr/ADR-XXXX-*.md` con secciones Contexto / Decision / Consecuencias / Alternativas / Estado.

No se edita un ADR aceptado; se crea otro que lo supersede.

## Consecuencias

Historia auditable; overhead minimo por decision; evita el documento-monolito.

## Alternativas

Documento unico de arquitectura (rechazado: mezcla ciclos de vida distintos).
