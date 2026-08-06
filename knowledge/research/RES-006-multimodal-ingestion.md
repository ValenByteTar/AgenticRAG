---
id: RES-006
category: research
status: proposed
created: 2026-07-29
updated: 2026-07-29
author: human
components: [knowledge_builder, pdf_extractor, llm_entity_extractor, vector_store, kir_cache, acquisition_connectors, normalizers, canonical_document, cir]
tags: [architecture, ingestion, multimodal, vision-llm, ocr, connectors, knowledge-sources, extensible, canonical-document, normalizer, cir, versioning, fingerprint]
related: [RES-005, RES-002, ADR-0021, ADR-0018]
supersedes: null
superseded_by: null
---

# RES-006 - Multimodal Ingestion: Knowledge Sources, Normalizers & Acquisition Connectors

## Topic

Extender el pipeline de ingesta para soportar multiples fuentes de conocimiento mas alla del texto de PDFs, separando arquitectonicamente tres conceptos:

1. **Knowledge Sources**: tipos de contenido a parsear y extraer (documentos, codigo, web, tablas, conversaciones, datos estructurados, imagenes, presentaciones, emails, archives)
2. **Normalizers**: capa que transforma la salida de cualquier parser en un `CanonicalDocument` con encoding, unicode, metadata, idioma y estructura normalizados
3. **Acquisition Connectors**: mecanismos de adquisicion que descubren y sincronizan contenido desde plataformas externas (Local FS, Google Drive, GitHub, Notion, etc.)

Los conectores no son fuentes de conocimiento; simplemente alimentan las mismas fuentes que el sistema ya soporta. Esta separacion permite agregar un nuevo conector (ej: SharePoint) sin crear nuevos parsers.

## Sources

- RES-005: Unified Ingestion Pipeline (limitacion conocida: solo texto)
- `src/pdf_extractor.py`: extractor actual solo soporta texto de PDFs
- `knowledge_builder/frontend/llm_entity_extractor.py`: extractor LLM sobre texto plano
- `src/chunker.py`: chunking por caracteres o tokens sobre texto
- `src/embedder.py`: embeddings sobre texto
- ADR-0021: cache KIR por chunk
- ADR-0018: arquitectura del Knowledge Builder

---

## 1. Principio arquitectonico central

Cada Knowledge Source produce una **representacion canonica del documento** (contenido, estructura y metadata). A partir de esa representacion se generan las distintas vistas necesarias para el pipeline: texto para embeddings, metadata para KIR, imagenes para vision, tablas para analisis estructurado, etc.

El texto deja de ser el centro. El texto pasa a ser simplemente una de las representaciones posibles del `CanonicalDocument`.

## 2. Arquitectura propuesta

```
                    Acquisition Connectors
                    ├── Local File System
                    ├── Google Drive
                    ├── GitHub
                    ├── Notion
                    ├── Confluence
                    ├── SharePoint
                    ├── Dropbox
                    ├── OneDrive
                    └── S3
                         |
                         v
                    [Discovery & Sync → staging/]
                         |
                         v
                    Knowledge Sources (parsers)
                    ├── Documents       (PDF, DOCX, TXT, MD)
                    ├── Code            (.py, .js, .cpp, README, ADRs)
                    ├── Web             (HTML, URLs)
                    ├── Tables          (CSV, XLSX)
                    ├── Conversations   (ChatGPT, Claude, Slack, Discord, Teams, WhatsApp)
                    ├── Structured      (JSON, XML, YAML)
                    ├── Images          (PNG, JPG, JPEG, TIFF)
                    ├── Presentations   (PPTX, KEY)
                    ├── Emails          (EML, MBOX, PST)
                    └── Archives        (ZIP, RAR, 7Z, TAR — contenedor, no conocimiento)
                         |
                         v
                    [Normalizers]
                    ├── Encoding        (UTF-8, deteccion automatica)
                    ├── Unicode         (NFC, normalizacion de caracteres)
                    ├── Markdown        (frontmatter, headings, estructura)
                    ├── Tables          (preservar estructura tabular)
                    ├── Images          (metadata EXIF, dimensiones)
                    ├── Metadata        (timestamps, autor, idioma)
                    └── Language        (deteccion de idioma)
                         |
                         v
                    [CanonicalDocument]
                         |
                    ┌────┴────────┐
                    v             v
              [Vector DB]    [Knowledge Builder]
              (embeddings)    (KIR cache → Warm Artifacts)
              (texto vista)   (metadata + texto vista)
              (imagen vista)  (tabla vista)
```

