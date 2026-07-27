# InfraPolus - Principios Arquitectonicos

Reglas inviolables. Romper una exige un ADR que lo justifique.

La jerarquia de la [filosofia](philosophy.md) resuelve empates entre principios.

## Principios

- **P1. Local-first e integro.** Ningun dato del usuario sale del entorno local.
- **P2. Contratos estables, implementaciones desechables.** El Kernel conoce contratos, no implementaciones.
- **P3. Observabilidad antes que magia.** Toda decision es trazable, atribuible y reproducible.
- **P4. Medible antes que inteligente.** Ninguna capacidad se integra sin forma de medir su efecto.
- **P5. Sin estado oculto.** El estado es explicito y serializable (`ExecutionState`).
- **P6. Separacion de planos.** Control, Capabilities y Knowledge no se mezclan; el Control no conoce implementaciones de capabilities.
- **P7. El dominio es dato, no arquitectura.** El nucleo no codifica supuestos de ciberseguridad.
- **P8. Fachada estable / compatibilidad hacia atras.** Los contratos externos se versionan.
- **P9. Determinismo en el control, razonamiento en el lenguaje.** El flujo es deterministico; el LLM razona/genera, no decide el flujo salvo tras seam explicito y medible.
- **P10. Terminacion garantizada.** Todo bucle agentico tiene presupuesto y parada.
- **P11. Abstraer por costo de cambio.** Se abstrae solo donde el costo de cambiar la frontera es mucho mayor que mantener la abstraccion. Ni "por si acaso" ni "siempre tarde".
- **P12. ADRs inmutables.** Las decisiones no se editan; se superseden.
- **P13. Inversion de dependencias.** Ningun componente crea directamente sus dependencias. Se reciben por inyeccion; solo el Composition Root cablea implementaciones. (No implica un framework DI; ver ADR-0014.)
- **P14. Una responsabilidad por eslabon.** Evaluation senaliza, Policy decide, Controller ejecuta, Registry resuelve, Capability trabaja. Ningun eslabon invade al siguiente.
- **P15. Registrar, no cablear.** Agregar una capacidad es registrarla en el Registry, nunca modificar el Controller ni el Kernel.
- **P16. Ownership de decisiones.** Cada decision tiene un unico dueno; ningun otro componente la toma, sobrescribe ni replica. (ADR-0020)
- **P17. La observabilidad no cambia el comportamiento.** Instrumentacion, benchmarking, tracing y evaluacion pueden ampliar la informacion disponible, pero nunca modificar las decisiones del pipeline. (ADR-0020)

## Criterio operativo de P11

Contratos estables SOLO para fronteras garantizadas a futuro aunque su implementacion cambie:

- ModelProvider
- KnowledgeSystem
- Controller
- RetrievalPipeline
- Tools
- Evaluation
- Memory
- Capability / Registry
- Policy

**NO** se abstraen aun (evolucionan por refactor):

- Planner
- Knowledge Architect
- Taxonomia de memoria
- Esquema interno del Knowledge System
