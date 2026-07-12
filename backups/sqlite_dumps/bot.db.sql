BEGIN TRANSACTION;
CREATE TABLE bolao_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        prize TEXT NOT NULL,
                        team_1 TEXT NOT NULL,
                        team_2 TEXT NOT NULL,
                        channel_id INTEGER,
                        message_id INTEGER UNIQUE,
                        created_by INTEGER NOT NULL,
                        receiver_user_id INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        is_active INTEGER NOT NULL DEFAULT 1
                    );
INSERT INTO "bolao_events" VALUES(1,'X2 Bet','Bet do Ru','Um abraço','01 e Gnomo','Halifer e Fayre',1330479704007905364,1520604722724208723,1405245502424879116,1405245502424879116,'2026-06-28T01:40:20.343453+00:00',0);
INSERT INTO "bolao_events" VALUES(2,'Oitavas da Copa do Mundo','Aposte no bolão pelo resultado exato deste jogo da Copa.','10.000 Pontos','Argentina','Egito',1524029234945986771,1524040554009202910,1405245502424879116,1405245502424879116,'2026-07-07T13:13:03.918981+00:00',0);
INSERT INTO "bolao_events" VALUES(3,'Oitavas de Final da Copa do Mundo','Colômbia x Suíca','10000 pontos','Colômbia','Suíca',1523780454564495591,1524140755923243155,1405245502424879116,1405245502424879116,'2026-07-07T19:51:14.302614+00:00',0);
INSERT INTO "bolao_events" VALUES(4,'França x Marrocos','Quartas de Final da Copa do Mundo','20000 moedas','França','Marrocos',1523780454564495591,1524763225588236409,1405245502424879116,1405245502424879116,'2026-07-09T13:04:41.956706+00:00',1);
CREATE TABLE bolao_guesses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        bolao_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        score_team_1 INTEGER NOT NULL,
                        score_team_2 INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(bolao_id) REFERENCES bolao_events(id)
                            ON DELETE CASCADE,
                        UNIQUE(bolao_id, user_id)
                    );
INSERT INTO "bolao_guesses" VALUES(1,2,1405245502424879116,1,2,'2026-07-07T13:14:58.507886+00:00');
INSERT INTO "bolao_guesses" VALUES(2,2,1229409880033722470,4,0,'2026-07-07T13:46:03.298490+00:00');
INSERT INTO "bolao_guesses" VALUES(3,2,1516104057780174893,2,1,'2026-07-07T13:48:26.438899+00:00');
INSERT INTO "bolao_guesses" VALUES(4,2,1516213487678787634,2,3,'2026-07-07T14:06:11.197177+00:00');
INSERT INTO "bolao_guesses" VALUES(5,2,993767757478891550,2,1,'2026-07-07T14:54:35.718330+00:00');
INSERT INTO "bolao_guesses" VALUES(6,3,1405245502424879116,2,0,'2026-07-07T19:58:58.476728+00:00');
INSERT INTO "bolao_guesses" VALUES(7,3,1516213487678787634,2,1,'2026-07-07T20:01:12.126577+00:00');
INSERT INTO "bolao_guesses" VALUES(8,3,1230689087716065324,2,0,'2026-07-07T20:36:42.317234+00:00');
INSERT INTO "bolao_guesses" VALUES(9,3,1430214127426736272,2,1,'2026-07-07T20:56:36.054369+00:00');
INSERT INTO "bolao_guesses" VALUES(10,3,1307108925073526895,2,0,'2026-07-07T22:07:14.180562+00:00');
INSERT INTO "bolao_guesses" VALUES(11,3,1210783456750211129,1,0,'2026-07-07T22:36:32.984308+00:00');
INSERT INTO "bolao_guesses" VALUES(12,4,1405245502424879116,3,2,'2026-07-09T13:07:01.167192+00:00');
INSERT INTO "bolao_guesses" VALUES(13,4,1430022981559521353,2,3,'2026-07-09T13:07:04.906585+00:00');
INSERT INTO "bolao_guesses" VALUES(14,4,348655155568181251,2,1,'2026-07-09T13:10:20.773711+00:00');
INSERT INTO "bolao_guesses" VALUES(15,4,291401995712200704,3,1,'2026-07-09T13:10:56.549439+00:00');
INSERT INTO "bolao_guesses" VALUES(16,4,1229409880033722470,1,3,'2026-07-09T13:16:05.338524+00:00');
INSERT INTO "bolao_guesses" VALUES(17,4,1281861244860764160,3,1,'2026-07-09T13:21:23.295616+00:00');
INSERT INTO "bolao_guesses" VALUES(18,4,1516213487678787634,3,1,'2026-07-09T13:34:08.965792+00:00');
INSERT INTO "bolao_guesses" VALUES(19,4,1474837463158624308,1,2,'2026-07-09T13:51:11.106657+00:00');
INSERT INTO "bolao_guesses" VALUES(20,4,968661285900267590,2,0,'2026-07-09T13:58:00.471066+00:00');
INSERT INTO "bolao_guesses" VALUES(21,4,744322486187065414,3,1,'2026-07-09T13:58:49.359449+00:00');
INSERT INTO "bolao_guesses" VALUES(22,4,1399716559856861236,2,3,'2026-07-09T14:01:50.725103+00:00');
INSERT INTO "bolao_guesses" VALUES(23,4,536337731396173854,3,1,'2026-07-09T14:16:39.944811+00:00');
INSERT INTO "bolao_guesses" VALUES(24,4,1511581440981205078,2,0,'2026-07-09T16:45:09.226972+00:00');
CREATE TABLE collective_race_bets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        race_id INTEGER NOT NULL,
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        mascot TEXT NOT NULL,
                        stake INTEGER NOT NULL,
                        potential_payout INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        debit_transaction_id INTEGER,
                        payout_transaction_id INTEGER,
                        created_at TEXT NOT NULL,
                        settled_at TEXT,
                        FOREIGN KEY(race_id) REFERENCES collective_races(id)
                            ON DELETE CASCADE,
                        UNIQUE(race_id, user_id)
                    );