### 2.1 Capas

| Capa | Responsabilidad | No hace |
|---|---|---|
| Connector | Descubrir, descargar, sincronizar | Parsear contenido |
| Parser | Extraer contenido crudo de un formato | Normalizar, decidir encoding |
| Normalizer | Normalizar encoding, unicode, metadata, idioma, estructura | Extraer contenido de un formato |
| CanonicalDocument | Contrato de salida unificado | Procesar, embedir, extraer KIR |

### 2.2 Por que Normalizer es una capa separada

Un parser solamente extrae. El normalizer decide:

- encoding (UTF-8, deteccion automatica)
- unicode (NFC, normalizacion de caracteres)
- tablas (preservar estructura vs aplanar)
- markdown (frontmatter, headings, estructura)
- imagenes (metadata EXIF, dimensiones)
- metadata (timestamps, autor, idioma)
- idioma (deteccion automatica)

Esto desacopla completamente la extraccion (parser) de la normalizacion (normalizer). Un parser de DOCX y un parser de HTML pueden compartir el mismo normalizador de unicode y metadata.

## 3. CanonicalDocument (contrato explicito)

Todos los parsers producen exactamente el mismo output: un `CanonicalDocument`.

```python
@dataclass
class CanonicalDocument:
    # Identidad
    id: str                          # UUID o hash determinista
    source: str                      # "local" | "gdrive" | "github" | ...
    uri: str                         # path o URL original

    # Metadata
    title: str | None
    author: str | None
    created_at: datetime | None
    updated_at: datetime | None

    # Contenido
    content: str                     # vista de texto (serializacion CIR)
    metadata: dict                   # metadata arbitraria del parser
    attachments: list[CanonicalDocument]  # attachments recursivos
    sections: list[DocumentSection]  # estructura jerarquica
    language: str                    # codigo ISO 639-1 ("es", "en", ...)

    # Fingerprinting
    binary_hash: str                 # SHA-256 del archivo binario original
    content_hash: str                # SHA-256 del contenido normalizado

    # Versioning
    version: int                     # version del documento (incremental)
    previous_version_id: str | None  # id de la version anterior
```

```python
@dataclass
class DocumentSection:
    heading: str | None
    level: int                       # profundidad (1 = top-level)
    content: str                     # texto de la seccion
    subsections: list[DocumentSection]
    tables: list[Table]
    images: list[Image]
    page_range: tuple[int, int] | None  # para PDFs
```

```python
@dataclass
class Table:
    headers: list[str]
    rows: list[list[str]]
    caption: str | None

@dataclass
class Image:
    id: str
    path: str                        # path al archivo de imagen
    format: str                      # "png" | "jpg" | ...
    width: int
    height: int
    ocr_text: str | None             # texto extraido via OCR
    vision_description: str | None   # descripcion via Vision LLM
    detected_objects: list[str]      # objetos detectados
    layout: str | None               # "diagram" | "screenshot" | "photo" | "chart"
    caption: str | None
```

### 3.1 Vistas del CanonicalDocument

El `CanonicalDocument` es la representacion canonica. A partir de el se generan vistas:

| Vista | Consumidor | Generacion |
|---|---|---|
| Texto plano | Vector DB (embeddings) | `content` field |
| Texto estructurado | Knowledge Builder (KIR) | `content` + `sections` + `metadata` |
| Imagenes | Vision LLM | `images[]` |
| Tablas | Analisis estructurado | `sections[].tables[]` |
| Metadata | DocCards, roles, centrality | `metadata` + `title` + `author` |

## 4. Canonical Intermediate Representation (CIR)

El `CanonicalDocument` contiene una representacion intermedia del documento que es mas rica que texto plano:

```
Document
├── Sections
│   ├── Paragraphs
│   ├── Tables
│   ├── Images
│   └── Subsections
│       └── ...
├── Metadata
│   ├── title, author, dates
│   ├── language
│   └── source-specific fields
├── Attachments
│   └── (CanonicalDocuments recursivos)
└── Content fingerprint (binary + content hash)
```

La CIR permite:
- Serializar a texto para embeddings (vista de texto)
- Preservar estructura para KIR extraction (vista estructurada)
- Extraer imagenes para vision (vista visual)
- Preservar tablas para analisis (vista tabular)

