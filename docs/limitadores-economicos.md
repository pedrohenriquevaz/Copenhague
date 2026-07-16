# Limitadores por faixa econômica

A política econômica usa o saldo oficial (`UserWallet.balance`), o lucro líquido
diário registrado no PostgreSQL e as faixas definidas em `ECONOMIC_TIERS`. A
decisão pertence ao serviço de domínio `EconomicDifficultyPolicyService`,
registrado no `AppContainer` e compartilhado pelos serviços dos jogos.

Uma decisão registra a faixa, a janela diária, o lucro e o limite considerados,
a razão em pontos-base, a dificuldade e o nome da política. O value object é
imutável para que a mesma decisão seja usada na validação, no sorteio e no
pagamento de uma rodada instantânea.

## Seleção da política

- Com `casino_limiters_enabled` desativado, a política é `disabled`. Não são
  consultados saldo, faixa ou lucro diário, e nenhuma nova regra afeta o jogo.
- As faixas Inicial e Emergente, níveis 1 e 2, recebem `tier_exempt`. Elas não
  sofrem dificuldade, teto de lucro nem limite diário de compra da raspadinha,
  independentemente do lucro já acumulado.
- A partir da faixa Próspero, nível 3, calcula-se
  `máximo(0, lucro diário) / limite diário`.
- Um limite diário igual ou inferior a zero produz `invalid_limit`: dificuldade
  e teto de lucro ficam inativos com segurança. Para usuários não isentos, o
  limite diário de compra da raspadinha continua independente e ativo.
- Lucro negativo, inclusive após apostas, estornos ou cashback, resulta em razão
  zero e política `standard`.

O limiar padrão da política `increased` é configurado por
`ECONOMIC_DIFFICULTY_THRESHOLD_BPS`, atualmente em 7.000 bps. Esse valor é
recebido pelo construtor de `EconomicDifficultyPolicyService` e pode ser
substituído na composição do serviço, sem espalhar o percentual pelos jogos. O
serviço aceita valores de 1 bps até um ponto abaixo do limiar `severe`, definido
por `SEVERE_ECONOMIC_DIFFICULTY_THRESHOLD_BPS`. A tabela efetiva de passos é
montada e validada uma única vez pelo serviço:

| Razão do lucro diário | Política | Dificuldade |
|---:|---|---:|
| até 69,99% (`0` a `6.999` bps) | `standard` | 0 bps |
| de 70% a 89,99% (`7.000` a `8.999` bps) | `increased` | 3.500 bps |
| a partir de 90% (`9.000` bps ou mais) | `severe` | 5.000 bps |

Com a configuração padrão, o valor exato de 70% já seleciona `increased` e
valores acima de 100% continuam em `severe`. A razão usa divisão inteira em
pontos-base, evitando comparações de ponto flutuante.

## Efeito sobre os jogos

Somente jogos instantâneos elegíveis têm o resultado probabilístico afetado:

| Jogo | Significado da dificuldade | Momento da decisão |
|---|---|---|
| Cara ou coroa | Uma vitória sorteada pode ser convertida no lado perdedor. | Antes do sorteio e da aposta |
| Dados | Uma vitória sorteada pode receber um resultado perdedor válido para o modo escolhido. | Antes do sorteio e da aposta |
| Slot | Uma combinação vencedora pode ser substituída por uma combinação perdedora válida. | Antes do sorteio e da aposta |
| Roleta | Uma vitória sorteada pode receber uma cor perdedora válida. | Antes do sorteio e da aposta |
| Corrida de mascotes | O mascote vencedor pode ser substituído por outro participante. | Antes do sorteio e da aposta |
| Raspadinha | Reduz o portão de aceitação de uma grade vencedora comum; grades perdedoras continuam válidas. | Antes da compra e da geração da grade |

Nos cinco jogos instantâneos de cassino, 3.500 ou 5.000 bps representam,
respectivamente, 35% ou 50% de chance de vetar uma vitória que já havia sido
sorteada. Na raspadinha, a dificuldade reduz proporcionalmente a probabilidade
base de preservar uma grade vencedora. Uma grade de jackpot não é convertida em
perdedora por essa etapa, embora o pagamento final ainda possa ser limitado.

As probabilidades permanecem dentro do intervalo seguro de 1 a 10.000 bps
quando a probabilidade base é positiva. Não são produzidos lados, cores, dados,
símbolos ou vencedores inválidos.

Blackjack armazena a decisão no início da sessão e não altera cartas já
distribuídas. Duelos também selecionam a política dos dois participantes antes
dos débitos e não modificam o vencedor sorteado. Corrida coletiva, apostas de
partidas, Truco e UNO não têm cartas, odds ou vencedores alterados; nesses jogos,
a decisão tomada antes do débito é serializada em um snapshot versionado e
restaurada no pagamento. Nenhum resultado já iniciado é recalculado
retroativamente.

Os snapshots da corrida coletiva e das apostas de partidas são persistidos nas
respectivas apostas pelo campo `economic_policy_json`, adicionado pela migration
`0010_economic_policy_snapshots.sql`. Truco e UNO armazenam um snapshot por
participante dentro do estado serializado e persistido da sessão. O snapshot
preserva faixa, lucro, limite, razão, dificuldade, política, início da janela e
versão do formato. Registros legados sem snapshot usam um fallback explícito que
reconstrói a faixa anterior ao débito e emite um `WARNING` estruturado.

A mesma migration adiciona `idempotency_key` às transações econômicas, cria um
índice único parcial por `(guild_id, idempotency_key)` para as chaves não nulas e
cria `economy_effect_claims`, usada para tornar idempotentes os efeitos de
proteção de crédito.

## Teto diário de lucro e pagamentos