INSERT INTO "collective_race_bets" VALUES(1,2,1330479704007905360,1353471433212428308,'dragao',100,500,'lost',1452,NULL,'2026-07-08T14:53:09.399601+00:00','2026-07-08T14:53:15.516300+00:00');
INSERT INTO "collective_race_bets" VALUES(2,2,1330479704007905360,1430022981559521353,'raposa',100,500,'lost',1453,NULL,'2026-07-08T14:53:13.889165+00:00','2026-07-08T14:53:15.516300+00:00');
INSERT INTO "collective_race_bets" VALUES(4,3,1330479704007905360,743167735055515770,'raposa',150,750,'lost',2905,NULL,'2026-07-08T19:29:28.837630+00:00','2026-07-08T19:29:51.801888+00:00');
INSERT INTO "collective_race_bets" VALUES(5,3,1330479704007905360,1441100461200375878,'raposa',150,750,'lost',2910,NULL,'2026-07-08T19:29:34.843760+00:00','2026-07-08T19:29:51.801888+00:00');
INSERT INTO "collective_race_bets" VALUES(6,3,1330479704007905360,1430214127426736272,'aguia',150,750,'lost',2911,NULL,'2026-07-08T19:29:36.897434+00:00','2026-07-08T19:29:51.801888+00:00');
INSERT INTO "collective_race_bets" VALUES(7,3,1330479704007905360,1364700235737206814,'lobo',150,750,'lost',2915,NULL,'2026-07-08T19:29:42.731632+00:00','2026-07-08T19:29:51.801888+00:00');
INSERT INTO "collective_race_bets" VALUES(8,4,1330479704007905360,1441100461200375878,'dragao',200,1000,'lost',2935,NULL,'2026-07-08T19:31:06.641349+00:00','2026-07-08T19:31:32.280977+00:00');
INSERT INTO "collective_race_bets" VALUES(9,4,1330479704007905360,876267780792524863,'aguia',200,1000,'lost',2936,NULL,'2026-07-08T19:31:08.839171+00:00','2026-07-08T19:31:32.280977+00:00');
INSERT INTO "collective_race_bets" VALUES(10,4,1330479704007905360,743167735055515770,'tartaruga',200,1000,'lost',2937,NULL,'2026-07-08T19:31:11.022948+00:00','2026-07-08T19:31:32.280977+00:00');
CREATE TABLE collective_races (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        channel_id INTEGER,
                        message_id INTEGER UNIQUE,
                        stake INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        opened_by INTEGER NOT NULL,
                        opened_at TEXT NOT NULL,
                        closes_at TEXT NOT NULL,
                        winner TEXT,
                        finished_at TEXT
                    );
INSERT INTO "collective_races" VALUES(1,1330479704007905360,1524029234945986771,1524423561593487471,100,'finished',1405245502424879116,'2026-07-08T14:34:59.939403+00:00','2026-07-08T14:35:09.939403+00:00','tartaruga','2026-07-08T14:35:09.445228+00:00');
INSERT INTO "collective_races" VALUES(2,1330479704007905360,1524029234945986771,1524428095673602099,100,'finished',1405245502424879116,'2026-07-08T14:53:01.003001+00:00','2026-07-08T14:53:16.003001+00:00','tartaruga','2026-07-08T14:53:15.516300+00:00');
INSERT INTO "collective_races" VALUES(3,1330479704007905360,1524029234945986771,1524497639364886660,150,'finished',1405245502424879116,'2026-07-08T19:29:22.239368+00:00','2026-07-08T19:29:52.239368+00:00','gato','2026-07-08T19:29:51.801888+00:00');
INSERT INTO "collective_races" VALUES(4,1330479704007905360,1524029234945986771,1524498060846174329,200,'finished',1405245502424879116,'2026-07-08T19:31:02.713547+00:00','2026-07-08T19:31:32.713547+00:00','lobo','2026-07-08T19:31:32.280977+00:00');
CREATE TABLE form_responses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        form_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        answers_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(form_id) REFERENCES forms(id)
                            ON DELETE CASCADE,
                        UNIQUE(form_id, user_id)
                    );
INSERT INTO "form_responses" VALUES(1,1,743167735055515770,'{"q1": "Jornal", "q2": "Tarde", "q3": "Pq n\u00e3o tem nenhum competente o suficiente pra fazer o jornal \ud83e\udd1f", "q4": "N\u00e3o \u00e9 minha fun\u00e7\u00e3o pq eu vou ser s\u00f3 jornalista ent\u00e3o eu iria entrevistar as partes, brincadeira a parte, eu s\u00f3 ia fazer oq j\u00e1 fizeram cmg uma vez, abrir ticket e resolver tudo por l\u00e1 apagando td que for desagrad\u00e1vel para o chat e resolvendo as coisas pelo ticket", "q5": "Voltar com eventos semanais para engajar o server, como era o mvp da semana etc"}','2026-06-25T23:54:25.033687+00:00');
INSERT INTO "form_responses" VALUES(2,1,1430214127426736272,'{"q1": "Jornal", "q2": "Manh\u00e3", "q3": "Pq eu acho q se eu entrar na staff o rust vai parar de me excluir dos eventos e tirar meu nome dos sorteios", "q4": "Pedindo calma dos dois lados", "q5": "Controlar o palavreado e organizar pts cm os membros"}','2026-06-25T23:59:42.058717+00:00');
CREATE TABLE forms (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        response_channel_id INTEGER NOT NULL,
                        channel_id INTEGER,
                        message_id INTEGER UNIQUE,
                        created_by INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        questions_json TEXT NOT NULL
                    );
