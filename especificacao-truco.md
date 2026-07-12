segredo é separar o jogo em duas interfaces ao mesmo tempo:

uma mesa pública, visível para todos;
uma mão privada, visível apenas para cada jogador.

No Discord, isso funciona muito bem usando embeds públicas + respostas ephemeral + botões sincronizados. Mensagens ephemeral são visíveis apenas para quem iniciou a interação, então servem perfeitamente para mostrar cartas escondidas.

Como seria na prática

Imagine um Truco 2x2:

Pedro + Bella
vs
Lucas + João

O bot cria uma mensagem pública no canal:

🃏 PARTIDA DE TRUCO

Equipe Azul
Pedro + Bella

Equipe Vermelha
Lucas + João

Placar:
0 x 0

Rodada atual: 1
Vez de jogar: Pedro

[Ver minhas cartas]
[Trucar]
[Correr]

Essa mensagem é a mesa pública.

Ela mostra:

jogadores;
equipes;
placar;
cartas já jogadas;
quem deve jogar;
valor atual da mão;
pedidos de truco;
resultado das rodadas.

Mas ela nunca mostra as cartas ainda não utilizadas.

Como cada jogador vê suas cartas

Cada jogador clica em:

[Ver minhas cartas]

O bot responde de forma ephemeral:

🃏 Sua mão

1️⃣ 3 de Espadas
2️⃣ 7 de Copas
3️⃣ Ás de Ouros

Escolha uma carta:

[Jogar 3♠]
[Jogar 7♥]
[Jogar A♦]

Essa resposta aparece apenas para aquele jogador.

Se outro jogador clicar no mesmo botão, o bot consulta a mão dele e mostra as cartas dele.

Assim você não precisa mandar as cartas por DM e não corre o risco de poluir o canal.

Como sincronizar as ações

O jogo precisa existir no backend como uma sessão centralizada.

Exemplo simplificado:

TrucoSession(
    game_id=123,
    guild_id=456,
    channel_id=789,
    players=[pedro, bella, lucas, joao],
    teams={
        "blue": [pedro, bella],
        "red": [lucas, joao]
    },
    hands={
        pedro: [...],
        bella: [...],
        lucas: [...],
        joao: [...]
    },
    current_turn=pedro,
    round_number=1,
    hand_value=1,
    score_blue=0,
    score_red=0,
    status="PLAYING"
)

Todo botão consulta essa sessão antes de executar qualquer coisa.

Quando Pedro tenta jogar uma carta, o bot valida:

A partida ainda está ativa?
Pedro participa dela?
É a vez do Pedro?
Essa carta realmente pertence ao Pedro?
Essa carta ainda não foi jogada?
Existe algum pedido de truco pendente?

Se estiver tudo certo:

remove a carta da mão dele;
registra a jogada;
avança o turno;
atualiza a mesa pública;
bloqueia a carta usada;
registra a ação no banco.
Exemplo de sequência
Estado inicial

Mesa pública:

Rodada 1

Pedro: aguardando
Lucas: aguardando
Bella: aguardando
João: aguardando

Vez de Pedro

Pedro abre a mão privada e joga 3♠.

A mesa é atualizada:

Rodada 1

Pedro: 3♠
Lucas: aguardando
Bella: aguardando
João: aguardando

Vez de Lucas

Lucas abre a mão dele e escolhe A♦.

Rodada 1

Pedro: 3♠
Lucas: A♦
Bella: aguardando
João: aguardando

Vez de Bella

Todos acompanham a mesa pública, mas cada pessoa continua vendo apenas suas próprias cartas.

Pedido de Truco

Quando um jogador clicar em:

[TRUCO!]

A mesa pública muda:

🔥 PEDRO PEDIU TRUCO!

A mão atualmente vale 1 ponto.
Se aceito, passará a valer 3.

Equipe adversária deve responder.

[Aceitar]
[Correr]
[Pedir 6]

Somente jogadores da equipe adversária podem responder.

O backend registra:

pending_challenge = {
    "requested_by": pedro,
    "target_team": "red",
    "current_value": 1,
    "proposed_value": 3
}

Enquanto existir pedido pendente:

ninguém pode jogar carta;
apenas a equipe adversária pode responder;
o turno fica pausado.
Se aceitarem
Truco aceito!
A mão agora vale 3 pontos.

O jogo continua do ponto onde parou.

Se correrem
Equipe Vermelha correu.
Equipe Azul ganhou 1 ponto.
Se pedirem seis
Equipe Vermelha pediu SEIS!

Equipe Azul deve responder:
[Aceitar]
[Correr]
[Pedir 9]
Como evitar dois jogadores clicando ao mesmo tempo

Esse é o principal problema técnico.

Você precisa usar um lock por partida.

Exemplo conceitual:

async with game_lock:
    validar_estado()
    processar_jogada()
    salvar_estado()
    atualizar_mensagem()

Assim, se Pedro e Bella clicarem ao mesmo tempo, o bot processa uma interação por vez.

Sem isso, pode acontecer:

Pedro joga
Bella joga quase simultaneamente
os dois passam na validação
a ordem da partida quebra

Com lock:

Pedro entra primeiro
jogada é salva
turno muda
Bella entra depois
o bot percebe que ainda não é a vez dela

Resposta para Bella:

