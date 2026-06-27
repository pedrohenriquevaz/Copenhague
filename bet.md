# SPEC — Jogos de Cassino/Arcade para Bot Discord

## 1. Visão geral

Este documento especifica os jogos de cassino, cartas, apostas e minigames de sorte para o bot de Discord.

O objetivo é criar um módulo de entretenimento baseado em moeda virtual do servidor, permitindo que usuários apostem pontos, ganhem recompensas virtuais e interajam com outros membros da comunidade.

O sistema deve ser tratado como um **Arcade de Pontos Virtuais**, não como cassino real.

Não deve existir:

* Aposta com dinheiro real.
* Compra de pontos com dinheiro real.
* Conversão de pontos em dinheiro.
* Cashout.
* Pix.
* Criptomoeda.
* Prêmios com valor monetário real vinculados a jogos de sorte.
* Qualquer mecânica que caracterize aposta real.

A moeda usada deve ser exclusivamente interna do servidor.

---

## 2. Objetivos do módulo

O módulo de jogos deve:

1. Criar engajamento diário.
2. Dar utilidade extra aos pontos da economia.
3. Gerar interações sociais entre membros.
4. Criar momentos divertidos no servidor.
5. Permitir eventos sazonais.
6. Evitar abuso, spam e inflação da economia.
7. Ser simples para usuários comuns.
8. Ser seguro para staff administrar.
9. Ter logs e histórico das apostas.
10. Ser expansível para novos jogos no futuro.

---

## 3. Regras gerais para todos os jogos

Todos os jogos devem seguir as regras globais abaixo.

### 3.1. Moeda virtual

Todos os jogos usam pontos virtuais da economia do bot.

Cada aposta deve:

* Verificar saldo antes de iniciar.
* Bloquear saldo durante a partida, se necessário.
* Debitar a aposta de forma segura.
* Registrar transação.
* Registrar resultado.
* Pagar prêmio, se houver.
* Atualizar saldo final.

### 3.2. Limites globais

Deve existir configuração por servidor para:

```text
aposta mínima
aposta máxima
ganho máximo diário
perda máxima diária
cooldown global entre jogos
cooldown específico por jogo
quantidade máxima de partidas por dia
canais permitidos para jogos
cargos permitidos
cargos bloqueados
```

### 3.3. Segurança

O sistema deve impedir:

* Apostas sem saldo.
* Apostas negativas.
* Apostas com valor zero.
* Apostas acima do limite.
* Duplo clique em botões.
* Partidas simultâneas inválidas.
* Race condition no saldo.
* Exploração de interação antiga.
* Usuário tentando interagir em partida de outra pessoa.
* Bot jogando.
* Uso fora do servidor.
* Spam de comandos.

### 3.4. Auditoria

Toda partida deve gerar registro.

Campos mínimos:

```text
id
guild_id
user_id
game_type
bet_amount
payout_amount
profit_amount
result
status
metadata
created_at
finished_at
```

Status possíveis:

```text
PENDING
RUNNING
WON
LOST
DRAW
CANCELLED
EXPIRED
ERROR
```

### 3.5. Experiência do usuário

As respostas devem ser visuais, simples e agradáveis.

Usar:

* Embeds.
* Emojis moderados.
* Botões.
* Select menus quando fizer sentido.
* Respostas ephemeral para informações privadas.
* Mensagens públicas apenas quando o jogo for social ou coletivo.

Cada jogo deve mostrar:

```text
valor apostado
resultado
ganho ou perda
saldo atualizado
```

---

## 4. Ordem sugerida de implementação

A implementação deve seguir esta ordem:

```text
1. Cara ou Coroa
2. Dados
3. Slot Machine
4. Blackjack
5. Roleta
6. Duelo entre usuários
7. Crash
8. Raspadinha
9. Corrida de Mascotes
```

Para MVP inicial, implementar primeiro:

```text
1. Cara ou Coroa
2. Dados
3. Slot Machine
```

Esses três jogos são simples, rápidos e validam a estrutura base de apostas.

### 4.1. Estado atual do projeto

No projeto atual, a estrutura base de economia já existe em `app/repositories/economy_repository.py` e usa SQLite, não PostgreSQL.

Também já existe uma primeira implementação de cassino:

```text
/blackjack
app/cogs/casino/blackjack.py
app/services/blackjack_service.py
app/models/casino.py
app/ui/blackjack_view.py
```

O BlackJack atual já valida saldo, debita aposta, paga prêmios com pontos virtuais, bloqueia partidas simultâneas por usuário e usa botões interativos. As próximas implementações devem reaproveitar essa base em vez de criar uma segunda economia ou um novo padrão paralelo.