INSERT INTO "forms" VALUES(1,'Seja Staff','Formulário para inscrição na Staff do Servidor. Responda adequadamente à cada pergunta e aguarde o resultado',1516809676837097572,1336489742090371162,1519847516722561165,1405245502424879116,'2026-06-25T23:31:25.593806+00:00',1,'[{"id": "q1", "label": "Cargo desejado", "type": "select", "options": ["Modera\u00e7\u00e3o", "Suporte", "Eventos", "Jornal"], "required": true}, {"id": "q2", "label": "Hor\u00e1rio(s) Dispon\u00edvel(eis)", "type": "select", "options": ["Manh\u00e3", "Tarde", "Noite"], "required": true}, {"id": "q3", "label": "Por que deseja entrar para a Staff?", "type": "short", "options": [], "required": true}, {"id": "q4", "label": "De que maneira intermediaria uma discuss\u00e3o?", "type": "short", "options": [], "required": true}, {"id": "q5", "label": "Qual sua proposta de melhoria para o server?", "type": "short", "options": [], "required": true}]');
CREATE TABLE game_achievements (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        achievement_key TEXT NOT NULL,
                        name TEXT NOT NULL,
                        description TEXT NOT NULL,
                        reward_points INTEGER NOT NULL DEFAULT 0,
                        badge_emoji TEXT,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL, reward_points_customized INTEGER NOT NULL DEFAULT 0,
                        UNIQUE(guild_id, achievement_key)
                    );
INSERT INTO "game_achievements" VALUES(1,1330479704007905360,'first_bet','Primeira aposta','Fez sua primeira aposta nos jogos do servidor.',25,'🎟️',1,'2026-06-28T18:41:34.852401+00:00',0);
INSERT INTO "game_achievements" VALUES(2,1330479704007905360,'first_win','Primeira vitória','Venceu pela primeira vez em um jogo.',25,'🏆',1,'2026-06-28T18:41:34.861710+00:00',0);
INSERT INTO "game_achievements" VALUES(3,1330479704007905360,'first_loss','Primeira derrota','Jogou, perdeu e continuou na esportiva.',25,'🧭',1,'2026-06-28T18:41:34.870048+00:00',0);
INSERT INTO "game_achievements" VALUES(4,1330479704007905360,'first_scratch','Primeira raspadinha','Comprou sua primeira raspadinha.',25,'🎫',1,'2026-06-28T18:41:34.878894+00:00',0);
INSERT INTO "game_achievements" VALUES(5,1330479704007905360,'scratch_jackpot','Jackpot da raspadinha','Encontrou o prêmio acumulado da raspadinha.',750,'💎',1,'2026-06-28T18:41:34.887883+00:00',0);
INSERT INTO "game_achievements" VALUES(6,1330479704007905360,'collective_race_win','Venceu corrida coletiva','Acertou o mascote vencedor de uma corrida coletiva.',50,'🏁',1,'2026-06-28T18:41:34.897229+00:00',0);
INSERT INTO "game_achievements" VALUES(269,1330479704007905360,'first_coin_flip','Cara ou coroa','Jogou sua primeira partida de cara ou coroa.',25,'🪙',1,'2026-07-08T11:40:26.685123+00:00',0);
INSERT INTO "game_achievements" VALUES(270,1330479704007905360,'first_dice','Primeiro lançamento','Jogou dados pela primeira vez.',25,'🎲',1,'2026-07-08T11:40:26.692957+00:00',0);
INSERT INTO "game_achievements" VALUES(271,1330479704007905360,'first_slot','Primeiro giro','Girou a slot machine pela primeira vez.',25,'🎰',1,'2026-07-08T11:40:26.700702+00:00',0);
INSERT INTO "game_achievements" VALUES(272,1330479704007905360,'first_roulette','Primeira roleta','Apostou na roleta pela primeira vez.',25,'🔴',1,'2026-07-08T11:40:26.708382+00:00',0);
INSERT INTO "game_achievements" VALUES(273,1330479704007905360,'first_mascot_race','Primeira corrida solo','Apostou em uma corrida de mascotes individual.',25,'🏁',1,'2026-07-08T11:40:26.716284+00:00',0);
INSERT INTO "game_achievements" VALUES(274,1330479704007905360,'first_duel','Primeiro X1','Participou de seu primeiro duelo.',25,'⚔️',1,'2026-07-08T11:40:26.724059+00:00',0);
INSERT INTO "game_achievements" VALUES(275,1330479704007905360,'first_blackjack','Primeiro BlackJack','Entrou em sua primeira mesa de BlackJack.',25,'🃏',1,'2026-07-08T11:40:26.731790+00:00',0);
INSERT INTO "game_achievements" VALUES(276,1330479704007905360,'scratch_win','Raspadinha premiada','Ganhou pontos em uma raspadinha.',50,'✨',1,'2026-07-08T11:40:26.739409+00:00',0);
INSERT INTO "game_achievements" VALUES(277,1330479704007905360,'duel_win','Vitória no X1','Venceu um duelo contra outro membro.',50,'🥇',1,'2026-07-08T11:40:26.747027+00:00',0);
INSERT INTO "game_achievements" VALUES(279,1330479704007905360,'games_10','Aquecimento da banca','Fez 10 apostas em jogos do servidor.',50,'📌',1,'2026-07-08T11:40:26.762472+00:00',0);
INSERT INTO "game_achievements" VALUES(280,1330479704007905360,'wins_5','Cinco vitórias','Somou 5 vitórias em jogos do servidor.',50,'✅',1,'2026-07-08T11:40:26.770255+00:00',0);
INSERT INTO "game_achievements" VALUES(281,1330479704007905360,'points_10k','Primeiros 10 mil','Acumulou 10.000 pontos ganhos no servidor.',100,'💰',1,'2026-07-08T11:40:26.778029+00:00',0);
INSERT INTO "game_achievements" VALUES(282,1330479704007905360,'games_50','Presença constante','Fez 50 apostas em jogos do servidor.',100,'📊',1,'2026-07-08T11:40:26.785828+00:00',0);
INSERT INTO "game_achievements" VALUES(283,1330479704007905360,'wins_25','Sequência respeitável','Somou 25 vitórias em jogos do servidor.',800,'🌟',1,'2026-07-08T11:40:26.793369+00:00',1);
INSERT INTO "game_achievements" VALUES(284,1330479704007905360,'wager_10k','10 mil na mesa','Apostou 10.000 pontos no total.',100,'💸',1,'2026-07-08T11:40:26.849059+00:00',0);
INSERT INTO "game_achievements" VALUES(285,1330479704007905360,'big_win_1k','Prêmio de 1 mil','Recebeu pelo menos 1.000 pontos em uma única aposta.',100,'🎯',1,'2026-07-08T11:40:26.873939+00:00',0);
INSERT INTO "game_achievements" VALUES(286,1330479704007905360,'points_50k','Carteira pesada','Acumulou 50.000 pontos ganhos no servidor.',300,'💼',1,'2026-07-08T11:40:26.883634+00:00',0);
INSERT INTO "game_achievements" VALUES(287,1330479704007905360,'wager_50k','50 mil em apostas','Apostou 50.000 pontos no total.',300,'🏦',1,'2026-07-08T11:40:26.893066+00:00',0);
INSERT INTO "game_achievements" VALUES(288,1330479704007905360,'profit_10k','Lucro de 10 mil','Ficou com 10.000 pontos de lucro líquido nos jogos.',300,'📈',1,'2026-07-08T11:40:26.902370+00:00',0);
INSERT INTO "game_achievements" VALUES(289,1330479704007905360,'big_win_5k','Tacada de 5 mil','Recebeu pelo menos 5.000 pontos em uma única aposta.',300,'💎',1,'2026-07-08T11:40:26.910455+00:00',0);
INSERT INTO "game_achievements" VALUES(290,1330479704007905360,'blackjack_streak_3','Mesa quente','Venceu 3 partidas seguidas de BlackJack.',300,'🔥',1,'2026-07-08T11:40:26.919019+00:00',0);
INSERT INTO "game_achievements" VALUES(291,1330479704007905360,'scratch_veteran','Veterano da raspadinha','Comprou 25 raspadinhas.',300,'🎫',1,'2026-07-08T11:40:26.931118+00:00',0);
INSERT INTO "game_achievements" VALUES(292,1330479704007905360,'duel_king','Rei do X1','Venceu 10 duelos contra membros da comunidade.',500,'👑',1,'2026-07-08T11:40:26.939695+00:00',0);
INSERT INTO "game_achievements" VALUES(293,1330479704007905360,'collective_race_king','Domador das corridas','Venceu 10 corridas coletivas.',500,'🐾',1,'2026-07-08T11:40:26.949474+00:00',0);
CREATE TABLE game_jackpots (
                        guild_id INTEGER NOT NULL,
                        jackpot_key TEXT NOT NULL,
                        amount INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (guild_id, jackpot_key)
                    );
