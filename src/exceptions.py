# Custom Exception Hierarchy for CivicAudit
"""
Domain-specific exceptions for the CivicAudit system.
Provides structured error handling with clear categorization.
"""

from typing import Optional


class CivicAuditError(Exception):
    """Base exception for all CivicAudit errors."""

    def __init__(self, message: str, details: Optional[str] = None) -> None:
        self.message = message
        self.details = details
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class ConfigurationError(CivicAuditError):
    """Configuration-related errors (missing keys, invalid values)."""

    pass


class DatabaseError(CivicAuditError):
    """Database operation errors (connection, query execution)."""

    pass


class SandboxError(CivicAuditError):
    """Sandbox execution errors (Docker, code execution)."""

    pass


class ValidationError(CivicAuditError):
    """Input validation errors (guardrails, SQL injection prevention)."""

    pass


class AgentError(CivicAuditError):
    """Agent execution errors (LLM calls, workflow failures)."""

    pass
