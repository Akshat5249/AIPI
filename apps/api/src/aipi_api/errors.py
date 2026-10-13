"""Sanitized error envelopes and validated request IDs for every HTTP response."""

import re
from uuid import uuid4

from aipi_tools.scope import ScopeDenied
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from aipi_api.incidents import MissingIncident
from aipi_api.investigation_repository import InvestigationUnavailable


class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        raw = dict(scope.get("headers", [])).get(b"x-request-id", b"").decode("latin-1")
        request_id = raw if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", raw) else uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        async def with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                message["headers"].append((b"x-request-id", request_id.encode()))
            await send(message)

        await self.app(scope, receive, with_id)


def install_errors(app: FastAPI) -> None:
    app.add_middleware(RequestIDMiddleware)

    def response(
        request: Request, code: str, message: str, status: int, retryable: bool = False
    ) -> JSONResponse:
        body = ErrorEnvelope(
            error=ErrorDetail(
                code=code,
                message=message,
                retryable=retryable,
                request_id=getattr(request.state, "request_id", "unavailable"),
            )
        )
        return JSONResponse(
            status_code=status,
            content=body.model_dump(),
            headers={"X-Request-ID": body.error.request_id},
        )

    @app.exception_handler(RequestValidationError)
    async def validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return response(request, "VALIDATION_ERROR", "Request validation failed", 422)

    @app.exception_handler(InvestigationUnavailable)
    async def unavailable(request: Request, exc: InvestigationUnavailable) -> JSONResponse:
        return response(
            request,
            exc.code,
            "Investigation report unavailable",
            409 if exc.code == "INVESTIGATION_NOT_READY" else 500,
        )

    @app.exception_handler(MissingIncident)
    async def missing(request: Request, exc: MissingIncident) -> JSONResponse:
        return response(request, "NOT_FOUND", "Requested resource not found", 404)

    @app.exception_handler(ScopeDenied)
    async def denied(request: Request, exc: ScopeDenied) -> JSONResponse:
        return response(
            request, "SCOPE_POLICY_DENIED", "Requested scope exceeds incident bounds", 403
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code = (
            "NOT_FOUND"
            if exc.status_code == 404
            else "VALIDATION_ERROR"
            if exc.status_code in {400, 422}
            else "HTTP_ERROR"
        )
        message = (
            "Endpoint not found" if exc.status_code == 404 else "Request could not be completed"
        )
        return response(request, code, message, exc.status_code, exc.status_code >= 500)

    @app.exception_handler(DBAPIError)
    async def database_error(request: Request, exc: DBAPIError) -> JSONResponse:
        return response(request, "EVIDENCE_QUERY_TIMEOUT", "Database query unavailable", 503, True)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        return response(request, "INTERNAL_ERROR", "Request could not be completed", 500)