Recien despues de construir la CIR, el pipeline puede serializarla a las distintas vistas necesarias. No asume que todo es texto.

## 5. Knowledge Sources

### 5.1 Documentos (⭐⭐⭐⭐⭐)

**Formatos**: PDF, DOCX, TXT, Markdown

**Estado actual**: PDF y TXT soportados via `PDFExtractor` + `data/extracted_texts/`.

**Gaps**:
- DOCX: requiere `python-docx` o `mammoth` para extraccion de texto
- Markdown: ya es texto plano, pero necesita parsing de frontmatter y estructura de headings
- PDF: no extrae imagenes ni tablas (ver 5.7)

**Parser propuesto**:
```
DocumentParser
├── PDFParser        (existente + extension para tablas e imagenes)
├── DOCXParser       (nuevo)
├── TXTParser        (existente, trivial)
└── MarkdownParser   (nuevo, frontmatter + headings → sections)
```

### 5.2 Presentaciones (⭐⭐⭐⭐⭐)

**Formatos**: PPTX, KEY

**Separado de Documentos** porque una presentacion no es prosa. Tiene:
- Slides como unidades semanticas (no paginas)
- Notas del orador (speaker notes)
- Imagenes y diagramas embebidos
- Transiciones y layout visual

**Parser propuesto**:
```
PresentationParser
├── PPTXParser       (python-pptx: slides + notes + imagenes)
└── KEYParser        (iWork: extraer JSON interno)
```

**Estrategia**: cada slide genera un `DocumentSection` con:
- `content`: texto de la slide + notas del orador
- `images`: imagenes embebidas (procesadas via 5.7)
- `level`: 1 (slides son top-level)

### 5.3 Codigo fuente (⭐⭐⭐⭐⭐)

**Formatos**: Repos Git, .py, .js, .cpp, README, ADRs

**Consideraciones**:
- El codigo no se chunking igual que prosa: respetar funciones/clases como unidades semanticas
- README y ADRs son prosa con estructura (markdown)
- Imports, docstrings y type hints son metadata valiosa para extraccion de entidades
- Los repos Git tienen estructura de directorios que aporta contexto (ej: `src/auth/` implica dominio de autenticacion)

**Parser propuesto**:
```
CodeParser
├── PythonParser     (AST-based chunking por funcion/clase)
├── JSParser         (AST-based)
├── CPPParser        (regex/AST-based)
├── GenericCodeParser (fallback: chunking por lineas con heuristica)
└── MarkdownParser   (compartido con 5.1 para README/ADR)
```

**KIR extraction**: el LLM puede extraer entidades como modulos, clases, funciones, dependencias, patrones de diseño. Relations como "depends_on", "implements", "extends".

### 5.4 Paginas web (⭐⭐⭐⭐⭐)

**Formatos**: HTML, URLs

**Separacion en sub-componentes**:

```
Crawler          → descubre URLs (seed, follow links, robots.txt)
  ↓
Fetcher          → descarga HTML (requests, cache, rate limit, retries)
  ↓
HTML Parser      → extrae texto, estructura, metadata (BeautifulSoup / trafilatura)
  ↓
Boilerplate Removal → elimina nav, footer, ads, sidebars
  ↓
Normalizer       → encoding, unicode, metadata, idioma
  ↓
CanonicalDocument
```

El crawling es un problema independiente: seeds, depth limit, robots.txt, rate limiting, deduplicacion de URLs. Mezclarlo con parsing acopla dos concerns distintos.

**Componentes propuestos**:
```
WebPipeline
├── Crawler           (seed URLs, depth, robots.txt, rate limit)
├── Fetcher           (requests + cache de HTML descargado + retries)
├── HTMLParser         (BeautifulSoup / trafilatura)
├── BoilerplateRemover (trafilatura / readability)
└── SPAFetcher         (Playwright, opcional para JS-rendered sites)
```

### 5.5 Datos tabulares (⭐⭐⭐⭐)

**Formatos**: CSV, XLSX

**Consideraciones**:
- Cada fila es un registro; las columnas son atributos
- El LLM puede extraer entidades de las filas (ej: "producto X, precio Y")
- Headers definen el schema semantico
- Tablas grandes: muestrear o agregar por grupo

