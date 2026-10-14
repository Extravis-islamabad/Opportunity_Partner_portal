from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.exc import DataError, IntegrityError
import structlog

from app.core.exceptions import AppException

logger = structlog.get_logger()


def register_error_handlers(app: FastAPI) -> None:

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        # Flatten to the same top-level {code, message, details} shape the
        # other handlers use. Without this, HTTPException's default handler
        # nests everything under "detail" and the frontend (which reads
        # response.data.message) falls back to its generic error strings.
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.error_message,
                "details": exc.details,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for error in exc.errors():
            field = " -> ".join(str(loc) for loc in error["loc"])
            errors.append({"field": field, "message": error["msg"]})
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": {"errors": errors},
            },
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "code": "BAD_REQUEST",
                "message": str(exc),
                "details": {},
            },
        )

    # Bad input that only the database caught: an unknown enum value in a
    # filter, a number past the column's range. These are the caller's mistake,
    # not ours, so they get a 400 rather than a 500. Registered for the specific
    # classes on purpose: the catch-all below runs in Starlette's outermost
    # middleware, which re-raises after replying and so drops the upstream
    # connection — nginx then answered the *next* request with a 502.
    @app.exception_handler(DataError)
    async def data_error_handler(request: Request, exc: DataError) -> JSONResponse:
        logger.warning("db_data_error", error=str(exc.orig), path=request.url.path)
        return JSONResponse(
            status_code=400,
            content={
                "code": "INVALID_VALUE",
                "message": "One of the values sent is not valid — it is out of range or not an accepted option.",
                "details": {},
            },
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("db_integrity_error", error=str(exc.orig), path=request.url.path)
        return JSONResponse(
            status_code=409,
            content={
                "code": "CONFLICT",
                "message": "This change conflicts with existing data or leaves out a required value.",
                "details": {},
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_exception", error=str(exc), path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "details": {},
            },
        )
