# Engineering Knowledge System (EKS)

Memoria de ingenieria del proyecto. **No es documentacion estatica.** Acumula experiencia, registra decisiones, conserva evidencia experimental y guia a Devin/Cascade en tiempo de desarrollo.

Formalizado en [ADR-0017](../docs/adr/ADR-0017-engineering-knowledge-system.md).

## Que es / Que NO es

| Es | NO es |
|----|-------|
| Experiencia de ingenieria (dev-time) | Knowledge System runtime (ADR-0015, Ola 3) |
| Fuera de `src/`; no lo consume el Kernel | Parte del plano Knowledge de runtime |
| Formato fijo + metadata filtrable | Documentos libres sin estructura |
| Consumido por Skills de desarrollo | Un segundo arbol de ADRs |

## Donde viven los ADRs

**Unica casa:** `docs/adr/`.

No existe `knowledge/adr/`. La relacion entre un doc EKS y un ADR se expresa con el campo `related` del frontmatter (ej. `related: [ADR-0006]`).

## Estructura

```
knowledge/
  _schema/metadata.md     # contrato de frontmatter compartido
  _templates/             # plantillas por categoria
  decisions/              # DEC — micro-decisiones (no merecen ADR)
  experiments/            # EXP — hipotesis, config, resultados
  benchmarks/             # BM  — mediciones congeladas
  postmortems/            # PM  — incidentes y prevencion
  patterns/               # PAT — soluciones reutilizables
  research/               # RES — papers, ideas, comparativas
  skills/                 # skill-docs que consumen el EKS
```

## Arbol de decision (¿que carpeta?)

| Pregunta | Destino |
|----------|---------|
| ¿Cambia una frontera arquitectonica? | **ADR** en `docs/adr/` (no aqui) |
| ¿Decision pequena que no merece ADR? | `decisions/` |
| ¿Probamos algo y medimos? | `experiments/` |
| ¿Congelamos metricas de referencia? | `benchmarks/` |
| ¿Algo se rompio y aprendimos? | `postmortems/` |
| ¿Solucion reutilizable a un problema recurrente? | `patterns/` |
| ¿Investigacion sin decision aun? | `research/` |

## Como se usa

1. **Antes de implementar:** skill [Engineering Context Builder](skills/engineering-context-builder.md).
2. **Despues de un experimento:** skill [Experiment Logging](skills/experiment-logging.md).
3. **Al detectar decision repetitiva o codigo repetido:** skill [ADR Proposal](skills/adr-proposal.md).

Todo documento nuevo: copiar el template de `_templates/`, completar frontmatter (`_schema/metadata.md`) y secciones fijas.

## Diferido

- Index generado (disparo ~30-40 docs).
- Knowledge Curator (dev-time; nombre distinto del Knowledge Architect runtime).