Para faixas não isentas com limite válido, um usuário que já alcançou o teto não
pode iniciar uma nova jogada coberta pela validação. Se uma vitória ultrapassaria
o restante disponível, o pagamento é reduzido, podendo chegar a zero. Empates e
devoluções que não superam a aposta não são tratados como lucro novo.

O lucro líquido considera as transações `CASINO_BET`, `CASINO_PAYOUT`,
`MATCH_BET`, `MATCH_BET_PAYOUT`, `REFUND` e `CREDIT_CASHBACK` da janela atual. O
cálculo do lucro e o crédito do pagamento acontecem na mesma transação de banco,
serializada pela carteira do usuário, para impedir que pagamentos concorrentes
ultrapassem o teto.

Pagamentos de corrida coletiva, apostas de partidas, Truco e UNO também recebem
uma `idempotency_key` determinística, formada pela modalidade, pelo ID persistido
da aposta ou partida e, quando necessário, pelo usuário vencedor. Em uma nova
tentativa após timeout, retry ou crash, o repositório retorna a transação já
registrada e não credita a carteira novamente. A chave é validada contra a mesma
guild e o mesmo usuário, e pagamentos limitados a zero também são registrados,
preservando a idempotência.

Reembolsos desses fluxos usam a mesma proteção em `economy_transactions`. As
chaves distinguem o estorno de uma falha parcial no início da partida do estorno
posterior por cancelamento. Repetir a mesma tentativa retorna a transação já
existente, sem creditar novamente a aposta; causas legitimamente diferentes não
consomem a chave umas das outras.

Os efeitos de proteção de crédito usam uma chave separada, normalmente com o
sufixo `:credit`. O claim é inserido em `economy_effect_claims` na mesma transação
que atualiza a sequência de derrotas, consome um save e, quando aplicável,
credita o cashback. Um replay da mesma chave não incrementa novamente a
sequência, não consome outro save e não duplica o cashback. A chave é única por
guild e o repositório também confirma que ela pertence ao mesmo usuário.

O teto alcança os jogos instantâneos, raspadinha, duelo, Blackjack, corrida
coletiva, apostas de partidas, Truco e UNO. Ele limita o valor creditado, sem
mudar retroativamente o resultado apresentado pela partida.

### Limite transacional conhecido

As garantias acima são atômicas para cada pagamento, reembolso ou efeito de
proteção de crédito. A resolução de corrida coletiva, match bet, Truco e UNO,
porém, percorre vários usuários e atualiza estado da partida, carteira, proteção
de crédito e progresso em operações separadas. Não existe uma Unit of Work única
que englobe todos esses repositórios e participantes.

Um cancelamento assíncrono ou crash entre `awaits` pode, portanto, deixar a
resolução parcialmente concluída: alguns usuários podem já ter sido processados
enquanto outros ainda não, ou uma transação econômica pode existir antes da
marcação correspondente no estado do jogo. As chaves idempotentes permitem
repetir com segurança as mutações já iniciadas e facilitam reconciliação, mas não
garantem, sozinhas, retomada automática nem atomicidade global do fluxo
multiusuário.

### Testes de concorrência e retry

Os testes de integração PostgreSQL cobrem concorrência, replay com a mesma chave
e consistência temporal em:

- `test_postgres_casino_payout_idempotency_prevents_double_credit`;
- `test_postgres_balance_mutation_idempotency_prevents_double_refund`;
- `test_postgres_credit_protection_effect_is_idempotent`;
- `test_postgres_settlement_uses_one_instant_for_day_and_created_at`.

Eles ficam em `tests/test_postgres_repositories.py`. No nível dos serviços,
`test_collective_race_duplicate_rollback_does_not_consume_cancel_refund_key`,
`test_truco_partial_start_failure_retry_and_cancel_use_distinct_refunds` e
`test_uno_partial_start_failure_retry_and_cancel_use_distinct_refunds` cobrem
falha parcial, retry e cancelamento sem colisão entre causas de reembolso. Essa
cobertura verifica que operações repetidas não duplicam crédito ou efeitos; ela
não representa uma transação atômica de ponta a ponta entre todos os usuários.

## Janela diária e observabilidade

O início do dia usa o timezone econômico já adotado, UTC-03:00. A decisão da
partida mantém sua janela original no snapshot, mas o início da janela contábil
é recalculado no momento de cada pagamento. O repositório obtém um único `now`
depois de abrir e bloquear a transação e deriva dele tanto o início do dia
econômico quanto o `created_at` do crédito. Assim, não existe uma virada de dia
entre a consulta do lucro e a gravação do pagamento.

Se uma partida atravessar a meia-noite local, o lucro disponível e o crédito são
apurados contra a nova janela diária, sem reaproveitar o acumulado do dia
anterior. Ao materializar o modelo, datas com timezone são normalizadas para UTC;
isso não muda a fronteira contábil, que continua sendo a meia-noite em UTC-03:00.
Apostas, estornos e cashbacks registrados nessa janela afetam o lucro líquido de
forma natural.

A seleção registra somente em `DEBUG`: `guild_id`, usuário, faixa, lucro diário,
limite diário, razão em bps, política e jogo. O settlement acrescenta pagamento
solicitado, pagamento efetivamente creditado e início da janela contábil. Campos
não consultados são marcados como `not_evaluated`; não há log em `INFO` a cada
jogada nem exposição de tokens ou segredos. Replays idempotentes são indicados
por `idempotent_replay` no resultado e no log de settlement.

Além do log de depuração, cada transação de pagamento recebe metadados
auditáveis: `economic_policy`, `economic_tier`, `economic_ratio_bps`,
`economic_daily_limit`, `economic_policy_window_start` e
`economic_settlement_window_start`. Assim, é possível distinguir a política
congelada no início da partida da janela contábil efetivamente usada no crédito.
