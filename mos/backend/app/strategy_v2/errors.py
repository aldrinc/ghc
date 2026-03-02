from __future__ import annotations


class StrategyV2Error(RuntimeError):
    """Base class for all Strategy V2 pipeline errors."""


class StrategyV2SchemaValidationError(StrategyV2Error):
    """Raised when stage or decision payload validation fails."""


class StrategyV2MissingContextError(StrategyV2Error):
    """Raised when required upstream context is missing."""


class StrategyV2ExternalDependencyError(StrategyV2Error):
    """Raised when external providers fail or time out."""


class StrategyV2ScorerError(StrategyV2Error):
    """Raised when deterministic scorer execution fails."""


class StrategyV2DecisionError(StrategyV2Error):
    """Raised when a HITL decision payload is invalid or incomplete."""
