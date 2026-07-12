# Discord Bot Copenhague

Bot de Discord em Python com `discord.py`, Slash Commands, SQLite e uma
arquitetura organizada por cogs, services, repositories, models e UI.

O bot atende uma comunidade com economia de pontos, loja, cassino social,
apostas de partidas, eventos, giveaways, formularios e utilidades de
administracao.

## Funcionalidades

### Base e operacao

- Carregamento automatico de cogs em `app/cogs`.
- Sincronizacao global de Slash Commands ou homologacao por `GUILD_IDS`.
- Views persistentes para paineis, loja, giveaways, formularios, bets e eventos.
- Logs estruturados de inicializacao, cogs e sincronizacao.
- Prefixo legado `cp!` apenas para comandos operacionais antigos.
- Persistencia SQLite local com schemas criados pelos repositories.

### Painel do bot

- `/anuncio_bot`: publica uma embed de apresentacao do bot em um canal.
- A embed aceita imagem anexada dentro da propria embed.
- Botoes publicos:
  - `Ajuda/comandos`: envia documentacao de comandos livres em privado.
  - `Presente diario`: concede entre 50 e 200 pontos uma vez ao dia.
  - `Pacote inicial`: concede 1500 pontos uma unica vez por usuario.

### Economia

Comandos de usuario:

- `/saldo`: mostra o saldo do usuario.
- `/perfil`: mostra resumo economico do usuario.
- `/historico`: mostra transacoes recentes.
- `/ranking`: mostra ranking de saldo.
- `/converter_atividade`: converte mensagens e tempo em call em pontos.

Comandos administrativos:

- `/give_points`: concede pontos a um usuario.
- `/give_points_role`: concede pontos a todos os usuarios de um cargo.
- `/remove_points`: remove pontos de um usuario.
- `/economy_status`: mostra configuracao atual.
- `/economy_config`: ajusta moeda, taxas, minimos, canais, limite admin e cargo gerente.
- `/economy_panel_setup`: publica painel publico de economia.

Recursos:

- Carteira por usuario e servidor.
- Transacoes imutaveis.
- Saldo nunca fica negativo.
- Auditoria administrativa.
- Conversao por delta para evitar duplicidade.
- Pontuacao por mensagem e por call.
- Controle de call sozinho e canal AFK.

### Loja

Comandos:

- `/loja`: abre a loja em privado.
- `/embed_loja`: publica a loja fixa em um canal, com imagem opcional.
- `/reward_create`: cria item na loja.
- `/reward_update`: atualiza nome, descricao, preco, estoque, cargo, mensagem e status.
- `/reward_remove`: remove item da loja com soft delete.
- `/reward_list`: lista recompensas cadastradas.

Recursos:

- Embed com imagem dentro da propria embed.
- Select menu para escolher item.
- Botao `Consultar Pontos`.
- Botao `Converter atividade` para executar o fluxo de `/converter_atividade`.
- Confirmacao antes de comprar.
- Estoque limitado ou ilimitado.
- Estado `Esgotado` quando estoque chega a zero.
- Limite por usuario.
- Entrega de cargo ou recompensa manual.
- Historico de compras preservado mesmo quando item e removido.

### Cassino social

Comandos:

- `/cara_coroa`
- `/dado`
- `/slot`
- `/roleta`
- `/duelo`
- `/corrida`
- `/blackjack`
- `/truco`
- `/truco_maquina`
- `/uno`
- `/uno_maquina`
- `/jogos_perfil`
- `/jogos_ranking`
- `/jogos_historico`

Recursos:

- Controle de saldo e aposta minima/maxima.
- Cooldown por jogo.
- Historico por usuario.
- Ranking por lucro.
- Animacoes visuais em jogos instantaneos.
- Duelo entre jogadores com botoes.
- Blackjack com Pedir Carta, Parar e Dobrar.
- Truco Paulista em duplas com mesa visual persistente.
- UNO multiplayer com lobby, mãos privadas e mesa pública dinâmica.
- Modos contra a máquina com pagamento de 2x em caso de vitória.
- Partidas PvP pagam o pote com bônus de 25% da casa.
- Notificacao publica de vitorias nos jogos.
- Notificacao publica de derrotas expressivas acima de 500 pontos.
- Winstreak no BlackJack: vitorias seguidas aumentam o lucro pago, com teto de
  bonus.

### Eventos de jogos

Comandos:

- `/raspadinha`
- `/corrida_iniciar`
- `/corrida_finalizar`
- `/jackpot`
- `/conquistas`
- `/evento_sazonal`
- `/evento_sazonal_definir`

Recursos:

- Raspadinha por tier.
- Jackpot acumulado.
- Corrida coletiva com botoes persistentes.
- Conquistas por usuario.
- Tema sazonal por servidor.

### Apostas de partidas

Comandos:

