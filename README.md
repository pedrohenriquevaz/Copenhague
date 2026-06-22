# Discord Bot

Bot de Discord em Python usando `discord.py` com Slash Commands.

## Estrutura

```text
.
|-- app/
|   |-- cogs/
|   |   |-- events/
|   |   |-- fun/
|   |   `-- moderation/
|   |-- core/
|   |-- services/
|   |-- types/
|   `-- utils/
|-- tests/
|-- bot.py
|-- docker-compose.yml
|-- Dockerfile
|-- pyproject.toml
|-- requirements-dev.txt
`-- requirements.txt
```

## Configuracao local

Crie um arquivo `.env` a partir de `.env.example`:

```env
DISCORD_TOKEN=seu-token
GUILD_ID=id-do-servidor-de-testes
ENVIRONMENT=development
LOG_LEVEL=INFO
ENABLE_MEMBERS_INTENT=false
ENABLE_MESSAGE_CONTENT_INTENT=false
```

Se ativar `ENABLE_MEMBERS_INTENT=true`, habilite tambem o intent
`Server Members Intent` no Discord Developer Portal. Para sincronizar comandos
em um servidor de testes, confirme que `GUILD_ID` e o ID do servidor onde o bot
esta presente e que o convite usou o escopo `applications.commands`.

## Executando

```bash
python bot.py
```

## Docker

```bash
docker compose up --build
```

## Qualidade

```bash
python -m pytest
python -m ruff check .
python -m black --check .
```
