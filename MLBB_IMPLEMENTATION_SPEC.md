# Projeto Copenhague

## Especificação Técnica de Integração com a MLBB Public Data API

**Versão do documento:** 1.0  
**Data de verificação:** 16 de julho de 2026  
**Responsável pelo produto:** Pedro  
**Status:** Planejamento pronto para implementação faseada  
**Público-alvo:** Desenvolvimento, revisão técnica, homologação e operação do Bot Copenhague

> Este documento define como integrar dados de Mobile Legends: Bang Bang ao Bot Copenhague, preservando a arquitetura existente, priorizando segurança no vínculo de contas e entregando uma experiência visual coesa no Discord.

---

# Sumário executivo

A integração será construída como um novo domínio `mlbb` dentro da raiz `app/`. Ela não criará uma estrutura paralela, não colocará SQL em Cogs e não alterará contratos públicos dos módulos já existentes.

A primeira entrega será exclusivamente o vínculo seguro entre uma conta do Discord e uma conta do Mobile Legends. O usuário iniciará o processo por um botão em uma embed pública, informará Game ID e Zone ID em um modal, receberá no correio do jogo um código temporário e concluirá o vínculo informando esse código em uma interação ephemeral.

Depois da autenticação, o bot poderá oferecer:

- cartão principal do jogador;
- rank atual e maior rank histórico;
- total de partidas, vitórias e Win Rate;
- quantidade de MVPs, maior sequência de vitórias e tempo jogado;
- destaques pessoais de desempenho;
- histórico paginado de partidas;
- detalhes de uma partida;
- heróis mais utilizados por temporada;
- Win Rate, partidas, vitórias, score e MMR por herói;
- cards visuais gerados com Pillow em uma fase posterior.

A integração utilizará diretamente `aiohttp`, que já faz parte do projeto, por meio de um client isolado em `app/integrations/`. Não será necessário adotar o SDK OpenMLBB na primeira versão. Essa escolha mantém o fluxo totalmente assíncrono, permite controle explícito de timeout, retry, telemetria e contratos, e reduz o acoplamento com uma API comunitária que pode mudar.

Tokens JWT nunca serão apresentados ao usuário, registrados em logs ou salvos em texto puro. O JWT será criptografado com uma chave mantida em variável de ambiente. O código de verificação não será persistido. Uma conta vinculada poderá ser marcada como `REAUTH_REQUIRED` quando a API rejeitar o token.

---

# 1. Contexto e base analisada

A especificação foi construída considerando os arquivos fornecidos do projeto:

- `project(1).md`;
- `pyproject(1).toml`;
- `requirements.txt`;
- `requirements-dev(1).txt`;
- `Dockerfile(1)`.

## 1.1. Arquitetura atual relevante

O projeto segue a separação:

- **Cogs:** recebem interações do Discord;
- **Services:** concentram regras de negócio;
- **Repositories:** concentram persistência PostgreSQL;
- **Models:** representam o domínio com dataclasses e enums;
- **Integrations:** concentram HTTP, timeout, erros e acesso externo;
- **UI:** concentra views, buttons, selects e modals;
- **Utils:** concentra helpers de apresentação, permissões e formatação;
- **AppContainer:** compõe repositories, services e integrações.

A nova funcionalidade deve respeitar esse desenho sem criar uma raiz `bot/` e sem reorganizar módulos existentes.

## 1.2. Stack considerada

- Python 3.11 ou superior;
- imagem Docker baseada em Python 3.12 slim;
- `discord.py >= 2.4`;
- `aiohttp >= 3.10`;
- `Pillow >= 10.4`;
- PostgreSQL com `psycopg[binary,pool]`;
- `python-dotenv`;
- pytest, pytest-asyncio, Ruff e Black.

## 1.3. Decisões obrigatórias de compatibilidade

1. Todo código novo deve ficar em `app/`.
2. Slash Commands e componentes de interação são a interface principal.
3. Cogs não executam SQL nem chamam a API diretamente.
4. Services não conhecem detalhes do Discord além dos identificadores necessários.
5. Repositories são a única camada que persiste vínculos e estados.
6. O client HTTP fica em `app/integrations/mlbb/`.
7. O `AppContainer` deve criar e compartilhar o client, repository e services.
8. A primeira versão não deve alterar Giveaway, Economia, Loja, Bolão, Cassino, Formulários ou Moderação.
9. Em PostgreSQL, operações concorrentes devem usar transações, constraints e, quando necessário, `SELECT ... FOR UPDATE`; não utilizar `BEGIN IMMEDIATE`, que é uma construção associada ao SQLite.

---

# 2. Provedor externo e contrato disponível

## 2.1. Provedor selecionado

O provedor proposto é a **MLBB Public Data API**, mantida pela comunidade RoneAI/ridwaanhall. Ela não é uma API oficial da Moonton. A integração deve ser tratada como dependência externa não controlada pelo projeto.

Bases divulgadas pelo projeto:

- `https://mlbb.rone.dev/api` para uso padrão;
- `https://openmlbb.fastapicloud.dev/api` como alternativa recomendada pelo mantenedor para volume maior.

A URL ativa deve ser configurável em `.env`, nunca espalhada pelo código.

## 2.2. Endpoints usados no escopo

| Finalidade | Método e endpoint | Autenticação |
|---|---|---|
| Enviar código no jogo | `POST /api/user/auth/send-vc` | Não |
| Trocar código por sessão | `POST /api/user/auth/login` | Não |
| Encerrar sessão externa | `POST /api/user/auth/logout` | Bearer JWT |
| Obter perfil | `GET /api/user/info?lang=pt` | Bearer JWT |
| Obter estatísticas gerais | `GET /api/user/stats?lang=pt` | Bearer JWT |
| Listar temporadas | `GET /api/user/season?lang=pt` | Bearer JWT |
| Listar partidas | `GET /api/user/matches` | Bearer JWT |
| Detalhar partida | `GET /api/user/matches/{match_id}` | Bearer JWT |
| Heróis frequentes | `GET /api/user/heroes/frequent` | Bearer JWT |
| Partidas filtradas por herói | `GET /api/user/matches/hero/{hero_identifier}` | Bearer JWT |

Os endpoints de privacidade do jogo existem, porém ficam deliberadamente fora do escopo. O bot não deve modificar configurações da conta do jogador sem uma necessidade futura explícita.

## 2.3. Fluxo de autenticação do provedor

1. Enviar `role_id` e `zone_id` para `send-vc`.
2. O jogador recebe um código no correio interno do jogo.
3. O código informado é enviado com `role_id` e `zone_id` para `login`.
4. A resposta de sucesso contém `jwt`, `token`, `roleid`, `zoneid` e timestamp.
5. Os endpoints privados usam `Authorization: Bearer <jwt>`.
6. Segundo a documentação do provedor, o código de verificação vale cinco minutos.

O projeto armazenará somente o JWT necessário. O campo adicional `token` retornado pelo login não será persistido na primeira versão, pois a documentação indica o JWT como credencial dos endpoints e do logout.

## 2.4. Dados úteis confirmados

### Perfil

- `avatar`;
- `name`;
- `level`;
- `rank_level`;
- `history_rank_level`;
- `reg_country`;
- `roleId`;
- `zoneId`.

### Estatísticas gerais

- `wc`: vitórias;
- `tc`: partidas;
- `as`: score médio, normalmente formatado como `as / 100`;
- `gt`: tempo total jogado em horas;
- `mvpc`: MVPs;
- `wsc`: maior sequência de vitórias;
- destaques de maior número de kills, assistências, dano, dano recebido, ouro e score;
- `sids`: temporadas disponíveis.

### Histórico

- temporada;
- identificador da batalha;
- herói;
- kills, mortes e assistências;
- lane;
- score;
- indicador de MVP;
- vitória ou derrota;
- timestamp;
- metadados e imagens do herói;
- paginação por cursor.

### Heróis frequentes

- partidas e vitórias com o herói;
- Win Rate derivado;
- score médio;
- rating;
- power score/MMR;
- imagens e nome do herói;
- paginação por cursor.

## 2.5. Cálculos derivados

```python
win_rate = round((wins / total_matches) * 100, 2) if total_matches else 0.0

hero_win_rate = (
    round((hero_wins / hero_matches) * 100, 2)
    if hero_matches
    else 0.0
)

average_score = round(raw_average_score / 100, 2)
match_score = round(raw_match_score / 100, 2)
```

Nunca dividir por zero. Campos ausentes ou `null` devem gerar apresentação neutra, como `Não disponível`, e não exceção para o usuário.

## 2.6. Risco de evolução do contrato

A API é comunitária. A versão indicada no OpenAPI e a versão da release do repositório podem não estar sincronizadas. Por isso:

- nenhuma resposta será consumida como dicionário solto dentro de Cogs;
- haverá DTOs/dataclasses normalizados;
- campos extras serão ignorados;
- campos opcionais serão tolerados;
- mudanças incompatíveis devem gerar erro de integração controlado;
- testes de contrato devem usar fixtures sanitizadas;
- a URL base deve ser configurável;
- o client deve registrar `traceID` quando presente, sem registrar tokens.

---

# 3. Objetivos de produto

## 3.1. Objetivo principal

Permitir que um membro vincule voluntariamente sua conta do Discord à sua conta de Mobile Legends e consulte estatísticas reais no servidor de forma segura, rápida e visualmente agradável.

