# Faixas econômicas

O sistema classifica cada usuário pelo `balance` de `UserWallet`, o saldo oficial
da economia. A definição fica centralizada em `ECONOMIC_TIERS`, em
`app/core/constants.py`, e a classificação é feita por `EconomicTierService`,
registrado no `AppContainer`.

O serviço retorna um value object `EconomicTier` com:

- identificador estável;
- nome de exibição;
- saldo mínimo;
- saldo máximo, quando existir;
- posição ou nível da faixa.

## Convenção dos limites

Os saldos são inteiros e os limites inferior e superior são inclusivos. As
faixas são contínuas: o início de cada faixa é uma moeda acima do fim da
anterior. A última faixa não possui limite superior.

Saldos negativos, embora não devam ocorrer nas operações normais, são tratados
explicitamente como faixa Inicial. A classificação somente normaliza o valor
para essa consulta; ela não altera nem persiste o saldo recebido. Valores que
não sejam inteiros são rejeitados.

## Tabela padrão

| Nível | Identificador | Nome | Saldo mínimo | Saldo máximo |
|---:|---|---|---:|---:|
| 1 | `initial` | Inicial | 0 | 5.000 |
| 2 | `emerging` | Emergente | 5.001 | 25.000 |
| 3 | `prosperous` | Próspero | 25.001 | 99.999 |
| 4 | `tycoon` | Magnata | 100.000 | 350.000 |
| 5 | `millionaire` | Milionário | 350.001 | sem limite |

Não há uma distribuição de saldos versionada no projeto. Por isso, os limites
intermediários e superior são valores padrão fáceis de recalibrar: separam a
progressão inicial, a consolidação e o grande patrimônio, preservando as
referências de 0 a 5.000 e de 100.000 a 350.000 moedas.

Para recalibrar as faixas, altere somente `ECONOMIC_TIERS`. Na inicialização, o
serviço valida o início em zero, níveis sequenciais, identificadores únicos,
limites válidos, continuidade e a existência de uma faixa final aberta.

## Uso pelos limitadores

A classificação é consumida pela política econômica central antes das rodadas
e dos pagamentos elegíveis. As faixas Inicial e Emergente, níveis 1 e 2, são
isentas dos limitadores. A partir da faixa Próspero, nível 3, podem ser aplicados
a dificuldade progressiva e o teto diário de lucro descritos em
`docs/limitadores-economicos.md`.

O restante da economia continua usando o mesmo saldo oficial; a classificação
não cria carteira, moeda ou saldo paralelo.