- `/bet_criar`: cria sessao de apostas com dois times e odds iniciais.
- `/bet_odds`: altera odds ao vivo.
- `/bet_encerrar`: encerra partida, paga vencedores ou cancela.
- `/bet_listar`: lista bets ativas.

Recursos:

- Odds travadas no momento da aposta do usuario.
- Multiplas apostas por usuario.
- Confirmacao privada antes de apostar.
- Debito e pagamento atomicos via economia.
- Notificacao publica quando odds mudam.

### Bolao, giveaways e formularios

Bolao:

- `/bolao_create`
- `/bolao_close`
- `/bolao_list`

Giveaway:

- `/giveaway_create`
- `/giveaway_publish`
- `/giveaway_unpublish`
- `/giveaway_codes`
- `/give_ticket`
- `/user_ticket`
- `/remove_ticket`

Formularios:

- `/form_create`
- `/form_close`
- `/form_list`

### Administracao e analytics

- `/admin_panel`: painel central com status de economia, loja, bets e eventos.
- `/admin_analytics`: indicadores acumulados de pontos, atividade, loja, cassino,
  bets, eventos, ranking e auditoria.
- `/ban`: moderacao basica de banimento.
- `/purge`: remove mensagens recentes do canal atual.
- `/lembrete`: agenda lembrete simples por DM.
- `/ping`: latencia atual do bot.

## Persistencia

O bot usa SQLite. Os caminhos sao configuraveis por variaveis de ambiente:

- `GIVEAWAY_DB_PATH`
- `BOLAO_DB_PATH`
- `MATCH_BET_DB_PATH`
- `GAME_PROGRESS_DB_PATH`
- `FORM_DB_PATH`
- `ECONOMY_DB_PATH`

Por padrao, os bancos ficam em `data/`.

## Configuracao local

Crie `.env` a partir de `.env.example`:

```env
DISCORD_TOKEN=seu-token
GUILD_IDS=id-servidor-teste-1,id-servidor-teste-2
ENVIRONMENT=development
LOG_LEVEL=INFO
GIVEAWAY_DB_PATH=data/giveaways.sqlite3
BOLAO_DB_PATH=data/bot.db
MATCH_BET_DB_PATH=data/bot.db
GAME_PROGRESS_DB_PATH=data/bot.db
FORM_DB_PATH=data/bot.db
ECONOMY_DB_PATH=data/economy.sqlite3
ENABLE_MEMBERS_INTENT=false
ENABLE_MESSAGE_CONTENT_INTENT=false
```

Ative `ENABLE_MEMBERS_INTENT=true` quando usar distribuicao por cargo ou precisar
carregar membros do servidor. Ative o mesmo intent no Discord Developer Portal.

Ative `ENABLE_MESSAGE_CONTENT_INTENT=true` somente se precisar dos comandos
prefixados legados `cp!give_ticket`, `cp!user_ticket` e `cp!remove_ticket`.

## Executando

```bash
python bot.py
```

## Docker

```bash
docker compose up -d --build
docker compose logs -f --tail=100 discord-bot
```

O `docker-compose.yml` monta `./data:/app/data`, preservando os bancos SQLite
entre reinicios e rebuilds.

Para atualizar a imagem localmente no Windows:

```powershell
.\scripts\update-container.ps1
```

Para criar backup dos bancos antes de atualizar:

```powershell
.\scripts\backup-data.ps1
```

Veja o guia completo em `docs/containerizacao.md`.

## Checklist de deploy

1. Criar `.env` com token real e caminhos de banco.
2. Confirmar que `data/` esta persistido em volume.
3. Convidar o bot com escopos `bot` e `applications.commands`.
4. Habilitar intents necessarios no Developer Portal.
5. Em homologacao, definir `GUILD_IDS` para sincronizacao rapida. Em producao,
   deixar vazio para os comandos funcionarem em qualquer servidor.
6. Rodar o bot e confirmar todos os cogs nos logs.
7. Testar `/admin_panel`, `/admin_analytics` e `/economy_status`.
8. Publicar `/anuncio_bot`, `/economy_panel_setup` e `/embed_loja`.
9. Reiniciar o bot e testar botoes persistentes.
10. Fazer backup periodico de `data/*.sqlite3` e `data/*.db`.

## Qualidade

```bash
python -m pytest
python -m ruff check .
python -m black --check .
```

## Estrutura

```text
app/
  cogs/          # Slash commands e eventos Discord
  core/          # bot, config e logging
  models/        # dataclasses e enums de dominio
  providers/     # providers de atividade
  repositories/  # SQLite e transacoes
  services/      # regras de negocio
  ui/            # views, botoes, selects e modals
  utils/         # embeds, permissoes e helpers
tests/
data/
bot.py
Dockerfile
docker-compose.yml
pyproject.toml
```