## 3.2. Princípios de experiência

- vínculo iniciado por botão em painel público;
- dados sensíveis e erros respondidos em ephemeral;
- perfil consultável por Slash Command;
- visual consistente com os demais painéis do bot;
- navegação por botões, selects e paginação;
- nenhuma exposição de JWT, código de verificação ou payload bruto;
- mensagens claras quando a API estiver indisponível;
- reautenticação simples quando a sessão expirar;
- consentimento e controle de visibilidade pelo usuário.

## 3.3. Escopo inicial

- painel de vinculação;
- autenticação por Game ID, Zone ID e código temporário;
- gerenciamento do vínculo;
- perfil resumido;
- estatísticas gerais;
- histórico paginado;
- detalhes de partida;
- heróis frequentes;
- cache curto em memória;
- logs técnicos e métricas operacionais;
- testes unitários e de integração simulada.

## 3.4. Fora do escopo inicial

- coletar login, senha, e-mail ou credenciais da Moonton;
- contornar o código enviado dentro do jogo;
- modificar configurações de privacidade do jogo;
- sincronização periódica em background;
- ranking global de jogadores não vinculados;
- armazenar histórico completo de partidas no PostgreSQL;
- prometer disponibilidade ou exatidão equivalente a uma API oficial;
- integração automática com economia, loja ou cassino;
- consulta de qualquer jogador apenas por ID sem consentimento/vínculo;
- múltiplas contas ativas para o mesmo membro na mesma guild na versão inicial.

---

# 4. Jornadas do usuário

## 4.1. Publicação do painel

Um administrador executa:

```text
/mlbb painel_publicar canal:#mobile-legends
```

O bot publica uma embed persistente com:

- título: `Mobile Legends — Vincule sua conta`;
- breve explicação do processo;
- aviso de que o código chega no correio interno do jogo;
- botão `Vincular conta`;
- botão `Gerenciar vínculo`;
- atribuição discreta ao provedor de dados.

## 4.2. Início do vínculo

Ao clicar em `Vincular conta`:

1. o bot valida guild e usuário;
2. verifica cooldown e vínculo existente;
3. abre modal com `Game ID` e `Zone ID/Área`;
4. normaliza apenas dígitos;
5. cria ou substitui uma tentativa pendente;
6. chama `send-vc`;
7. responde em ephemeral informando que o código foi enviado;
8. apresenta botão `Informar código` e alternativa `/mlbb confirmar`.

## 4.3. Confirmação

Ao informar o código:

1. o bot encontra a tentativa pendente do mesmo usuário e guild;
2. verifica expiração local;
3. verifica limite de tentativas;
4. chama `login`;
5. valida `code == 0` e presença do JWT;
6. consulta imediatamente `/user/info` para confirmar identidade;
7. criptografa o JWT;
8. grava o vínculo em transação;
9. invalida a tentativa pendente;
10. mostra cartão de sucesso com nome e avatar;
11. oferece `Ver perfil` e `Configurar privacidade no bot`.

## 4.4. Consulta do próprio perfil

```text
/mlbb perfil
```

O bot apresenta um cartão com:

- avatar e nome;
- nível;
- rank atual;
- maior rank histórico;
- partidas;
- vitórias;
- Win Rate;
- MVPs;
- país, quando disponível;
- data da última atualização;
- botões `Conquistas`, `Histórico`, `Heróis` e `Atualizar`.

## 4.5. Consulta de outro membro

```text
/mlbb perfil membro:@usuario
```

A consulta é permitida apenas quando:

- o membro possui vínculo ativo naquela guild;
- a visibilidade está como `GUILD` ou `PUBLIC`;
- o solicitante está no mesmo servidor;
- o vínculo não está marcado para reautenticação.

O default recomendado é `GUILD`.

## 4.6. Histórico de partidas

```text
/mlbb historico temporada:atual
```

A resposta usa paginação. Cada página deve exibir de uma a cinco partidas, conforme a densidade final do layout. Cada item mostra:

- Vitória ou Derrota;
- herói;
- K/D/A;
- lane;
- score;
- MVP;
- data relativa;
- botão ou select para `Ver detalhes`.

## 4.7. Desvinculação

Em `Gerenciar vínculo` ou `/mlbb conta`:

1. o usuário escolhe `Desvincular`;
2. o bot pede confirmação;
3. tenta chamar logout no provedor;
4. independentemente da resposta externa, remove ou revoga localmente o JWT;
5. preserva apenas auditoria mínima sem credenciais;
6. confirma a remoção em ephemeral.

---

# 5. Arquitetura alvo

## 5.1. Estrutura incremental

```text
app/
  cogs/
    mlbb/
      __init__.py
      account.py                 # /mlbb conta, vincular, confirmar, desvincular
      profile.py                 # /mlbb perfil, estatisticas, conquistas
      matches.py                 # /mlbb historico, detalhes e filtros
      heroes.py                  # /mlbb herois
      admin.py                   # /mlbb painel_publicar, status e configuracoes
  integrations/
    mlbb/
      __init__.py
      client.py                  # aiohttp, endpoints e auth header
      dto.py                     # DTOs normalizados da resposta externa
      errors.py                  # hierarquia de erros do provedor
      mappers.py                 # payload externo -> DTO
      rank_resolver.py           # tradução segura de rank, com fallback
  models/
    mlbb.py                      # vínculos, estados, visibilidade e tentativas
  repositories/
    mlbb_repository.py           # PostgreSQL
  services/
    mlbb_auth_service.py         # fluxo de vínculo, reauth e unlink
    mlbb_profile_service.py      # perfil, stats, cálculo e visibilidade
    mlbb_match_service.py        # temporadas, histórico, detalhes
    mlbb_hero_service.py         # heróis frequentes e cálculos
    mlbb_cache_service.py        # TTL cache em memória
  ui/
    mlbb_panel.py                # view persistente do painel
    mlbb_modals.py               # ID/área e código
    mlbb_profile_view.py         # navegação do perfil
    mlbb_match_view.py           # paginação e detalhes
    mlbb_hero_view.py            # paginação de heróis
  utils/
    mlbb_formatters.py           # duração, WR, KDA, lanes e datas
    mlbb_cards.py                # fase visual com Pillow
  core/
    container.py                 # composição dos novos componentes
  migrations/
    ...                          # seguir o mecanismo real já usado pelo projeto

tests/
  integrations/
    test_mlbb_client.py
    test_mlbb_mappers.py
  repositories/
    test_mlbb_repository.py
  services/
    test_mlbb_auth_service.py
    test_mlbb_profile_service.py
    test_mlbb_match_service.py
    test_mlbb_hero_service.py
  cogs/
    test_mlbb_interactions.py
  fixtures/
    mlbb/
      send_vc_success.json
      login_success.json
      user_info_success.json
      user_stats_success.json
      seasons_success.json
      matches_success.json
      match_details_success.json
      heroes_frequent_success.json
```

Adapte o caminho de migrations ao mecanismo real encontrado no repositório. Não crie um segundo sistema de migrations.

## 5.2. Responsabilidades

### Cogs

- definem grupos e Slash Commands;
- validam se a interação ocorre em guild;
- usam `defer` quando necessário;
- chamam services;
- transformam resultados de domínio em embeds/views;
- respondem erros conhecidos em português;
- não acessam repository, token ou `aiohttp` diretamente.

### UI

- implementa botões persistentes;
- abre modals;
- controla quem pode interagir com uma view ephemeral;
- mantém paginação de histórico e heróis;
- não contém regra de autenticação ou persistência.

### Services

- valida estados e regras de negócio;
- controla cooldown e tentativas;
- garante que o usuário só conclua a própria tentativa;
- orquestra client e repository;
- calcula Win Rate e campos derivados;
- aplica visibilidade;
- traduz falhas técnicas em erros de domínio;
- nunca retorna JWT para Cogs.

### Repository

- persiste tentativa, vínculo, visibilidade e estado;
- usa transações PostgreSQL;
- implementa upsert e constraints;
- não realiza chamada HTTP;
- retorna models/dataclasses.

### Integration client

- cria requests HTTP;
- controla headers, timeout, retry e serialização;
- valida HTTP status e campo `code`;
- converte payload em DTO;
- não conhece guild ou interação Discord;
- não persiste dados.

### AppContainer

- compartilha uma única `aiohttp.ClientSession` ou a infraestrutura HTTP já existente;
- instancia `MlbbClient`;
- instancia repository e services;
- injeta services nos Cogs;
- fecha recursos na finalização do bot.

## 5.3. Decisão: integração direta com aiohttp

Usar `aiohttp` diretamente é a opção recomendada porque:

- já está instalado;
- combina com a natureza assíncrona do bot;
- evita adicionar um wrapper desnecessário;
- oferece controle sobre timeout e retry;
- facilita mocks com servidor HTTP fake;
- mantém o provedor atrás de uma interface própria;
- permite trocar a URL ou o provedor sem alterar Cogs e services.

O SDK pode ser reavaliado no futuro, mas não deve ser a base arquitetural.

---

# 6. Modelo de domínio

## 6.1. Enums

