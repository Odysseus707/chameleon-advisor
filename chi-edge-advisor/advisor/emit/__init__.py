"""advisor.emit -- render + dry-check a runnable python-chi lease spec."""
from .spec import DryCheckResult, dry_check, render_spec

__all__ = ["DryCheckResult", "dry_check", "render_spec"]