INSERT INTO "game_jackpots" VALUES(1330479704007905360,'scratch_card',4185,'2026-07-09T01:26:53.145499+00:00');
CREATE TABLE game_seasonal_settings (
                        guild_id INTEGER PRIMARY KEY,
                        theme TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
INSERT INTO "game_seasonal_settings" VALUES(1330479704007905360,'copa','2026-07-08T12:14:42.149168+00:00');
CREATE TABLE match_bet_matches (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        team_1 TEXT NOT NULL,
                        team_2 TEXT NOT NULL,
                        odd_team_1_bps INTEGER NOT NULL,
                        odd_team_2_bps INTEGER NOT NULL,
                        channel_id INTEGER,
                        message_id INTEGER UNIQUE,
                        created_by INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        resolved_winner TEXT,
                        resolved_at TEXT
                    );
INSERT INTO "match_bet_matches" VALUES(1,1330479704007905360,'Semi Finais','Teste','Teste 2',163,201,1509246409956921534,1520855306761011361,1405245502424879116,'2026-06-28T18:16:01.831674+00:00',0,'team_1','2026-06-28T18:16:33.379064+00:00');
INSERT INTO "match_bet_matches" VALUES(2,1330479704007905360,'Oitavas da Copa do Mundo','Argentina','Egito',211,189,1524029234945986771,1524040116593754123,1405245502424879116,'2026-07-07T13:11:19.611592+00:00',0,'team_1','2026-07-07T18:10:53.710205+00:00');
INSERT INTO "match_bet_matches" VALUES(3,1330479704007905360,'França x Marrocos','França','Marrocos',132,351,1523780454564495591,1524764870791397468,1405245502424879116,'2026-07-09T13:11:14.279705+00:00',1,NULL,NULL);
CREATE TABLE match_bet_tickets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        match_id INTEGER NOT NULL,
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        team TEXT NOT NULL,
                        team_name_snapshot TEXT NOT NULL,
                        stake INTEGER NOT NULL,
                        odd_bps INTEGER NOT NULL,
                        potential_payout INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        debit_transaction_id INTEGER,
                        payout_transaction_id INTEGER,
                        created_at TEXT NOT NULL,
                        settled_at TEXT,
                        FOREIGN KEY(match_id) REFERENCES match_bet_matches(id)
                            ON DELETE CASCADE
                    );
