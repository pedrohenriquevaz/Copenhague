# MLBB — contrato observado na Fase 0

Auditoria realizada em 16 de julho de 2026 contra o OpenAPI 4.1.0 publicado em
https://mlbb.rone.dev/api/openapi.json e o repositório
https://github.com/ridwaanhall/api-mobilelegends.

## Endpoints normalizados

| Operação | Método e caminho | DTO/retorno |
|---|---|---|
| Enviar código | POST /user/auth/send-vc | MlbbClient retorna None |
| Login | POST /user/auth/login | MlbbLoginResult |
| Logout | POST /user/auth/logout | MlbbClient retorna None |
| Perfil | GET /user/info?lang=pt | MlbbPlayerProfile |
| Estatísticas | GET /user/stats?lang=pt | MlbbPlayerStatsRaw |
| Temporadas | GET /user/season?lang=pt | tupla de inteiros |
| Partidas | GET /user/matches | MlbbMatchPage |
| Detalhe | GET /user/matches/{match_id} | MlbbMatchDetails |
| Heróis frequentes | GET /user/heroes/frequent | MlbbHeroPage |

A base configurada já inclui /api. O client usa lang=pt em todos os GETs
acima, pois o contrato atual declara suporte ao parâmetro.

## Campos e tolerância

- code é obrigatório no envelope e somente o inteiro 0 representa sucesso.
- data e os campos estruturais do retorno solicitado são obrigatórios.
- No perfil, roleId, zoneId e name são obrigatórios para formar uma identidade
  verificável; avatar, level, ranks e país são opcionais.
- Estatísticas numéricas ausentes assumem zero quando esse é o valor neutro.
  Highlights e temporadas podem estar vazios.
- Campos novos são ignorados. Campos presentes com tipos incompatíveis geram
  MlbbInvalidResponseError.
- IDs de batalha são strings nos DTOs. bid_s sempre vence bid, pois o exemplo
  público atual demonstra que o valor numérico pode divergir do valor textual
  além do limite de precisão segura de JavaScript.
- O token secundário retornado pelo login não integra o DTO. Somente o JWT,
  marcado com repr=False, é devolvido à futura camada de autenticação.
- traceID é aceito somente em formato seguro e registrado sem payload,
  credenciais ou headers.

## Erros e retry

HTTP 401/403 em endpoint autenticado é evidência clara de sessão expirada.
Timeout, falha de rede, 429 e 5xx não classificam o vínculo como inválido.
Somente GETs repetem automaticamente: falha de rede/timeout e HTTP
429/502/503/504, com no máximo duas novas tentativas. HTTP 500 é falha
indisponível sem retry. send-vc, login e logout nunca são repetidos.

O OpenAPI não documenta uma tabela estável de códigos externos de erro.
Consequentemente, a implementação não inventa códigos: mensagens claras de
autenticação são classificadas de modo conservador; os demais code diferente
de 0 viram MlbbProviderResponseError, preservando apenas o código e o traceID
seguros.

## Pendência de rank

O contrato publica apenas rank_level e history_rank_level, com exemplos
numéricos como 8000 e 9999. O RankEnum do OpenAPI pertence aos filtros de
estatísticas agregadas de heróis e não prova a tradução desses códigos de
jogador. Nenhum mapa numérico confiável foi localizado no material do
provedor. Nesta fase, resolve_rank_name retorna exclusivamente
“Rank não mapeado (código X)” para códigos presentes e nunca inventa um nome.

Todas as fixtures locais são fictícias e usam hosts .example.test; nenhum JWT,
token, código de verificação ou identificador de jogador real foi salvo.