**Parser propuesto**:
```
TableParser
├── CSVParser        (pandas / csv stdlib)
└── XLSXParser       (openpyxl / pandas)
```

**Estrategia de extraccion**: preservar la tabla como `Table` en la CIR. Serializar cada fila (o grupo de filas) en texto natural para el LLM. Ej: "Fila 1: El producto 'Firewall X' tiene precio $500 y categoria 'Seguridad'."

### 5.6 Conversaciones (⭐⭐⭐⭐)

**Formatos**: ChatGPT Export, Claude Export, Gemini Export, Slack, Discord, Teams, WhatsApp

**Arquitectura**: un solo `ConversationParser` con adapters por plataforma. Todos representan la misma estructura:

```
Conversation
  ↓
Thread
  ↓
Turn
  ↓
Message (speaker, timestamp, content)
```

La diferencia entre plataformas es el **importador** (adapter), no el parser.

```
ConversationParser
  ↓
ConversationModel (Conversation → Thread → Turn → Message)
  ↓
Adapters
  ├── ChatGPTAdapter    (JSON de export oficial)
  ├── ClaudeAdapter     (JSON/HTML de export)
  ├── GeminiAdapter     (JSON de export)
  ├── SlackAdapter      (ZIP de export oficial)
  ├── DiscordAdapter    (CSV/JSON de export)
  ├── TeamsAdapter      (HTML/JSON)
  └── WhatsAppAdapter   (chat export .txt)
```

**Estrategia**: el adapter convierte el formato de plataforma a `ConversationModel`. El parser recorre el modelo y agrupa mensajes por thread/topic en bloques semanticos para enviar al LLM.

### 5.7 Imagenes (⭐⭐⭐⭐)

**Formatos**: PNG, JPG, JPEG, TIFF

**Arquitectura**: el ImageParser produce **artifacts** independientes, no una combinacion inmediata. Esto permite agregar nuevos processors sin romper nada.

```
ImageParser
  ↓
Artifacts
  ├── OCR Text           (texto embebido: labels, captions)
  ├── Vision Description (descripcion narrativa del contenido)
  ├── Detected Objects   (lista de objetos detectados)
  └── Layout             (diagram | screenshot | photo | chart | formula)
  ↓
Normalizer
  ↓
CanonicalDocument (con Image en sections)
```

**Extension futura sin romper nada**:
- Deteccion de tablas (TableDetector)
- Deteccion de formulas (FormulaDetector)
- Deteccion de graficos (ChartDetector)

Cada nuevo detector es un artifact adicional. El Normalizer lo incorpora al `Image` del `CanonicalDocument`.

**Procesadores propuestos**:
```
ImageParser
├── OCRProcessor        (Tesseract / PaddleOCR → ocr_text)
├── VisionLLMProcessor  (LLaVA via Ollama → vision_description)
├── ObjectDetector      (YOLO / OWL-ViT → detected_objects)
├── LayoutClassifier    (clasificar: diagram | screenshot | photo | chart)
└── PDFImageExtractor   (PyMuPDF: extraer imagenes embebidas de PDFs)
```

### 5.8 Datos estructurados (⭐⭐⭐⭐)

**Formatos**: JSON, XML, YAML

**Consideraciones**:
- Ya son estructurados, pero la semantica no es explicita (que significa cada campo)
- El LLM puede inferir entidades y relaciones del schema
- YAML con comentarios puede tener contexto adicional
- JSON anidado: preservar jerarquia como sections

**Parser propuesto**:
```
StructuredDataParser
├── JSONParser
├── XMLParser
└── YAMLParser
```

**Estrategia**: preservar la estructura jerarquica como `DocumentSection`s en la CIR. Serializar a texto legible como vista de texto.

### 5.9 Emails (⭐⭐⭐⭐)

**Formatos**: EML, MBOX, PST

**Consideraciones**:
- Estructura: headers (from, to, subject, date) + body (text/html) + attachments
- Attachments pueden ser cualquier otro Knowledge Source (PDF, imagen, etc.) → recursion de `CanonicalDocument.attachments`
- Threads de email: agrupar por subject/References header
- El LLM puede extraer entidades mencionadas en el cuerpo

**Parser propuesto**:
```
EmailParser
├── EMLParser       (email stdlib)
├── MBOXParser      (mailbox stdlib)
└── PSTParser       (libpst / aspose)
```

