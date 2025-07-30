"""Common base exception class for DVD Maker.

This module provides the base exception class that all DVD Maker exceptions
should inherit from for consistent error handling and context support.
"""

from typing import Any, Dict, Optional


class DVDMakerError(Exception):
    """Base exception for all DVD Maker errors.
    
    This class provides a common base for all DVD Maker exceptions with
    support for additional error context that can be useful for debugging
    and error reporting.
    
    Attributes:
        context: Optional dictionary containing additional error context
    """
    
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Initialize the DVD Maker error.
        
        Args:
            message: The error message
            context: Optional dictionary with additional error context
        """
        super().__init__(message)
        self.context = context or {}
    
    def __str__(self) -> str:
        """Return string representation of the error."""
        base_message = super().__str__()
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{base_message} (context: {context_str})"
        return base_message