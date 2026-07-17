from __future__ import annotations


class MlbbIntegrationError(RuntimeError):
    """Erro base seguro para a MLBB Public Data API."""


class MlbbUnavailableError(MlbbIntegrationError):
    """O provedor esta indisponivel ou falhou de forma transitoria."""


class MlbbTimeoutError(MlbbUnavailableError):
    """O provedor nao respondeu dentro do timeout configurado."""


class MlbbRateLimitedError(MlbbUnavailableError):
    """O provedor recusou temporariamente novas requisicoes."""

    def __init__(
        self,
        message: str = "A MLBB Public Data API limitou as requisicoes.",
        *,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class MlbbInvalidResponseError(MlbbIntegrationError):
    """A resposta nao respeita o contrato minimo esperado."""

    def __init__(
        self,
        message: str = "A MLBB Public Data API retornou uma resposta invalida.",
        *,
        status: int | None = None,
        trace_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.trace_id = trace_id


class MlbbProviderResponseError(MlbbIntegrationError):
    """O envelope HTTP foi valido, mas o provedor informou falha."""

    def __init__(
        self,
        *,
        external_code: int,
        trace_id: str | None = None,
    ) -> None:
        super().__init__("A MLBB Public Data API recusou a operacao.")
        self.external_code = external_code
        self.trace_id = trace_id


class MlbbAuthenticationError(MlbbIntegrationError):
    """A autenticacao com o provedor falhou de forma clara."""


class MlbbInvalidVerificationCodeError(MlbbAuthenticationError):
    """O codigo de verificacao foi recusado."""


class MlbbVerificationExpiredError(MlbbAuthenticationError):
    """O codigo de verificacao expirou."""


class MlbbSessionExpiredError(MlbbAuthenticationError):
    """O JWT foi recusado ou a sessao expirou."""


class MlbbAccountNotFoundError(MlbbIntegrationError):
    """A conta informada nao foi encontrada pelo provedor."""
