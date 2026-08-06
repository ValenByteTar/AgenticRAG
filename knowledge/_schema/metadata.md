# EKS Metadata Schema

Contrato de frontmatter YAML obligatorio en todo documento bajo `knowledge/`.

Disenado para reuso futuro por el Knowledge System runtime (ADR-0015) **sin fusionar planos**: mismo schema de documento, consumidores distintos (dev-time vs runtime).

## Campos

```yaml
---
id:            # string unico. Prefijos: DEC-NNN | EXP-NNN | BM-NNN | PM-NNN | PAT-NNN | RES-NNN
category:      # decision | experiment | benchmark | postmortem | pattern | research
status:        # draft | proposed | accepted | rejected | superseded
created:       # YYYY-MM-DD
updated:       # YYYY-MM-DD  (obligatorio al editar)
author:        # humano o agente (ej. cascade, human)
components:    # lista de fronteras tocadas (ver vocabulario)
tags:          # lista libre de terminos de busqueda
related:       # lista de IDs EKS o ADR (ej. [ADR-0006, EXP-001])
supersedes:    # id o null
superseded_by: # id o null
---
```

## Vocabulario de `components`

Usar solo fronteras del sistema (plan v2):

- `kernel`
- `control`
- `capabilities`
- `knowledge`          # plano Knowledge runtime (no el EKS)
- `evaluation`
- `observability`
- `configuration`
- `retrieval`
- `generation`
- `providers`
- `policies`
- `facade`             # fachada de consulta / HybridRAG.query

## Prefijos de ID

| Prefijo | Categoria | Carpeta |
|---------|-----------|---------|
| DEC | decision | `decisions/` |
| EXP | experiment | `experiments/` |
| BM | benchmark | `benchmarks/` |
| PM | postmortem | `postmortems/` |
| PAT | pattern | `patterns/` |
| RES | research | `research/` |

IDs monotónicos por categoria (DEC-001, DEC-002, ...). No reutilizar IDs.

## Relacion con ADRs

Los ADRs **no** usan este frontmatter (tienen su propio formato en `docs/adr/`). Un doc EKS referencia ADRs via `related: [ADR-XXXX]`.

## Status

Alineado al ciclo de decision (P12): documentos aceptados no se reescriben en sustancia; se superseden con un nuevo ID y se rellenan `supersedes` / `superseded_by`.
