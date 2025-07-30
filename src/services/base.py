"""Base service class for DVD Maker services.

This module provides a common base class for all DVD Maker services
with shared functionality like settings injection, logging setup, and
common validation patterns.
"""

from typing import Any, List

from ..config.settings import Settings
from ..utils.logging import get_logger


class BaseService:
    """Base class for all DVD Maker services.

    Provides common functionality including:
    - Settings injection and management
    - Logging setup with service-specific loggers
    - Common tool validation patterns
    - Consistent service initialization

    All services should inherit from this class to ensure consistent
    patterns and reduce code duplication.
    """

    def __init__(self, settings: Settings):
        """Initialize the base service.

        Args:
            settings: Application settings object
        """
        self.settings = settings
        self.logger = get_logger(self.__class__.__module__)

        # Log service initialization
        service_name = self.__class__.__name__
        self.logger.debug(f"{service_name} initialized with settings")

    def _validate_tools(self, required_tools: List[str]) -> None:
        """Validate that required tools are available.

        This is a common pattern used by services that depend on external tools.
        Services can override this method to provide custom validation logic.

        Args:
            required_tools: List of tool names that must be available

        Raises:
            NotImplementedError: This base implementation should be overridden
        """
        # This is a placeholder for common tool validation logic
        # Services that need tool validation should override this method
        # and implement their specific validation requirements
        pass

    def _log_operation_start(self, operation: str, **context: Any) -> None:
        """Log the start of an operation with context.

        Args:
            operation: Name of the operation being started
            **context: Additional context to include in the log
        """
        context_str = ", ".join(f"{k}={v}" for k, v in context.items())
        if context_str:
            self.logger.info(f"Starting {operation} (context: {context_str})")
        else:
            self.logger.info(f"Starting {operation}")

    def _log_operation_complete(self, operation: str, **context: Any) -> None:
        """Log the completion of an operation with context.

        Args:
            operation: Name of the operation that completed
            **context: Additional context to include in the log
        """
        context_str = ", ".join(f"{k}={v}" for k, v in context.items())
        if context_str:
            self.logger.info(f"Completed {operation} (context: {context_str})")
        else:
            self.logger.info(f"Completed {operation}")

    def _log_operation_error(
        self, operation: str, error: Exception, **context: Any
    ) -> None:
        """Log an operation error with context.

        Args:
            operation: Name of the operation that failed
            error: The exception that occurred
            **context: Additional context to include in the log
        """
        context_str = ", ".join(f"{k}={v}" for k, v in context.items())
        if context_str:
            self.logger.error(f"Failed {operation}: {error} (context: {context_str})")
        else:
            self.logger.error(f"Failed {operation}: {error}")
