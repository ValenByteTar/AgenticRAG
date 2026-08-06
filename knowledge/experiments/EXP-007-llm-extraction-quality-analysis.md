---
id: EXP-007
title: "Calidad de extraccion LLM Granite-4.1-8b en corpus cybersecurity: analisis preliminar"
date: 2026-07-31
status: in_progress
category: experiments
tags: [knowledge-builder, llm-extraction, kir, granite, quality, coverage, evidence]
related: [RES-002, ADR-0018, DEC-011, BM-004]
---

# EXP-007 — Calidad de extraccion LLM Granite-4.1-8b en corpus cybersecurity

## Hipotesis

El modelo `ibm/granite4.1:8b-q4_K_M` produce extracciones KIR de calidad suficiente para alimentar Warm Artifacts en el pipeline del Knowledge Builder, con las siguientes sub-hipotesis:

**H1 — Precision semantica**: Las entidades, relaciones y evidence extraidas por el LLM son semanticamente correctas y verificables contra el texto fuente.

**H2 — Cobertura parcial aceptable**: El LLM no extrae exhaustivamente todas las entidades de un documento, pero la cobertura parcial (40-70%) es suficiente para construir un Knowledge Model utilizable despues de los passes de compilacion (Normalize + Canonicalize + Dedup).

**H3 — Calidad varía por tipo de documento**: Los documentos estructurados (listas, tablas, comandos) obtienen mejor cobertura que los documentos narrativos/analiticos densos (reportes, guias normativas).

**H4 — Ruido es filtrable**: Las entidades de ruido (ej: "Unknown", metadatos de pagina) son minoria y pueden ser filtradas por el compilador via confidence thresholds o Dedup.

## Setup

- **Modelo**: `ibm/granite4.1:8b-q4_K_M` via Ollama (GPU, timeout=300s)
- **Build ID**: `ka_v2.0.0_full`
- **Corpus**: 928 documentos PDF de cybersecurity (extraidos a texto con PyMuPDF)
- **Chunking**: ~4000 chars por chunk (config.yaml: chunking)
- **Cache**: chunk-level KIR con SHA-256, skip cache en extraction_error
- **Extractor**: `LLMEntityExtractor` en `knowledge_builder/frontend/llm_entity_extractor.py`
- **Schema KIR**: entity_claims, alias_claims, document_claims, relation_claims (con evidence, confidence, raw metadata)

## Resultados preliminares

### Metricas globales (build parcial: 26/928 docs, 640 chunks)

| Metrica | Valor |
|---------|-------|
| Documentos cacheados | 26 de 928 (2.8%) |
| Chunks totales | 640 |
| Claims totales | 6,988 |
| Errores de extraccion | 0 |
| Avg claims/chunk | 10.9 |
| Avg claims/doc | 268.8 |

### Caso 1: "100 Essential Linux Commands.pdf" — Documento estructurado (lista de comandos)

**Perfil**: 4 chunks, 112 claims. Documento con listas estructuradas de comandos agrupados por categoria (File Operations, Networking, Text Processing, etc.).

| Criterio | Score | Notas |
|----------|-------|-------|
| Cobertura | 7/10 | Capto comandos principales de cada seccion. Omite variantes (`ls -R`, `ls -a`, `ls -al`) y comandos menores (`tar`, `dd`, `hdparm`) |
| Precision evidence | 10/10 | Quotes literales del PDF en cada claim |
| Tipos de entidad | 6/10 | Usa `command`, `concept`, `technology`. Inconsistente: `iostat` como `technology` pero deberia ser `command` |
| Relaciones | 8/10 | Semantica en lenguaje natural, normalizable al catalogo v2 |
| Document claims | 8/10 | Summary preciso por chunk |
| Ruido | 9/10 | Sin ruido significativo |

**Hallazgo clave**: Las entidades tienen `surface_form`, `canonical_name`, `entity_types`, `confidence`, `evidence` con quote literal. Las relaciones capturan la semantica del comando (ej: `ls` -> "lists files and directories in" -> `present working directory`).

