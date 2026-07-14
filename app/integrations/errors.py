from __future__ import annotations


class ExternalApiError(RuntimeError):
    """Base segura para erros de provedores externos."""


class ExternalApiTimeoutError(ExternalApiError):
    """O provedor nao respondeu dentro da politica de timeout."""


class ExternalApiUnavailableError(ExternalApiError):
    """O provedor esta indisponivel ou falhou de forma transitoria."""


class ExternalApiAuthenticationError(ExternalApiError):
    """A autenticacao com o provedor falhou."""


class ExternalApiRateLimitedError(ExternalApiError):
    """O provedor recusou a requisicao por limite de uso."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ExternalApiResponseError(ExternalApiError):
    """O provedor retornou uma resposta definitiva invalida."""

    def __init__(self, message: str, *, status: int) -> None:
        super().__init__(message)
        self.status = status