Ainda não é sua vez de jogar.
Onde salvar o estado

Durante a partida, você pode manter o jogo em memória para respostas rápidas, mas também deve persistir no banco.

Minha recomendação:

Memória:
estado ativo e rápido da partida

Banco:
snapshot da partida, jogadores, mãos, turno e jogadas

Assim, se o bot reiniciar, a partida pode ser:

restaurada;
cancelada com segurança;
ou encerrada com devolução de apostas.

Não deixe partidas importantes existirem apenas em um dicionário Python.

Modelo de tabelas
truco_games
id
guild_id
channel_id
message_id
status
current_turn_user_id
hand_value
round_number
score_team_a
score_team_b
pending_challenge
created_at
updated_at
truco_players
game_id
user_id
team
seat_position
joined_at
truco_cards
game_id
user_id
card_code
is_played
played_at
round_number
play_order

As cartas podem ser armazenadas de forma segura no banco. Os usuários não têm acesso direto ao banco, então não precisam ser criptografadas necessariamente, mas nunca devem aparecer em logs comuns.

truco_actions
id
game_id
user_id
action_type
metadata
created_at

Ações:

JOIN
LEAVE
PLAY_CARD
REQUEST_TRUCO
ACCEPT_TRUCO
RUN
REQUEST_SIX
REQUEST_NINE
REQUEST_TWELVE
TIMEOUT
Lobby antes da partida

O fluxo pode começar assim:

/truco criar formato:2x2 aposta:1000

Mensagem pública:

🃏 MESA DE TRUCO

Criador: @Pedro
Formato: 2x2
Aposta: 1.000 muriwuris por jogador
Pote total: 4.000 muriwuris

Jogadores:
1. Pedro
2. Bella
3. Vazio
4. Vazio

[Entrar]
[Sair]
[Iniciar]
[Cancelar]

Quando quatro jogadores entram:

Todos os lugares foram preenchidos.

O criador pode iniciar, ou o jogo começa automaticamente após confirmação.

Antes de começar:

verificar saldo de todos;
bloquear a aposta de todos;
sortear equipes ou respeitar equipes escolhidas;
embaralhar;
distribuir cartas;
criar o estado da partida.
Organização da interface

Eu usaria três camadas.

1. Mesa pública

Uma mensagem fixa editada durante toda a partida.

Ela contém:

jogadores;
placar;
rodada;
cartas na mesa;
turno;
valor da mão;
eventos importantes.
2. Painel privado

Resposta ephemeral individual.

Contém:

cartas da pessoa;
botão de jogar cada carta;
indicação se é sua vez;
valor atual da mão.
3. Painel de decisões

Quando houver truco, seis, nove ou doze:

aparece publicamente;
só o time autorizado consegue responder;
os demais recebem erro ephemeral.
E as cartas viradas?

No Truco, pode existir a opção de jogar carta fechada.

Na mão privada:

[Jogar aberta]
[Jogar fechada]

Depois o usuário escolhe a carta.

Na mesa pública:

Pedro jogou: 🂠 Carta fechada

No backend, o bot sabe qual carta foi jogada, mas não revela aos demais.

Ao calcular a rodada, aplica a regra definida para carta fechada.

Tempo de turno

Você precisa estabelecer timeout.

Sugestão:

Tempo normal: 45 segundos
Aviso: após 30 segundos
Timeout: após 45 segundos

Ao expirar:

Pedro não jogou dentro do tempo.

Possibilidades configuráveis:

jogar uma carta aleatória;
perder a rodada;
perder a mão;
cancelar a partida após reincidência.

Para uma comunidade casual, eu usaria:

1º timeout: carta aleatória
2º timeout: advertência
3º timeout: derrota automática
Espectadores

Espectadores podem acompanhar:

cartas jogadas;
placar;
pedidos de truco;
andamento.

Eles não podem:

ver mãos;
clicar em ações;
responder pedidos;
influenciar a partida.

Todo callback precisa verificar:

if interaction.user.id not in session.players:
    return "Você não participa desta partida."
Arquitetura recomendada
TrucoCog
Responsável pelos comandos e interações.

TrucoService
Responsável pelas regras do jogo.

TrucoSessionManager
Mantém sessões ativas e locks.

TrucoRepository
Salva e recupera partidas.

TrucoView
Mesa pública e seus botões.

TrucoHandView
Painel ephemeral das cartas.

TrucoChallengeView
Aceitar, correr, pedir seis, nove ou doze.

O ponto central é: o Discord não sincroniza o jogo para você. O bot mantém um único estado oficial e cada clique tenta modificar esse estado.

Os botões são apenas controles remotos.

Resumo visual
                    BANCO / SESSÃO CENTRAL
                           │
             ┌─────────────┴─────────────┐
             │                           │
      MESA PÚBLICA                PAINÉIS PRIVADOS
             │                           │
   placar, turno, cartas          mão de cada jogador
       jogadas, truco            botões para jogar carta

Essa abordagem também serve para:

Uno;
Poker;
Buraco;
Cacheta;
Dominó;
batalha naval;
jogos de draft;
RPG por turnos.

O modelo mental é simples:

Um estado central, uma mesa pública e uma interface privada para cada jogador.

Para Truco, essa é a solução mais natural dentro do Discord.