"""IR Validation (RES-002 §6)."""

from .validator import KIRValidator, ValidationResult
from .semantic_validator import SemanticValidator

__all__ = ["KIRValidator", "ValidationResult", "SemanticValidator"]
