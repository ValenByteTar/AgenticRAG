# ADR-0009 - Contratos de Memory y Tool

- **Estado:** Aceptado
- **Fecha:** 2026-07-21

## Contexto

Memoria y herramientas son fronteras garantizadas por la vision; sus tipos concretos no.

## Decision

Declarar contratos minimos:

- **Memory:** read con provenance; write controlado y verificable
- **Tool:** invocacion tipada con entrada/salida y trazas

Implementacion inicial minima (Memory de solo-lectura sobre lo existente; catalogo de Tools vacio o con retrievers internos).

## Consecuencias

Agregar memoria de largo plazo o una herramienta especializada es implementar el contrato.

## Diferido

Tipos de memoria (episodica/semantica), politica de aprendizaje.
