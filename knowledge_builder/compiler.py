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
from .frontend import DocCardsExtractor, EntityAliasesExtractor, EquivalencesExtractor, LLMEntityExtractor
from .kir import KIR
from .model.confidence import ConfidencePolicy, get_policy
from .model.knowledge_model import KnowledgeModel
from .passes import CanonicalizePass, DeduplicationPass, NormalizePass
from .publish import Publisher
from .validate.semantic_validator import SemanticValidator
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
    """Orquesta el pipeline completo: front-end -> KIR -> passes -> validation -> model -> back-end.

    ADR-0021: expone 4 fases separables:
        - extract_only(): extractores -> KIR crudo (con cache)
        - compile_only(): KIR -> passes -> KnowledgeModel (sin codegen)
        - validate_only(): KnowledgeModel -> validation report
        - publish_only(): codegen desde modelo validado -> Registry

    El metodo compile() mantiene retrocompatibilidad ejecutando las 4 fases en secuencia.
    """

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
        use_llm_extractor: bool = False,
        llm_model: str = "ibm/granite4.1:3b-q6_K",
        llm_max_docs: int = 50,
        llm_verbose: bool = False,
        llm_max_workers: int = 4,
        llm_num_predict: int = 1200,
        llm_num_ctx: int = 4096,
        use_semantic_validation: bool = False,
        cache_dir: Optional[Path | str] = None,
        use_cache: bool = True,
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

        # LLM extractor (E5)
        self.use_llm_extractor = use_llm_extractor
        if use_llm_extractor:
            self.extractors.append(LLMEntityExtractor(
                model=llm_model,
                doc_roles=doc_roles if doc_roles else None,
                max_docs=llm_max_docs,
                verbose=llm_verbose,
                max_workers=llm_max_workers,
                num_predict=llm_num_predict,
                num_ctx=llm_num_ctx,
                cache_dir=cache_dir,
                use_cache=use_cache,
            ))

        # Warm codegen knows the predicate catalog
        self.warm_codegen = WarmCodegen(builder_version=builder_version)

        # Passes
        self.predicate_ids = self.warm_codegen.predicate_ids
        self.normalize_pass = NormalizePass()
        self.canonicalize_pass = CanonicalizePass(predicate_catalog=self.predicate_ids)
        self.dedup_pass = DeduplicationPass(confidence_policy=self.confidence_policy)

        # Validator
        self.validator = KIRValidator(predicate_catalog=self.predicate_ids)

        # Semantic validator (E5)
        self.use_semantic_validation = use_semantic_validation
        self.semantic_validator = SemanticValidator(
            use_llm=use_semantic_validation,
            model=llm_model,
        )

        # Cold codegen
        self.cold_codegen = ColdCodegen()

    # ------------------------------------------------------------------ #
    # Phase 1: extract — extractors -> KIR crudo (con cache)
    # ------------------------------------------------------------------ #
    def extract_only(self) -> KIR:
        """ADR-0021.1: extract phase. Extractors -> KIR. No passes, no validation."""
        kir = KIR()
        for extractor in self.extractors:
            sub_kir = extractor.extract()
            kir.merge(sub_kir)
        return kir

    # ------------------------------------------------------------------ #
    # Phase 2: compile — KIR -> passes -> KnowledgeModel (sin codegen)
    # ------------------------------------------------------------------ #
    def compile_only(self, kir: KIR) -> tuple[KnowledgeModel, ValidationResult, Dict[str, Any]]:
        """ADR-0021.1: compile phase. KIR -> passes -> KnowledgeModel.

        Returns (model, validation, cold_artifacts_data).
        Does NOT generate Warm Artifacts (that's publish).
        """
        initial_claim_count = kir.claim_count()

        # Middle-end: passes
        kir = self.normalize_pass.run(kir)
        kir = self.canonicalize_pass.run(kir)
        kir = self.dedup_pass.run(kir)

        # Validation (structural)
        validation = self.validator.validate(kir)
        if not validation.is_valid:
            raise ValueError(
                f"KIR validation failed with {len(validation.errors)} errors: "
                + "; ".join(validation.errors[:5])
            )

        # Semantic validation (E5) — errors are warnings (Cold), not hard failures
        semantic_result = None
        if self.use_semantic_validation or self.use_llm_extractor:
            semantic_result = self.semantic_validator.validate(kir)
            if semantic_result.get("errors"):
                for err in semantic_result["errors"]:
                    validation.warnings.append(f"semantic: {err}")

        # Knowledge Model
        model = KnowledgeModel.from_kir(kir, builder_version=self.builder_version)

        # Cold artifacts data (for publish to write)
        cold_data = {
            "kir": kir.to_dict(),
            "validation": validation.to_dict(),
            "build_metadata": kir.metadata,
        }
        if semantic_result:
            cold_data["semantic_validation"] = semantic_result

        return model, validation, cold_data

    # ------------------------------------------------------------------ #
    # Phase 3: validate — KnowledgeModel -> validation report
    # ------------------------------------------------------------------ #
    def validate_only(self, model: KnowledgeModel, validation: ValidationResult) -> Dict[str, Any]:
        """ADR-0021.1: validate phase. Returns validation report for the model.

        This is a separate checkpoint. The structural validation already ran
        in compile_only(); this phase exposes the result as a standalone report
        and can run additional contract checks.
        """
        return {
            "is_valid": validation.is_valid,
            "errors": list(validation.errors),
            "warnings": list(validation.warnings),
            "quarantined": list(validation.quarantined),
            "passed": validation.passed,
            "rejected": validation.rejected,
            "model_stats": model.stats(),
        }

    # ------------------------------------------------------------------ #
    # Phase 4: publish — codegen from validated model -> Registry
    # ------------------------------------------------------------------ #
    def publish_only(
        self,
        model: KnowledgeModel,
        cold_data: Dict[str, Any],
        registry,
        promote: bool = True,
    ) -> tuple[str, Dict[str, Any], Dict[str, Any]]:
        """ADR-0021.1: publish phase. Codegen + Registry publish.

        Returns (build_id, manifest, artifacts).
        """
        warm_output = self.warm_codegen.generate(model, build_id=self.build_id)
        manifest = warm_output["manifest"]
        artifacts = warm_output["artifacts"]

        cold_artifacts = self.cold_codegen.generate(
            KIR.from_dict(cold_data.get("kir", {"metadata": {}})),
            ValidationResult(
                errors=cold_data.get("validation", {}).get("errors", []),
                warnings=cold_data.get("validation", {}).get("warnings", []),
                quarantined=cold_data.get("validation", {}).get("quarantined", []),
                passed=cold_data.get("validation", {}).get("passed", 0),
                rejected=cold_data.get("validation", {}).get("rejected", 0),
            ),
            build_metadata=cold_data.get("build_metadata", {}),
        )
        if "semantic_validation" in cold_data:
            cold_artifacts["semantic_validation"] = cold_data["semantic_validation"]

        publisher = Publisher(registry)
        if promote:
            build_id = publisher.publish_and_promote(
                manifest, artifacts,
                expected_contract_version="warm-v1",
            )
        else:
            build_id = publisher.publish(manifest, artifacts)

        return build_id, manifest, artifacts, cold_artifacts

    # ------------------------------------------------------------------ #
    # Backward-compatible compile() — runs all 4 phases in sequence
    # ------------------------------------------------------------------ #
    def compile(self) -> CompileResult:
        """Ejecuta el pipeline completo y retorna el resultado.

        Retrocompatible: ejecuta extract -> compile -> validate -> publish(codegen).
        No publica al Registry (eso sigue siendo publish()).
        """
        kir = self.extract_only()
        initial_claim_count = kir.claim_count()
        extractor_ids = kir.extractor_ids()

        model, validation, cold_data = self.compile_only(kir)
        model_stats = model.stats()

        warm_output = self.warm_codegen.generate(model, build_id=self.build_id)
        cold_artifacts = self.cold_codegen.generate(
            kir, validation, build_metadata=kir.metadata
        )
        if "semantic_validation" in cold_data:
            cold_artifacts["semantic_validation"] = cold_data["semantic_validation"]

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