```python
class MlbbLinkStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"
    REVOKED = "REVOKED"


class MlbbProfileVisibility(StrEnum):
    PRIVATE = "PRIVATE"
    GUILD = "GUILD"
    PUBLIC = "PUBLIC"


class MlbbAuthAttemptStatus(StrEnum):
    CREATED = "CREATED"
    CODE_SENT = "CODE_SENT"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
```

`PUBLIC` pode ser reservado para uso futuro fora da guild. Na primeira versão, seu comportamento pode ser equivalente a `GUILD`.

## 6.2. Dataclasses principais

```python
@dataclass(slots=True, frozen=True)
class MlbbAccountLink:
    guild_id: int
    discord_user_id: int
    role_id: int
    zone_id: int
    player_name: str
    avatar_url: str | None
    country_code: str | None
    encrypted_jwt: str
    status: MlbbLinkStatus
    visibility: MlbbProfileVisibility
    verified_at: datetime
    last_validated_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class MlbbAuthAttempt:
    id: UUID
    guild_id: int
    discord_user_id: int
    role_id: int
    zone_id: int
    status: MlbbAuthAttemptStatus
    attempts: int
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
```

O código de verificação não aparece na dataclass persistida.

## 6.3. DTOs normalizados

```python
@dataclass(slots=True, frozen=True)
class MlbbPlayerProfile:
    role_id: int
    zone_id: int
    name: str
    avatar_url: str | None
    level: int | None
    current_rank_code: int | None
    highest_rank_code: int | None
    country_code: str | None


@dataclass(slots=True, frozen=True)
class MlbbPlayerStats:
    wins: int
    matches: int
    win_rate: float
    average_score: float | None
    game_time_hours: float | None
    mvp_count: int
    longest_win_streak: int
    highlights: tuple["MlbbStatHighlight", ...]
    season_ids: tuple[int, ...]
```

Normalizar nomes reduz a propagação de abreviações como `wc`, `tc` e `mvpc` pelo projeto.

---

# 7. Persistência PostgreSQL

## 7.1. Tabela de tentativas

```sql
CREATE TABLE IF NOT EXISTS mlbb_auth_attempts (
    id UUID PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    discord_user_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    zone_id INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempts SMALLINT NOT NULL DEFAULT 0,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (role_id > 0),
    CHECK (zone_id > 0),
    CHECK (attempts >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mlbb_open_attempt_user_guild
ON mlbb_auth_attempts(guild_id, discord_user_id)
WHERE status IN ('CREATED', 'CODE_SENT');

CREATE INDEX IF NOT EXISTS idx_mlbb_auth_attempts_expiry
ON mlbb_auth_attempts(expires_at)
WHERE status IN ('CREATED', 'CODE_SENT');
```

## 7.2. Tabela de vínculos

```sql
CREATE TABLE IF NOT EXISTS mlbb_account_links (
    guild_id BIGINT NOT NULL,
    discord_user_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    zone_id INTEGER NOT NULL,
    player_name TEXT NOT NULL,
    avatar_url TEXT,
    country_code VARCHAR(8),
    encrypted_jwt TEXT NOT NULL,
    status VARCHAR(32) NOT NULL,
    visibility VARCHAR(16) NOT NULL DEFAULT 'GUILD',
    verified_at TIMESTAMPTZ NOT NULL,
    last_validated_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id, discord_user_id),
    UNIQUE (guild_id, role_id, zone_id),
    CHECK (role_id > 0),
    CHECK (zone_id > 0)
);

CREATE INDEX IF NOT EXISTS idx_mlbb_links_game_account
ON mlbb_account_links(role_id, zone_id);

CREATE INDEX IF NOT EXISTS idx_mlbb_links_status
ON mlbb_account_links(guild_id, status);
```

A constraint `(guild_id, role_id, zone_id)` impede que dois usuários diferentes reivindiquem a mesma conta dentro da mesma guild.

## 7.3. Auditoria mínima

Caso o projeto já possua uma tabela de auditoria genérica, reutilize-a. Caso contrário, criar uma tabela simples:

```sql
CREATE TABLE IF NOT EXISTS mlbb_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    discord_user_id BIGINT NOT NULL,
    action VARCHAR(64) NOT NULL,
    outcome VARCHAR(32) NOT NULL,
    reason_code VARCHAR(64),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Metadados permitidos:

- role ID parcialmente mascarado;
- zone ID;
- status anterior e posterior;
- código interno de erro;
- duração da operação;
- trace ID externo.

Metadados proibidos:

- JWT;
- código de verificação;
- headers de autorização;
- payload completo do login;
- segredo de criptografia.

## 7.4. Transação de conclusão

A conclusão deve ser atômica:

1. selecionar a tentativa aberta para o usuário;
2. bloquear a linha com `FOR UPDATE`;
3. validar status e expiração;
4. gravar/upsert do vínculo;
5. marcar tentativa como `VERIFIED`;
6. registrar auditoria;
7. commit.

A chamada externa de login não deve ocorrer mantendo uma transação longa aberta. Faça a validação local, chame a API e depois abra uma transação curta para persistir o resultado, revalidando o estado antes do commit.

---

# 8. Segurança

## 8.1. Ameaças e controles

| Ameaça | Controle obrigatório |
|---|---|
| Roubo do JWT pelo banco | Criptografia de aplicação com chave em `.env` |
| JWT exposto em log | Filtro/redaction e proibição de payload bruto |
| Usuário confirma tentativa alheia | Busca sempre por guild + Discord user + tentativa aberta |
| Reutilização do código | Código não persistido; tentativa encerrada após sucesso |
| Força bruta no código | Limite de tentativas e cooldown |
| Spam de envio de código | Rate limit por usuário, guild e conta |
| Duplo clique | idempotência, lock e estado persistido |
| Conta vinculada por duas pessoas | unique constraint por conta na guild |
| Token expirado | estado `REAUTH_REQUIRED` e novo fluxo de vínculo |
| API lenta | timeout, defer e mensagem de indisponibilidade |
| Payload alterado | mappers defensivos e testes de contrato |
| Avatar malicioso | usar URL diretamente na embed ou download restrito |
| Funcionário lê token | nenhum comando/admin endpoint retorna credenciais |

## 8.2. Criptografia do JWT

Adicionar dependência madura, por exemplo `cryptography`, e usar Fernet/MultiFernet. Não implementar cifra própria.

Variáveis:

```env
MLBB_API_BASE_URL=https://mlbb.rone.dev/api
MLBB_API_FALLBACK_BASE_URL=https://openmlbb.fastapicloud.dev/api
MLBB_TOKEN_ENCRYPTION_KEY=<chave-fernet>
MLBB_HTTP_TIMEOUT_SECONDS=15
MLBB_CACHE_TTL_SECONDS=120
MLBB_SEND_VC_COOLDOWN_SECONDS=60
MLBB_MAX_CONFIRM_ATTEMPTS=5
MLBB_AUTH_TTL_SECONDS=300
```

A chave não deve entrar no repositório, imagem Docker ou logs.

## 8.3. Rotação de chave

Preparar o serviço de criptografia para receber uma lista ordenada de chaves:

- primeira chave: usada para novas criptografias;
- demais chaves: usadas somente para descriptografar valores antigos;
- ao usar uma chave antiga, o token pode ser recriptografado com a atual.

Essa capacidade pode ser implementada na fase de hardening.

## 8.4. Código de verificação

- não persistir;
- não logar;
- não devolver em mensagens;
- validar formato numérico e tamanho aceito pelo provedor;
- mantê-lo apenas na memória da chamada que executa `login`;
- limpar referências após uso;
- não repetir automaticamente a chamada de login.

## 8.5. Rate limits recomendados

Valores iniciais configuráveis:

- enviar código: 1 por minuto por usuário;
- no máximo 3 envios por 15 minutos por usuário;
- no máximo 5 confirmações por tentativa;
- cooldown de atualização manual de perfil: 30 segundos;
- limite global de concorrência do client: 10 requests;
- histórico: no máximo 20 itens carregados por interação, paginados visualmente.

O rate limit definitivo deve ser ajustado após homologação.

## 8.6. Privacidade no Discord

Cada vínculo possui visibilidade:

- `PRIVATE`: somente o dono vê;
- `GUILD`: membros da mesma guild podem consultar;
- `PUBLIC`: reservado para futuro uso cross-guild.

Defaults:

- `GUILD` para facilitar o recurso comunitário;
- opção clara para mudar para `PRIVATE`;
- nunca mostrar JWT, token ou código;
- ID do jogo pode ser mascarado no cartão;
- exclusão/desvinculação disponível ao dono.

## 8.7. Logs

Exemplos de log seguro:

```text
mlbb.send_vc outcome=success guild_id=... user_id=... zone_id=1234 duration_ms=320
mlbb.login outcome=invalid_code guild_id=... user_id=... attempt=2
mlbb.profile outcome=upstream_timeout guild_id=... user_id=... endpoint=user/info
```

Nunca usar `logger.exception` com objetos de request que contenham headers de autorização sem redaction prévia.

---

# 9. Client HTTP e contratos

## 9.1. Interface sugerida

```python
class MlbbClientProtocol(Protocol):
    async def send_verification_code(
        self,
        *,
        role_id: int,
        zone_id: int,
    ) -> None: ...

    async def login(
        self,
        *,
        role_id: int,
        zone_id: int,
        verification_code: str,
    ) -> MlbbLoginResult: ...

    async def logout(self, *, jwt: str) -> None: ...

    async def get_user_info(self, *, jwt: str) -> MlbbPlayerProfile: ...

    async def get_user_stats(self, *, jwt: str) -> MlbbPlayerStatsRaw: ...

    async def get_seasons(self, *, jwt: str) -> tuple[int, ...]: ...

    async def get_matches(
        self,
        *,
        jwt: str,
        season_id: int,
        limit: int,
        cursor: int | None,
    ) -> MlbbMatchPage: ...

    async def get_match_details(
        self,
        *,
        jwt: str,
        season_id: int,
        match_id: int,
    ) -> MlbbMatchDetails: ...

    async def get_frequent_heroes(
        self,
        *,
        jwt: str,
        season_id: int,
        limit: int,
        cursor: int | None,
    ) -> MlbbHeroPage: ...
