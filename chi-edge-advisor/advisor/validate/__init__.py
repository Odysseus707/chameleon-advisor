"""advisor.validate -- CHI@Edge trap checks over a Recommendation."""
from .checks import CheckResult, ValidationReport, validate_recommendation

__all__ = ["CheckResult", "ValidationReport", "validate_recommendation"]
