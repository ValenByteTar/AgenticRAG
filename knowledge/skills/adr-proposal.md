# Skill: ADR Proposal

**Cuando:** se detecta una decision repetitiva, un cambio de frontera, o codigo/patron que implica arquitectura.  
**Objetivo:** **proponer** un ADR (o un Pattern) — nunca escribirlo y darlo por aceptado en silencio.

## Entradas

- Descripcion de la decision o del patron de codigo.
- Evidencia (archivos, DECs previas, EXPs).

## Pasos

1. **Clasificar severidad**

   | Senal | Destino |
   |-------|---------|
   | Cambia contrato Kernel / plano / principio | **ADR** en `docs/adr/` |
   | Solucion reutilizable sin nueva frontera | **Pattern** en `knowledge/patterns/` |
   | Local y reversible | **Decision** DEC (skill no aplica; usar template DEC) |
   | Ya existe ADR que cubre el caso | Citar el ADR; no proponer duplicado |

2. **Buscar colisiones**
   - Leer `docs/adr/README.md` e indice.
   - Grep en `docs/adr/` y `knowledge/` por tags/tema.
   - Si hay ADR relacionado: proponer **supersede** o **extension**, no un paralelo contradictorio (P12).

3. **Redactar propuesta (no commit automatico de aceptacion)**

   Para ADR, usar el formato de `docs/adr/ADR-0000-proceso-y-formato.md`:

   ```
   # ADR-XXXX - Titulo
   - Estado: Propuesto
   - Fecha: YYYY-MM-DD
   ## Contexto
   ## Decision
   ## Consecuencias
   ## Alternativas
   ```

   Para Pattern, copiar `knowledge/_templates/pattern.md` con frontmatter completo.

4. **Presentar al humano**
   - Mostrar el borrador completo.
   - Explicitar: "Estado: Propuesto — requiere aprobacion".
   - No marcar Aceptado ni actualizar el indice de ADRs como aceptado sin confirmacion.
   - Si el usuario aprueba: escribir el archivo, anadir fila en `docs/adr/README.md` (o patterns README), y enlazar `related` desde DECs/EXPs que lo motivaron.

5. **Si es Pattern + ADR**
   - Se pueden proponer ambos: PAT describe el "como reutilizar"; ADR fija la frontera.

## Reglas

- **P12:** ADRs aceptados no se editan; se superseden.
- **No** crear `knowledge/adr/`.
- No auto-aceptar.
- Una decision por ADR (atomico).

## Salida

- Borrador del ADR o PAT.
- Lista de ADRs relacionados / riesgo de colision.
- Pregunta explicita de aprobacion al usuario.
