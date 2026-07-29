"""Knowledge Compiler — orquestador del pipeline (RES-002 §2.2).

Pipeline:

    Front-end (extractors) -> KIR
        -> NormalizePass -> CanonicalizePass -> DeduplicationPass
        -> Validation
        -> Knowledge Model
        -> Warm Codegen + Cold Codegen
        -> Publish (Artifact Registry)

Uso:

    compiler = KnowledgeCompiler(
        equivalences_text=EQUIVALENCES_EMBEDDED_TEXT,
        entity_aliases=ENTITY_ALIASES_DICT,
        doc_roles=doc_roles_dict,
    )
    result = compiler.compile()
    compiler.publish(result, registry)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .backend.cold_codegen import ColdCodegen
from .backend.warm_codegen import WarmCodegen
from .frontend import DocCardsExtractor, EntityAliasesExtractor, EquivalencesExtractor
from .kir import KIR
from .model.confidence import ConfidencePolicy, get_policy
from .model.knowledge_model import KnowledgeModel
from .passes import CanonicalizePass, DeduplicationPass, NormalizePass
from .publish import Publisher
from .validate.validator import KIRValidator, ValidationResult


@dataclass
class CompileResult:
    """Resultado de una compilacion completa."""
    build_id: str
    manifest: Dict[str, Any]
    artifacts: Dict[str, Any]
    cold_artifacts: Dict[str, Any]
    validation: ValidationResult
    model_stats: Dict[str, int]
    kir_claim_count: int
    extractor_ids: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.validation.is_valid


class KnowledgeCompiler:
    """Orquesta el pipeline completo: front-end -> KIR -> passes -> validation -> model -> back-end."""

    def __init__(
        self,
        equivalences_text: str = "",
        entity_aliases: Optional[Mapping[str, List[str]]] = None,
        doc_roles: Optional[Mapping[str, Any]] = None,
        doc_roles_path: Optional[Path | str] = None,
        builder_version: str = "1.0.0",
        confidence_policy: str = "weighted",
        confidence_policy_kwargs: Optional[Mapping[str, Any]] = None,
        build_id: str = "ka_v1.0.0",
    ):
        self.builder_version = builder_version
        self.build_id = build_id
        self.confidence_policy: ConfidencePolicy = get_policy(
            confidence_policy, **(dict(confidence_policy_kwargs) if confidence_policy_kwargs else {})
        )

        # Front-end extractors
        self.extractors: List[Any] = []
        if equivalences_text:
            self.extractors.append(EquivalencesExtractor(equivalences_text))
        if entity_aliases:
            self.extractors.append(EntityAliasesExtractor(entity_aliases))
        if doc_roles or doc_roles_path:
            self.extractors.append(DocCardsExtractor(doc_roles=doc_roles, path=doc_roles_path))

        # Warm codegen knows the predicate catalog
        self.warm_codegen = WarmCodegen(builder_version=builder_version)

        # Passes
        self.predicate_ids = self.warm_codegen.predicate_ids
        self.normalize_pass = NormalizePass()
        self.canonicalize_pass = CanonicalizePass(predicate_catalog=self.predicate_ids)
        self.dedup_pass = DeduplicationPass(confidence_policy=self.confidence_policy)

        # Validator
        self.validator = KIRValidator(predicate_catalog=self.predicate_ids)

        # Cold codegen
        self.cold_codegen = ColdCodegen()

    def compile(self) -> CompileResult:
        """Ejecuta el pipeline completo y retorna el resultado."""

        # 1. Front-end: extractors -> KIR
        kir = KIR()
        for extractor in self.extractors:
            sub_kir = extractor.extract()
            kir.merge(sub_kir)

        initial_claim_count = kir.claim_count()
        extractor_ids = kir.extractor_ids()

        # 2. Middle-end: passes
        kir = self.normalize_pass.run(kir)
        kir = self.canonicalize_pass.run(kir)
        kir = self.dedup_pass.run(kir)

        # 3. Validation
        validation = self.validator.validate(kir)
        if not validation.is_valid:
            raise ValueError(
                f"KIR validation failed with {len(validation.errors)} errors: "
                + "; ".join(validation.errors[:5])
            )

        # 4. Knowledge Model
        model = KnowledgeModel.from_kir(kir, builder_version=self.builder_version)
        model_stats = model.stats()

        # 5. Back-end: codegen
        warm_output = self.warm_codegen.generate(model, build_id=self.build_id)
        cold_artifacts = self.cold_codegen.generate(
            kir, validation, build_metadata=kir.metadata
        )

        return CompileResult(
            build_id=self.build_id,
            manifest=warm_output["manifest"],
            artifacts=warm_output["artifacts"],
            cold_artifacts=cold_artifacts,
            validation=validation,
            model_stats=model_stats,
            kir_claim_count=initial_claim_count,
            extractor_ids=extractor_ids,
        )

    def publish(self, result: CompileResult, registry, promote: bool = True) -> str:
        """Publica el resultado al Artifact Registry."""
        publisher = Publisher(registry)
        if promote:
            return publisher.publish_and_promote(
                result.manifest, result.artifacts,
                expected_contract_version="warm-v1",
            )
        return publisher.publish(result.manifest, result.artifacts)
