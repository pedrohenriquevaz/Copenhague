# Projeto Copenhague - Evolucao de Economia, Atividade e Loja

Este documento substitui o prompt generico original por uma especificacao
adaptada ao bot atual. A prioridade e escalar a arquitetura existente em
`app/`, sem criar uma segunda estrutura paralela e sem sobrescrever os
sistemas ja implementados.

## 1. Objetivo

Adicionar ao bot Copenhague um sistema de economia virtual por servidor, com:

- carteira de pontos por usuario e guild;
- conversao sob demanda de atividade em pontos;
- pontos concedidos/removidos por administradores;
- historico de transacoes;
- loja de recompensas;
- compras com validacao de saldo, estoque e permissao;
- auditoria administrativa;
- paineis interativos com embeds, botoes, selects e modals.

O desenvolvimento deve preservar os sistemas atuais:

- Giveaway de codigos;
- Formularios dinamicos;
- Bolao de placar;
- Moderacao basica;
- Comandos de diversao;
- carregamento automatico de cogs;
- persistencia SQLite via repositories.

## 2. Estado Atual do Projeto

A estrutura real do projeto hoje e:

```text
.
|-- app/
|   |-- cogs/
|   |   |-- betting/      # Bolao
|   |   |-- events/       # Eventos de ciclo de vida
|   |   |-- forms/        # Formularios dinamicos
|   |   |-- fun/          # Ping e placeholders
|   |   |-- giveaway/     # Giveaway de codigos
|   |   |-- moderation/   # Ban e placeholders
|   |   `-- utility/      # Reservado
|   |-- core/             # Bot, config e logging
|   |-- models/           # Dataclasses de dominio
|   |-- repositories/     # Persistencia SQLite
|   |-- services/         # Regras de negocio
|   |-- types/            # Protocolos/tipos compartilhados
|   |-- ui/               # Views, botoes, selects e modals
|   `-- utils/            # Embeds, permissoes e helpers
|-- tests/
|-- bot.py
|-- README.md
|-- pyproject.toml
|-- requirements.txt
`-- requirements-dev.txt
```

O bot ja segue uma separacao saudavel:

- Cogs recebem interacoes do Discord.
- Services concentram regra de negocio.
- Repositories concentram persistencia.
- Models usam dataclasses e enums de dominio.
- UI concentra views, buttons, selects e modals.
- `DiscordBot` instancia repositories e services em `app/core/bot.py`.

## 3. Decisoes de Compatibilidade

Estas decisoes sao obrigatorias para evitar retrabalho e sobreposicao.

### 3.1. Nao criar uma nova raiz `bot/`

O prompt original sugeria uma arvore `bot/`. Este projeto ja usa `app/`.
Todas as novas funcionalidades devem ser adicionadas dentro de `app/`.

### 3.2. Nao trocar a persistencia atual

O prompt original sugeria PostgreSQL, `asyncpg` e migrations. Para este
projeto, a primeira versao da economia deve manter o padrao atual:

- SQLite;
- repositories dedicados;
- schema criado/atualizado no proprio repository;
- chamadas bloqueantes isoladas com `asyncio.to_thread`;
- locks e transacoes nas operacoes criticas.

PostgreSQL, migrations formais ou ORM ficam como evolucao futura, nao como
pre-requisito desta fase.

### 3.3. Nao misturar SQL em Cogs

Comandos novos devem chamar services. Services devem chamar repositories.
Nenhum comando deve abrir conexao SQLite diretamente.

### 3.4. Nao sobrescrever funcionalidades existentes

Giveaway, Formularios e Bolao continuam independentes. A economia pode se
integrar a eles no futuro, mas a primeira implementacao nao deve alterar seus
contratos publicos.

### 3.5. Slash Commands primeiro

Os novos comandos devem ser Slash Commands. Comandos prefixados so devem ser
criados quando houver uma razao operacional clara.

## 4. Arquitetura Alvo Incremental

Adicionar novos arquivos sem reorganizar os existentes:

```text
app/
  cogs/
    economy/
      __init__.py
      economy.py              # /saldo, /perfil, /historico, /ranking
      admin.py                # /give_points, /remove_points, configs
      activity.py             # /converter_atividade, setup painel
      shop.py                 # /loja e comandos administrativos da loja
  models/
    economy.py                # Wallet, Transaction, ActivityCursor
    activity.py               # ActivityStats, VoiceSession, MessageStats
    shop.py                   # RewardItem, Purchase, RewardCode
    audit.py                  # AdminAuditLog
    guild_settings.py         # Configuracoes por guild
  repositories/
    economy_repository.py
    activity_repository.py
    shop_repository.py
    audit_repository.py
    guild_settings_repository.py
  services/
    economy_service.py        # carteira, saldo, transacoes
    activity_service.py       # conversao sob demanda
    shop_service.py           # compra e entrega
    audit_service.py          # auditoria administrativa
    economy_config_service.py
  providers/
    __init__.py
    stat_provider.py          # Protocol/base de providers
    native_activity_provider.py
    statbot_provider.py       # fase futura
  ui/
    economy_panel.py
    shop_panel.py
    shop_modals.py
    pagination.py             # se reutilizavel