```

## 9.2. Headers

```text
Accept: application/json
Content-Type: application/json
Authorization: Bearer <jwt>  # somente endpoints privados
User-Agent: CopenhagueBot/<versao> MLBBIntegration
```

## 9.3. Timeout

Sugestão inicial:

- connect: 5 segundos;
- sock read: 10 segundos;
- total: 15 segundos.

O usuário deve receber mensagem amigável após timeout. Não deixar a interação expirar sem resposta.

## 9.4. Retry

Retry automático somente para operações idempotentes `GET`, nas condições:

- erro transitório de rede;
- HTTP 429 respeitando `Retry-After`;
- HTTP 502, 503 ou 504;
- no máximo duas novas tentativas;
- backoff com jitter.

Não repetir automaticamente:

- `send-vc`;
- `login`;
- `logout`, exceto se houver uma estratégia idempotente explicitamente testada.

## 9.5. Validação de resposta

A resposta pode falhar mesmo com HTTP 200. Validar:

1. status HTTP;
2. JSON válido;
3. campo `code` compatível com sucesso;
4. presença dos campos obrigatórios;
5. tipos básicos;
6. valores semanticamente possíveis.

## 9.6. Hierarquia de erros

```python
class MlbbIntegrationError(Exception): ...
class MlbbUnavailableError(MlbbIntegrationError): ...
class MlbbTimeoutError(MlbbUnavailableError): ...
class MlbbRateLimitedError(MlbbUnavailableError): ...
class MlbbInvalidResponseError(MlbbIntegrationError): ...
class MlbbAuthenticationError(MlbbIntegrationError): ...
class MlbbInvalidVerificationCodeError(MlbbAuthenticationError): ...
class MlbbVerificationExpiredError(MlbbAuthenticationError): ...
class MlbbSessionExpiredError(MlbbAuthenticationError): ...
class MlbbAccountNotFoundError(MlbbIntegrationError): ...
```

Os services convertem esses erros em mensagens de produto; Cogs não interpretam códigos externos.

## 9.7. Failover de base URL

Não alternar automaticamente o host em qualquer erro, pois isso pode duplicar operações de autenticação. Estratégia recomendada:

- base primária configurada;
- fallback somente para GETs idempotentes;
- health state em memória;
- `send-vc` e `login` sempre usam a base escolhida para toda a tentativa;
- persistir `provider_base` na tentativa se houver suporte a múltiplos hosts;
- homologar os dois hosts antes de habilitar fallback.

---

# 10. Serviço de autenticação

## 10.1. `start_link`

Entrada:

- `guild_id`;
- `discord_user_id`;
- `role_id`;
- `zone_id`.

Regras:

1. rejeitar DMs;
2. validar IDs positivos e limites de tamanho;
3. verificar cooldown;
4. verificar se a conta já pertence a outro membro na guild;
5. cancelar tentativa anterior aberta do mesmo membro;
6. criar tentativa com TTL de cinco minutos;
7. chamar `send_verification_code`;
8. marcar como `CODE_SENT`;
9. registrar auditoria;
10. retornar expiração e instruções.

Se o envio falhar, a tentativa deve ser marcada como `FAILED` ou removida, conforme padrão do projeto.

## 10.2. `confirm_link`

Entrada:

- `guild_id`;
- `discord_user_id`;
- `verification_code`.

Regras:

1. carregar tentativa aberta;
2. validar expiração;
3. incrementar tentativas de forma segura;
4. chamar login;
5. consultar perfil com o JWT recebido;
6. confirmar que role/zone retornados correspondem à tentativa;
7. criptografar JWT;
8. gravar vínculo;
9. invalidar tentativa;
10. limpar cache anterior;
11. retornar resumo seguro do jogador.

## 10.3. `unlink`

1. verificar dono;
2. descriptografar JWT somente no service;
3. tentar logout com timeout curto;
4. revogar/remover vínculo local;
5. apagar cache;
6. registrar auditoria sem token;
7. responder sucesso mesmo quando o logout externo falhar, informando apenas que o vínculo local foi removido.

## 10.4. `reauthenticate`

Reutiliza o mesmo fluxo de vínculo, mas preserva configurações do vínculo, como visibilidade. Após sucesso:

- substitui JWT;
- status volta para `ACTIVE`;
- atualiza nome/avatar;
- atualiza `verified_at` e `last_validated_at`.

---

# 11. Comandos e experiência visual

## 11.1. Grupo de comandos

```text
/mlbb conta
/mlbb vincular
/mlbb confirmar
/mlbb desvincular
/mlbb privacidade
/mlbb perfil [membro]
/mlbb conquistas [membro]
/mlbb historico [membro] [temporada]
/mlbb herois [membro] [temporada]
/mlbb partida <id> [temporada]
/mlbb painel_publicar <canal>       # admin
/mlbb status                        # admin
```

O botão continua sendo o fluxo preferencial. `/mlbb vincular` e `/mlbb confirmar` funcionam como alternativa operacional.

## 11.2. Card principal

### Cabeçalho

- avatar como thumbnail;
- nome do jogador;
- indicador `Conta verificada`;
- data de atualização.

### Corpo

```text
Rank atual          Maior rank
Partidas            Vitórias
Win Rate            MVPs
Nível               País
```

### Rodapé

- `Dados fornecidos por MLBB Public Data API`;
- ID mascarado, por exemplo `••••6789 (1234)`;
- aviso quando os dados estiverem em cache.

## 11.3. Rank

A API retorna códigos numéricos. Não inventar um mapeamento. A fase de contrato deve obter exemplos reais e identificar uma fonte confiável para os códigos.

O `rank_resolver` deve:

1. resolver códigos conhecidos;
2. manter a tabela em um único módulo;
3. possuir testes;
4. retornar fallback `Rank não mapeado (código X)`;
5. nunca falhar todo o perfil por código desconhecido.

## 11.4. Conquistas e destaques

A tela pode apresentar:

- maior sequência de vitórias;
- tempo total jogado;
- score médio;
- maior número de kills;
- maior número de assistências;
- maior dano;
- maior dano recebido;
- maior ouro;
- melhor score;
- herói associado a cada destaque.

Uma boa primeira versão usa embed com campos. A versão avançada gera um card horizontal com Pillow.

## 11.5. Histórico

Formato sugerido por partida:

```text
✅ Vitória · Fanny · Jungle
K/D/A: 14/1/11 · Score: 11,80 · MVP: Não
há 2 horas
```

Mapeamento de lanes confirmado pelo contrato:

- 1: EXP;
- 2: Mid;
- 3: Roam;
- 4: Jungle;
- 5: Gold;
- outros: `Lane desconhecida`.

A paginação deve:

- pertencer ao usuário que iniciou a interação;
- expirar após período configurado;
- usar cursor externo sem expô-lo ao usuário;
- desabilitar `Próximo` quando `hasNext` for falso;
- permitir abrir detalhes da partida selecionada.

## 11.6. Detalhe de partida

Exibir:

- resultado;
- duração;
- composição de times, quando retornada;
- heróis e jogadores;
- K/D/A;
- score;
- dano e contribuição;
- itens;
- nível do herói;
- lane/role;
- MVP.

Como o Discord limita campos e tamanho da embed, o detalhamento deve usar:

- paginação por time; ou
- imagem gerada com Pillow; ou
- resumo na embed e select para participantes.

A implementação textual vem antes do card visual.

## 11.7. Heróis frequentes

Cada item exibe:

```text
Fanny
8 partidas · 7 vitórias · WR 87,50%
Score 8,45 · MMR 1460
```

Oferecer filtros por temporada e paginação. O nome e imagem vêm do payload do provedor.

## 11.8. Cards com Pillow

O projeto já possui Pillow. Na fase visual:

- executar renderização em `asyncio.to_thread`;
- limitar dimensões e peso;
- usar fontes disponíveis no container;
- não baixar imagens sem timeout e limite de bytes;
- criar cache de imagens de heróis;
- usar placeholder quando download falhar;
- nunca bloquear o event loop com processamento pesado;
- manter a embed textual como fallback.

---

# 12. Cache, desempenho e resiliência

## 12.1. Cache inicial

Usar cache TTL em memória, por processo:

| Recurso | TTL sugerido |
|---|---:|
| Perfil | 5 minutos |
| Estatísticas | 2 minutos |
| Temporadas | 15 minutos |
| Histórico por cursor | 60 segundos |
| Heróis frequentes | 5 minutos |
| Detalhe de partida | 10 minutos |

O comando `Atualizar` ignora cache apenas quando o cooldown permitir.

## 12.2. Cache key

Nunca usar JWT como chave. Usar:

```text
mlbb:profile:{guild_id}:{discord_user_id}
mlbb:stats:{guild_id}:{discord_user_id}
mlbb:matches:{guild_id}:{discord_user_id}:{season_id}:{cursor}
```

## 12.3. Deduplicação de chamadas

Evitar que vários cliques simultâneos façam a mesma request:

- lock assíncrono por chave;
- double-check do cache após adquirir lock;
- timeout do lock;
- limpeza de locks sem usuários.

## 12.4. Modo degradado

Quando a API estiver indisponível:

- usar cache ainda válido;
- opcionalmente usar cache expirado recente com aviso `Dados podem estar desatualizados`;
- não devolver stack trace;
- não marcar token como expirado por timeout ou 5xx;
- marcar `REAUTH_REQUIRED` somente por erro claro de autenticação.

---

# 13. Roadmap de implementação

## Fase 0 — Descoberta e contrato

### Objetivo

Validar o provedor antes de criar telas ou persistir tokens.

### Entregas

- inventário dos endpoints usados;
- fixtures sanitizadas;
- `MlbbClient` inicial;
- DTOs e mappers;
- erros tipados;
- testes HTTP simulados;
- decisão documentada sobre códigos de rank;
- relatório de campos opcionais e comportamentos de erro.

### Critérios de aceite

- nenhuma chamada ocorre em Cog;
- testes cobrem sucesso, timeout, 429, 5xx, JSON inválido e `code != 0`;
- payloads não carregam tokens em logs;
- `ruff`, `black` e `pytest` passam;
- nenhum token real entra em fixture ou commit.

## Fase 1 — Autenticação e vínculo seguro

### Objetivo

Entregar o painel e o fluxo completo de vínculo, sem comandos de estatísticas.

### Entregas

- migrations;
- models de vínculo/tentativa;
- repository;
- criptografia;
- auth service;
- painel persistente;
- modal ID/Zone;
- modal de código;
- comandos de fallback;
- desvinculação e reautenticação;
- auditoria segura.

### Critérios de aceite

- o código chega no jogo;
- o vínculo só é concluído pelo mesmo usuário;
- JWT é criptografado;
- código não é persistido;
- duplo clique não duplica vínculo;
- uma conta não é vinculada a dois usuários na guild;
- expiração e código inválido têm mensagem clara;
- reiniciar o bot não perde a tentativa persistida dentro do TTL;
- painel persistente volta a funcionar após restart.

## Fase 2 — Perfil e estatísticas gerais

### Objetivo

Disponibilizar o cartão principal e a tela de conquistas.

### Entregas

- profile service;
- cache;
- `/mlbb perfil`;
- `/mlbb conquistas`;
- visibilidade;
- formatadores;
- rank resolver com fallback;
- botões de navegação;
- atualização de nome/avatar do vínculo.

### Critérios de aceite

- Win Rate correto;
- zero partidas não causa erro;
- campos `null` são suportados;
- token expirado muda o status para `REAUTH_REQUIRED`;
- timeout não invalida o vínculo;
- usuário privado não pode ser consultado por terceiros;
- resposta cabe nos limites do Discord.

## Fase 3 — Histórico e detalhe de partidas

### Objetivo

Entregar navegação coesa pelo histórico.

### Entregas

- seasons e match service;
- `/mlbb historico`;
- cursor pagination;
- seleção de temporada;
- detalhe de partida;
- lanes e datas formatadas;
- fallback para respostas incompletas.

### Critérios de aceite

- paginação não repete ou pula cursor;
- view só aceita o usuário autorizado;
- histórico vazio é tratado;
- IDs grandes não perdem precisão;
- `bid_s` é preferido quando fornecido;
- botões desabilitam corretamente;
- detalhe suporta itens ausentes.

## Fase 4 — Heróis e análise avançada

### Objetivo

Mostrar heróis frequentes e filtros úteis.

### Entregas

- hero service;
- `/mlbb herois`;
- Win Rate por herói;
- MMR/power score;
- filtro por temporada;
- partidas filtradas por herói;
- destaque de melhores desempenhos.

### Critérios de aceite

- cálculo correto por herói;
- paginação confiável;
- hero identifier é validado;
- imagens ausentes usam placeholder;
- dados de temporadas antigas são apresentados corretamente.

## Fase 5 — Cards visuais

### Objetivo

Elevar a apresentação visual sem comprometer estabilidade.

### Entregas

- card de perfil com Pillow;
- board de histórico;
- card de detalhe;
- cache de assets;
- placeholders;
- renderização off-thread;
- fallback textual.

### Critérios de aceite

- event loop não é bloqueado;
- imagens cabem no limite do Discord;
- fontes existem no Docker;
- falha de imagem não derruba o comando;
- layout é testado com nomes longos e caracteres especiais.

## Fase 6 — Hardening e operação

### Objetivo

Preparar rollout amplo.

### Entregas

- key rotation;
- métricas e health status;
- rate limit refinado;
- limpeza de tentativas expiradas;
- cache stale-if-error;
- admin status;
- documentação operacional;
- feature flag por guild;
- rollout gradual.

### Critérios de aceite

- nenhum segredo nos logs;
- dashboards mostram taxa de sucesso e latência;
- falha do provedor não afeta outros módulos;
- feature pode ser desligada sem deploy;
- recuperação de token expirado é simples;
- backup e restore são testados.

---

# 14. Testes

## 14.1. Unitários

### Auth service

- início válido;
- ID inválido;
- vínculo existente;
- conta já usada por outro membro;
- cooldown;
- tentativa expirada;
- código inválido;
- máximo de tentativas;
- login válido;
- mismatch de role/zone na resposta;
- criptografia e descriptografia;
- reautenticação;
- desvinculação com logout externo falhando.

### Profile service

- cálculo de WR;
- zero partidas;
- campos ausentes;
- visibilidade;
- token expirado;
- timeout;
- cache hit/miss;
- cache invalidado após reauth.

### Match service

- temporada default;
- cursor inicial;
- cursor seguinte;
- fim da paginação;
- histórico vazio;
- detalhe sem itens;
- timestamps;
- lane desconhecida;
- match ID grande.

### Hero service

- WR por herói;
- zero partidas;
- paginação;
- MMR ausente;
- imagem ausente.

## 14.2. Repository

- upsert de tentativa;
- unicidade por usuário;
- unicidade da conta na guild;
- expiração;
- transição válida de estado;
- concorrência em conclusão;
- update de visibilidade;
- revogação;
- nenhum token aparece em audit metadata.

## 14.3. Integration client

Usar servidor fake ou mocks de `aiohttp`:

- HTTP 200 + `code=0`;
- HTTP 200 + erro externo;
- HTTP 401/403;
- HTTP 429 + Retry-After;
- HTTP 500;
- timeout;
- JSON inválido;
- campo obrigatório ausente;
- campos extras;
- response lenta;
- retry somente em GET.

## 14.4. Interações Discord

- botão abre modal;
- modal aceita somente o autor;
- resposta é ephemeral;
- views persistentes são registradas no startup;
- componentes expiram e desabilitam;
- usuário diferente não controla paginação;
- comando de terceiro respeita privacidade.

## 14.5. Comandos de qualidade

```bash
python -m pytest
python -m ruff check .
python -m black --check .
```

---

# 15. Configuração e dependências

## 15.1. Nova dependência

Adicionar ao `pyproject.toml` e `requirements.txt`:

```text
cryptography>=43.0.0
```

A versão mínima pode ser ajustada ao ambiente real e à política de atualização do projeto.

Não é necessário adicionar `requests`, SDK síncrono ou ORM.

## 15.2. `.env.example`

```env
# MLBB Public Data API
MLBB_ENABLED=false
MLBB_API_BASE_URL=https://mlbb.rone.dev/api
MLBB_API_FALLBACK_BASE_URL=https://openmlbb.fastapicloud.dev/api
MLBB_TOKEN_ENCRYPTION_KEYS=
MLBB_HTTP_TIMEOUT_SECONDS=15
MLBB_CACHE_TTL_SECONDS=120
MLBB_AUTH_TTL_SECONDS=300
MLBB_SEND_VC_COOLDOWN_SECONDS=60
MLBB_MAX_CONFIRM_ATTEMPTS=5
MLBB_MAX_CONCURRENT_REQUESTS=10
MLBB_ALLOW_STALE_CACHE=true
```

`MLBB_TOKEN_ENCRYPTION_KEYS` pode aceitar uma lista separada por vírgula para rotação futura.

## 15.3. Docker

O Dockerfile atual já possui fontes DejaVu e Noto, úteis para cards com Pillow. Confirmar que as famílias escolhidas realmente estão disponíveis no container usando `fc-list` durante a fase visual.

Nenhum segredo deve ser copiado durante build. As variáveis entram apenas em runtime.

---

# 16. Observabilidade e operação

## 16.1. Métricas

- envios de código iniciados;
- envios com sucesso/falha;
- confirmações com sucesso;
- códigos inválidos;
- sessões expiradas;
- vínculos ativos;
- vínculos `REAUTH_REQUIRED`;
- latência por endpoint;
- HTTP 429/5xx;
- cache hit rate;
- renderizações de cards e falhas;
- comandos por guild.

## 16.2. `/mlbb status`

Comando administrativo ephemeral:

```text
Integração: habilitada
Base: mlbb.rone.dev
Saúde: degradada/ok
Latência média: 420 ms
Vínculos ativos na guild: 37
Reautenticação necessária: 2
Tentativas abertas: 1
Erros nas últimas 24h: 5
Cache hit: 73%
```

Não mostrar tokens ou IDs completos.

## 16.3. Feature flag

- `MLBB_ENABLED` global;
- configuração por guild futura ou desde a Fase 1;
- Cogs podem carregar, mas responder `recurso desabilitado`;
- desligar chamadas externas sem afetar startup do bot.

## 16.4. Limpeza

Job interno ou rotina periódica:

- marcar tentativas vencidas como `EXPIRED`;
- remover tentativas antigas após período de retenção;
- remover cache expirado;
- não executar mais de uma vez por hora;
- não depender de scheduler externo na primeira versão.

---

# 17. Riscos e mitigação

| Risco | Impacto | Mitigação |
|---|---|---|
| API comunitária indisponível | Comandos sem dados | timeout, cache, modo degradado e feature flag |
| Mudança de payload | Erros de parsing | adapter, DTO, fixtures e contract tests |
| JWT expira sem aviso | Perfil falha | detectar auth error e solicitar reauth |
| Rate limit desconhecido | Bloqueio temporário | cache, limiter, retry consciente e métricas |
| Rank numérico sem mapa estável | Texto incorreto | resolver com fallback e não inventar valores |
| Vazamento de credencial | Comprometimento da conta | criptografia, redaction e acesso mínimo |
| Duplo vínculo | Impersonação | código no jogo, constraints e transação |
| Imagem externa falha | Card quebrado | placeholder e fallback textual |
| Nome muito longo | Layout ruim | truncamento visual e testes de render |
| Volume cresce | Sobrecarga | semaphore, cache e paginação |
| Provedor muda termos | Necessidade de desligar | atribuição, feature flag e adapter substituível |

---

# 18. Definition of Done global

A integração é considerada pronta para produção quando:

- todas as fases selecionadas têm testes;
- nenhum segredo é armazenado em texto puro;
- nenhuma chamada HTTP ocorre em Cog;
- nenhum SQL ocorre em Cog ou service;
- views persistentes sobrevivem a restart;
- usuário consegue vincular, consultar e desvincular;
- token expirado gera reautenticação orientada;
- perfil respeita visibilidade;
- histórico e heróis paginam corretamente;
- API indisponível não derruba o bot;
- logs não contêm credenciais;
- Docker sobe com migrations;
- Ruff, Black e pytest passam;
- README e `.env.example` estão atualizados;
- a atribuição do provedor está presente;
- homologação real foi feita com conta de teste;
- houve rollout em guild de homologação antes da liberação geral.

---

# 19. Protocolo de execução para o Codex

Os prompts abaixo foram desenhados para serem enviados separadamente. Não pedir ao Codex que implemente todas as fases em uma única execução.

Regras para cada execução:

1. inspecionar o repositório antes de editar;
2. localizar padrões equivalentes já existentes;
3. apresentar um plano curto;
4. implementar somente a fase solicitada;
5. preservar compatibilidade;
6. adicionar migrations no mecanismo existente;
7. adicionar testes;
8. executar qualidade;
9. corrigir os erros encontrados;
10. ao final, listar arquivos alterados, decisões, testes e pendências reais.

Nunca aceitar como conclusão apenas código escrito. A fase termina com testes e relatório.

---

# 20. Prompt mestre de contexto

Copie este prompt no início de uma nova sessão do Codex quando o contexto do repositório não estiver carregado.

```text
Você está trabalhando no Bot Copenhague, um bot de Discord em Python com discord.py e Slash Commands.

