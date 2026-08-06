# ADR-0011 - Local-first como invariante

- **Estado:** Aceptado
- **Fecha:** 2026-07-21

## Contexto

Privacidad es el proposito del proyecto.

## Decision

Ninguna implementacion puede requerir una llamada de red saliente de datos del usuario para el flujo principal. Toda capacidad debe tener camino local.

## Consecuencias

Descarta tools/servicios cloud como dependencia dura; frameworks que asuman cloud quedan excluidos.

## Alternativas

Cloud-first (rechazado por vision).