---

# 5. Jogo 1 — Cara ou Coroa

## 5.1. Descrição

Jogo simples de aposta 50/50 onde o usuário escolhe cara ou coroa.

## 5.2. Comando

```text
/cara_coroa aposta:100 escolha:cara
```

Parâmetros:

```text
aposta: número inteiro obrigatório
escolha: cara ou coroa
```

## 5.3. Regras

* O usuário escolhe `cara` ou `coroa`.
* O bot sorteia aleatoriamente um dos dois resultados.
* Se o usuário acertar, ganha.
* Se errar, perde.
* Empate não existe.

## 5.4. Pagamento sugerido

```text
Vitória: 2x o valor apostado
Derrota: perde a aposta
```

Exemplo:

```text
Aposta: 100
Vitória: recebe 200
Lucro líquido: 100
Derrota: recebe 0
Lucro líquido: -100
```

## 5.5. Resposta de vitória

```text
🪙 Cara ou Coroa

Você escolheu: Cara
Resultado: Cara

Você venceu!
Ganho: 200 pontos
Lucro: +100 pontos
Saldo atual: 850 pontos
```

## 5.6. Resposta de derrota

```text
🪙 Cara ou Coroa

Você escolheu: Cara
Resultado: Coroa

Você perdeu!
Perda: 100 pontos
Saldo atual: 650 pontos
```

## 5.7. Observações

Este jogo deve ter cooldown curto, mas não deve permitir spam excessivo.

Sugestão:

```text
cooldown: 5 segundos
limite diário: configurável
```

---

# 6. Jogo 2 — Dados

## 6.1. Descrição

Jogo baseado em lançamento de dado de 6 lados.

O usuário pode apostar em diferentes modos.

## 6.2. Comando

```text
/dado aposta:100 modo:numero valor:6
```

Parâmetros:

```text
aposta: número inteiro obrigatório
modo: obrigatório
valor: opcional, dependendo do modo
```

## 6.3. Modos disponíveis

### 6.3.1. Número exato

Usuário aposta em um número de 1 a 6.

```text
/dado aposta:100 modo:numero valor:6
```

Pagamento sugerido:

```text
Acerto: 6x
Erro: perde aposta
```

### 6.3.2. Par ou ímpar

Usuário aposta se o dado cairá em número par ou ímpar.

```text
/dado aposta:100 modo:par
/dado aposta:100 modo:impar
```

Pagamento sugerido:

```text
Acerto: 2x
Erro: perde aposta
```

### 6.3.3. Maior ou menor

Usuário aposta se o resultado será maior ou menor que 3.

```text
/dado aposta:100 modo:maior
/dado aposta:100 modo:menor
```

Regras:

```text
Maior: 4, 5, 6
Menor: 1, 2, 3
```

Pagamento sugerido:

```text
Acerto: 2x
Erro: perde aposta
```

## 6.4. Resposta exemplo

```text
🎲 Dados

Modo: Número exato
Sua aposta: 6
Resultado: 6

Você venceu!
Ganho: 600 pontos
Lucro: +500 pontos
Saldo atual: 1.200 pontos
```

## 6.5. Observações

Este jogo é ótimo para MVP porque permite vários níveis de risco.

---

# 7. Jogo 3 — Slot Machine

## 7.1. Descrição

Jogo de caça-níquel com símbolos sorteados aleatoriamente.

O usuário aposta um valor e recebe uma combinação de 3 símbolos.

## 7.2. Comando

```text
/slot aposta:100
```

## 7.3. Símbolos sugeridos

```text
🍒 Cereja
🍋 Limão
🍇 Uva
🔔 Sino
⭐ Estrela
💎 Diamante
7️⃣ Sete
```

## 7.4. Tabela de pagamento sugerida

```text
🍒 🍒 🍒 = 3x
🍋 🍋 🍋 = 4x
🍇 🍇 🍇 = 5x
🔔 🔔 🔔 = 8x
⭐ ⭐ ⭐ = 10x
💎 💎 💎 = 20x
7️⃣ 7️⃣ 7️⃣ = 50x
2 símbolos iguais = 1.2x ou devolve parte da aposta
sem combinação = perde aposta
```

## 7.5. Resultado exemplo

```text
🎰 Slot Machine

Resultado:
🍒 🍒 🍋

Quase!
Você recebeu 20 pontos de volta.

Aposta: 100
Retorno: 20
Lucro: -80
Saldo atual: 920 pontos
```

