"""LLMEntityExtractor — extractor LLM que produce KIR desde documentos (RES-002 §3.3, §8.2).

El LLM es **un extractor mas**, no el eje de la arquitectura. Produce exactamente
el mismo formato KIR que los extractores deterministas.

Modelo por defecto: Granite 4.1 3B via Ollama (RES-002 §8.2).

Para cada documento:
    1. Lee el texto de data/extracted_texts/{name}.txt
    2. Envia un chunk al LLM con un prompt estructurado
    3. Parsea la respuesta JSON
    4. Genera EntityClaim, AliasClaim, RelationClaim, DocumentClaim

El extractor es configurable:
    - max_docs: limite de documentos a procesar (default: 50)
    - chunk_size: tamano de chunk en caracteres (default: 4000)
    - timeout: timeout por llamada LLM (default: 120s)
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from ..kir import (
    AliasClaim,
    DocumentClaim,
    EntityClaim,
    EvidenceItem,
    KIR,
    RelationClaim,
    normalize_text,
    slugify,
)


_EXTRACTOR_ID_DEFAULT = "llm:granite-4.1-3b"

_EXTRACTION_PROMPT = """You are a knowledge extractor. Analyze the following document text and extract entities, aliases, and relations.

Return ONLY a JSON object with this exact structure:
{
  "entities": [
    {"name": "Entity Name", "types": ["concept", "technology"], "confidence": 0.9, "quote": "short quote from text as evidence"}
  ],
  "aliases": [
    {"alias": "Short Name", "canonical": "Full Canonical Name", "confidence": 0.8, "quote": "short quote as evidence"}
  ],
  "relations": [
    {"subject": "Entity A", "predicate": "natural language predicate", "object": "Entity B", "confidence": 0.7, "quote": "short quote as evidence"}
  ],
  "doc_role": "entity_profile",
  "doc_summary": "Brief one-sentence summary of the document"
}

Rules:
- Extract entities of any type — do not restrict to any domain
- Entity types are free-form: use whatever best describes the entity (e.g. concept, technology, standard, organization, person, method, tool, law, etc.)
- Predicates: describe the relationship in natural language (e.g. "governs", "implements", "extends", "depends on", "references", "contains", "uses", "creates", "is part of", "certifies", "is equivalent to")
- Only extract entities explicitly mentioned in the text
- Include a short quote (max 200 chars) from the text as evidence for each claim
- Confidence: 0.0-1.0 based on how clearly the text supports the claim
- doc_role must be one of: list, entity_profile, guide, reference, analysis, other
  - list: a catalog, index, or enumeration of items
  - entity_profile: detailed profile of a specific entity
  - guide: instructional or procedural document
  - reference: manual, specification, or reference material
  - analysis: report, assessment, or analysis
  - other: does not fit any category above

Document text:
---
{text}
---

