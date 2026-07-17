from __future__ import annotations

from collections.abc import Iterable

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class MlbbTokenCipherError(RuntimeError):
    """Falha segura ao proteger uma credencial MLBB."""


class MlbbTokenCipherConfigurationError(MlbbTokenCipherError):
    """A configuracao de chaves MLBB esta ausente ou invalida."""


class MlbbTokenDecryptionError(MlbbTokenCipherError):
    """A credencial persistida nao pode ser descriptografada."""


class MlbbTokenCipher:
    """Criptografa JWTs com MultiFernet e suporta rotacao ordenada de chaves."""

    def __init__(self, keys: Iterable[str]) -> None:
        normalized = tuple(key.strip() for key in keys if key.strip())
        self._cipher: MultiFernet | None = None
        if not normalized:
            return
        try:
            self._cipher = MultiFernet(
                [Fernet(key.encode("ascii")) for key in normalized]
            )
        except (ValueError, UnicodeEncodeError) as exc:
            raise MlbbTokenCipherConfigurationError(
                "As chaves de criptografia MLBB sao invalidas."
            ) from exc

    @property
    def configured(self) -> bool:
        return self._cipher is not None

    def encrypt(self, jwt: str) -> str:
        cipher = self._require_cipher()
        if not jwt:
            raise MlbbTokenCipherError("A credencial MLBB esta vazia.")
        return cipher.encrypt(jwt.encode("utf-8")).decode("ascii")

    def decrypt(self, encrypted_jwt: str) -> str:
        cipher = self._require_cipher()
        try:
            return cipher.decrypt(encrypted_jwt.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError) as exc:
            raise MlbbTokenDecryptionError(
                "A credencial MLBB armazenada nao pode ser lida."
            ) from exc

    def _require_cipher(self) -> MultiFernet:
        if self._cipher is None:
            raise MlbbTokenCipherConfigurationError(
                "A criptografia MLBB nao foi configurada."
            )
        return self._cipher