## 7.6. Jackpot

Opcionalmente, o jogo pode ter jackpot acumulado.

Regras do jackpot:

* Uma porcentagem das apostas entra no jackpot.
* Apenas combinação rara libera jackpot.
* O jackpot deve ter limite máximo.
* O valor atual deve ser exibido no comando.

Exemplo:

```text
Jackpot atual: 25.000 pontos
```

## 7.7. Observações

A Slot Machine é divertida, mas pode inflacionar a economia se os multiplicadores forem altos demais.

Deve ser muito bem balanceada.

---

# 8. Jogo 4 — Blackjack

## 8.1. Descrição

Jogo de cartas contra o dealer.

O usuário tenta chegar mais perto de 21 sem estourar.

## 8.2. Comando

```text
/blackjack aposta:200
```

## 8.3. Regras básicas

* O usuário recebe 2 cartas.
* O dealer recebe 2 cartas.
* Uma carta do dealer fica oculta.
* O usuário pode comprar carta ou parar.
* Se passar de 21, perde.
* Depois que o usuário para, o dealer joga.
* Dealer compra até atingir pelo menos 17.
* Quem tiver pontuação mais próxima de 21 vence.
* Empate devolve aposta.

## 8.4. Valor das cartas

```text
2 a 10 = valor numérico
J, Q, K = 10
A = 1 ou 11, escolhendo automaticamente o melhor valor possível
```

## 8.5. Botões

O jogo deve usar botões:

```text
[Comprar carta]
[Parar]
[Cancelar]
```

Apenas o usuário que iniciou a partida pode clicar.

## 8.6. Pagamento sugerido

```text
Vitória comum: 2x
Blackjack natural: 2.5x
Empate: devolve aposta
Derrota: perde aposta
```

## 8.7. Embed inicial

```text
🃏 Blackjack

Sua mão:
8♠️ K♦️
Total: 18

Mão do dealer:
? 7♣️

Aposta: 200 pontos

[Comprar carta] [Parar]
```

## 8.8. Vitória exemplo

```text
🃏 Blackjack

Sua mão:
8♠️ K♦️
Total: 18

Dealer:
7♣️ 9♥️
Total: 16

Você venceu!
Ganho: 400 pontos
Lucro: +200 pontos
Saldo atual: 1.500 pontos
```

## 8.9. Derrota exemplo

```text
🃏 Blackjack

Sua mão:
10♠️ 8♦️ 6♣️
Total: 24

Você estourou!

Perda: 200 pontos
Saldo atual: 900 pontos
```

## 8.10. Expiração

Se o usuário não interagir em até 60 segundos:

* A partida expira.
* A aposta pode ser devolvida ou considerada perdida, conforme configuração.
* O recomendado é devolver no MVP.

---

# 9. Jogo 5 — Roleta Simplificada

## 9.1. Descrição

Jogo de roleta com cores simplificadas para Discord.

## 9.2. Comando

```text
/roleta aposta:100 cor:vermelho
```

Parâmetros:

```text
aposta
cor: vermelho, preto ou verde
```

## 9.3. Regras

O bot sorteia uma cor.

Cores:

```text
vermelho
preto
verde
```

Probabilidade sugerida:

```text
vermelho: 47.5%
preto: 47.5%
verde: 5%
```

## 9.4. Pagamento sugerido

```text
Vermelho: 2x
Preto: 2x
Verde: 10x ou 14x
```

## 9.5. Resposta exemplo

```text
🎡 Roleta

Você apostou em: Verde
Resultado: Verde 🟩

Você venceu!
Ganho: 1.000 pontos
Lucro: +900 pontos
Saldo atual: 2.300 pontos
```

## 9.6. Animação opcional

Antes do resultado, o bot pode editar a mensagem algumas vezes:

```text
🟥 ⬛ 🟥 ⬛ 🟩
⬛ 🟥 ⬛ 🟥 ⬛
🟩 ⬛ 🟥 ⬛ 🟥
```

Não exagerar na quantidade de edições para evitar rate limit.

## 9.7. Observações

Roleta é simples e visualmente forte.

Ideal para segunda fase após MVP.

---

# 10. Jogo 6 — Duelo entre Usuários

## 10.1. Descrição

Jogo social onde um usuário desafia outro para apostar pontos.

O resultado pode ser decidido por sorte, dados, jokenpô ou cartas simples.

## 10.2. Comando

```text
/duelo desafiar:@usuario aposta:200 modo:dados
```

Parâmetros:

```text
desafiar: usuário alvo
aposta: valor
modo: sorte, dados, jokenpo
```

