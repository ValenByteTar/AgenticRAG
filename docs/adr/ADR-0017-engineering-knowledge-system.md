# ADR-0017 - Engineering Knowledge System (EKS) dev-time con schema compartido

- **Estado:** Aceptado
- **Fecha:** 2026-07-22

## Contexto

Falta memoria de ingenieria estructurada. Devin/Cascade necesita contexto curado al implementar: decisiones previas, experimentos, benchmarks, patterns y research. Hoy eso vive disperso o no se registra.

El Knowledge System runtime (ADR-0015) es un plano distinto: conocimiento de dominio para el usuario final. No debe mezclarse con la experiencia de ingenieria del proyecto (P6, P7).

## Decision

Se adopta un **Engineering Knowledge System (EKS)** exclusivamente **dev-time**:

1. Vive en `knowledge/` en la raiz del repo, **fuera de `src/`**. No lo consume el runtime.
2. Seis categorias con formato fijo: `decisions/`, `experiments/`, `benchmarks/`, `postmortems/`, `patterns/`, `research/`.
3. **No** existe `knowledge/adr/`. Los ADRs tienen una unica casa en `docs/adr/`. La relacion EKS <-> ADR se expresa via el campo `related` del frontmatter.
4. Todo documento EKS usa un **schema de metadata compartido** (`knowledge/_schema/metadata.md`), disenado para reuso futuro por el Knowledge System runtime sin fusionar planos.
5. Tres skills consumen el EKS: Engineering Context Builder, Experiment Logging, ADR Proposal.
6. Index generado y Knowledge Curator quedan **diferidos** (P11) hasta umbral de volumen.

## Consecuencias

- Memoria de ingenieria organizada, filtrable y accionable por el agente.
- Separacion clara: arquitectura en `docs/`, experiencia en `knowledge/`, ADRs solo en `docs/adr/`.
- Schema reutilizable a futuro por ADR-0015 sin acoplar dev-time y runtime.
- Overhead de escritura bajo (templates fijos); riesgo de frontmatter desactualizado mitigado por `updated` obligatorio.

## Alternativas

- **Todo bajo `docs/`** — rechazado: mezcla arquitectura estable con experiencia de ciclo corto.
- **Fusionar EKS con Knowledge System runtime** — rechazado: viola P6/P7.
- **Index + Curator ahora** — rechazado: viola P11; sin volumen el index a mano se desincroniza.
- **`knowledge/adr/` como puntero a `docs/adr/`** — rechazado: dos caminos al mismo concepto generan ruido.
