from __future__ import annotations

from app.ui.bot_announcement import (
    build_bot_announcement_embed,
    build_user_commands_embed,
)


def test_user_commands_embed_lists_common_member_commands_only() -> None:
    embed = build_user_commands_embed()
    text = _embed_text(embed)

    expected_commands = {
        "/saldo",
        "/perfil",
        "/transferir",
        "/historico",
        "/ranking",
        "/converter_atividade",
        "/loja",
        "/blackjack",
        "/cara_coroa",
        "/dado",
        "/slot",
        "/roleta",
        "/duelo",
        "/corrida",
        "/raspadinha",
        "/jogos_perfil",
        "/jogos_ranking",
        "/jogos_historico",
        "/conquistas",
        "/jackpot",
        "/evento_sazonal",
        "/lembrete",
        "/ping",
    }
    admin_commands = {
        "/give_points",
        "/reset_profile",
        "/bet_criar",
        "/bolao_create",
        "/giveaway_create",
        "/form_create",
        "/purge",
    }

    for command in expected_commands:
        assert command in text
    for command in admin_commands:
        assert command not in text


def test_bot_announcement_embed_uses_pt_br_accents() -> None:
    embed = build_bot_announcement_embed()
    text = _embed_text(embed)

    assert "apostas saudáveis" in text
    assert "botões" in text
    assert "presente diário" in text


def _embed_text(embed) -> str:
    parts = [embed.title or "", embed.description or ""]
    for field in embed.fields:
        parts.extend([field.name, field.value])
    return "\n".join(str(part) for part in parts)