## 10.3. Regras gerais

* O desafiante precisa ter saldo suficiente.
* O desafiado precisa ter saldo suficiente.
* O bot envia uma mensagem com botões para aceitar ou recusar.
* Se aceitar, os pontos dos dois são bloqueados.
* O jogo executa o modo escolhido.
* Vencedor recebe o pote.
* Em caso de empate, ambos recebem de volta.

## 10.4. Botões

```text
[Aceitar duelo]
[Recusar]
```

Apenas o usuário desafiado pode aceitar ou recusar.

## 10.5. Modos

### 10.5.1. Sorte

Resultado 50/50.

```text
O bot sorteia o vencedor.
```

### 10.5.2. Dados

Cada usuário rola um dado.

```text
Maior número vence.
Empate rola novamente ou devolve aposta.
```

### 10.5.3. Jokenpô

Cada usuário escolhe:

```text
pedra
papel
tesoura
```

Pode usar select menu ou botões ephemeral.

## 10.6. Resposta exemplo

```text
⚔️ Duelo

@Pedro desafiou @Lucas
Aposta de cada um: 200 pontos
Pote total: 400 pontos
Modo: Dados

@Lucas, você aceita?

[Aceitar duelo] [Recusar]
```

## 10.7. Resultado exemplo

```text
⚔️ Resultado do Duelo

@Pedro rolou: 🎲 5
@Lucas rolou: 🎲 2

Vencedor: @Pedro
Prêmio: 400 pontos
```

## 10.8. Expiração

Se o desafiado não responder em até 60 segundos:

* O duelo expira.
* Nenhum ponto é movimentado.
* Registrar status `EXPIRED`.

## 10.9. Observações

Este jogo tem alto valor social.

Deve ser priorizado após os jogos básicos.

---

# 11. Jogo 7 — Crash

## 11.1. Descrição

Jogo onde o multiplicador sobe progressivamente até crashar.

O usuário precisa retirar antes do crash.

## 11.2. Comando

```text
/crash aposta:100
```

## 11.3. Regras

* Usuário inicia apostando pontos.
* O bot gera previamente um ponto de crash oculto.
* O multiplicador começa em 1.00x.
* O multiplicador aumenta em intervalos.
* Usuário pode clicar em `Retirar`.
* Se retirar antes do crash, recebe aposta multiplicada.
* Se não retirar antes do crash, perde a aposta.

## 11.4. Botões

```text
[Retirar]
```

Apenas o usuário que iniciou pode retirar.

## 11.5. Exemplo de execução

```text
🚀 Crash

Aposta: 100 pontos
Multiplicador atual: 1.40x
Retorno atual: 140 pontos

[Retirar]
```

Se retirar:

```text
🚀 Crash

Você retirou em 1.80x!

Aposta: 100
Retorno: 180
Lucro: +80
Saldo atual: 1.080
```

Se crashar:

```text
💥 Crash!

O jogo crashou em 2.31x.
Você não retirou a tempo.

Perda: 100 pontos
Saldo atual: 900
```

## 11.6. Implementação segura

O ponto de crash deve ser calculado antes da partida começar.

Não alterar resultado depois que a partida iniciou.

Evitar atualizações muito rápidas.

Sugestão:

```text
Atualizar a cada 1 segundo
Tempo máximo de partida: 30 segundos
```

## 11.7. Observações

Crash é emocionante, mas mais complexo.

Deve ser implementado somente depois que o sistema de apostas estiver maduro.

---

# 12. Jogo 8 — Raspadinha

## 12.1. Descrição

Jogo casual onde o usuário compra uma raspadinha virtual e revela os símbolos.

## 12.2. Comando

```text
/raspadinha valor:100
```

Ou com tipos:

```text
/raspadinha tipo:bronze
/raspadinha tipo:prata
/raspadinha tipo:ouro
```

## 12.3. Tipos sugeridos

```text
Bronze: 50 pontos
Prata: 100 pontos
Ouro: 250 pontos
Diamante: 500 pontos
```

## 12.4. Regras

* Usuário compra uma raspadinha.
* Bot gera uma grade de símbolos.
* Usuário clica em revelar.
* Se houver combinação vencedora, recebe prêmio.
* Se não houver, perde a aposta.

## 12.5. Grade sugerida

```text
3x3
```

Exemplo:

```text
🍒 ⭐ 🍒
💎 🍒 ⭐
🍒 🍒 🍒
```

## 12.6. Condições de vitória

```text
3 símbolos iguais em linha
3 símbolos iguais em coluna
3 símbolos iguais na diagonal
combinação especial configurável
```

