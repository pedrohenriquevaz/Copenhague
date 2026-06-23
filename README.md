# Discord Bot

Bot de Discord em Python usando `discord.py` com Slash Commands.

## Estrutura

```text
.
|-- app/
|   |-- cogs/
|   |   |-- giveaway/
|   |   |-- events/
|   |   |-- fun/
|   |   `-- moderation/
|   |-- core/
|   |-- models/
|   |-- repositories/
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
GIVEAWAY_DB_PATH=data/giveaways.sqlite3
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

## Giveaway

Comandos administrativos disponiveis:

- `/giveaway_create`
- `/giveaway_publish`
- `/giveaway_unpublish`

`/giveaway_create` aceita:

- `title`
- `description`
- `total_codes`
- `reward_plan`
- `notify_user`

`/giveaway_publish` aceita:

- `event_id`
- `channel`
- `embed_color`
- `duration_minutes`

`/giveaway_unpublish` aceita:

- `event_id`
- `delete_message`

Formato do `reward_plan` aceito no `giveaway_create`:

```text
Diamantes|100|2;Diamantes|300|1;500|1
```

Tambem e aceito JSON, por exemplo:

```json
[{"reward_name":"Diamantes","reward_amount":100,"reward_quantity":2}]
```

Fluxo:

1. Crie o evento com `/giveaway_create`
2. Publique com `/giveaway_publish`
3. O usuario clica no botao para receber um codigo
4. O bot registra o resgate e anuncia publicamente se houver premio
5. Ao encerrar, o bot publica um resumo com os codigos restantes e o valor de cada um

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
