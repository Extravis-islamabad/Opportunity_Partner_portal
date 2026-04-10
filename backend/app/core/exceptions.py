from fastapi import HTTPException, status
from typing import Any, Dict, Optional


class AppException(HTTPException):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.error_message = message
        self.details = details or {}
        super().__init__(
            status_code=status_code,
            detail={"code": code, "message": message, "details": self.details},
        )


class BadRequestException(AppException):
    def __init__(self, code: str = "BAD_REQUEST", message: str = "Bad request", details: Optional[Dict[str, Any]] = None):
        super().__init__(status.HTTP_400_BAD_REQUEST, code, message, details)


class UnauthorizedException(AppException):
    def __init__(self, code: str = "UNAUTHORIZED", message: str = "Authentication required", details: Optional[Dict[str, Any]] = None):
        super().__init__(status.HTTP_401_UNAUTHORIZED, code, message, details)


class ForbiddenException(AppException):
    def __init__(self, code: str = "FORBIDDEN", message: str = "Access denied", details: Optional[Dict[str, Any]] = None):
        super().__init__(status.HTTP_403_FORBIDDEN, code, message, details)


class NotFoundException(AppException):
    def __init__(self, code: str = "NOT_FOUND", message: str = "Resource not found", details: Optional[Dict[str, Any]] = None):
        super().__init__(status.HTTP_404_NOT_FOUND, code, message, details)


class ConflictException(AppException):
    def __init__(self, code: str = "CONFLICT", message: str = "Resource conflict", details: Optional[Dict[str, Any]] = None):
        super().__init__(status.HTTP_409_CONFLICT, code, message, details)


class UnprocessableException(AppException):
    def __init__(self, code: str = "UNPROCESSABLE_ENTITY", message: str = "Validation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(status.HTTP_422_UNPROCESSABLE_ENTITY, code, message, details)