## 12.7. Botão

```text
[Revelar raspadinha]
```

## 12.8. Resposta exemplo

```text
🎟️ Raspadinha

🍒 ⭐ 🍒
💎 🍒 ⭐
🍒 🍒 🍒

Você encontrou uma linha de cerejas!

Prêmio: 300 pontos
Saldo atual: 1.400 pontos
```

## 12.9. Eventos sazonais

Permitir temas temporários:

```text
Raspadinha de Natal
Raspadinha de Halloween
Raspadinha da Copa
Raspadinha Anime
Raspadinha Aniversário do Servidor
```

## 12.10. Observações

Excelente para eventos e campanhas.

Pode ser usada como recompensa de participação também.

---

# 13. Jogo 9 — Corrida de Mascotes

## 13.1. Descrição

Jogo coletivo onde usuários apostam em mascotes participantes de uma corrida simulada.

## 13.2. Comando individual

```text
/corrida aposta:100 mascote:dragao
```

## 13.3. Comando coletivo

```text
/corrida_iniciar duracao:60
```

Esse comando deve abrir uma janela de apostas por tempo limitado.

## 13.4. Mascotes sugeridos

```text
🐉 Dragão
🐺 Lobo
🦊 Raposa
🐢 Tartaruga
🦅 Águia
🐱 Gato
```

## 13.5. Regras do modo individual

* Usuário aposta em um mascote.
* O bot simula a corrida.
* Um mascote vence.
* Se o usuário escolheu o vencedor, ganha.
* Se não, perde.

## 13.6. Regras do modo coletivo

* Staff ou sistema inicia corrida.
* Usuários têm um tempo para apostar.
* Cada usuário escolhe um mascote.
* Após o tempo, apostas fecham.
* O bot simula a corrida publicamente.
* Vencedores recebem prêmio.
* Perdedor perde aposta.

## 13.7. Pagamento sugerido

Pagamento pode depender da quantidade de mascotes.

Com 6 mascotes:

```text
Acerto: 5x ou 6x
Erro: perde aposta
```

Para modo coletivo, pode usar odds dinâmicas:

```text
Mascote com menos apostas paga mais.
Mascote com muitas apostas paga menos.
```

## 13.8. Simulação visual

Exemplo:

```text
🏁 Corrida de Mascotes

🐉 Dragão: 3 passos
🐺 Lobo: 5 passos
🦊 Raposa: 4 passos
🐢 Tartaruga: 2 passos
```

Atualizações:

```text
🐺 Lobo disparou!
🐢 Tartaruga tropeçou!
🐉 Dragão recuperou terreno!
🦊 Raposa ultrapassou no final!
```

Resultado:

```text
🏆 Vencedor: 🦊 Raposa
```

## 13.9. Resposta final

```text
🏁 Resultado da Corrida

Vencedor: 🦊 Raposa

Você apostou em: 🦊 Raposa
Aposta: 100 pontos
Prêmio: 600 pontos
Lucro: +500 pontos
Saldo atual: 2.100 pontos
```

## 13.10. Observações

Este é um dos jogos com maior potencial de comunidade.

Funciona muito bem em eventos, calls e transmissões.

---

# 14. Sistema de estatísticas dos jogos

Criar estatísticas por usuário e por servidor.

## 14.1. Estatísticas por usuário

Campos sugeridos:

```text
total_games_played
total_bet_amount
total_payout_amount
net_profit
biggest_win
biggest_loss
favorite_game
current_win_streak
current_loss_streak
best_win_streak
```

## 14.2. Estatísticas por jogo

Campos sugeridos:

```text
games_played
total_bet
total_payout
house_profit
biggest_winner
biggest_single_win
```

## 14.3. Comandos

```text
/jogos_perfil
/jogos_historico
/jogos_ranking
/jogos_stats
```

---

# 15. Ranking

Criar rankings separados.

## 15.1. Rankings sugeridos

```text
maior saldo
maior lucro em jogos
maior perda em jogos
maior vitória única
mais partidas jogadas
maior sequência de vitórias
maior sequência de derrotas
```

## 15.2. Regras

* Ranking deve ter paginação.
* Ranking deve respeitar privacidade, se o usuário optar por não aparecer.
* Ranking não deve incentivar perda excessiva.
* Evitar destacar negativamente usuários de forma ofensiva.

---

# 16. Sistema de conquistas

Criar conquistas para deixar o sistema menos focado apenas em ganhar ou perder pontos.

## 16.1. Conquistas sugeridas

