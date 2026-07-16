# Fundação do módulo de moderação

O módulo separa modelos, serviço de autorização, comandos e persistência. As
configurações e os casos ficam exclusivamente no PostgreSQL, acessados por
`ModerationRepositoryProtocol` e sua implementação PostgreSQL. O serviço e o
repositório são registrados no `AppContainer` e injetados nos cogs.

## Persistência por servidor

A migration `0009_moderation_foundation.sql` é a fundação imutável do módulo e
cria:

- `moderation_settings`, com o canal padrão de logs por `guild_id`;
- `moderation_authorized_roles`, com IDs de cargos e chave composta por servidor;
- `moderation_cases`, com ID serial, guild, ação, usuário afetado, moderador,
  motivo, data, duração opcional, status, origem e metadados JSONB;
- os índices para histórico de casos por data e por usuário afetado.

Como migrations já aplicadas não são reescritas, a `0009` preserva sua definição
original, inclusive a compatibilidade que aceitava `duration_seconds = 0`. A
migration `0011_moderation_constraints.sql` evolui o schema sem modificar essa
fundação. Antes de tornar a duração estritamente positiva, ela converte valores
legados iguais a zero para `NULL`, que representa ausência de duração.

A `0011` adiciona as constraints de IDs positivos, canal opcional positivo,
cargo positivo, enums válidos de ação, status e origem, motivo não vazio,
duração positiva ou nula e metadados JSONB em formato de objeto. As constraints
são adicionadas como `NOT VALID` e depois validadas, permitindo verificar também
as linhas preexistentes.

A migration `0012_moderation_mute_action.sql` renomeia o tipo de caso
`TIMEOUT` para `MUTE` sem reescrever as migrations anteriores. Casos legados são
convertidos antes de o constraint de ações ser recriado e validado; novas
gravações com o nome antigo são rejeitadas.

No schema final, as consultas de configuração e de casos são isoladas por guild.
A remoção das configurações de um servidor remove também seus cargos autorizados
por `ON DELETE CASCADE`.

O serviço normaliza espaços do motivo, exige texto não vazio de até 500
caracteres, converte duração para segundos inteiros positivos e limita os
metadados serializáveis em JSON a 16 KiB. Ações, status e origens são enums
validados pelo serviço e, após a `0011`, também pelo banco.

## Política de autorização

As verificações visuais e `default_permissions` do Discord servem apenas para a
interface. Toda configuração ou ação é validada novamente por
`ModerationService`, com IDs e contexto atual da guild.

### Configuração

- O proprietário e administradores podem iniciar a configuração mesmo quando
  ainda não existe cargo autorizado.
- Outros usuários precisam simultaneamente de um cargo cadastrado e da
  permissão nativa `manage_guild`.
- O cargo `@everyone`, cargos de outra guild e IDs inválidos são rejeitados.
- O canal de logs precisa pertencer à mesma guild, e o bot precisa das
  permissões efetivas `view_channel`, `send_messages` e `embed_links` para
  visualizar o canal e publicar os embeds de moderação.

### Ações

Cada tipo possui uma política central, em vez de receber nomes de permissões dos
comandos:

| Ação | Permissão do moderador | Permissão do bot | Exige alvo |
|---|---|---|---|
| `BAN` | `ban_members` | `ban_members` | sim |
| `KICK` | `kick_members` | `kick_members` | sim |
| `MUTE` | `moderate_members` | `moderate_members` | sim |
| `WARN` | `moderate_members` | nenhuma permissão nativa | sim |
| `PURGE` | `manage_messages` | `view_channel`, `read_message_history` e `manage_messages` | não |

- Um moderador comum precisa de cargo configurado e da permissão nativa da ação.
- Administradores ignoram a lista de cargos e permissões nativas individuais,
  pois `administrator` as engloba, mas não ignoram a hierarquia sobre o alvo.
- O proprietário ignora somente a comparação entre o próprio cargo e o cargo do
  alvo. Ele ainda passa pelas demais validações aplicáveis.
