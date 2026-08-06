# Skill: Engineering Context Builder

**Cuando:** antes de implementar cualquier cambio no trivial.  
**Objetivo:** descubrir, filtrar y resumir el conocimiento de ingenieria relevante a la tarea. Entregar un briefing curado — no una lista cruda de archivos.

## Entradas

- Descripcion de la tarea / issue / pedido del usuario.
- (Opcional) componentes tocados, tags conocidos.

## Pasos

1. **Extraer senales de la tarea**
   - Componentes probables (vocabulario de `_schema/metadata.md`: kernel, retrieval, evaluation, ...).
   - Tags/keywords (ej. bm25, latency, parity, facade).
   - Si menciona decision arquitectonica → incluir busqueda en `docs/adr/`.

2. **Descubrir**
   - Buscar en `knowledge/**/*.md` por `tags:`, `components:`, `id:` y texto del titulo.
   - Buscar en `docs/adr/*.md` por titulo y cuerpo (ADRs no usan el frontmatter EKS).
   - Incluir siempre, si existe: BM de baseline vigente y EXP abiertos del area.

3. **Filtrar**
   - Descartar docs con `status: superseded` salvo que la tarea sea historica.
   - Priorizar: `accepted` > `proposed` > `draft`.
   - Maximo orientativo: 5-8 docs EKS + 3-5 ADRs. Si hay mas, quedarse con los de mayor overlap de `components`/`tags`.

4. **Resumir (briefing)**
   Entregar al hilo de trabajo un bloque con esta forma:

   ```
   ## Engineering context
   ### ADRs aplicables
   - ADR-XXXX — una linea: decision y consecuencia relevante a la tarea
   ### Benchmarks / baselines
   - BM-XXX — metricas gate que no se pueden regresar
   ### Experiments previos
   - EXP-XXX — hipotesis y conclusion (o "abierto")
   ### Decisions / Patterns
   - DEC/PAT-XXX — que reutilizar o no repetir
   ### Research (si aplica)
   - RES-XXX — takeaway
   ### Huecos
   - Que no se encontro y habria que decidir/medir
   ```

5. **No implementar todavia**
   - Esta skill termina en el briefing. La implementacion es un paso posterior que ya parte del contexto.

## Reglas

- No inventar IDs ni metricas: solo lo leido.
- No crear `knowledge/adr/`. ADRs solo en `docs/adr/`.
- Si no hay hits, decirlo explicitamente en Huecos.
- Preferir citar paths absolutos del workspace al referir archivos.

## Salida

El briefing markdown de la seccion 4, listo para pegar al inicio del trabajo de implementacion.