### Caso 2: "1-Routing Basics.pdf" — Documento tecnico con diagramas (networking)

**Perfil**: 5 chunks, 78 claims. PDF de Cisco ISP Workshops (46 paginas) sobre fundamentos de routing: IPv4, IGP/EGP, BGP, OSPF, distancias administrativas.

| Criterio | Score | Notas |
|----------|-------|-------|
| Cobertura | 8/10 | Capta conceptos, protocolos, ASes, valores numericos exactos |
| Precision evidence | 10/10 | Quotes literales del PDF |
| Tipos de entidad | 9/10 | Usa `autonomous_system`, `network`, `link_type`, `protocol`, `concept`, `technology` — tipado rico de dominio |
| Relaciones | 10/10 | Modelo el flujo de routing multi-AS con 10 relaciones precisas. Tabla de distancias administrativas extraida con valores exactos (OSPF=110, RIP=120, etc.) |
| Document claims | 8/10 | Summaries precisos |
| Ruido | 7/10 | `Unknown` como entidad (conf=0.8) — basura de la tabla |

**Hallazgo clave**: El LLM entendio la semantica del documento, no solo nombres. Modelo el flujo de routing entre ASes (AS1 -> "announces to" -> AS2), la taxonomia de protocolos (BGP4 -> "is a type of" -> EGP), y valores numericos exactos de la tabla de distancias administrativas de Cisco. **Mejor calidad que el Caso 1** a pesar de ser un documento mas abstracto.

### Caso 3: "02 ISOIEC 27001 Implementation Guide.pdf" — Documento normativo denso

**Perfil**: 37 chunks, 334 claims. Guia de implementacion ISO/IEC 27001:2013 (38 paginas, 112K chars). Documento normativo con 14 secciones de controles Annex A (A.5 a A.18), referencias cruzadas a multiples estandares, procesos de auditoria.

| Criterio | Score | Notas |
|----------|-------|-------|
| Cobertura de controles | 5/14 | Solo A.5, A.6, A.8, A.9, A.10 extraidos como entidades. Faltan 9 de 14 controles Annex A |
| Precision normativa | 9/10 | Relaciones capturan requisitos reales del estandar (SoA obligatorio, policies aprobadas por top management, Annex A como menu para risk treatment) |
| Tipos de entidad | 8/10 | Usa `standard`, `procedure`, `policy`, `process`, `document`, `concept`, `report`, `questionnaire`, `presentation` |
| Relaciones cruzadas | 9/10 | 27001 -> 31000, 27001 -> 27005, 27001 -> Annex SL — todas correctas |
| Evidence | 9/10 | Quotes literales del PDF |
| Densidad | 6/10 | 3-7 entidades por chunk — bajo para documento denso |
| Ruido | 8/10 | `Passwords Awareness Poster` como entidad es discutible |

**Hallazgo clave**: La precision normativa es excelente (las relaciones capturan requisitos jerarquicos correctos del estandar), pero **la cobertura es incompleta** — 9 de 14 controles Annex A no fueron extraidos. El LLM demuestra comprension del dominio normativo pero es conservador en la cantidad de extracciones por chunk.

**Problema detectado**: Relacion `ISO/IEC 27001` -> "implements" -> `Access Control Policy` es semantica invertida — el estandar *requiere* implementar la policy, no la *implementa*. El compilador deberia normalizar esto.

### Caso 4: "2022 Data Breach Investigations Report.pdf" — Reporte analitico abstracto

**Perfil**: 61 chunks, 608 claims. DBIR 2022 de Verizon (198K chars, ~100 paginas). Reporte analitico con estadisticas, patrones de ataque (VERIS), tendencias multi-anio, analisis por industria y region, eventos de ransomware, frameworks de seguridad.

