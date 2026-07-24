# InfraPolus - Vision Arquitectonica

## Que es InfraPolus

Plataforma local-first de IA especializada en conocimiento tecnico, razonamiento y ciberseguridad, disenada para incorporar capacidades durante anios sin reescritura del nucleo. El Hybrid RAG actual es su primera capacidad, no su definicion.

## El Kernel

El **Kernel es el nucleo minimo y estable contra el que se enchufa todo lo demas.** Regla de oro: **el Kernel conoce contratos, jamas implementaciones.** Cambia casi nunca; si cambia seguido, esta mal disenado.

**Vive DENTRO del Kernel (estable):**

- Contratos: `ModelProvider`, `Capability`, `Step`, `Policy`, `EvaluationSignal`, `KnowledgeSystem`, `Memory`, `Tool`, `Controller`
- `ExecutionState` (estado explicito y serializable)
- Runtime del Controller (bucle que ejecuta acciones y garantiza terminacion)
- Capability Registry (mecanismo de registro/resolucion, no las capacidades)
- Policy Engine (motor que evalua policies, no las policies concretas)
- Hooks de Observability y contratos de Evaluation y Configuration
- Composition Root (unico lugar que cablea implementaciones concretas)

**Vive FUERA del Kernel (desechable/extensible):**

- Toda implementacion concreta: capabilities, policies, model providers, Knowledge System, memorias, tools, suites de evaluacion

Agregar una capacidad = escribir un modulo que cumple un contrato y **registrarlo**. El Kernel no se toca.

Codigo de referencia: `src/kernel/`.

## Modelo de planos

Tres planos verticales, atravesados por tres preocupaciones transversales.

```
CONTROL          | CAPABILITIES       | KNOWLEDGE
Controller,      | Retrieval, Gen,    | Knowledge System:
Policy Engine,   | Assess, Verify,    | entidades, relaciones,
Registry         | Planner, Tools     | provenance, confianza,
                 | (todas plugin)     | evidencia, derivaciones,
                 |                    | versiones
-----------------+--------------------+------------------------
transversal: OBSERVABILITY
transversal: EVALUATION   (offline: suites | online: senales)
transversal: CONFIGURATION
```

Observability, Evaluation y Configuration **no son capacidades**; atraviesan todo.

## Cadena de responsabilidad de runtime

> **Evaluation produce senales; Policy interpreta esas senales; Controller ejecuta la accion; Registry resuelve la capacidad; Capability realiza el trabajo.**

```
EVALUATION --senales--> POLICY --decision--> CONTROLLER --ref--> REGISTRY --cap--> CAPABILITY
     ^                                                                              |
     +---------------------- nuevas senales tras el trabajo ------------------------+
```

- Evaluation no decide. Policy no ejecuta. Controller no conoce capacidades concretas. Registry no decide. Capability no enruta.
- Ningun eslabon puede convertirse en god object: cada uno esta estructuralmente impedido de invadir al siguiente.

## Horizonte de capacidades

- **Ola 1 fundacional:** Kernel, Retrieval, Gen, Evaluation, Observability, Control
- **Ola 2 agentica:** Assess, Retry, Verify, Planner
- **Ola 3 conocimiento:** Knowledge System pleno, memoria verificada, Knowledge Architect
- **Ola 4 compuesta:** agentes especializados, tools, aprendizaje, multi-modelo
- **Ola 5 emergente:** capacidades hoy inexistentes admitidas por adicion

## No-goals

- No es asistente generalista
- No es cloud/multi-tenant (local-first invariante)
- No es producto rapido (es base tecnologica)
- No es wrapper de frameworks de agentes

## Definicion de exito

InfraPolus tiene exito si, dentro de 12-24 meses, **agregar una capacidad de Ola 3-4 significa implementar contra un contrato existente y registrar un ADR, no reescribir el nucleo.**
