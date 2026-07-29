---
id: DEC-012
title: "Storage backend del Artifact Registry: filesystem versionado con swap atomico de puntero"
date: 2026-07-28
status: accepted
category: decisions
tags: [artifact-registry, storage, filesystem, atomic-swap, integrity, retention]
related: [ADR-0018, RES-001, DEC-011]
---

# DEC-012 — Storage backend del Artifact Registry

## Contexto

E2 implementa el Artifact Registry como componente con identidad propia (RES-001 §5: "no es un
directorio"). El backend de almacenamiento quedo como open question de RES-001: filesystem
versionado vs SQLite vs otro. La operacion critica es `promote`: el swap del puntero al build
activo debe ser atomico — un Consumer resolviendo nunca puede ver un estado intermedio.

## Decision

**Filesystem versionado, puntero atomico por rename, estado en JSON.**

Layout:

```
<registry_root>/
  builds/
    <build_id>/
      manifest.json
      artifacts/
        <artifact>.json
  state/
    active.json        # puntero: {"build_id": ..., "promoted_at": ...}
    builds_index.json  # build_id -> {state, created_at, promoted_at, deprecated_at, archived_at}
```

Reglas:

1. **Swap atomico**: `promote` escribe `active.json.tmp` y aplica `os.replace` (atomico en el
   mismo volumen, incluido Windows). Nunca se escribe el puntero in-place.
2. **Immutabilidad de builds**: un build publicado no se modifica. Toda mutacion de estado vive en
   `builds_index.json`, fuera del build.
3. **Checksums sobre bytes**: el `sha256` del manifest se computa sobre los bytes exactos del
   archivo escrito. La escritura usa serializacion canonica (`sort_keys`, UTF-8) para que el
   checksum sea reproducible por el Builder. `verify_integrity` relee los bytes y re-hashea.
4. **Retencion como funcion de operador** (`apply_retention`), no como operacion nueva de la
   interfaz de 7: `deprecated` -> `archived` por conteo, `archived` -> `purged` por antiguedad.
   El build activo y el candidato de rollback nunca se purgan.
5. **Migrations como transforms registradas** `(from_version, to_version) -> fn(manifest,
   artifacts)`, aplicadas y luego revalidadas con `validate_build` de la version destino. En
   warm-v1 el registro esta vacio (no hay version destino aun).

## Consecuencias

- Inspeccionable con herramientas basicas (explorador, diff, gitignore-able).
- Sin dependencias nuevas: `os.replace`, `hashlib`, `json` de stdlib.
- La interfaz de 7 operaciones de RES-001 §5.1 se mantiene intacta: el backend es detalle detras
  del componente.
- Un backend distinto (SQLite, object storage) puede reemplazarse despues sin tocar Builder ni
  Consumer: solo implementa la misma interfaz.

## Alternativas consideradas

1. **SQLite**: transaccional de por si, pero opaco a inspeccion manual, agrega un artefacto binario
   al repo y obliga a migrar blobs de artifacts de todas formas. Rechazado para el contexto actual
   (single-machine, builds de baja frecuencia).
2. **Git como backend**: versionado gratis, pero acopla el runtime a git y mezcla historia de
   codigo con historia de builds. Rechazado.
3. **Puntero por symlink**: atomico, pero requiere privilegios de desarrollador en Windows.
   Rechazado.

## Criterios de aceptacion

- Round-trip E2E: publish -> staging -> promote -> resolve -> rollback.
- Corrupcion de un artifact en disco detectada por `verify_integrity` y por `resolve`.
- `contract_version` incompatible rechazada en `publish` y en `promote`.
- Un solo build activo en todo momento; swap sin estados intermedios.

## Por que no es ADR

No define frontera ni interfaz nueva: elige la implementacion interna de un componente cuya
interfaz ya esta fijada por RES-001 §5.1 bajo ADR-0018. Es reemplazable sin tocar el contrato
(otro backend, misma interfaz). Vive como DEC.