| Criterio | Score | Notas |
|----------|-------|-------|
| Cobertura de conceptos | 8/10 | Capta VERIS, threat actors, attack patterns, frameworks (CIS, MITRE ATT&CK), eventos especificos |
| Precision evidence | 10/10 | Quotes literales del PDF |
| Tipos de entidad | 9/10 | Usa `actor`, `attack_pattern`, `malware`, `threat_actor`, `APT`, `organization`, `infrastructure`, `standard`, `framework`, `report` — tipado muy rico |
| Relaciones | 9/10 | Modelo eventos de ransomware con actores y victimas (DarkSide -> Colonial Pipeline, REvil -> Kaseya VSA), mapeos entre frameworks (VERIS -> CIS, VERIS -> MITRE ATT&CK) |
| Densidad | 7/10 | 2-10 entidades por chunk — variable, mayor en chunks con eventos concretos |
| Document claims | 8/10 | Summaries precisos por chunk |
| Ruido | 8/10 | `2022` y `2008` como entidades tipo `year` — discutible pero no incorrecto |

**Hallazgos clave por chunk**:

- **Chunk 1 (VERIS framework)**: Extrajo `VERIS` (framework), `Threat actor` (concept), `Malware` (threat_action). Relaciones: `VERIS` -> "defines" -> `Threat actor`, `VERIS` -> "classifies into categories" -> `Threat action`. **Correcto y preciso.**

- **Chunk 10 (Assets)**: Extrajo `Servers`, `Web application servers`, `Mail servers`, `Operational Technology (OT)` con estadisticas exactas: Web app servers -> "account for" -> "56% of top asset varieties", Mail servers -> "account for" -> "28%". **Valores numericos correctos.**

- **Chunk 20 (Social Engineering pattern)**: Extrajo `Phishing`, `BECs`, `Credentials`, `Ransomware`, `Downloader`, `Backdoor or C2`. Relaciones: `Phishing` -> "is a dominant entry point into" -> `organization`, `Phishing` -> "steals" -> `credentials`, `BECs` -> "is almost entirely composed of" -> `pretexting`. **Semantica de ataque correcta.**

- **Chunk 40 (Industry analysis)**: Extrajo `External` (actor), `Internal` (actor), `System Intrusion` (attack_pattern), `Social Engineering` (attack_pattern), `Basic Web Application Attacks` (attack_pattern). Relaciones: `System Intrusion` -> "has drop-kicked" -> `Social Engineering` out of top three. **Lenguaje coloquial pero semantica correcta.**

- **Chunk 50 (Year in review — ransomware events)**: **Mejor chunk del corpus analizado.** 10 entidades, 6 relaciones. Extrajo `Colonial Pipeline`, `DarkSide ransomware`, `Fancy Lazarus`, `REvil ransomware`, `Kimsuky`, `APT29`, `Kaseya VSA`, `BlackMatter ransomware`, `SolarWinds Serv-U`, `Poly Network`. Relaciones con evidence literal:
  - `DarkSide ransomware` -> "caused" -> `Colonial Pipeline shutdown` (conf=0.96)
  - `REvil ransomware` -> "abused" -> `Kaseya VSA` (conf=0.94)
  - `BlackMatter ransomware` -> "incorporated features from" -> `DarkSide` (conf=0.9)
  - `Chinese threat actor` -> "targeted" -> `SolarWinds Serv-U software` (conf=0.88)
  - `Poly Network` -> "experienced a theft of" -> "$600 million in cryptocurrencies" (conf=0.85)
  
  **Esto es extraccion de inteligencia de amenazas de calidad profesional.**

- **Chunk 55 (Appendix B — VERIS and Standards)**: Extrajo `VERIS`, `CIS Critical Security Controls`, `MITRE ATT&CK`, `DBIR`. Alias: `CSC` -> `CIS Critical Security Controls`, `ATT&CK` -> `MITRE Adversary Tactics...`. Relaciones: `VERIS` -> "aligns with" -> `CIS CSC`, `VERIS` -> "maps to" -> `MITRE ATT&CK`. **Mapeo entre frameworks correcto.**

## Analisis comparativo