### 5.10 Archives (⭐⭐⭐⭐)

**Formatos**: ZIP, RAR, 7Z, TAR

**No son una fuente de conocimiento.** Son **contenedores**: mucha documentacion viene comprimida.

**Rol**: descomprimir y alimentar los archivos internos al parser correspondiente. Cada archivo dentro del archive se procesa como un `CanonicalDocument` independiente.

```
ArchiveExtractor
├── ZIPExtractor    (stdlib zipfile)
├── RARExtractor    (rarfile)
├── SevenZExtractor (py7zr)
└── TarExtractor    (stdlib tarfile)
  ↓
[Para cada archivo interno]
  ↓
[Knowledge Source Parser correspondiente por extension/mime type]
```

## 6. Versioning

Un mismo documento puede cambiar a lo largo del tiempo. El sistema debe trackear versiones.

### 6.1 Document Version

Cada `CanonicalDocument` tiene:
- `version`: entero incremental
- `previous_version_id`: id de la version anterior (cadena)

### 6.2 Impacto en cache

Cuando un documento cambia:
- **Binary hash** cambia → detectar nueva version
- **Content hash** puede o no cambiar (metadata cambio pero contenido no)
- Si content hash no cambia → cache hit (no re-procesar)
- Si content hash cambia → cache miss (re-procesar)

### 6.3 Versioning por conector

Cada conector puede proveer version info nativa:
- Google Drive: `modifiedTime` + `md5Checksum`
- GitHub: commit SHA + blob hash
- Notion: `last_edited_time`
- Confluence: `version.number`

El conector mapea su version nativa al `version` + `previous_version_id` del `CanonicalDocument`.

## 7. Content Fingerprinting

No usar un solo hash. Usar dos:

| Hash | Que hashea | Invalidation |
|---|---|---|
| **Binary Hash** | SHA-256 del archivo binario original (bytes crudos) | archivo binario cambia (incluye metadata del archivo) |
| **Content Hash** | SHA-256 del contenido normalizado (texto + estructura CIR) | contenido semantico cambia |

### 7.1 Por que dos hashes

`doc.pdf` puede:
- **Cambiar metadata sin cambiar contenido**: binary hash cambia, content hash no → cache hit (no re-procesar)
- **Cambiar contenido sin cambiar metadata**: binary hash cambia, content hash cambia → cache miss (re-procesar)
- **Re-exportar con diferente tool**: binary hash cambia, content hash puede no cambiar → cache hit

### 7.2 Uso en el pipeline

- **Vector DB**: usa content hash para decidir re-embedding
- **KIR cache**: usa content hash por chunk para decidir re-extraccion
- **Connector sync**: usa binary hash para decidir re-download
- **Versioning**: usa binary hash para detectar cambios + content hash para decidir si procesar

## 8. Acquisition Connectors

Los conectores **no parsean contenido**. Solo descubren, descargan y sincronizan archivos hacia un staging area local. Luego los parsers de Knowledge Sources los procesan.

### 8.1 Arquitectura de conectores

```
ConnectorInterface
├── discover()  → lista de archivos disponibles (con binary_hash, version info)
├── fetch(id)   → descarga archivo al staging area
├── sync()      → discover + fetch incremental (solo cambios desde ultimo sync)
└── metadata(id) → info del archivo (tipo, tamano, fecha modificacion, version nativa)
```

### 8.2 Conectores propuestos

| Conector | Auth | Sync mechanism | Version info | Notas |
|---|---|---|---|---|
| Local File System | N/A | Watch directory | mtime + inode | Ya implementado via `ingest_incremental.py` |
| Google Drive | OAuth2 | Drive API + change token | modifiedTime + md5Checksum | Filtros por folder/mime type |
| GitHub | PAT / App | Git API + webhook | commit SHA + blob hash | Clonar repo o descargar archivos |
| Notion | API token | Notion API + last_edited | last_edited_time | Paginas y bases de datos |
| Confluence | PAT / OAuth | REST API + version | version.number | Pages y attachments |
| SharePoint | OAuth2 | Graph API + delta query | delta token | Document libraries |
| Dropbox | OAuth2 | Files API + cursor | rev (revision) | Recursive folder sync |
| OneDrive | OAuth2 | Graph API + delta query | delta token | Similar a SharePoint |
| S3 | IAM keys | S3 API + ListObjectsV2 | ETag + versioning | Prefix-based, versioning-aware |

