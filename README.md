# Discord Bot Copenhague

Bot de Discord em Python usando `discord.py`, Slash Commands e alguns comandos prefixados com `cp!`.

O projeto esta organizado por cogs e possui sistemas completos para giveaways de codigos, formularios dinamicos e bolao de placar, alem de comandos basicos de diversao, moderacao e eventos de ciclo de vida.

## Funcionalidades

### Inicializacao e estrutura

- Carregamento automatico de cogs em `app/cogs`.
- Sincronizacao de Slash Commands no servidor definido por `GUILD_ID` ou globalmente quando `GUILD_ID` nao esta configurado.
- Registro automatico de views persistentes de giveaways e formularios ativos apos reiniciar o bot.
- Registro dinamico dos botoes persistentes do bolao.
- Logs estruturados durante inicializacao, carregamento de cogs, sincronizacao de comandos e eventos importantes.
- Prefixo para comandos tradicionais: `cp!`.

### Diversao

- `/ping`: mostra a latencia atual do bot em milissegundos.

Arquivos existentes como `games.py` e `profile.py` ainda estao como placeholders e nao possuem comandos ativos no momento.

### Moderacao

- `/ban`: bane um membro do servidor.

O comando de banimento valida:

- uso apenas dentro de servidores;
- tentativa de autoban;
- tentativa de banir o proprio bot;
- hierarquia de cargos do usuario executor;
- hierarquia de cargos do bot;
- permissoes do Discord e falhas de API.

Arquivos como `purge.py` e `warnings.py` ainda estao como placeholders e nao possuem comandos ativos no momento.

### Giveaway de codigos

Sistema administrativo para criar, publicar, encerrar e gerenciar eventos de distribuicao de codigos.

Comandos Slash:

- `/giveaway_create`: cria um evento de distribuicao de codigos.
- `/giveaway_publish`: publica a mensagem do evento em um canal com botao de resgate.
- `/giveaway_unpublish`: encerra/despublica o evento e pode apagar a mensagem original.
- `/giveaway_codes`: consulta os codigos ainda disponiveis de um evento.
- `/give_ticket`: adiciona tickets extras de resgate para um usuario.
- `/user_ticket`: consulta os tickets extras restantes de um usuario.
- `/remove_ticket`: remove tickets extras de um usuario.

Comandos prefixados equivalentes:

- `cp!give_ticket <event_id> <usuario> [quantidade]`
- `cp!user_ticket <event_id> <usuario>`
- `cp!remove_ticket <event_id> <usuario> [quantidade]`

Fluxo do giveaway:

1. Um administrador cria o evento com `/giveaway_create`.
2. O administrador publica o evento com `/giveaway_publish`.
3. O bot envia uma mensagem publica com embed e botao **Resgatar codigo**.
4. O usuario clica no botao para receber um codigo de forma privada.
5. O bot registra o resgate para impedir duplicidade, salvo quando o usuario possui tickets extras.
6. Se o codigo tiver premio, o bot anuncia publicamente o vencedor no canal.
7. Opcionalmente, o bot envia DM para o usuario responsavel por notificacoes.
8. O evento pode ser encerrado manualmente ou automaticamente ao expirar.
9. Ao encerrar, o bot publica um resumo final com vencedores e codigos restantes.

Recursos do giveaway:

- geracao de codigos hexadecimais unicos;
- plano de premios em formato compacto ou JSON;
- codigos premiados e nao premiados;
- limite de um resgate gratuito por usuario;
- tickets extras por usuario e por evento;
- consulta de codigos restantes;
- finalizacao automatica por tempo;
- views persistentes para manter botoes funcionando apos restart;
- respostas privadas para operacoes administrativas e resgates.

Formato compacto aceito em `reward_plan`:

```text
Diamantes|100|2;Diamantes|300|1;500|1
```

Formato JSON aceito em `reward_plan`:

```json
[{"reward_name":"Diamantes","reward_amount":100,"reward_quantity":2}]
```

### Formularios dinamicos

Sistema administrativo para criar formularios interativos no Discord e encaminhar respostas para um canal especifico.

Comandos Slash:

- `/form_create`: cria e publica um formulario no canal atual.
- `/form_close`: encerra um formulario existente.
- `/form_list`: lista os formularios ativos.

Fluxo dos formularios:

1. Um administrador cria o formulario com `/form_create`.
2. O bot publica um embed com o botao **Responder**.
3. O usuario clica no botao.
4. Se houver perguntas de selecao, o bot mostra menus privados para escolha.
5. Se houver perguntas curtas, o bot abre um modal.
6. O bot valida e registra a resposta.
7. O bot envia a resposta para o canal configurado.
8. O usuario recebe confirmacao privada.
9. O formulario pode ser encerrado com `/form_close`, desativando o botao publico.

Tipos de pergunta aceitos:

- `curta`: resposta textual em modal.
- `combo`: selecao unica em menu.
- `multipla`: selecao de uma ou mais opcoes em menu.

Formato aceito para `perguntas`:

```text
curta|Qual seu nome?;combo|Cargo desejado|Moderador,Suporte,Eventos;multipla|Horarios disponiveis|Manha,Tarde,Noite
```

Limites atuais:

- ate 5 perguntas curtas;
- ate 4 perguntas de selecao;
- ate 25 opcoes por pergunta de selecao;
- cada usuario pode responder apenas uma vez por formulario.

### Bolao de placar

Sistema de palpites para jogos, com publicacao em canal, coleta de placar por modal e calculo de vencedores por placar exato.

Comandos Slash:

- `/bolao_create`: cria e publica um bolao no canal atual.
- `/bolao_close`: encerra um bolao, recebe o placar final e calcula os vencedores.
- `/bolao_list`: lista os boloes ativos.

Fluxo do bolao:

1. Um administrador cria o bolao com `/bolao_create`.
2. O bot publica um embed com o botao **Enviar Palpite**.
3. O usuario clica no botao e recebe um modal para informar o placar.
4. O bot valida e registra o palpite.
5. O responsavel configurado recebe uma DM com o palpite enviado.
6. Cada usuario pode enviar apenas um palpite por bolao.
7. O administrador encerra o bolao com `/bolao_close`, informando o placar final.
8. O bot desativa o botao publico e publica um resumo com o resultado e vencedores.

Recursos do bolao:

- identificacao por ID do bolao ou ID da mensagem publicada;
- validacao de placares numericos;
- armazenamento de palpites;
- deteccao de palpite duplicado;
- notificacao privada ao responsavel;
- calculo de vencedores por placar exato;
- botoes persistentes via `discord.ui.DynamicItem`.

### Eventos

- Listener `on_ready`: registra nos logs quando o bot conecta e fica operacional.

## Persistencia

O bot usa SQLite para persistir dados locais. Os caminhos sao configuraveis por variaveis de ambiente:

- `GIVEAWAY_DB_PATH`: banco de giveaways, codigos, resgates e tickets extras.
- `BOLAO_DB_PATH`: banco de boloes e palpites.
- `FORM_DB_PATH`: banco de formularios e respostas.

Por padrao, os exemplos usam arquivos dentro de `data/`.

## Estrutura

```text
.
|-- app/
|   |-- cogs/
|   |   |-- betting/      # Bolao
|   |   |-- events/       # Eventos do bot
|   |   |-- forms/        # Formularios dinamicos
|   |   |-- fun/          # Comandos simples de diversao
|   |   |-- giveaway/     # Giveaway de codigos
|   |   |-- moderation/   # Moderacao
|   |   `-- utility/      # Reservado para utilidades
|   |-- core/             # Bot, configuracao e logging
|   |-- models/           # Dataclasses e tipos de dominio
|   |-- repositories/     # Persistencia SQLite
|   |-- services/         # Regras de negocio
|   |-- types/            # Protocolos/tipos compartilhados
|   |-- ui/               # Views, botoes, selects e modals
|   `-- utils/            # Embeds, permissoes e helpers
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
BOLAO_DB_PATH=data/bot.db
FORM_DB_PATH=data/bot.db
ENABLE_MEMBERS_INTENT=false
ENABLE_MESSAGE_CONTENT_INTENT=false
```

Se ativar `ENABLE_MEMBERS_INTENT=true`, habilite tambem o intent `Server Members Intent` no Discord Developer Portal.

Se ativar `ENABLE_MESSAGE_CONTENT_INTENT=true`, habilite tambem o intent `Message Content Intent` no Discord Developer Portal. Esse intent e necessario para comandos prefixados como `cp!give_ticket`, `cp!user_ticket` e `cp!remove_ticket`.

Para sincronizar comandos em um servidor de testes, confirme que `GUILD_ID` aponta para um servidor onde o bot esta presente e que o convite usou o escopo `applications.commands`.

## Executando localmente

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