INSERT INTO "match_bet_tickets" VALUES(3,2,1330479704007905360,1229409880033722470,'team_1','Argentina',50,134,67,'won',351,404,'2026-07-07T13:45:37.838400+00:00','2026-07-07T18:10:53.710205+00:00');
INSERT INTO "match_bet_tickets" VALUES(4,2,1330479704007905360,1516104057780174893,'team_1','Argentina',100,134,134,'won',353,405,'2026-07-07T13:48:45.868318+00:00','2026-07-07T18:10:53.710205+00:00');
INSERT INTO "match_bet_tickets" VALUES(5,2,1330479704007905360,1516213487678787634,'team_2','Egito',50,470,235,'lost',356,NULL,'2026-07-07T14:06:00.240944+00:00','2026-07-07T18:10:53.710205+00:00');
INSERT INTO "match_bet_tickets" VALUES(6,2,1330479704007905360,993767757478891550,'team_1','Argentina',180,134,241,'won',383,406,'2026-07-07T14:54:19.202169+00:00','2026-07-07T18:10:53.710205+00:00');
INSERT INTO "match_bet_tickets" VALUES(7,2,1330479704007905360,1516213487678787634,'team_2','Egito',30,189,56,'lost',403,NULL,'2026-07-07T17:48:30.091783+00:00','2026-07-07T18:10:53.710205+00:00');
INSERT INTO "match_bet_tickets" VALUES(8,3,1330479704007905360,1516213487678787634,'team_1','França',50,132,66,'open',3875,NULL,'2026-07-09T13:11:45.819055+00:00',NULL);
INSERT INTO "match_bet_tickets" VALUES(9,3,1330479704007905360,1430214127426736272,'team_1','França',10,132,13,'open',3888,NULL,'2026-07-09T13:13:55.884957+00:00',NULL);
INSERT INTO "match_bet_tickets" VALUES(10,3,1330479704007905360,1430214127426736272,'team_1','França',10,132,13,'open',3889,NULL,'2026-07-09T13:14:10.587567+00:00',NULL);
INSERT INTO "match_bet_tickets" VALUES(11,3,1330479704007905360,1430214127426736272,'team_2','Marrocos',10,351,35,'open',3890,NULL,'2026-07-09T13:14:28.314235+00:00',NULL);
INSERT INTO "match_bet_tickets" VALUES(12,3,1330479704007905360,1229409880033722470,'team_2','Marrocos',100,351,351,'open',3895,NULL,'2026-07-09T13:15:44.306460+00:00',NULL);
INSERT INTO "match_bet_tickets" VALUES(13,3,1330479704007905360,1430022981559521353,'team_1','França',500,132,660,'open',3912,NULL,'2026-07-09T13:21:36.651660+00:00',NULL);
INSERT INTO "match_bet_tickets" VALUES(14,3,1330479704007905360,1281861244860764160,'team_1','França',600,132,792,'open',3961,NULL,'2026-07-09T13:28:54.403036+00:00',NULL);
INSERT INTO "match_bet_tickets" VALUES(15,3,1330479704007905360,1516104057780174893,'team_2','Marrocos',50,351,175,'open',3972,NULL,'2026-07-09T13:30:14.685926+00:00',NULL);
INSERT INTO "match_bet_tickets" VALUES(16,3,1330479704007905360,418567145249570818,'team_1','França',2500,132,3300,'open',4031,NULL,'2026-07-09T13:45:37.029414+00:00',NULL);
INSERT INTO "match_bet_tickets" VALUES(17,3,1330479704007905360,743167735055515770,'team_1','França',1000,132,1320,'open',4063,NULL,'2026-07-09T13:56:11.322455+00:00',NULL);
INSERT INTO "match_bet_tickets" VALUES(18,3,1330479704007905360,1314654459728756777,'team_1','França',250,132,330,'open',4159,NULL,'2026-07-09T14:56:38.180155+00:00',NULL);
INSERT INTO "match_bet_tickets" VALUES(19,3,1330479704007905360,1353471433212428308,'team_1','França',200,132,264,'open',4207,NULL,'2026-07-09T15:17:54.191344+00:00',NULL);
INSERT INTO "match_bet_tickets" VALUES(20,3,1330479704007905360,1511581440981205078,'team_1','França',2087,132,2754,'open',4287,NULL,'2026-07-09T16:45:55.094468+00:00',NULL);
INSERT INTO "match_bet_tickets" VALUES(21,3,1330479704007905360,938261848761970809,'team_1','França',20,132,26,'open',4291,NULL,'2026-07-09T16:48:16.892447+00:00',NULL);
CREATE TABLE user_game_achievements (
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        achievement_key TEXT NOT NULL,
                        unlocked_at TEXT NOT NULL,
                        PRIMARY KEY (guild_id, user_id, achievement_key),
                        FOREIGN KEY(guild_id, achievement_key)
                            REFERENCES game_achievements(guild_id, achievement_key)
                    );
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430022981559521353,'first_bet','2026-07-06T20:17:06.836634+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430022981559521353,'first_scratch','2026-07-06T20:17:06.889877+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430022981559521353,'first_loss','2026-07-06T20:17:06.942367+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1211780100043841538,'first_bet','2026-07-06T23:32:50.213540+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1211780100043841538,'first_scratch','2026-07-06T23:32:50.280189+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1211780100043841538,'first_loss','2026-07-06T23:32:50.345060+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516213487678787634,'first_bet','2026-07-07T19:51:07.271121+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516213487678787634,'first_scratch','2026-07-07T19:51:07.342560+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516213487678787634,'first_loss','2026-07-07T19:51:07.395601+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'first_bet','2026-07-08T02:25:19.180761+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'first_scratch','2026-07-08T02:25:19.248268+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'first_win','2026-07-08T02:25:19.325921+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,968661285900267590,'first_bet','2026-07-08T02:29:33.168825+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,968661285900267590,'first_scratch','2026-07-08T02:29:33.224860+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,968661285900267590,'first_loss','2026-07-08T02:29:33.280324+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430022981559521353,'first_blackjack','2026-07-08T12:00:40.895357+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430022981559521353,'games_10','2026-07-08T12:00:41.363947+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430022981559521353,'wins_5','2026-07-08T12:00:41.612120+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430022981559521353,'points_10k','2026-07-08T12:00:41.845796+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430022981559521353,'big_win_1k','2026-07-08T12:00:42.120141+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430022981559521353,'blackjack_streak_3','2026-07-08T12:00:42.378128+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430022981559521353,'first_win','2026-07-08T12:01:13.902656+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430022981559521353,'first_duel','2026-07-08T12:03:33.165011+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430022981559521353,'duel_win','2026-07-08T12:13:14.892708+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1281861244860764160,'first_bet','2026-07-08T12:14:57.096918+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1281861244860764160,'first_coin_flip','2026-07-08T12:14:57.355314+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1281861244860764160,'first_win','2026-07-08T12:14:57.608311+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1281861244860764160,'first_blackjack','2026-07-08T12:16:02.517747+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1281861244860764160,'first_loss','2026-07-08T12:16:15.325254+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1281861244860764160,'big_win_1k','2026-07-08T12:16:44.966360+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1281861244860764160,'wins_5','2026-07-08T12:23:22.705188+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1281861244860764160,'games_10','2026-07-08T12:23:39.204366+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430022981559521353,'wager_10k','2026-07-08T12:23:48.188764+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1281861244860764160,'blackjack_streak_3','2026-07-08T12:24:17.170565+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1281861244860764160,'points_10k','2026-07-08T12:24:39.349975+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430022981559521353,'points_50k','2026-07-08T12:39:28.784010+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1230689087716065324,'first_bet','2026-07-08T14:09:28.775692+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1230689087716065324,'first_blackjack','2026-07-08T14:09:29.028870+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1230689087716065324,'games_10','2026-07-08T14:09:29.531725+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1230689087716065324,'games_50','2026-07-08T14:09:29.790025+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1230689087716065324,'wins_5','2026-07-08T14:09:30.088233+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1230689087716065324,'wins_25','2026-07-08T14:09:30.338216+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1230689087716065324,'points_10k','2026-07-08T14:09:30.593532+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1230689087716065324,'wager_10k','2026-07-08T14:09:30.838056+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1230689087716065324,'big_win_1k','2026-07-08T14:09:31.099821+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1230689087716065324,'blackjack_streak_3','2026-07-08T14:09:31.351231+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1230689087716065324,'first_win','2026-07-08T14:09:36.777659+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1230689087716065324,'first_loss','2026-07-08T14:10:26.958376+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1230689087716065324,'first_coin_flip','2026-07-08T14:20:42.453130+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1353471433212428308,'first_bet','2026-07-08T14:51:15.580471+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1353471433212428308,'first_coin_flip','2026-07-08T14:51:15.841953+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1353471433212428308,'first_loss','2026-07-08T14:51:16.096037+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1353471433212428308,'first_blackjack','2026-07-08T14:52:25.462559+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1353471433212428308,'first_win','2026-07-08T14:52:35.422259+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430214127426736272,'first_bet','2026-07-08T15:09:49.357482+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430214127426736272,'first_coin_flip','2026-07-08T15:09:49.741117+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430214127426736272,'first_loss','2026-07-08T15:09:50.065580+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430214127426736272,'first_win','2026-07-08T15:10:35.533278+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'first_blackjack','2026-07-08T15:13:21.993656+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'games_10','2026-07-08T15:13:22.555003+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'wins_5','2026-07-08T15:13:22.860116+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'first_loss','2026-07-08T15:13:57.577831+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430214127426736272,'games_10','2026-07-08T15:14:00.206600+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430214127426736272,'wins_5','2026-07-08T15:14:43.695968+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430214127426736272,'first_duel','2026-07-08T15:15:48.959879+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'first_dice','2026-07-08T15:16:44.363424+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430214127426736272,'duel_win','2026-07-08T15:16:52.945282+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'first_duel','2026-07-08T15:17:54.920545+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'duel_win','2026-07-08T15:17:56.078445+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'first_bet','2026-07-08T15:18:38.241328+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'first_coin_flip','2026-07-08T15:18:38.547877+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'first_loss','2026-07-08T15:18:38.881251+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'first_dice','2026-07-08T15:19:56.769442+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'first_blackjack','2026-07-08T15:20:22.170825+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'first_win','2026-07-08T15:20:44.892267+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'first_coin_flip','2026-07-08T15:20:55.498088+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430022981559521353,'games_50','2026-07-08T15:21:03.279054+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'first_duel','2026-07-08T15:21:34.727774+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'duel_win','2026-07-08T15:21:35.907796+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430214127426736272,'big_win_1k','2026-07-08T15:22:52.173112+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'big_win_1k','2026-07-08T15:23:22.794227+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'first_roulette','2026-07-08T15:23:40.284581+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'first_mascot_race','2026-07-08T15:24:16.390263+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'first_slot','2026-07-08T15:24:48.226868+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'games_10','2026-07-08T15:26:58.419932+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'wins_5','2026-07-08T15:26:58.724122+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430214127426736272,'points_10k','2026-07-08T15:29:01.060280+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430022981559521353,'wins_25','2026-07-08T15:30:43.328039+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,743167735055515770,'first_bet','2026-07-08T15:39:00.367658+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,743167735055515770,'first_blackjack','2026-07-08T15:39:00.652567+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,743167735055515770,'first_coin_flip','2026-07-08T15:40:40.291762+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,743167735055515770,'first_loss','2026-07-08T15:40:40.811879+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516213487678787634,'games_10','2026-07-08T15:42:53.382907+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516213487678787634,'games_50','2026-07-08T15:42:53.900405+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516213487678787634,'wins_5','2026-07-08T15:42:54.367847+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516213487678787634,'wins_25','2026-07-08T15:42:54.631975+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516213487678787634,'points_10k','2026-07-08T15:42:54.886442+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516213487678787634,'points_50k','2026-07-08T15:42:55.165750+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516213487678787634,'wager_10k','2026-07-08T15:42:55.436804+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516213487678787634,'wager_50k','2026-07-08T15:42:55.712752+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516213487678787634,'big_win_1k','2026-07-08T15:42:56.001927+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516213487678787634,'blackjack_streak_3','2026-07-08T15:42:56.285717+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516213487678787634,'first_blackjack','2026-07-08T15:43:46.987694+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'blackjack_streak_3','2026-07-08T15:44:06.175689+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'games_50','2026-07-08T15:45:24.714085+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516213487678787634,'first_win','2026-07-08T15:46:14.103276+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430214127426736272,'wager_10k','2026-07-08T15:48:47.032033+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430214127426736272,'games_50','2026-07-08T15:49:32.554346+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,418567145249570818,'first_bet','2026-07-08T15:50:57.952910+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,418567145249570818,'first_blackjack','2026-07-08T15:50:58.229049+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,418567145249570818,'big_win_1k','2026-07-08T15:50:58.765678+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,418567145249570818,'first_win','2026-07-08T15:51:20.095107+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,418567145249570818,'wins_5','2026-07-08T15:51:20.638240+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,418567145249570818,'games_10','2026-07-08T15:51:41.676465+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,418567145249570818,'first_loss','2026-07-08T15:51:47.938114+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'points_10k','2026-07-08T15:51:50.738548+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,336223804722380801,'first_bet','2026-07-08T15:53:20.598998+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,336223804722380801,'first_blackjack','2026-07-08T15:53:20.867128+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,336223804722380801,'first_loss','2026-07-08T15:53:27.148938+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1353471433212428308,'first_mascot_race','2026-07-08T17:36:57.842657+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1353471433212428308,'games_10','2026-07-08T17:38:22.840595+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1353471433212428308,'wins_5','2026-07-08T17:40:13.230849+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1353471433212428308,'first_duel','2026-07-08T17:40:39.295712+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'wager_10k','2026-07-08T17:42:14.325210+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,743167735055515770,'first_slot','2026-07-08T17:44:33.780284+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'points_10k','2026-07-08T17:48:38.531098+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'games_50','2026-07-08T17:51:58.724481+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'wins_25','2026-07-08T17:54:15.967270+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,876267780792524863,'first_bet','2026-07-08T17:58:16.145226+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,876267780792524863,'first_coin_flip','2026-07-08T17:58:16.761109+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,876267780792524863,'first_win','2026-07-08T17:58:17.616686+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,876267780792524863,'first_loss','2026-07-08T17:58:50.039488+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'big_win_5k','2026-07-08T18:00:40.191159+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,876267780792524863,'wins_5','2026-07-08T18:00:54.687615+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1441100461200375878,'first_bet','2026-07-08T18:02:14.409751+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1441100461200375878,'first_coin_flip','2026-07-08T18:02:15.647241+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1441100461200375878,'first_win','2026-07-08T18:02:16.865740+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1441100461200375878,'big_win_1k','2026-07-08T18:02:18.091559+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,876267780792524863,'games_10','2026-07-08T18:03:07.727771+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1230689087716065324,'first_dice','2026-07-08T18:05:49.425672+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,876267780792524863,'first_blackjack','2026-07-08T18:07:06.702413+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430022981559521353,'wager_50k','2026-07-08T18:10:14.853759+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1441100461200375878,'points_10k','2026-07-08T18:10:19.610138+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1441100461200375878,'big_win_5k','2026-07-08T18:10:19.671381+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430022981559521353,'big_win_5k','2026-07-08T18:10:22.819944+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,418567145249570818,'first_roulette','2026-07-08T18:11:02.504980+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'points_50k','2026-07-08T18:11:21.978399+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1441100461200375878,'wins_5','2026-07-08T18:11:52.983075+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1441100461200375878,'first_loss','2026-07-08T18:12:18.429689+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1441100461200375878,'wager_10k','2026-07-08T18:12:19.076391+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,876267780792524863,'first_roulette','2026-07-08T18:12:28.504514+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1441100461200375878,'games_10','2026-07-08T18:14:37.134736+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'wager_50k','2026-07-08T18:15:26.830499+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'profit_10k','2026-07-08T18:21:50.722232+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430022981559521353,'profit_10k','2026-07-08T18:24:48.031721+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430214127426736272,'wins_25','2026-07-08T18:49:41.053257+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,291401995712200704,'first_bet','2026-07-08T18:50:06.228142+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,291401995712200704,'first_scratch','2026-07-08T18:50:06.882307+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,291401995712200704,'first_loss','2026-07-08T18:50:07.558647+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,291401995712200704,'first_blackjack','2026-07-08T18:50:29.802054+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,291401995712200704,'first_win','2026-07-08T18:52:09.819640+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,291401995712200704,'first_coin_flip','2026-07-08T18:52:34.963172+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1511581440981205078,'first_bet','2026-07-08T18:53:42.923116+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1511581440981205078,'first_scratch','2026-07-08T18:53:43.580503+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1511581440981205078,'first_loss','2026-07-08T18:53:44.212294+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1511581440981205078,'first_blackjack','2026-07-08T18:54:46.115698+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516104057780174893,'first_bet','2026-07-08T18:55:29.598200+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516104057780174893,'first_coin_flip','2026-07-08T18:55:32.004907+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516104057780174893,'first_loss','2026-07-08T18:55:33.561441+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516104057780174893,'first_win','2026-07-08T18:56:20.053654+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1441100461200375878,'points_50k','2026-07-08T18:57:23.303086+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1281861244860764160,'wager_10k','2026-07-08T19:02:48.798886+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516104057780174893,'first_dice','2026-07-08T19:02:53.748619+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1441100461200375878,'wager_50k','2026-07-08T19:03:58.292495+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'wager_10k','2026-07-08T19:07:38.885226+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'wins_25','2026-07-08T19:07:50.659466+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,743167735055515770,'first_roulette','2026-07-08T19:10:00.760167+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,743167735055515770,'first_win','2026-07-08T19:10:01.392379+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1441100461200375878,'first_dice','2026-07-08T19:11:27.302586+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,743167735055515770,'big_win_1k','2026-07-08T19:12:29.949535+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516104057780174893,'wins_5','2026-07-08T19:12:44.559429+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516104057780174893,'games_10','2026-07-08T19:13:08.255570+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516104057780174893,'first_duel','2026-07-08T19:14:05.629845+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1441100461200375878,'wins_25','2026-07-08T19:14:15.401259+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1441100461200375878,'profit_10k','2026-07-08T19:15:08.197106+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1441100461200375878,'games_50','2026-07-08T19:15:34.142092+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,291401995712200704,'wins_5','2026-07-08T19:16:06.559437+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,291401995712200704,'big_win_1k','2026-07-08T19:16:06.634633+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,291401995712200704,'games_10','2026-07-08T19:17:44.059152+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'big_win_1k','2026-07-08T19:18:16.178290+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1230689087716065324,'first_roulette','2026-07-08T19:22:53.073594+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,876267780792524863,'first_slot','2026-07-08T19:23:39.242647+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1230689087716065324,'first_slot','2026-07-08T19:23:49.031207+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1441100461200375878,'first_duel','2026-07-08T19:27:06.841464+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1211780100043841538,'first_win','2026-07-08T19:27:21.804506+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1211780100043841538,'scratch_win','2026-07-08T19:27:22.501885+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1211780100043841538,'games_10','2026-07-08T19:27:23.217662+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1211780100043841538,'wins_5','2026-07-08T19:27:23.268662+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1211780100043841538,'points_10k','2026-07-08T19:27:23.319439+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1211780100043841538,'big_win_1k','2026-07-08T19:27:23.366689+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,743167735055515770,'games_10','2026-07-08T19:29:34.490132+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1441100461200375878,'duel_win','2026-07-08T19:29:40.266788+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516104057780174893,'duel_win','2026-07-08T19:30:59.386113+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1230689087716065324,'first_scratch','2026-07-08T19:31:57.528798+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1230689087716065324,'scratch_win','2026-07-08T19:32:46.806559+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1230689087716065324,'first_mascot_race','2026-07-08T19:34:25.501731+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516104057780174893,'first_scratch','2026-07-08T19:35:30.492495+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516104057780174893,'scratch_win','2026-07-08T19:36:01.224420+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1211780100043841538,'first_roulette','2026-07-08T19:38:01.913711+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1353471433212428308,'games_50','2026-07-08T20:01:45.031080+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1353471433212428308,'wins_25','2026-07-08T20:05:34.531825+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,887470727962431528,'first_bet','2026-07-08T21:03:55.371274+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,887470727962431528,'first_scratch','2026-07-08T21:03:56.068566+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,887470727962431528,'first_loss','2026-07-08T21:03:56.732588+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,887470727962431528,'first_win','2026-07-08T21:04:14.186941+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,887470727962431528,'scratch_win','2026-07-08T21:04:14.839713+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,887470727962431528,'big_win_1k','2026-07-08T21:04:55.397916+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,887470727962431528,'points_10k','2026-07-08T21:05:27.922147+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,887470727962431528,'big_win_5k','2026-07-08T21:05:27.980024+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,887470727962431528,'games_10','2026-07-08T21:07:02.776694+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,887470727962431528,'wins_5','2026-07-08T21:09:03.827593+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,887470727962431528,'scratch_veteran','2026-07-08T21:09:46.767270+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430214127426736272,'first_scratch','2026-07-08T21:09:58.847592+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,887470727962431528,'wager_10k','2026-07-08T21:10:39.351456+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,887470727962431528,'profit_10k','2026-07-08T21:11:04.751599+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430214127426736272,'first_roulette','2026-07-08T21:22:02.289304+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430214127426736272,'first_slot','2026-07-08T21:23:44.446652+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,887470727962431528,'games_50','2026-07-08T21:23:45.123755+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430214127426736272,'first_blackjack','2026-07-08T21:26:30.545598+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,887470727962431528,'first_roulette','2026-07-08T21:27:58.633758+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430214127426736272,'blackjack_streak_3','2026-07-08T21:39:33.527549+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,291401995712200704,'points_10k','2026-07-08T23:38:20.082260+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,291401995712200704,'first_roulette','2026-07-08T23:40:13.599636+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,291401995712200704,'wager_10k','2026-07-08T23:40:33.522426+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,291401995712200704,'blackjack_streak_3','2026-07-08T23:42:42.218740+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,291401995712200704,'first_duel','2026-07-08T23:48:21.375500+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,291401995712200704,'duel_win','2026-07-08T23:48:23.430804+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1441100461200375878,'first_blackjack','2026-07-09T00:00:27.606756+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1430214127426736272,'first_mascot_race','2026-07-09T00:06:00.087372+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,996575450950275153,'blackjack_streak_3','2026-07-09T00:28:52.771726+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516213487678787634,'first_duel','2026-07-09T00:57:15.422948+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1364700235737206814,'duel_king','2026-07-09T00:57:19.639905+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516104057780174893,'first_blackjack','2026-07-09T01:28:11.854824+00:00');
INSERT INTO "user_game_achievements" VALUES(1330479704007905360,1516213487678787634,'big_win_5k','2026-07-09T01:31:44.342163+00:00');
CREATE INDEX idx_bolao_events_active
                    ON bolao_events(is_active, created_at)
                    ;
