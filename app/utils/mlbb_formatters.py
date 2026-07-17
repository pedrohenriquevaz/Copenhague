from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from app.integrations.mlbb.dto import MlbbStatHighlightKind

NOT_AVAILABLE = "Não disponível"

HIGHLIGHT_LABELS: Mapping[MlbbStatHighlightKind, str] = MappingProxyType(
    {
        MlbbStatHighlightKind.MOST_DAMAGE: "Maior dano",
        MlbbStatHighlightKind.HIGHEST_KILLS: "Maior número de kills",
        MlbbStatHighlightKind.MOST_ASSISTS: "Maior número de assistências",
        MlbbStatHighlightKind.HIGHEST_SCORE: "Melhor score",
        MlbbStatHighlightKind.MOST_DAMAGE_TAKEN: "Maior dano recebido",
        MlbbStatHighlightKind.MOST_GOLD: "Maior ouro",
        MlbbStatHighlightKind.MOST_TOTAL_DAMAGE: "Maior dano total",
    }
)


def calculate_win_rate(wins: int, total_matches: int) -> float:
    """Calcula o percentual de vitórias sem dividir por zero."""

    if total_matches <= 0:
        return 0.0
    return round((wins / total_matches) * 100, 2)


def normalize_score(raw_score: float | int | None) -> float | None:
    """Normaliza scores do contrato MLBB, enviados em centésimos."""

    if raw_score is None:
        return None
    return round(float(raw_score) / 100, 2)


def format_decimal_pt_br(
    value: float | int | None,
    *,
    decimal_places: int = 2,
) -> str:
    """Formata um número com separadores legíveis em pt-BR."""

    if value is None:
        return NOT_AVAILABLE
    if decimal_places < 0:
        raise ValueError("decimal_places não pode ser negativo")

    formatted = f"{value:,.{decimal_places}f}"
    return formatted.translate(str.maketrans({",": ".", ".": ","}))


def format_percentage(value: float | int | None) -> str:
    if value is None:
        return NOT_AVAILABLE
    return f"{format_decimal_pt_br(value)}%"


def format_score(raw_score: float | int | None) -> str:
    return format_decimal_pt_br(normalize_score(raw_score))


def format_optional_number(value: float | int | None) -> str:
    """Formata contagens/medidas sem confundir zero com ausência."""

    if value is None:
        return NOT_AVAILABLE
    numeric_value = float(value)
    decimal_places = 0 if numeric_value.is_integer() else 2
    return format_decimal_pt_br(value, decimal_places=decimal_places)


def format_duration_hours(hours: float | int | None) -> str:
    """Converte horas decimais do provedor em horas e minutos."""

    if hours is None or hours < 0:
        return NOT_AVAILABLE

    total_minutes = int(round(float(hours) * 60))
    whole_hours, minutes = divmod(total_minutes, 60)
    parts: list[str] = []
    if whole_hours:
        parts.append(f"{whole_hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}min")
    return " ".join(parts)


def mask_game_id(
    role_id: int | str | None,
    zone_id: int | str | None = None,
    *,
    visible_digits: int = 4,
) -> str:
    """Mascara o Game ID e, quando fornecida, exibe a área separadamente."""

    if role_id is None:
        return NOT_AVAILABLE
    if visible_digits < 0:
        raise ValueError("visible_digits não pode ser negativo")

    raw_role_id = str(role_id).strip()
    if not raw_role_id:
        return NOT_AVAILABLE

    # Nunca devolve o identificador completo, nem para IDs atipicamente curtos.
    masked = _mask_component(raw_role_id, visible_digits)
    if zone_id is not None:
        raw_zone_id = str(zone_id).strip()
        if raw_zone_id:
            masked = f"{masked} (Área {_mask_component(raw_zone_id, 2)})"
    return masked


def highlight_label(kind: MlbbStatHighlightKind) -> str:
    """Retorna o rótulo seguro de um tipo normalizado de destaque."""

    return HIGHLIGHT_LABELS.get(kind, "Destaque")


def format_highlight_value(
    kind: MlbbStatHighlightKind,
    value: float | int | None,
) -> str:
    """Formata um destaque, normalizando somente scores em centésimos."""

    if kind is MlbbStatHighlightKind.HIGHEST_SCORE:
        return format_score(value)
    return format_optional_number(value)


def _mask_component(value: str, visible_digits: int) -> str:
    visible_count = min(visible_digits, max(len(value) - 1, 0))
    hidden_count = len(value) - visible_count
    return ("•" * hidden_count) + value[hidden_count:]