Antes de alterar qualquer arquivo, inspecione a estrutura real do repositório, o AppContainer, o carregamento automático de Cogs, a infraestrutura HTTP, o padrão de migrations, os repositories, services, models, UI, configuração, logging e testes existentes.

Arquitetura obrigatória:
- raiz funcional em app/;
- Cogs recebem interações e chamam services;
- services concentram regras de negócio;
- repositories concentram PostgreSQL;
- integrations concentram chamadas HTTP;
- models usam dataclasses/enums;
- UI concentra views, buttons, selects e modals;
- AppContainer compõe e injeta dependências;
- nenhum SQL em Cogs ou services;
- nenhuma chamada HTTP externa em Cogs;
- não criar uma segunda raiz bot/;
- não reescrever módulos existentes sem necessidade;
- preservar Giveaway, Economia, Loja, Cassino, Bolão, Formulários e Moderação.

Stack atual:
- Python 3.11+; Docker Python 3.12;
- discord.py;
- aiohttp;
- Pillow;
- psycopg com pool PostgreSQL;
- python-dotenv;
- pytest, pytest-asyncio, Ruff e Black.

Novo domínio: integração com a MLBB Public Data API.
A API é comunitária e não oficial. Isole-a atrás de app/integrations/mlbb/ e de DTOs normalizados. Use aiohttp diretamente. A base URL deve vir de configuração. Não use requests síncrono.