```

Observacao: `app/providers/` e uma extensao nova e pequena. Ela existe para
separar fonte de estatisticas da regra de economia. Se o projeto preferir
menos pastas, esses providers podem morar em `app/services/`, mas devem manter
interfaces claras.

## 5. Responsabilidades por Camada

### Cogs

Responsabilidades:

- validar contexto basico do Discord;
- deferir resposta quando a acao puder demorar;
- chamar services;
- montar feedback usando embeds/views;
- tratar erros conhecidos com resposta ephemeral.

Nao devem:

- conter SQL;
- calcular saldo manualmente;
- manipular estoque diretamente;
- conter regras antifraude complexas.

### Services

Responsabilidades:

- aplicar regras de negocio;
- validar valores;
- orquestrar repositories;
- garantir transacoes criticas;
- produzir DTOs/resultados para os cogs.

### Repositories

Responsabilidades:

- criar/atualizar schema SQLite;
- executar queries;
- manter locks por banco;
- usar `BEGIN IMMEDIATE` em operacoes criticas;
- retornar models/dataclasses de dominio.

### Models

Responsabilidades:

- representar dados de dominio;
- expor enums de status/tipo;
- manter dataclasses com `slots=True` quando fizer sentido.

### UI

Responsabilidades:

- views persistentes;
- buttons;
- select menus;
- modals;
- confirmacoes de compra;
- paineis publicos.

## 6. Economia - Escopo Funcional

### 6.1. Carteira

Cada usuario tera uma carteira por guild.

Campos minimos:

```text
guild_id
user_id
balance
total_earned
total_spent
created_at
updated_at
```

Regras:

- saldo nunca pode ficar negativo;
- toda mudanca de saldo gera transacao;
- transacoes sao imutaveis;
- operacoes criticas usam lock/transacao;
- comandos administrativos exigem motivo e auditoria.

### 6.2. Transacoes

Tipos iniciais:

```text
ACTIVITY_CONVERSION
ADMIN_GIVE
ADMIN_REMOVE
SHOP_PURCHASE
REFUND
SYSTEM_ADJUSTMENT
```

Campos minimos:

```text
id
guild_id
user_id
actor_id
type
amount
balance_before
balance_after
reason
metadata_json
created_at
```

### 6.3. Comandos Publicos

```text
/saldo
/perfil
/converter_atividade
/historico
/ranking
```

### 6.4. Comandos Administrativos

```text
/give_points
/remove_points
/economy_config
/economy_status
/economy_panel_setup
```

`/give_points` deve:

- funcionar apenas em guild;
- recusar bots;
- exigir permissao administrativa ou cargo configurado;
- exigir quantidade positiva;
- exigir motivo;
- respeitar limite maximo por uso;
- registrar transacao;
- registrar auditoria;
- responder ao admin em ephemeral.

`/remove_points` deve seguir as mesmas regras, com permissao mais restrita.

## 7. Atividade e Conversao Sob Demanda

A economia nao deve converter pontos em tempo real.

Fluxo correto:

1. O bot coleta ou consulta atividade acumulada.
2. O usuario usa `/converter_atividade` ou botao do painel.
3. O service busca estatisticas atuais.
4. O service busca cursor de ultima conversao.
5. Calcula apenas o delta.
6. Converte delta em pontos.
7. Atualiza carteira, transacao e cursor em operacao atomica.
8. Responde com resumo ephemeral.

### 7.1. Cursor de Conversao

Campos minimos:

```text
guild_id
user_id
claimed_voice_seconds
claimed_messages
last_claimed_at
last_source
```

### 7.2. Provider Nativo

Implementar primeiro o provider nativo.

Ele deve contar:

- mensagens por guild/canal/usuario;
- sessoes de voz com inicio/fim/duracao.

Regras:

- nao armazenar conteudo de mensagens;
- ignorar bots;
- ignorar DMs;
- ignorar canais configurados;
- nao contar canal AFK quando configurado;
- nao contar sessoes menores que o minimo;
- ao iniciar o bot, lidar com sessoes abertas de forma segura.

### 7.3. Statbot

`StatbotProvider` fica como fase posterior.

A interface deve existir desde cedo, mas a implementacao pode retornar erro
amigavel enquanto nao houver API key/configuracao.

## 8. Loja - Escopo Funcional

### 8.1. Recompensas

Campos minimos:

```text
id
guild_id
name
description
type
price
stock_quantity
stock_mode
max_per_user
role_id
delivery_message
is_active
created_at
updated_at
created_by
deleted_at
```

Tipos iniciais:

```text
ROLE
CUSTOM_TEXT
MANUAL_REWARD
DIGITAL_CODE
VIP_ACCESS
EVENT_ENTRY
```

### 8.2. Comandos de Usuario

```text
/loja
```

Interface:

- embed da loja;
- select menu de recompensas;
- botao atualizar;
- botao ver saldo;
- botao minhas compras;
- confirmacao antes de comprar.

### 8.3. Comandos Administrativos

```text
/reward_create
/reward_edit
/reward_delete
/reward_enable
/reward_disable
/reward_stock_add
/reward_stock_set
/reward_list
/reward_info
/shop_panel_setup
```

### 8.4. Compra

A compra deve ser atomica:

1. Verificar item ativo.
2. Verificar estoque.
3. Verificar limite por usuario.
4. Verificar saldo.
5. Debitar saldo.
6. Criar transacao.
7. Baixar estoque.
8. Criar purchase.
9. Entregar ou marcar pendente.
10. Registrar auditoria/log se necessario.

## 9. Guild Settings

Criar configuracao por servidor, sem substituir `app/core/config.py`.

Campos minimos:

```text
guild_id
currency_name
voice_points_per_minute
message_points
activity_provider
economy_channel_id
shop_channel_id
staff_log_channel_id
min_voice_seconds_to_claim
min_messages_to_claim
ignore_afk_channel
ignore_bots
count_voice_when_alone
max_admin_grant_per_use
economy_manager_role_id
created_at
updated_at
```

Configuracoes globais sensiveis continuam em `.env`.
Configuracoes por guild ficam no SQLite.

## 10. Persistencia SQLite Adaptada

Criar novos repositories seguindo o padrao dos existentes:

- `_connect()` configura `row_factory`, `foreign_keys`, `busy_timeout`,
  `synchronous=NORMAL` e `temp_store=MEMORY`;
- `_initialize_schema()` cria tabelas e indices;
- metodos publicos async delegam para sync com `asyncio.to_thread`;
- operacoes criticas usam `threading.RLock` e `BEGIN IMMEDIATE`.

Indices recomendados:

```sql
CREATE INDEX IF NOT EXISTS idx_economy_transactions_guild_user_created
ON economy_transactions(guild_id, user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_reward_purchases_guild_user_created
ON reward_purchases(guild_id, user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_native_voice_sessions_guild_user
ON native_voice_sessions(guild_id, user_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_native_message_stats_guild_user
ON native_message_stats(guild_id, user_id);

CREATE INDEX IF NOT EXISTS idx_reward_items_guild_active
ON reward_items(guild_id, is_active, price);
```

## 11. Seguranca e Antifraude

### Mensagens

Nao contar:

- bots;
- DMs;
- canais ignorados;
- categorias ignoradas;
- mensagens sem contexto de guild.

Configuracoes futuras:

```text
min_message_length
message_cooldown_seconds
ignored_text_channels
ignored_categories
```

Como o bot nao deve armazenar conteudo, antifraude baseado em texto repetido
fica para fase futura e deve ser pensado com cuidado de privacidade.

### Voz

Nao contar:

- canal AFK quando configurado;
- bots;
- canais ignorados;
- sessoes menores que o minimo;
- usuario sozinho quando configurado.

### Operacoes Criticas

Proteger contra:

- duplo clique;
- conversoes simultaneas;
- compra simultanea do ultimo estoque;
- saldo negativo;
- manipulacao de interacao antiga;
- compra de item inativo.

## 12. Permissoes

Usar helpers em `app/utils/permissions.py` e/ou `app/utils/checks.py`,
expandindo o que ja existe.

Niveis sugeridos:

```text
USER
STAFF
ECONOMY_MANAGER
ADMIN
OWNER
```

Toda validacao sensivel deve acontecer no backend do comando/service, nao
apenas via `default_permissions` do Discord.

## 13. Experiencia no Discord

Padroes:

- respostas privadas em saldo, historico, conversao e compra;
- paineis publicos apenas para economia e loja;
- embeds curtos e claros;
- selects para escolher recompensa;
- modals quando o usuario precisar informar texto;
- paginacao para historico, ranking e listas administrativas.

## 14. Logs e Auditoria

Eventos auditaveis:

- pontos concedidos;
- pontos removidos;
- conversao de atividade;
- compra de recompensa;
- falha de entrega;
- criacao/edicao/desativacao de recompensa;
- alteracao de configuracao;
- tentativa sem permissao.

Logs tecnicos vao para o logger Python. Logs de staff podem ir para canal
configurado por guild.

## 15. Ordem de Implementacao Adaptada

### Etapa 1 - Base da Economia

- Criar models de economia.
- Criar `economy_repository.py`.
- Criar `economy_service.py`.
- Criar `/saldo`.
- Criar testes de wallet/transacao.

### Etapa 2 - Admin e Auditoria

- Criar `audit_repository.py` e `audit_service.py`.
- Criar `/give_points`.
- Criar `/remove_points`.
- Registrar transacoes e auditoria.

### Etapa 3 - Atividade Nativa

- Criar `activity_repository.py`.
- Criar models de atividade.
- Criar provider nativo.
- Rastrear mensagens sem armazenar conteudo.
- Rastrear sessoes de voz.
- Criar cursor de conversao.

### Etapa 4 - Conversao

- Criar `activity_service.py`.
- Criar `/converter_atividade`.
- Criar painel de economia.
- Garantir idempotencia/transacao.
- Criar testes de delta e dupla conversao.

### Etapa 5 - Loja Basica

- Criar models/repository/service de shop.
- Criar CRUD administrativo de rewards.
- Criar `/loja`.
- Criar select menu e confirmacao de compra.
- Implementar `MANUAL_REWARD` primeiro.

### Etapa 6 - Entregas Automaticas

- Implementar `ROLE`.
- Implementar `DIGITAL_CODE`.
- Implementar `CUSTOM_TEXT`.
- Implementar `VIP_ACCESS` com expiracao.

### Etapa 7 - Polimento

- Ranking.
- Historico paginado.
- Painel persistente da loja.
- Logs de staff em embed.
- Melhorias de UX.

### Etapa 8 - Statbot

- Criar `StatbotProvider`.
- Configurar API key segura.
- Implementar cache/rate limit.
- Criar fallback para provider nativo.

## 16. Criterios de Aceite

Primeira versao completa:

- usuario ve saldo;
- admin concede pontos;
- admin remove pontos;
- transacoes sao registradas;
- auditoria e registrada;
- usuario converte mensagens em pontos;
- usuario converte tempo de voz em pontos;
- usuario nao converte a mesma atividade duas vezes;
- admin cria recompensa;
- usuario abre loja;
- usuario compra com saldo suficiente;
- usuario nao compra sem saldo;
- usuario nao compra item sem estoque;
- compra baixa estoque;
- compra gera transacao;
- cogs, services e repositories continuam separados;
- testes passam;
- Ruff e Black passam;
- nenhum conteudo de mensagem e armazenado.

## 17. Qualidade e Testes

Para cada modulo novo, criar testes em `tests/`.

Cobertura minima por comportamento:

- saldo inicial;
- add/remove pontos;
- saldo insuficiente;
- transacao imutavel;
- conversao sem delta;
- conversao com delta;
- conversao duplicada/simultanea;
- compra sem saldo;
- compra com estoque;
- compra esgotada;
- limite por usuario;
- permissao administrativa.

Comandos de verificacao:

```bash
python -m pytest
python -m ruff check .
python -m black --check .
```

## 18. Fora de Escopo Nesta Primeira Evolucao

Nao implementar agora:

- migracao para PostgreSQL;
- ORM;
- sistema formal de migrations;
- reescrita da estrutura `app/`;
- alteracao dos schemas de Giveaway/Formularios/Bolao sem necessidade;
- Statbot completo antes do provider nativo;
- antifraude baseado em conteudo de mensagem;
- integracao obrigatoria da economia com giveaways existentes.

Esses pontos podem virar milestones futuras depois da economia e loja basicas
estarem estaveis.