```text
Primeira aposta
Primeira vitória
Primeira derrota
Ganhou no cara ou coroa
Acertou número exato no dado
Fez blackjack natural
Ganhou 3 vezes seguidas
Perdeu 3 vezes seguidas
Venceu um duelo
Ganhou na roleta verde
Acertou jackpot da slot
Retirou no crash acima de 3x
Venceu corrida de mascotes
Comprou primeira raspadinha
```

## 16.2. Recompensas de conquistas

Opcionalmente, conquistas podem dar:

```text
pontos extras
cargos cosméticos
títulos
badges internas
entrada em sorteio virtual
```

---

# 17. Configurações administrativas

Criar comandos para configurar os jogos.

## 17.1. Comandos sugeridos

```text
/games_config
/games_enable
/games_disable
/games_set_limits
/games_set_channel
/games_set_cooldown
/games_set_max_bet
/games_set_min_bet
/games_set_daily_loss_limit
/games_set_daily_gain_limit
/games_stats_admin
```

## 17.2. Configurações por jogo

Cada jogo deve permitir:

```text
ativo/inativo
aposta mínima
aposta máxima
cooldown
limite diário
multiplicadores
canal permitido
```

---

# 18. Banco de dados aplicável ao projeto

## 18.1. Realidade atual

O projeto atual usa SQLite e repositórios explícitos, sem ORM.

As tabelas de economia, atividade e loja ficam em `SQLiteEconomyRepository`, usando:

```text
INTEGER para IDs, quantidades e flags booleanas
TEXT para datas serializadas
TEXT com JSON serializado para metadados
AUTOINCREMENT para IDs internos
```

Portanto, as especificações abaixo devem seguir SQLite. Não usar `BIGSERIAL`, `JSONB`, `TIMESTAMPTZ`, `BOOLEAN` nativo ou `DEFAULT now()` como se fosse PostgreSQL.

O BlackJack atual ainda mantém a sessão interativa em memória no `BlackjackService`. As transações financeiras já são persistidas em `economy_transactions` com `CASINO_BET` e `CASINO_PAYOUT`. As tabelas abaixo são a evolução recomendada para auditoria completa, estatísticas, cooldowns e configurações de todos os jogos.

## 18.2. Tabela existente: economy_transactions

Já existe e deve continuar sendo a fonte primária do histórico financeiro.

Os jogos devem registrar:

```text
CASINO_BET: débito da aposta
CASINO_PAYOUT: crédito de vitória, empate ou devolução
REFUND: estorno operacional, quando necessário
SYSTEM_ADJUSTMENT: ajuste administrativo, quando necessário
```

Metadados mínimos recomendados para jogos:

```json
{
  "game": "blackjack",
  "session_id": 123,
  "bet": 100,
  "outcome": "PLAYER_WIN"
}
```

## 18.3. Nova tabela: game_settings

Configuração por servidor e por jogo. Deve ser criada futuramente no repositório SQLite do cassino ou no `SQLiteEconomyRepository`, se a opção for manter toda a economia no mesmo banco.

```sql
CREATE TABLE IF NOT EXISTS game_settings (
    guild_id INTEGER NOT NULL,
    game_type TEXT NOT NULL,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    min_bet INTEGER NOT NULL DEFAULT 10,
    max_bet INTEGER NOT NULL DEFAULT 1000,
    cooldown_seconds INTEGER NOT NULL DEFAULT 5,
    daily_loss_limit INTEGER,
    daily_gain_limit INTEGER,
    max_daily_games INTEGER,
    allowed_channel_id INTEGER,
    allowed_role_id INTEGER,
    blocked_role_id INTEGER,
    config_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, game_type)
);
```

## 18.4. Nova tabela: game_sessions

Auditoria lógica das partidas. Não precisa armazenar todo o estado interativo da UI; esse estado pode continuar em memória para jogos rápidos, como o BlackJack atual.

```sql
CREATE TABLE IF NOT EXISTS game_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    game_type TEXT NOT NULL,
    bet_amount INTEGER NOT NULL,
    payout_amount INTEGER NOT NULL DEFAULT 0,
    profit_amount INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    result TEXT,
    channel_id INTEGER,
    message_id INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    finished_at TEXT
);
```

Índices recomendados:

```sql
CREATE INDEX IF NOT EXISTS idx_game_sessions_guild_user_created
ON game_sessions(guild_id, user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_game_sessions_guild_game_created
ON game_sessions(guild_id, game_type, created_at DESC);
```

## 18.5. Nova tabela: game_user_stats

Estatísticas agregadas por usuário e servidor.

