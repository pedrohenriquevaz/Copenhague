from __future__ import annotations


def resolve_rank_name(rank_code: int | None) -> str:
    """Resolve rank sem inferir nomes que o contrato não documenta."""

    if rank_code is None:
        return "Não disponível"
    return f"Rank não mapeado (código {rank_code})"