Return ONLY the JSON object, no other text."""


class LLMEntityExtractor:
    """Extrae entidades, aliases y relaciones desde documentos usando un LLM."""

    def __init__(
        self,
        model: str = "ibm/granite4.1:3b-q6_K",
        base_url: str = "http://localhost:11434",
        docs_dir: Optional[Path | str] = None,
        doc_roles: Optional[Mapping[str, Any]] = None,
        max_docs: int = 50,
        chunk_size: int = 4000,
        timeout: int = 300,
        verbose: bool = False,
        cache_dir: Optional[Path | str] = None,
        use_cache: bool = True,
        max_workers: int = 4,
        num_predict: int = 1200,
        num_ctx: int = 4096,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.docs_dir = Path(docs_dir) if docs_dir else Path("data/extracted_texts")
        self.doc_roles = dict(doc_roles or {})
        self.max_docs = max_docs
        self.chunk_size = chunk_size
        self.timeout = timeout
        self.verbose = verbose
        self.cache_dir = Path(cache_dir) if cache_dir else Path("cache")
        self.use_cache = use_cache
        self.max_workers = max_workers
        self.num_predict = num_predict
        self.num_ctx = num_ctx
        self.extractor_id = f"llm:{model.split(':')[-1].replace('.', '-')}" if model else _EXTRACTOR_ID_DEFAULT

    def extract(self) -> KIR:
        kir = KIR(metadata={"extractor": self.extractor_id})

        docs = self._select_docs()
        if not docs:
            if self.verbose:
                print(f"  [LLM] No documents found in {self.docs_dir}")
            return kir

        if self.verbose:
            print(f"  [LLM] Processing {len(docs)} documents with {self.model} (workers={self.max_workers})")

        for i, (doc_name, doc_path) in enumerate(docs):
            if self.verbose:
                print(f"  [LLM]   [{i+1}/{len(docs)}] {doc_name}")

            try:
                text = doc_path.read_text(encoding="utf-8", errors="replace")
                if not text.strip():
                    if self.verbose:
                        print(f"  [LLM]     skip: empty text")
                    continue

                chunks = self._chunk_text(text, self.chunk_size)
                if self.verbose:
                    print(f"  [LLM]     {len(text)} chars -> {len(chunks)} chunks")

                if self.max_workers > 1 and len(chunks) > 1:
                    sub_kirs = self._extract_chunks_parallel(doc_name, chunks)
                    for sub_kir in sub_kirs:
                        kir.merge(sub_kir)
                else:
                    for chunk_idx, chunk in enumerate(chunks):
                        if self.verbose:
                            print(f"  [LLM]     chunk {chunk_idx+1}/{len(chunks)} ({len(chunk)} chars)...", end="", flush=True)
                        sub_kir = self._extract_from_chunk_cached(doc_name, chunk, chunk_idx)
                        if self.verbose:
                            n = len(sub_kir.entity_claims) + len(sub_kir.alias_claims) + len(sub_kir.relation_claims)
                            print(f" {n} claims", flush=True)
                        kir.merge(sub_kir)

            except Exception as e:
                if self.verbose:
                    print(f"  [LLM]   ERROR on {doc_name}: {e}", flush=True)
                continue

        if self.verbose:
            print(
                f"  [LLM] Done: {len(kir.entity_claims)} entities, "
                f"{len(kir.alias_claims)} aliases, "
                f"{len(kir.relation_claims)} relations, "
                f"{len(kir.document_claims)} docs"
            )

        return kir

    def _extract_chunks_parallel(self, doc_name: str, chunks: List[str]) -> List[KIR]:
        """Process chunks in parallel and return KIR list in order."""
        results: Dict[int, KIR] = {}
        lock = threading.Lock()

        def _process(idx: int, chunk: str) -> tuple[int, KIR]:
            sub_kir = self._extract_from_chunk_cached(doc_name, chunk, idx)
            if self.verbose:
                n = len(sub_kir.entity_claims) + len(sub_kir.alias_claims) + len(sub_kir.relation_claims)
                with lock:
                    print(f"  [LLM]     chunk {idx+1}/{len(chunks)} -> {n} claims", flush=True)
            return idx, sub_kir

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(_process, idx, chunk): idx
                for idx, chunk in enumerate(chunks)
            }
            for future in as_completed(futures):
                idx, sub_kir = future.result()
                results[idx] = sub_kir

        return [results[i] for i in range(len(chunks)) if i in results]

    def _load_exclusions(self) -> set[str]:
        """Load corpus exclusion manifest if present."""
        exclusions_path = self.docs_dir.parent / "corpus_exclusions.json"
        if not exclusions_path.exists():
            return set()
        try:
            data = json.loads(exclusions_path.read_text(encoding="utf-8"))
            return {item["file"] for item in data.get("excluded", [])}
        except Exception:
            return set()

    def _select_docs(self) -> List[tuple[str, Path]]:
        """Selects documents to process, prioritized by centrality."""
        if not self.docs_dir.exists():
            return []

        all_files = sorted(self.docs_dir.glob("*.txt"))
        if not all_files:
            return []

        excluded = self._load_exclusions()
        if excluded:
            all_files = [f for f in all_files if f.name not in excluded]
            if self.verbose:
                print(f"  [LLM] Corpus exclusions: {len(excluded)} files filtered")

        docs_info = self.doc_roles.get("docs", {}) if self.doc_roles else {}

        def _centrality(path: Path) -> float:
            from src.utils.canonical_id import canonical_doc_id
            cid = canonical_doc_id(path.name)
            info = docs_info.get(cid, {})
            return float(info.get("centrality", 0.0))

        prioritized = sorted(all_files, key=_centrality, reverse=True)
        selected = prioritized[: self.max_docs]
        return [(p.name.replace(".txt", ".pdf"), p) for p in selected]

    def _chunk_text(self, text: str, chunk_size: int) -> List[str]:
        """Splits text into chunks at paragraph boundaries."""
        if len(text) <= chunk_size:
            return [text]

        chunks: List[str] = []
        paragraphs = text.split("\n\n")
        current = ""
        for para in paragraphs:
            if len(current) + len(para) > chunk_size and current:
                chunks.append(current.strip())
                current = para
            else:
                current = current + "\n\n" + para if current else para
        if current.strip():
            chunks.append(current.strip())
        return chunks

    def _chunk_hash(self, chunk: str) -> str:
        """Compute SHA-256 hash of a chunk for cache keying."""
        return hashlib.sha256(chunk.encode("utf-8")).hexdigest()[:16]

    def _extract_from_chunk_cached(self, doc_name: str, chunk: str, chunk_idx: int) -> KIR:
        """Extract from chunk with cache support (ADR-0021.2)."""
        if not self.use_cache:
            return self._extract_from_chunk(doc_name, chunk, chunk_idx)

        doc_slug = slugify(doc_name)
        chunk_hash = self._chunk_hash(chunk)
        chunk_file = self.cache_dir / doc_slug / f"chunk_{chunk_idx}.kir.json"
        meta_file = self.cache_dir / doc_slug / "meta.json"

        existing_meta = {}
        if meta_file.exists():
            try:
                existing_meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                existing_meta = {}

        chunks_meta = existing_meta.get("chunks", {})
        chunk_meta = chunks_meta.get(str(chunk_idx), {})

        if chunk_file.exists() and chunk_meta.get("hash") == chunk_hash:
            if self.verbose:
                print(" (cached)", end="", flush=True)
            data = json.loads(chunk_file.read_text(encoding="utf-8"))
            return KIR.from_dict(data)

        if chunk_meta.get("fail_count", 0) >= 2 and chunk_meta.get("hash") == chunk_hash:
            if self.verbose:
                print(" (skip: permanently_failed)", end="", flush=True)
            kir = KIR()
            kir.metadata["extraction_error"] = "permanently_failed"
            return kir

        sub_kir = self._extract_from_chunk(doc_name, chunk, chunk_idx)

        if sub_kir.metadata.get("extraction_error"):
            if self.verbose:
                print(f" [SKIP CACHE: {sub_kir.metadata['extraction_error']}]", end="", flush=True)
            doc_cache_dir = self.cache_dir / doc_slug
            doc_cache_dir.mkdir(parents=True, exist_ok=True)
            fail_count = chunk_meta.get("fail_count", 0) + 1
            existing_meta.setdefault("doc_name", doc_name)
            existing_meta.setdefault("chunks", {})
            existing_meta["chunks"][str(chunk_idx)] = {
                "hash": chunk_hash,
                "fail_count": fail_count,
                "last_error": sub_kir.metadata["extraction_error"],
                "updated_at": time.time(),
            }
            meta_file.write_text(
                json.dumps(existing_meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return sub_kir

        doc_cache_dir = self.cache_dir / doc_slug
        doc_cache_dir.mkdir(parents=True, exist_ok=True)

        chunk_file.write_text(
            json.dumps(sub_kir.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        meta_file = self.cache_dir / doc_slug / "meta.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        else:
            meta = {}

        meta.setdefault("doc_name", doc_name)
        meta.setdefault("model", self.model)
        meta.setdefault("chunks", {})
        meta["chunks"][str(chunk_idx)] = {"hash": chunk_hash, "processed_at": time.time()}
        meta["processed_at"] = time.time()

        meta_file.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return sub_kir

    def _extract_from_chunk(self, doc_name: str, chunk: str, chunk_idx: int) -> KIR:
        """Calls the LLM and parses the response into KIR claims."""
        kir = KIR(metadata={"extractor": self.extractor_id})

        prompt = _EXTRACTION_PROMPT.replace("{text}", chunk[:4000])
        response = self._call_llm(prompt)
        if not response:
            kir.metadata["extraction_error"] = "llm_no_response"
            return kir

        data = self._parse_json_response(response)
        if not data:
            kir.metadata["extraction_error"] = "llm_unparseable"
            return kir

        doc_id = f"doc:{slugify(doc_name)}"

        for ent in data.get("entities", []):
            name = ent.get("name", "")
            if isinstance(name, list):
                name = name[0] if name else ""
            name = str(name).strip()
            if not name:
                continue
            canonical = normalize_text(name)
            types = ent.get("types", [])
            if isinstance(types, str):
                types = [types]
            elif not isinstance(types, list):
                types = []
            conf = float(ent.get("confidence", 0.7))
            quote = ent.get("quote", "")
            quote = str(quote)[:200] if quote else ""

            kir.entity_claims.append(EntityClaim(
                surface_form=name,
                canonical_name=canonical,
                entity_types=list(types) if types else ["concept"],
                extractor_id=self.extractor_id,
                confidence=conf,
                evidence=[EvidenceItem(
                    source_doc_id=doc_id,
                    quote=quote or f"Entity mentioned in {doc_name}",
                )],
                raw={"source_doc": doc_name, "chunk_idx": chunk_idx},
            ))

        for alias in data.get("aliases", []):
            alias_name = alias.get("alias", "")
            canonical = alias.get("canonical", "")
            if isinstance(alias_name, list):
                alias_name = alias_name[0] if alias_name else ""
            if isinstance(canonical, list):
                canonical = canonical[0] if canonical else ""
            alias_name = str(alias_name).strip()
            canonical = str(canonical).strip()
            if not alias_name or not canonical:
                continue
            conf = float(alias.get("confidence", 0.7))
            quote = alias.get("quote", "")
            quote = str(quote)[:200] if quote else ""

            kir.alias_claims.append(AliasClaim(
                alias=normalize_text(alias_name),
                canonical_name=normalize_text(canonical),
                extractor_id=self.extractor_id,
                confidence=conf,
                evidence=[EvidenceItem(
                    source_doc_id=doc_id,
                    quote=quote or f"Alias {alias_name} -> {canonical} in {doc_name}",
                )],
                raw={"source_doc": doc_name, "chunk_idx": chunk_idx},
            ))

        for rel in data.get("relations", []):
            subject = rel.get("subject", "")
            predicate = rel.get("predicate", "")
            obj = rel.get("object", "")
            if isinstance(subject, list):
                subject = subject[0] if subject else ""
            if isinstance(predicate, list):
                predicate = predicate[0] if predicate else ""
            if isinstance(obj, list):
                obj = obj[0] if obj else ""
            subject = str(subject).strip()
            predicate = str(predicate).strip()
            obj = str(obj).strip()
            if not subject or not predicate or not obj:
                continue
            conf = float(rel.get("confidence", 0.6))
            quote = rel.get("quote", "")
            quote = str(quote)[:200] if quote else ""

            kir.relation_claims.append(RelationClaim(
                subject_name=normalize_text(subject),
                predicate=normalize_text(predicate),
                object_name=normalize_text(obj),
                extractor_id=self.extractor_id,
                confidence=conf,
                evidence=[EvidenceItem(
                    source_doc_id=doc_id,
                    quote=quote or f"Relation in {doc_name}",
                )],
                raw={"source_doc": doc_name, "chunk_idx": chunk_idx},
            ))

        role = data.get("doc_role", "other")
        if isinstance(role, list):
            role = role[0] if role else "other"
        role = str(role).strip() or "other"
        summary = data.get("doc_summary", "")
        summary = str(summary)[:300] if summary else ""

        kir.document_claims.append(DocumentClaim(
            source_path=doc_name,
            name=doc_name,
            role=role,
            attributes=[],
            centrality=0.0,
            entity_mentions=[normalize_text(e.get("name", "")) for e in data.get("entities", []) if e.get("name")],
            summary=summary,
            extractor_id=self.extractor_id,
            confidence=0.75,
            evidence=[EvidenceItem(
                source_doc_id=doc_id,
                quote=summary or f"Document {doc_name} analyzed by LLM",
            )],
            raw={"doc_id": doc_id, "source": "llm_extraction", "chunk_idx": chunk_idx},
        ))

        return kir

    def _call_llm(self, prompt: str) -> str:
        """Calls Ollama generate API."""
        import requests

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "num_gpu": 99,
                "temperature": 0.1,
                "num_ctx": self.num_ctx,
                "top_p": 0.9,
                "num_thread": 8,
                "num_predict": self.num_predict,
            },
            "keep_alive": "30m",
        }

        try:
            r = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            r.raise_for_status()
            return (r.json().get("response") or "").strip()
        except Exception as e:
            if self.verbose:
                print(f"  [LLM]   Ollama error: {e}")
            return ""

    @staticmethod
    def _parse_json_response(text: str) -> Optional[Dict[str, Any]]:
        """Extracts JSON from LLM response, handling markdown code fences."""
        if not text:
            return None

        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start == -1 or brace_end == -1:
            return None

        json_str = text[brace_start : brace_end + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            try:
                json_str = json_str.rstrip(",}")
                return json.loads(json_str + "}")
            except json.JSONDecodeError:
                return None