```sql
CREATE TABLE IF NOT EXISTS game_user_stats (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    total_games_played INTEGER NOT NULL DEFAULT 0,
    total_bet_amount INTEGER NOT NULL DEFAULT 0,
    total_payout_amount INTEGER NOT NULL DEFAULT 0,
    net_profit INTEGER NOT NULL DEFAULT 0,
    biggest_win INTEGER NOT NULL DEFAULT 0,
    biggest_loss INTEGER NOT NULL DEFAULT 0,
    current_win_streak INTEGER NOT NULL DEFAULT 0,
    current_loss_streak INTEGER NOT NULL DEFAULT 0,
    best_win_streak INTEGER NOT NULL DEFAULT 0,
    favorite_game TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);
```

## 18.6. Nova tabela: game_cooldowns

Cooldown por servidor, usuário e jogo.

```sql
CREATE TABLE IF NOT EXISTS game_cooldowns (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    game_type TEXT NOT NULL,
    last_played_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id, game_type)
);
```

## 18.7. Nova tabela: game_achievements

Catálogo de conquistas configuráveis por servidor.

```sql
CREATE TABLE IF NOT EXISTS game_achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    achievement_key TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    reward_points INTEGER NOT NULL DEFAULT 0,
    badge_emoji TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(guild_id, achievement_key)
);
```

## 18.8. Nova tabela: user_game_achievements

Conquistas desbloqueadas por usuário.

```sql
CREATE TABLE IF NOT EXISTS user_game_achievements (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    achievement_key TEXT NOT NULL,
    unlocked_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id, achievement_key)
);
```

## 18.9. Política de persistência por fase

Para jogos rápidos e individuais:

```text
estado interativo em memória
resultado financeiro em economy_transactions
auditoria em game_sessions quando a tabela existir
```

Para jogos sociais, coletivos ou longos:

```text
persistir sessão em game_sessions
persistir apostas dos participantes em tabela própria, se necessário
reconstruir ou encerrar sessão após restart
```

---

# 19. Services recomendados

## 19.1. Padrão aplicável ao projeto

O projeto já usa services por domínio e cogs finos. A expansão do cassino deve seguir esse padrão:

```text
app/cogs/casino/<jogo>.py
app/services/<jogo>_service.py
app/models/casino.py
app/ui/<jogo>_view.py
tests/test_<jogo>_service.py
```

O `BlackjackService` já existe e deve ser usado como referência para os próximos jogos.

## 19.2. Evitar excesso de services no MVP

Não criar todos os services abaixo de uma vez:

```text
GameService
BetService
PayoutService
GameLimitService
GameStatsService
AchievementService
CooldownService
GameAuditService
```

No estágio atual, a recomendação é evoluir incrementalmente:

```text
1. Um service por jogo enquanto houver pouca duplicação.
2. Extrair CasinoLedgerService quando 2 ou mais jogos repetirem débito/pagamento/auditoria.
3. Extrair GameLimitService quando limites por jogo forem persistidos.
4. Extrair GameStatsService quando ranking e histórico forem implementados.
5. Extrair AchievementService apenas quando conquistas entrarem no roadmap ativo.
```

## 19.3. Responsabilidades atuais e futuras

### Service do jogo

Responsável por:

```text
validar regras do jogo
sortear resultados
manter sessão em memória quando aplicável
resolver vitória, derrota, empate e expiração
chamar a camada econômica para débito e pagamento
```

### CasinoLedgerService futuro

Responsável por:

```text
criar game_sessions
debitar aposta com CASINO_BET
pagar prêmio com CASINO_PAYOUT
registrar REFUND quando houver erro operacional
finalizar status/result/metadados da sessão
```

### GameLimitService futuro

Responsável por:

```text
aposta mínima e máxima
cooldown global e por jogo
limite diário de perda/ganho
limite de partidas por dia
canal permitido
cargos permitidos ou bloqueados
```

### GameStatsService futuro

Responsável por:

```text
estatísticas por usuário
estatísticas por jogo
rankings
sequências de vitória/derrota
maior vitória única
```

---

# 20. Transações econômicas

Os jogos devem se integrar ao sistema de economia existente.

## 20.1. Tipos atuais

O projeto já possui o enum `EconomyTransactionType`. Para cassino, usar os tipos já implementados:

```text
CASINO_BET
CASINO_PAYOUT
REFUND
SYSTEM_ADJUSTMENT
```

Não usar `GAME_BET`, `GAME_WIN`, `GAME_REFUND`, `GAME_CANCELLED` ou `GAME_ADJUSTMENT` sem migração explícita do enum e dos dados existentes.

