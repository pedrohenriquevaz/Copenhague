# Containerizacao e deploy

Este guia deixa o bot pronto para rodar localmente em container e para ser
movido depois para uma VPS ou Railway com o minimo de mudanca.

## Modelo adotado

- Um container executa `python bot.py`.
- Um container `postgres:16-alpine` guarda os dados de producao.
- As variaveis ficam no arquivo `.env`.
- O volume `postgres-data` guarda os dados do Postgres fora da imagem.
- Os bancos SQLite ficam em `./data` apenas para migracao e rollback tecnico.
- O container reinicia automaticamente com `restart: unless-stopped`.
- Os logs do Docker fazem rotacao para nao crescer sem limite.

Com `DATABASE_BACKEND=postgres`, todos os repositorios principais usam
PostgreSQL: economia, atividade, auditoria, loja, progressao, conquistas,
jackpots, corridas coletivas, bets, bolao, formularios e sorteios.

## Primeira execucao local

No Windows, a partir da raiz do projeto:

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory -Force data
notepad .env
docker compose up -d --build
docker compose logs -f --tail=100 discord-bot
```

Preencha pelo menos:

- `DISCORD_TOKEN`
- `GUILD_ID`, se quiser sincronizacao rapida em um servidor de teste
- `ENABLE_MEMBERS_INTENT=true`, se usar distribuicao por cargo
- `ENABLE_MESSAGE_CONTENT_INTENT=true`, somente se ainda usar comandos legados
  com prefixo

## Atualizacao local

Para reconstruir a imagem e subir a versao atual do codigo:

```powershell
.\scripts\update-container.ps1
```

Para tambem buscar atualizacoes do Git antes do rebuild:

```powershell
.\scripts\update-container.ps1 -PullGit
```

Para apenas reiniciar com a imagem ja criada:

```powershell
.\scripts\update-container.ps1 -NoBuild
```

Comandos uteis:

```powershell
docker compose ps
docker compose logs -f --tail=100 discord-bot
docker compose restart discord-bot
docker compose down
```

## Postgres local

O `docker-compose.yml` inclui um Postgres local:

```powershell
docker compose up -d postgres
docker compose ps
```

Variaveis principais no `.env` de producao:

```env
DATABASE_BACKEND=postgres
POSTGRES_DB=copenhague
POSTGRES_USER=copenhague
POSTGRES_PASSWORD=copenhague
POSTGRES_PORT=5432
POSTGRES_SCHEMA=copenhague
POSTGRES_DSN=postgresql://copenhague:copenhague@postgres:5432/copenhague
POSTGRES_POOL_MIN_SIZE=2
POSTGRES_POOL_MAX_SIZE=10
```

Quando um script roda no host Windows, use `127.0.0.1` no DSN. Dentro do Docker,
use o host `postgres`.

## Schema e migracao

O gerenciador principal e:

```powershell
.\scripts\db-manage.ps1 status
.\scripts\db-manage.ps1 upgrade
.\scripts\db-manage.ps1 validate
```

Para migrar SQLite para Postgres, faca uma parada curta:

```powershell
docker compose stop discord-bot
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\scripts\db-manage.ps1 migrate-sqlite -Replace
```

O comando `migrate-sqlite`:

- sobe o servico `postgres`;
- atualiza os schemas SQLite locais antes da copia;
- cria um ZIP em `backups/sqlite-before-postgres-YYYYMMDD-HHMMSS.zip`;
- aplica migrations versionadas de `sql/postgres/migrations`;
- copia somente as tabelas do manifesto fixo;
- ajusta as sequencias das colunas `id`;
- compara contagens SQLite e Postgres e falha se houver divergencia.

Depois altere ou confirme no `.env`:

```env
DATABASE_BACKEND=postgres
POSTGRES_DSN=postgresql://copenhague:copenhague@postgres:5432/copenhague
POSTGRES_SCHEMA=copenhague
POSTGRES_POOL_MIN_SIZE=2
POSTGRES_POOL_MAX_SIZE=10
```

Suba o bot:

```powershell
docker compose up -d --build
docker compose logs -f --tail=100 discord-bot
```

Os logs de inicializacao devem indicar runtime PostgreSQL para economia,
progressao, bets, bolao, formularios e sorteios.

O script antigo continua disponivel e chama o fluxo novo:

```powershell
.\scripts\migrate-sqlite-to-postgres.ps1 -Replace
```

Para usar outro DSN no host:

```powershell
.\scripts\db-manage.ps1 migrate-sqlite `
  -Replace `
  -PostgresDsn "postgresql://usuario:senha@127.0.0.1:5432/copenhague" `
  -Schema "copenhague"
```

Para conferir as tabelas manualmente:

```powershell
docker compose exec postgres psql -U copenhague -d copenhague
```

Dentro do `psql`:

```sql
SET search_path TO copenhague;
\dt
SELECT COUNT(*) FROM economy_transactions;
SELECT COUNT(*) FROM user_wallets;
```

## Backup

Antes de mexer em dados de producao, pare o bot por alguns segundos e gere um
backup do diretorio `data/`:

```powershell
.\scripts\backup-data.ps1
```

O backup sera criado em `backups/data-YYYYMMDD-HHMMSS.zip`.

O `migrate-sqlite` tambem cria automaticamente um ZIP dos arquivos SQLite antes
da copia.

## Fluxo para VPS

Em uma VPS Linux, o desenho e o mesmo:

```bash
git clone <repo-do-bot>
cd Copenhague
cp .env.example .env
mkdir -p data backups
nano .env
docker compose up -d --build
docker compose logs -f --tail=100 discord-bot
```

Atualizacao:

```bash
git pull --ff-only
docker compose build --pull
docker compose up -d --remove-orphans
docker compose logs -f --tail=100 discord-bot
```

## Fluxo para Railway

No Railway, use o `Dockerfile` do repositorio e configure as mesmas variaveis do
`.env` no painel do projeto. Use um Postgres gerenciado e ajuste `POSTGRES_DSN`
para o DSN fornecido pela plataforma.

## Checklist antes de publicar mudancas

1. Rodar `python -m ruff check .`.
2. Rodar `python -m pytest`.
3. Rodar `.\scripts\db-manage.ps1 validate`.
4. Criar backup com `.\scripts\backup-data.ps1` quando houver SQLite envolvido.
5. Rodar `.\scripts\update-container.ps1`.
6. Acompanhar `docker compose logs -f --tail=100 discord-bot`.
7. Testar botoes persistentes e comandos principais no Discord.