Endpoints previstos:
POST /api/user/auth/send-vc
POST /api/user/auth/login
POST /api/user/auth/logout
GET /api/user/info
GET /api/user/stats
GET /api/user/season
GET /api/user/matches
GET /api/user/matches/{match_id}
GET /api/user/heroes/frequent
GET /api/user/matches/hero/{hero_identifier}

Segurança obrigatória:
- nunca logar ou exibir JWT, token ou código de verificação;
- não persistir o código de verificação;
- criptografar JWT com biblioteca madura e segredo em variável de ambiente;
- limitar tentativas e envios;
- aplicar idempotência e constraints;
- validar que role_id e zone_id retornados pertencem à tentativa;
- marcar vínculo como REAUTH_REQUIRED somente em erro claro de autenticação;
- timeout/5xx não invalidam o vínculo;
- não modificar privacidade dentro do jogo.

Ao executar uma fase:
1. faça uma auditoria dos arquivos relevantes;
2. proponha plano objetivo;
3. implemente somente o escopo solicitado;
4. crie ou atualize testes;
5. rode pytest, Ruff e Black;
6. corrija falhas;
7. entregue resumo com arquivos, decisões, comandos executados e pendências.

Não invente mapeamento de rank. Se o contrato não fornecer um mapa confiável, implemente fallback que mostre o código bruto sem falhar.
```

---

# 21. Prompts faseados para o Codex

## Prompt da Fase 0 — Client e contrato

```text
Implemente somente a Fase 0 da integração MLBB: descoberta técnica, client HTTP, DTOs, mappers, erros e testes de contrato. Não implemente Cogs, UI, banco ou vínculo nesta fase.

Objetivo:
Criar uma camada de integração assíncrona e defensiva para a MLBB Public Data API usando a infraestrutura aiohttp já existente no Bot Copenhague.

Primeiro:
- inspecione app/integrations/, app/core/config.py, AppContainer, logging e testes HTTP existentes;
- reutilize os padrões do projeto;
- confirme o mecanismo de criação/fechamento de ClientSession;
- não crie infraestrutura paralela.

Estrutura alvo adaptável:
app/integrations/mlbb/__init__.py
app/integrations/mlbb/client.py
app/integrations/mlbb/dto.py
app/integrations/mlbb/mappers.py
app/integrations/mlbb/errors.py
app/integrations/mlbb/rank_resolver.py, apenas se fizer sentido nesta fase