| Dimension | Linux Commands | Routing Basics | ISO 27001 Guide | DBIR 2022 |
|------------|----------------|----------------|-----------------|-----------|
| Tipo | Lista estructurada | Tecnico con diagramas | Normativo denso | Reporte analitico |
| Chunks | 4 | 5 | 37 | 61 |
| Claims | 112 | 78 | 334 | 608 |
| Claims/chunk | 28.0 | 15.6 | 9.0 | 10.0 |
| Cobertura | 7/10 | 8/10 | 5/10 | 8/10 |
| Precision | 10/10 | 10/10 | 9/10 | 10/10 |
| Tipado | 6/10 | 9/10 | 8/10 | 9/10 |
| Relaciones | 8/10 | 10/10 | 9/10 | 9/10 |
| Ruido | 9/10 | 7/10 | 8/10 | 8/10 |

## Conclusiones preliminares

### H1 — Precision semantica: **CONFIRMADA**

En los 4 casos analizados, la precision de evidence es 9-10/10. Los quotes son literales del PDF. Las relaciones son semanticamente correctas (con la excepcion de inversiones ocasionales como "implements" vs "requires"). El LLM no alucina entidades — lo que extrae es verificable contra el texto fuente.

### H2 — Cobertura parcial aceptable: **PARCIALMENTE CONFIRMADA**

La cobertura varía entre 5/10 (ISO 27001) y 8/10 (Routing Basics, DBIR). La cobertura parcial es utilizable para Knowledge Builder, pero el caso ISO 27001 muestra que documentos normativos densos pueden tener gaps significativos (9 de 14 controles Annex A faltantes). El compilador no puede inventar lo que no se extrajo.

### H3 — Calidad varía por tipo de documento: **CONFIRMADA**

- **Documentos estructurados** (Linux Commands): alta densidad (28 claims/chunk), cobertura buena, tipado inconsistente
- **Documentos tecnicos** (Routing Basics): mejor calidad integral, tipado rico de dominio, relaciones excelentes
- **Documentos normativos** (ISO 27001): precision normativa alta pero cobertura baja, densidad baja (9 claims/chunk)
- **Reportes analiticos** (DBIR): tipado muy rico, excelente en eventos concretos (chunk 50), variable en secciones analiticas

### H4 — Ruido es filtrable: **CONFIRMADA**

El ruido es minoria (1-2 entidades por documento como maximo): `Unknown` (DBIR), `Passwords Awareness Poster` (ISO 27001), `2022`/`2008` como entidades tipo `year` (DBIR). Todos tienen confidence < 1.0 y pueden filtrarse con threshold o Dedup.

## Riesgos identificados

| Riesgo | Probabilidad | Impacto | Mitigacion |
|--------|-------------|---------|------------|
| Cobertura incompleta en documentos normativos | Alta | Medio | Prompt engineering especifico para documentos normativos (ej: "extrae todos los controles mencionados") |
| Inversion semantica en relaciones | Baja | Bajo | Pass de normalizacion en compilador (Normalize) |
| Densidad variable por chunk | Media | Medio | Ajustar chunk size o prompt para extraer mas entidades por chunk |
| Ruido de metadatos de pagina | Baja | Bajo | Filtro por confidence < 0.75 o blacklist de tipos (`year`, `unknown`) |
| Throughput (~100s/chunk nuevo) | Alta | Alto | Modelo 8B en GPU (~100s/chunk). El cuello de botella es el tamanio del modelo y la cantidad de chunks (928 docs x multiples chunks). Considerar modelo mas pequeno con prompt optimizado o batch processing |

## Pendiente

- Completar extraccion del corpus completo (928 docs) y re-evaluar metricas globales
- Ejecutar compile + validate sobre el build `ka_v2.0.0_full` y medir cuantas entidades sobreviven los passes de normalizacion
- Comparar Warm Artifacts generados vs Vector DB retrieval en benchmark de calidad (BM-007 propuesto)
- Experimentar con prompt variations para mejorar cobertura en documentos normativos
- Medir impacto de confidence threshold en filtrado de ruido