### 8.3 Staging area

```
staging/
├── gdrive/
│   ├── <binary_hash>.pdf
│   └── <binary_hash>.docx
├── github/
│   ├── <repo>/<commit>/<path>/__init__.py
│   └── <repo>/<commit>/<path>/README.md
├── notion/
│   └── <page_id>.md
└── local/
    └── (symlinks o copias de data/extracted_texts/)
```

El staging area es el punto de entrada unificado. Los parsers no saben (ni necesitan saber) de donde vino el archivo.

### 8.4 Sync incremental

Cada conector mantiene su propio estado de sincronizacion:

```json
{
  "connector": "gdrive",
  "last_sync": "2026-07-30T...",
  "change_token": "abc123...",
  "synced_files": [
    {
      "id": "file_id_1",
      "binary_hash": "sha256...",
      "content_hash": "sha256...",
      "version": 3,
      "path": "staging/gdrive/<binary_hash>.pdf",
      "synced_at": "..."
    }
  ]
}
```

Re-sync solo descarga archivos cuyo binary hash cambio (segun change token / delta query / etag).

## 9. Integracion con RES-005

El pipeline unificado de RES-005 se extiende:

```
[Acquisition Connectors]
    ↓
[staging/]
    ↓
[Knowledge Source Parsers] → [Normalizers] → [CanonicalDocument]
    ↓                                              |
    ↓                                         ┌────┴────┐
    ↓                                         v         v
    ↓                                   [Vector DB]  [KB KIR cache]
    ↓                                   (texto vista)  (metadata + texto vista)
    ↓                                   (imagen vista) (tabla vista)
    ↓
[Compile + Validate + Publish]
```

El script `ingest_unified.py` de RES-005 se convierte en el orquestador de todo el flujo:

1. **Sync**: conectores descubren y descargan archivos nuevos/modificados al staging area
2. **Parse**: Knowledge Source parsers extraen contenido crudo de cada archivo
3. **Normalize**: normalizers transforman la salida del parser en `CanonicalDocument`
4. **Vector DB**: generar vista de texto → chunking + embedding + ChromaDB
5. **KB Extract**: generar vista estructurada → LLM extraction + KIR cache
6. **Compile + Validate + Publish**: al final, una sola vez

## 10. Cache y idempotencia

### 10.1 Cache por fuente

Cada Knowledge Source tiene su propio cache de extraccion, keyado por **content hash** (no binary hash):

| Source | Cache key | Invalidation |
|---|---|---|
| Documentos | content_hash del texto extraido | contenido semantico cambia |
| Codigo | content_hash del archivo | contenido semantico cambia |
| Web | content_hash del HTML parseado | contenido semantico cambia |
| Tablas | content_hash del archivo | contenido semantico cambia |
| Conversaciones | content_hash del archivo export | contenido semantico cambia |
| Estructurados | content_hash del archivo | contenido semantico cambia |
| Imagenes | content_hash de la imagen + version del modelo OCR/vision | imagen cambia o modelo mejora |
| Emails | content_hash del archivo | contenido semantico cambia |
| Presentaciones | content_hash del archivo | contenido semantico cambia |

### 10.2 Cache por conector

Cada conector mantiene su estado de sync independientemente, keyado por **binary hash**. Re-ejecutar un conector no re-descarga archivos cuyo binary hash no cambio.

### 10.3 Doble hash en accion

```
Archivo binario → binary_hash → connector decide: ¿descargar de nuevo?
                        ↓
Parser + Normalizer → content_hash → pipeline decide: ¿re-procesar?
                        ↓
                    ¿content_hash en cache?
                    ├── SI → cache hit (skip)
                    └── NO → cache miss (procesar)
```

## 11. Priorizacion de implementacion

