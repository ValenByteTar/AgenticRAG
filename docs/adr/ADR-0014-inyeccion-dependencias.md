# ADR-0014 - Inyeccion de dependencias y Composition Root

- **Estado:** Propuesto
- **Fecha:** 2026-07-21

## Contexto

Definir ModelProvider / Knowledge / Memory / Tool / Controller / Steps ya es, de facto, definir un contenedor.

## Decision

Se adopta **inversion de dependencias como principio** (P13): ningun componente instancia sus dependencias; las recibe por constructor/parametro.

Un unico **Composition Root** cablea implementaciones concretas al arrancar.

**No** se implementa un framework/contenedor DI (evita complejidad, P11).

## Consecuencias

Bajo acoplamiento, testeo con dobles, un solo lugar de wiring.

## Alternativas

Framework DI (rechazado hoy: sobre-ingenieria). Instanciacion directa (rechazado: acoplamiento actual `rag=self`).
