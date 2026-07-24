# ADR-0007 - ModelProvider

- **Estado:** Propuesto
- **Fecha:** 2026-07-21

## Contexto

Hoy `mistral:7b` / Ollama estan hardcodeados; el hardware crecera y habra multiples modelos.

## Decision

Todo acceso a modelos (generacion, y a futuro scoring/embeddings de razonamiento) pasa por un contrato `ModelProvider` (generate/stream, metadata de capacidad y costo).

Ollama es la primera implementacion. El nombre de modelo se lee de configuracion, no se hardcodea.

## Consecuencias

Cambiar/agregar modelos o correr varios es adicion, no reescritura. Frontera de altisimo costo de cambio -> se declara ahora (P11).

## Alternativas

Llamadas directas a Ollama (rechazado: acoplamiento irreversible).