| Fase | Componente | Esfuerzo | Impacto |
|---|---|---|---|
| 1 | CanonicalDocument + DocumentSection + Table + Image | bajo | alto (fundacion) |
| 1 | Normalizer base (encoding, unicode, metadata) | bajo | alto |
| 1 | MarkdownParser | bajo | alto (ADRs, READMEs) |
| 1 | DOCXParser | bajo | medio |
| 1 | CSV/XLSXParser | medio | medio |
| 2 | ImageParser + OCRProcessor (Tesseract) | medio | alto (diagramas) |
| 2 | ImageParser + VisionLLMProcessor (LLaVA) | medio-alto | alto |
| 2 | PDF image extraction (PyMuPDF) | medio | alto |
| 2 | LayoutClassifier | medio | medio |
| 3 | WebPipeline (Crawler + Fetcher + HTMLParser + Boilerplate) | medio-alto | alto |
| 3 | CodeParser (Python AST) | medio | medio |
| 3 | JSON/XML/YAMLParser | bajo | medio |
| 3 | PPTXParser | medio | medio |
| 4 | ArchiveExtractor (ZIP/TAR) | bajo | medio |
| 4 | GitHub connector | medio | alto |
| 4 | Google Drive connector | medio | medio |
| 5 | ConversationParser + adapters | medio | medio |
| 5 | EmailParser | medio | bajo |
| 5 | Notion / Confluence / SharePoint connectors | alto | medio |
| 5 | ObjectDetector (YOLO/OWL-ViT) | alto | medio |

## 12. Riesgos y mitigaciones

| Riesgo | Mitigacion |
|---|---|
| Vision LLM alucina entidades no presentes en la imagen | Cross-check OCR vs vision description; descartar claims sin evidencia textual |
| Conectores requieren credenciales y permisos | Vault de credenciales; secretos fuera del codigo |
| Formatos de export cambian entre plataformas | Adapters defensivos con fallback; tests por version de formato |
| Codigo fuente tiene estructura muy diferente a prosa | Parsers AST-aware; chunking por funcion/clase, no por caracteres |
| Tablas muy grandes exceden contexto del LLM | Muestreo estratificado; agregacion por grupo; paginacion |
| Emails con attachments requieren recursion | Procesar attachments como CanonicalDocument independiente (attachments[]) |
| Archives con paths maliciosos (zip slip) | Validar paths al descomprimir; sandbox |
| CIR demasiado compleja para parsers simples | CIR es incremental: TXTParser solo llena content + metadata; PDFParser llena sections + images |
| Binary hash cambia pero content hash no (falso positivo de sync) | Doble hash: connector re-descarga pero pipeline no re-procesa |

## 13. Open questions

1. **Vision LLM local vs remoto**: ¿LLaVA via Ollama (local, lento) o API externa (rapido, costo)?
2. **Chunking de codigo**: ¿AST-based por funcion/clase es suficiente, o hay casos donde chunking por lineas es mejor?
3. **Deduplicacion cross-source**: si el mismo documento esta en Google Drive y en Local FS, ¿como evitar doble ingesta? ¿content hash global?
4. **Versionamiento de conectores**: ¿como manejar cambios de API de Google Drive / GitHub / Notion?
5. **Rate limiting**: ¿como manejar limits de API de conectores (ej: GitHub 5000 req/h)?
6. **Attachments de email**: ¿procesar recursivamente como CanonicalDocument independiente o embebido en el email?
7. **SPA web fetching**: ¿vale la pena Playwright, o basta con fetch + HTML parse para la mayoria de sitios?
8. **CIR vs texto**: ¿hasta que punto la metadata estructural (headings de markdown, AST de codigo, schema de JSON) debe preservarse en la CIR vs aplanarse a texto?
9. **CIR evolutiva**: ¿como agregar nuevos fields a CanonicalDocument sin romper parsers existentes? ¿versionado del schema?
10. **Layout classification**: ¿modelo ML dedicado o heuristica basada en dimensiones/colores?
11. **Conversation threads**: ¿como agrupar mensajes en threads semanticos cuando la plataforma no provee threading nativo?
12. **Archive recursion depth**: ¿limitar profundidad de archives dentro de archives (zip dentro de zip)?

## 14. Compatibility con sistema actual

- `PDFExtractor` + `data/extracted_texts/` sigue funcionando como hoy
- `ingest_incremental.py` sigue funcionando para Local FS
- `build_knowledge.py` subcomandos no cambian (operan sobre KIR cache, agnostico de la fuente)
- Los nuevos parsers, normalizers y conectores son modulos adicionales que el orquestador unificado (RES-005) puede invocar
- Warm Artifacts y el Consumer no cambian: operan sobre KnowledgeModel, no sobre la fuente
- Migracion incremental: el primer paso es definir `CanonicalDocument` y envolver el `PDFExtractor` actual como un parser que produce `CanonicalDocument`