CREATE INDEX idx_bolao_guesses_event_user
                    ON bolao_guesses(bolao_id, user_id)
                    ;
CREATE INDEX idx_forms_active
                    ON forms(is_active, created_at)
                    ;
CREATE INDEX idx_form_responses_form_user
                    ON form_responses(form_id, user_id)
                    ;
CREATE INDEX idx_bolao_events_message
                    ON bolao_events(message_id)
                    ;
CREATE INDEX idx_bolao_guesses_winning
                    ON bolao_guesses(
                        bolao_id,
                        score_team_1,
                        score_team_2,
                        created_at
                    )
                    ;
CREATE INDEX idx_forms_active_published
                    ON forms(is_active, message_id, created_at)
                    ;
CREATE INDEX idx_match_bet_matches_active
                    ON match_bet_matches(guild_id, is_active, created_at)
                    ;
CREATE INDEX idx_match_bet_matches_message
                    ON match_bet_matches(message_id)
                    ;
CREATE INDEX idx_match_bet_tickets_match
                    ON match_bet_tickets(match_id, status, created_at)
                    ;
CREATE INDEX idx_match_bet_tickets_user
                    ON match_bet_tickets(guild_id, user_id, created_at)
                    ;
CREATE INDEX idx_collective_races_open
                    ON collective_races(guild_id, status, closes_at)
                    ;
CREATE INDEX idx_collective_race_bets_race
                    ON collective_race_bets(race_id, status, created_at)
                    ;
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('forms',1);
INSERT INTO "sqlite_sequence" VALUES('form_responses',2);
INSERT INTO "sqlite_sequence" VALUES('bolao_events',4);
INSERT INTO "sqlite_sequence" VALUES('match_bet_matches',3);
INSERT INTO "sqlite_sequence" VALUES('match_bet_tickets',21);
INSERT INTO "sqlite_sequence" VALUES('game_achievements',250023);
INSERT INTO "sqlite_sequence" VALUES('bolao_guesses',24);
INSERT INTO "sqlite_sequence" VALUES('collective_races',4);
INSERT INTO "sqlite_sequence" VALUES('collective_race_bets',10);
COMMIT;
