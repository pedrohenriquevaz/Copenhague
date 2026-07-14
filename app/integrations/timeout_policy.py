from __future__ import annotations

from dataclasses import dataclass

DISCORD_INTERACTION_ACK_DEADLINE_SECONDS = 3.0


@dataclass(frozen=True, slots=True)
class DiscordOrchestratedTimeoutPolicy:
    """Timeouts externos subordinados ao ciclo de interacao do Discord.

    Comandos que consultam provedores devem confirmar ou adiar a interacao antes
    do prazo de ACK. O timeout HTTP passa a valer somente depois desse ACK.
    """

    interaction_ack_seconds: float = 2.5
    connect_seconds: float = 3.0
    request_seconds: float = 15.0
    max_retries: int = 2

    def __post_init__(self) -> None:
        if (
            not 0
            < self.interaction_ack_seconds
            < DISCORD_INTERACTION_ACK_DEADLINE_SECONDS
        ):
            raise ValueError(
                "interaction_ack_seconds precisa ser menor que 3 segundos."
            )
        if self.connect_seconds <= 0:
            raise ValueError("connect_seconds precisa ser positivo.")
        if self.request_seconds < self.connect_seconds:
            raise ValueError("request_seconds nao pode ser menor que connect_seconds.")
        if self.max_retries < 0:
            raise ValueError("max_retries nao pode ser negativo.")