## 20.2. Fluxo financeiro recomendado

Toda aposta deve gerar uma transação de débito:

```text
amount = -aposta
type = CASINO_BET
metadata_json.game = nome_do_jogo
```

Todo pagamento deve gerar uma transação de crédito:

```text
amount = premio
type = CASINO_PAYOUT
metadata_json.game = nome_do_jogo
metadata_json.outcome = resultado
```

Derrota pura não gera pagamento, pois o débito da aposta já foi registrado.

Empate e devolução podem ser registrados como `CASINO_PAYOUT` com `amount = aposta`, ou `REFUND` caso a devolução seja causada por erro, cancelamento administrativo ou falha operacional.

## 20.3. Atomicidade

O repositório atual já usa lock e transações SQLite para mutações de saldo.

Regras para novos jogos:

```text
validar saldo imediatamente antes do débito
debitar a aposta antes de iniciar a partida
não confiar no saldo lido anteriormente após interação do usuário
usar mutate_balance para todo débito/crédito
salvar metadados suficientes para auditoria
```

Em caso de erro depois do débito, a aposta deve ser estornada com `REFUND` ou `CASINO_PAYOUT`, conforme a política definida para o jogo.

---

# 21. Proteção contra vício e abuso

Mesmo sendo moeda virtual, o sistema deve ter limites saudáveis.

Configurações recomendadas:

```text
limite diário de perda
limite diário de ganho
cooldown entre apostas
limite de partidas por hora
alerta quando usuário perder muito
bloqueio temporário opcional
```

Mensagem sugerida:

```text
Você atingiu seu limite diário de jogos.
Volte amanhã para jogar novamente.
```

---

# 22. Painel de jogos

Criar painel visual com os jogos disponíveis.

## 22.1. Comando

```text
/games_panel_setup canal:#canal
```

## 22.2. Embed

```text
🎲 Arcade da Comunidade

Use seus pontos para jogar minigames, desafiar amigos e participar de eventos.

Jogos disponíveis:
🪙 Cara ou Coroa
🎲 Dados
🎰 Slot Machine
🃏 Blackjack
🎡 Roleta
⚔️ Duelo
🚀 Crash
🎟️ Raspadinha
🏁 Corrida de Mascotes

Lembre-se: os pontos são virtuais e servem apenas para diversão dentro do servidor.

[Ver saldo] [Abrir jogos] [Ranking] [Histórico]
```

---

# 23. Critérios de aceite gerais

O módulo será considerado pronto quando:

* O usuário conseguir apostar pontos.
* O sistema validar saldo.
* O sistema aplicar limites.
* O sistema registrar partida.
* O sistema registrar transações.
* O sistema pagar corretamente vitórias.
* O sistema descontar corretamente derrotas.
* O usuário não conseguir burlar interações.
* O usuário não conseguir jogar por outro usuário.
* O admin conseguir ativar/desativar jogos.
* O admin conseguir configurar limites.
* Os jogos tiverem logs.
* Os jogos tiverem mensagens claras.
* Os jogos não travarem o bot.
* Os jogos não dependerem de dinheiro real.
* Os jogos estiverem integrados à economia virtual.

---

# 24. Roadmap recomendado

## Versão 0.1 — MVP

```text
/cara_coroa
/dado
/slot
saldo integrado
limites básicos
cooldown
histórico básico
```

## Versão 0.2 — Jogos com interação

```text
/blackjack
/roleta
botões
confirmação visual
melhor feedback
```

## Versão 0.3 — Jogos sociais

```text
/duelo
corrida individual
ranking de jogos
estatísticas por usuário
```

## Versão 0.4 — Eventos

```text
raspadinha
corrida coletiva
eventos sazonais
jackpot
conquistas
```

## Versão 0.5 — Maturidade

```text
painel completo
configuração avançada
limites por cargo
analytics
loja integrada
temporadas
```

---

# 25. Direção de produto

O módulo de jogos não deve ser apenas um lugar para perder ou ganhar pontos.

Ele deve funcionar como camada de entretenimento da comunidade.

A visão ideal é:

```text
Usuários ganham pontos participando.
Usuários usam pontos para jogar.
Jogos geram histórias, memes e interação.
Vitórias viram conquistas.
Eventos criam movimento no servidor.
A lojinha dá utilidade final aos pontos.
```

O foco principal deve ser diversão, socialização e engajamento, não aposta agressiva.

O produto deve parecer uma taverna/arcade da comunidade, não um cassino real.
