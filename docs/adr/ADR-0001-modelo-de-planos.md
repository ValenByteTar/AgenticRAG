# ADR-0001 - Modelo de planos: 3 verticales + 3 transversales

- **Estado:** Propuesto
- **Fecha:** 2026-07-21

## Contexto

Las capacidades futuras (memoria, tools, agentes, Knowledge Architect) deben entrar sin tocar el nucleo. Evaluation y Observability no son capacidades.

## Decision

Tres planos verticales (Control, Capabilities, Knowledge) atravesados por tres transversales (Observability, Evaluation, Configuration). Las transversales no son capabilities.

## Consecuencias

Ubicacion clara de cada componente; evita meter evaluacion/observabilidad como capabilities.

## Alternativas

Planos sin transversales (rechazado: convertia Evaluation en capability, contradiciendo "todo pasa por evaluacion").