- O proprietário do servidor nunca pode ser alvo, e o moderador não pode agir
  sobre si mesmo.
- `MUTE` também rejeita alvos com permissão `administrator`, restrição nativa
  do castigo do Discord.
- O cargo mais alto do moderador precisa estar estritamente acima do cargo mais
  alto do alvo. Em posições iguais, o desempate pelo ID replica a ordenação do
  Discord.
- O bot precisa das permissões nativas declaradas na tabela, salvo quando possui
  `administrator`, e sempre precisa de cargo estritamente superior ao alvo. A
  advertência não exige permissão nativa do bot porque é um registro interno com
  notificação por DM, mas a hierarquia continua sendo revalidada.
- Moderador, alvo e bot precisam pertencer à mesma guild informada.

No `/purge`, as permissões efetivas são obtidas no canal atual, incluindo seus
overwrites, e a ação não exige alvo. A visibilidade padrão do comando pede ao
moderador `manage_messages` e `read_message_history`; o serviço revalida
`manage_messages` para o moderador e exige do bot `view_channel`,
`read_message_history` e `manage_messages`. Falhas retornam mensagens claras
antes da chamada à API do Discord.

## Comandos de configuração

- `/moderation role add`
- `/moderation role remove`
- `/moderation role list`
- `/moderation log-channel set`
- `/moderation log-channel show`
- `/moderation log-channel clear`

Os comandos persistem IDs, não nomes. Seus nomes e parâmetros administrativos
são em inglês; descrições e respostas seguem o padrão em português e são
efêmeras quando contêm configuração ou erro.

## Ações atualmente conectadas

Os comandos `/ban`, `/kick`, `/mute` e `/warn` usam a autorização central para
validar cargo configurado, permissão nativa, proprietário e hierarquia do
moderador e do bot. Cada operação confirmada cria um caso `COMPLETED` com origem
`COMMAND`. Se houver canal padrão configurado, ele recebe um embed com número do
caso, ação, usuário, moderador, motivo e duração quando aplicável, sem menções
automáticas.

O `/mute member duration reason` usa `discord.Member.timeout`, o castigo nativo
do Discord, e não o mute exclusivo de voz. Durante o período, o usuário não pode
enviar ou reagir a mensagens em chats e threads nem entrar ou falar em canais de
voz ou palco do servidor. A duração obrigatória é informada em minutos e
revalidada no serviço entre 1 e 40.320 minutos, o máximo de 28 dias aceito pela
API. Aplicar outro mute substitui a expiração atual.

O `/warn member reason` registra a advertência antes de tentar avisar o usuário
por mensagem direta. A impossibilidade de entregar a DM não remove o caso: o
moderador recebe uma resposta explícita e o evento continua disponível no canal
de logs. Como a advertência não executa punição nativa, o bot não precisa de
`moderate_members`; o executor continua precisando dessa permissão e todas as
regras de cargo e hierarquia permanecem ativas.

O `/purge` também usa a política central. Sua assinatura é
`/purge amount:<1-100> reason:<opcional>`: `amount` limita a remoção de 1 a 100
mensagens e `reason` é normalizado pelo mesmo serviço usado nos casos. Quando o
motivo não é informado, o comando gera um motivo de auditoria com o executor. O
texto enviado à API do Discord respeita o limite validado de 500 caracteres. O
comando ainda não cria um caso persistente.

## Logs estruturados

Alterações de cargos e canal, além da criação de casos, geram eventos
estruturados com guild, IDs e resultado da operação. O motivo e os metadados do
caso não são incluídos nesses logs. Falhas ao persistir um caso ou entregar a
mensagem no canal configurado são registradas sem tokens ou credenciais. Se uma
falha inesperada de repositório ocorrer depois de a interação ser adiada, o cog
registra o contexto seguro e responde ao moderador com erro genérico, sem expor
detalhes do banco.
