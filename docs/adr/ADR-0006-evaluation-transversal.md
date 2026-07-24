# ADR-0006 - Evaluation transversal: offline + online

- **Estado:** Propuesto
- **Fecha:** 2026-07-21

## Contexto

El benchmark actual evalua solo RAG. ASSESS y VERIFY en runtime son evaluacion en vivo. Separarlos rompe la unidad conceptual de "todo pasa por evaluacion".

## Decision

Evaluation es un plano transversal con dos modos del mismo contrato de senal:

- **Offline:** suites/benchmark (el harness actual es la suite v1).
- **Online (runtime):** ASSESS (suficiencia de evidencia) y VERIFY (respuesta soportada por citas) son el plano Evaluation aflorando en runtime; producen `EvaluationSignal`.

Evaluation **produce senales, no decide**. Las senales las consume el Policy Engine.

## Consecuencias

Unifica medicion offline y online; ASSESS/VERIFY dejan de ser capabilities sueltas y pasan a ser evaluadores.

## Alternativas

Assess/verify como capabilities normales (rechazado: rompia la unidad conceptual).