tests/integrations/test_mlbb_client.py
tests/integrations/test_mlbb_mappers.py
tests/fixtures/mlbb/*.json

Implemente métodos para:
- send_verification_code(role_id, zone_id);
- login(role_id, zone_id, verification_code);
- logout(jwt);
- get_user_info(jwt);
- get_user_stats(jwt);
- get_seasons(jwt);
- get_matches(jwt, season_id, limit, cursor);
- get_match_details(jwt, season_id, match_id);
- get_frequent_heroes(jwt, season_id, limit, cursor).

Requisitos:
- base URL e timeout por configuração;
- lang=pt nos endpoints que suportam idioma;
- User-Agent identificando CopenhagueBot;
- Authorization Bearer somente quando necessário;
- validação de HTTP status e do campo externo code;
- DTOs/dataclasses com nomes legíveis, sem espalhar wc/tc/mvpc;
- tolerar campos extras e opcionais;
- IDs de batalha tratados sem perda de precisão; preferir bid_s quando existir;
- retry apenas para GET idempotente em erros transitórios e 429/502/503/504;
- não repetir send-vc ou login automaticamente;
- semaphore global ou mecanismo equivalente para concorrência;
- nunca registrar JWT, token, código ou headers de autorização;
- capturar traceID quando presente;
- erros tipados para timeout, indisponibilidade, rate limit, resposta inválida, código inválido e sessão expirada.

Fixtures:
- use somente dados fictícios ou payloads sanitizados;
- nenhum token real;
- inclua sucesso e respostas incompletas.

Testes mínimos:
- sucesso de cada mapper;
- HTTP 200 com code de erro;
- 401/403;
- 429 com Retry-After;
- 500;
- timeout;
- JSON inválido;
- campo obrigatório ausente;
- campo opcional ausente;
- retry ocorre somente nos GETs permitidos;
- nenhuma mensagem de log contém segredo.

Mapeamento de rank:
- investigue o que o payload realmente fornece;
- não invente nomes de rank;
- caso não exista fonte confiável, crie apenas um resolver com fallback “Rank não mapeado (código X)” e documente a pendência.

Ao final:
- execute pytest, Ruff e Black;
- corrija todos os problemas;
- informe arquivos criados/alterados, contratos normalizados, testes executados e riscos ainda não resolvidos.
```

## Prompt da Fase 1 — Autenticação segura

```text
Implemente somente a Fase 1 da integração MLBB: vínculo seguro de conta, persistência, criptografia, painel e gerenciamento. Não implemente perfil, histórico ou heróis ainda.

Pré-condição:
A Fase 0 já deve existir com MlbbClient, DTOs, mappers e erros. Inspecione a implementação real e adapte-se a ela; não duplique o client.

Primeiro:
- inspecione o mecanismo real de migrations PostgreSQL;
- inspecione repositories assíncronos, pool psycopg, AppContainer, views persistentes, modals, checks e auditoria existentes;
- reutilize padrões de UI e embeds do projeto.

Crie/adapte:
app/models/mlbb.py
app/repositories/mlbb_repository.py
app/services/mlbb_auth_service.py
app/ui/mlbb_panel.py
app/ui/mlbb_modals.py
app/cogs/mlbb/account.py
app/cogs/mlbb/admin.py
migrations no mecanismo existente
testes correspondentes

Banco:
- mlbb_auth_attempts;
- mlbb_account_links;
- use auditoria genérica existente; só crie mlbb_audit_logs se não houver mecanismo reutilizável;
- unique por guild_id + discord_user_id;
- unique por guild_id + role_id + zone_id;
- status PENDING/ACTIVE/REAUTH_REQUIRED/REVOKED e estados de tentativa;
- transações e SELECT FOR UPDATE quando necessário;
- não usar BEGIN IMMEDIATE.

Segurança:
- adicionar cryptography às dependências;
- implementar serviço de criptografia com chave em .env;
- não persistir código de verificação;
- não persistir o token adicional do login nesta versão;
- JWT criptografado em repouso;
- nunca expor credenciais em logs, embeds ou exceptions;
- cooldown de send-vc;
- máximo de tentativas de confirmação;
- tentativa expira em 5 minutos;
- validação de ownership por guild + Discord user;
- validar role_id/zone_id retornados após login;
- impedir vínculo duplicado da mesma conta na guild;
- operações idempotentes contra duplo clique.

UX:
- comando admin /mlbb painel_publicar canal;
- embed pública persistente com Vincular conta e Gerenciar vínculo;
- botão Vincular abre modal Game ID + Zone ID/Área;
- após send-vc, resposta ephemeral com botão Informar código;
- modal de código;
- alternativas /mlbb vincular e /mlbb confirmar;
- /mlbb conta mostra estado;
- /mlbb desvincular exige confirmação;
- reautenticação disponível quando status for REAUTH_REQUIRED;
- mensagens claras para código inválido, expirado, cooldown, conta já usada e API indisponível.

Fluxo de confirmação:
1. carregar tentativa aberta;
2. validar expiração e tentativas;
3. chamar login sem manter transação longa;
4. chamar get_user_info com o JWT;
5. verificar identidade;
6. criptografar JWT;
7. abrir transação curta;
8. revalidar tentativa;
9. upsert vínculo;
10. marcar tentativa VERIFIED;
11. registrar auditoria;
12. responder com nome/avatar, nunca com token.

Desvinculação:
- tentar logout externo;
- mesmo se logout falhar, revogar/remover localmente;
- apagar cache futuro se já houver infraestrutura;
- registrar somente metadados seguros.

Testes mínimos:
- start válido;
- IDs inválidos;
- cooldown;
- envio falha;
- tentativa expira;
- código inválido;
- limite de tentativas;
- sucesso;
- mismatch de conta retornada;
- duplo clique;
- concorrência;
- conta duplicada;
- JWT não está em texto puro;
- código não é persistido;
- reauth preserva visibilidade;
- unlink local funciona quando logout externo falha;
- views persistentes são registradas no startup.

Atualize:
- AppContainer;
- configuração e .env.example;
- carregamento de Cogs;
- README com fluxo de homologação.

Ao final, execute pytest, Ruff e Black, corrija falhas e entregue relatório objetivo.
```

## Prompt da Fase 2 — Perfil e conquistas

```text
Implemente somente a Fase 2 da integração MLBB: perfil, estatísticas gerais, conquistas, visibilidade e cache. Não implemente histórico detalhado ou heróis frequentes ainda.

Pré-condições:
- Fase 0 client/DTOs pronta;
- Fase 1 vínculo e criptografia pronta.
Inspecione as implementações reais e reutilize-as.

Crie/adapte:
app/services/mlbb_profile_service.py
app/services/mlbb_cache_service.py
app/ui/mlbb_profile_view.py
app/cogs/mlbb/profile.py
app/utils/mlbb_formatters.py
rank resolver, se ainda não existir
testes correspondentes

Comandos:
- /mlbb perfil [membro]
- /mlbb conquistas [membro]
- /mlbb privacidade valor:PRIVATE|GUILD

Perfil principal:
- avatar;
- nome;
- nível;
- rank atual;
- maior rank histórico;
- total de partidas;
- vitórias;
- Win Rate;
- MVPs;
- país;
- data da atualização;
- botões Conquistas, Histórico e Heróis podem existir, mas os dois últimos devem informar “disponível em próxima fase” sem erro, ou só serem adicionados quando os respectivos Cogs existirem.

Conquistas:
- maior sequência de vitórias;
- tempo jogado;
- score médio;
- maior kills;
- maior assistências;
- maior dano;
- maior dano recebido;
- maior ouro;
- melhor score;
- nome/imagem do herói associado quando disponível.

Regras:
- calcular WR com proteção contra zero;
- formatar as/100 e scores conforme contrato;
- campos null viram “Não disponível”;
- não inventar mapa de rank;
- resolver códigos conhecidos e usar fallback para desconhecidos;
- default de visibilidade GUILD;
- PRIVATE permite somente o dono;
- consulta de outro membro exige mesma guild;
- nunca retornar JWT ao Cog;
- atualizar nome/avatar persistidos após consulta válida;
- erro de autenticação marca REAUTH_REQUIRED;
- timeout, 429 ou 5xx não invalidam o vínculo.

Cache:
- TTL em memória;
- chave sem JWT;
- locks por chave para deduplicar chamadas;
- perfil 5 min, stats 2 min;
- botão Atualizar respeita cooldown;
- cache invalidado após reauth/desvinculação;
- opção de stale cache apenas se já houver padrão seguro no projeto.

UX:
- respostas próprias podem ser ephemeral ou públicas conforme padrão do bot;
- consulta de outro membro deve ser pública somente se a visibilidade permitir;
- embeds dentro dos limites do Discord;
- ID do jogo mascarado;
- atribuição ao provedor no rodapé;
- mensagem específica quando reautenticação for necessária.

Testes mínimos:
- WR normal e zero partidas;
- campos null;
- score formatado;
- rank desconhecido;
- cache hit/miss;
- deduplicação concorrente;
- PRIVATE bloqueia terceiro;
- GUILD permite membro da mesma guild;
- token expirado marca reauth;
- timeout preserva ACTIVE;
- atualização persiste nome/avatar;
- nenhum segredo é incluído na resposta.

Atualize documentação e rode pytest, Ruff e Black antes de concluir.
```

## Prompt da Fase 3 — Histórico de partidas

```text
Implemente somente a Fase 3 da integração MLBB: temporadas, histórico paginado e detalhe de partida. Não implemente cards com Pillow ainda.

Inspecione:
- MlbbClient e DTOs;
- services e cache;
- padrões existentes de paginação/views;
- limites e helpers de embed;
- tratamento de interaction ownership.

Crie/adapte:
app/services/mlbb_match_service.py
app/ui/mlbb_match_view.py
app/cogs/mlbb/matches.py
formatadores de lane, KDA, data e duração
testes correspondentes

Comandos:
- /mlbb historico [membro] [temporada]
- /mlbb partida match_id temporada [membro]

Fluxo:
- buscar temporadas disponíveis;
- escolher a mais recente por default sem presumir que o maior número sempre é válido antes de validar a lista retornada;
- buscar primeira página com limit configurável;
- guardar cursor no estado da view, nunca na mensagem;
- navegar Próximo/Anterior;
- para voltar, manter páginas visitadas em memória na view;
- parar quando hasNext=false ou nextCursor vazio;
- selecionar partida e abrir detalhe.

Apresentação por partida:
- vitória/derrota;
- herói;
- lane: 1 EXP, 2 Mid, 3 Roam, 4 Jungle, 5 Gold;
- K/D/A;
- score s/100;
- MVP;
- timestamp relativo e absoluto quando útil.

Detalhe:
- duração;
- participantes por time;
- herói;
- K/D/A;
- score;
- dano/contribuição quando presente;
- itens e imagens quando presentes;
- nível do herói;
- role/lane;
- resultado e MVP.

Regras críticas:
- usar bid_s como representação segura quando disponível;
- não converter identificadores grandes para float;
- view só pode ser controlada por quem iniciou;
- respeitar visibilidade do perfil alvo;
- histórico vazio deve gerar embed útil;
- ausência de item/imagem/campo não quebra a tela;
- request de detalhe usa sid válido;
- cache por usuário/temporada/cursor sem JWT na chave;
- token expirado segue o tratamento da fase 2.

Testes mínimos:
- temporada default;
- lista vazia;
- cursor inicial e seguinte;
- fim da paginação;
- página anterior local;
- IDs grandes;
- lane desconhecida;
- timestamp inválido;
- detalhe sem itens;
- interação por usuário não autorizado;
- target PRIVATE;
- timeout e API inválida.

Não implemente geração de imagem. Use embeds e componentes bem organizados. Rode testes e qualidade ao final.
```

## Prompt da Fase 4 — Heróis frequentes

```text
Implemente somente a Fase 4 da integração MLBB: heróis frequentes, Win Rate por herói, MMR/power score, paginação e filtro por herói.

Crie/adapte:
app/services/mlbb_hero_service.py
app/ui/mlbb_hero_view.py
app/cogs/mlbb/heroes.py
testes correspondentes

Comandos:
- /mlbb herois [membro] [temporada]
- opcional /mlbb heroi nome_ou_id [membro] [temporada], somente se o endpoint e UX estiverem estáveis

Cada herói deve mostrar:
- nome e imagem;
- partidas tc;
- vitórias wc;
- Win Rate calculado;
- score bs/100;
- rating mr;
- percentual mrp quando útil;
- power score/MMR p.

Regras:
- zero partidas => WR 0,00%;
- null => “Não disponível”;
- filtro por temporada validado contra temporadas reais;
- paginação por cursor;
- não expor cursor;
- respeitar privacidade;
- cache por temporada e cursor;
- imagem ausente usa placeholder;
- hero_identifier deve ser validado e escapado corretamente;
- não permitir que payload externo vire markdown injection visual.

Integre botões do perfil para abrir Heróis quando possível sem criar acoplamento circular. Use callbacks/services compartilhados ou comandos, seguindo o padrão real do projeto.

Testes mínimos:
- cálculo de WR;
- zero partidas;
- score;
- MMR ausente;
- paginação;
- temporada inválida;
- imagem ausente;
- nome com caracteres especiais;
- target privado;
- token expirado;
- resposta externa incompleta.

Rode pytest, Ruff e Black e atualize documentação.
```

## Prompt da Fase 5 — Cards visuais com Pillow

```text
Implemente somente a Fase 5: cards visuais de perfil e histórico usando Pillow, mantendo as embeds textuais como fallback obrigatório.

Antes:
- inspecione cards/imagens já existentes no projeto;
- identifique helpers de Pillow, fontes e padrões visuais;
- verifique fontes disponíveis no Dockerfile e container;
- não duplique pipeline de imagens se já existir.

Crie/adapte:
app/utils/mlbb_cards.py
serviço/cache de assets, apenas se necessário
testes de layout e utilidades
integração opcional nas views existentes

Cards desejados:
1. perfil: avatar, nome, rank, maior rank, partidas, vitórias, WR, MVPs;
2. conquistas: streak, tempo, score e destaques;
3. histórico: lista visual compacta de partidas;
4. detalhe: resumo dos dois times, se couber com legibilidade.

Requisitos técnicos:
- processamento Pillow em asyncio.to_thread;
- limite de download de imagem;
- timeout;
- validar Content-Type;
- preferir allowlist dos hosts conhecidos ou não baixar avatar e usar placeholder caso a origem seja inesperada;
- cache de imagens de herói com TTL e limite de memória;
- placeholder para falhas;
- sanitizar nomes;
- truncar texto sem cortar o layout;
- suportar acentos e caracteres Unicode comuns;
- dimensões e compressão adequadas ao Discord;
- nenhuma cor ou fonte deve ficar hardcoded em muitos módulos; centralize tema;
- embed textual continua disponível quando qualquer render falhar.

Testes:
- nome curto e longo;
- avatar ausente;
- imagem corrompida;
- campos null;
- muitos dígitos;
- Unicode;
- render dentro das dimensões;
- tamanho final controlado;
- chamada não bloqueia event loop em teste apropriado;
- fallback funciona.

Atualize Docker somente se uma fonte realmente necessária estiver ausente. Não copie arquivos de fonte privados. Rode qualidade e apresente imagens de homologação local apenas como artefatos de teste, não como requisito de runtime.
```

## Prompt da Fase 6 — Hardening e rollout

```text
Implemente somente a Fase 6: hardening, operação, métricas, limpeza, feature flags e rollout da integração MLBB.

Inspecione primeiro:
- logging e analytics existentes;
- admin_panel/admin_analytics;
- configuração por guild;
- jobs periódicos;
- auditoria;
- health checks;
- padrões de feature flag.

Entregas:
- MLBB_ENABLED global;
- configuração por guild se o projeto já possuir guild settings extensível;
- /mlbb status admin;
- métricas de chamadas, latência, erros, cache e vínculos;
- limpeza de tentativas expiradas;
- stale-if-error controlado;
- rate limits refinados;
- rotação de chaves com MultiFernet ou equivalente;
- recriptografia gradual;
- runbook de incidentes;
- checklist de homologação e rollout.

Regras:
- métricas nunca incluem JWT/código;
- admin não pode ler token;
- desligar integração não impede startup;
- falha do provedor não afeta outros Cogs;
- health check não deve consumir endpoints autenticados de usuário;
- limpar tentativas antigas com retenção configurável;
- só marcar REAUTH_REQUIRED em erro de autenticação;
- backoff e circuit breaker não podem bloquear indefinidamente;
- preservar compatibilidade com uma única instância e documentar limitações multi-instância.

Atualize /admin_panel ou /admin_analytics somente se isso seguir o padrão real e não criar dependência circular. Caso contrário, mantenha /mlbb status isolado.

Testes:
- feature desligada;
- limpeza;
- key rotation;
- token antigo recriptografado;
- métricas redigidas;
- circuit open/half-open/closed se implementado;
- stale cache;
- indisponibilidade total;
- recovery;
- integração não impede carregamento do bot.

Ao final, execute todos os testes do projeto, Ruff e Black. Produza relatório de prontidão para produção e liste qualquer validação que só pode ocorrer no Discord real.
```

---

# 22. Plano sugerido de commits

```text
feat(mlbb): add API client and normalized DTOs
feat(mlbb): add secure account linking persistence
feat(mlbb): add persistent linking panel and modals
feat(mlbb): add profile and statistics commands
feat(mlbb): add match history pagination
feat(mlbb): add match details
feat(mlbb): add frequent heroes analysis
feat(mlbb): add visual profile cards
chore(mlbb): add metrics, cleanup and feature flags
docs(mlbb): add integration and operations guide
```

Cada commit deve permanecer revisável. Evitar uma única alteração gigantesca com todas as fases.

---

# 23. Checklist de homologação real

## Autenticação

- publicar painel;
- clicar após restart;
- informar ID e Zone válidos;
- receber código no jogo;
- testar código errado;
- testar código expirado;
- testar código correto;
- confirmar que token não aparece nos logs;
- reiniciar e consultar estado;
- testar conta já vinculada;
- testar reautenticação;
- testar desvinculação.

## Perfil

- conta com muitas partidas;
- conta com poucos dados;
- avatar ausente;
- rank conhecido e desconhecido;
- visibilidade PRIVATE;
- consulta por outro membro;
- API fora do ar;
- token expirado.

## Histórico

- temporada atual;
- temporada antiga;
- próxima página;
- página anterior;
- histórico vazio;
- partida com item ausente;
- nome longo;
- IDs de batalha grandes.

## Operação

- feature flag desligada;
- Docker novo;
- migrations em banco limpo;
- migrations em banco existente;
- backup antes do deploy;
- rollback de código;
- limpeza de tentativas expiradas;
- métricas e status admin.

---

# 24. Fontes técnicas verificadas

- Repositório do provedor: `https://github.com/ridwaanhall/api-mobilelegends`
- OpenAPI: `https://mlbb.rone.dev/api/openapi.json`
- Swagger: `https://mlbb.rone.dev/api/docs`
- Documentação do SDK: `https://mlbb.rone.dev/openmlbb`

Atribuição recomendada no README ou rodapé do recurso:

```text
Powered by MLBB Public Data API.
Mobile Legends: Bang Bang data © Moonton.
API maintained by ridwaanhall / RoneAI.
```

A integração não representa parceria oficial com a Moonton. Verifique licença, termos e changelog do provedor antes de cada release relevante.

---

# 25. Conclusão

A melhor estratégia para o Copenhague não é apenas “chamar uma API”, mas criar um domínio isolado e resiliente que converta um serviço comunitário em uma experiência confiável dentro do Discord.

O vínculo por código dentro do jogo oferece uma base adequada de comprovação de propriedade. A separação entre integração, serviço, repository e UI evita vazamentos de token e mantém o projeto escalável. O desenvolvimento faseado reduz risco: primeiro provar o contrato, depois autenticar, então exibir perfil, histórico, heróis e, por último, investir nos cards visuais e na operação em larga escala.

Seguindo os prompts deste documento, o Codex deve produzir entregas menores, testáveis e alinhadas à arquitetura real, em vez de gerar uma implementação monolítica difícil de revisar.
