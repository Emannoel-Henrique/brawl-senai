# Brawl SENAI 3.6 — AFTERSHIFT

Abra **jogar.bat** no Windows. Teclado, Xbox e CPU podem dividir a mesma partida.

## Menus, abertura e opções

O jogo abre com uma sequência de ação de 6,2 segundos: dash, tiros, saltos, combos
e quatro combatentes, com cortes em quadrinhos e efeitos sonoros sincronizados.
**Enter / Espaço / A / Esc** ou **Pular** levam à tela inicial. Clique em
**Começar a jogar** para escolher um modo; **Esc** na seleção volta ao início.
Para rever a abertura ou desativá-la na próxima inicialização, abra **Opções**.

Na seleção, os botões maiores têm formato angular, ícones e destaque de foco.
Uma **batalha real de quatro bots** acontece ao fundo: troque a arena em
**Trocar cenário** ou clique na área da batalha para criar impactos visuais.
Use **↑ / ↓** ou a **roda do mouse** para percorrer os modos, **Enter / A**
para entrar e **1–5** para abrir um modo direto. **Tab / Shift+Tab** percorrem os
botões. A descrição do modo acompanha o foco e o movimento do mouse.

No lobby de Arena e Treino, escolha o mapa pelas **setas ao lado da miniatura**.
Os filtros **Todos / Clássicos / Eventos** organizam as dez arenas; Infectados tem
**Todos / Interiores / Exterior** para seus três cenários. A telinha mostra o
layout real do mapa selecionado. **Aleatório** sorteia um cenário a cada partida.

**Opções** está no menu principal e na pausa. Ajuste **brilho (60–140%)**, volume
geral, música e efeitos de forma independente; também há tela cheia, silenciar som
e redução das animações dos menus, que também congela a batalha ao fundo.
**Clique ou arraste as barras**, use **− / +** ou selecione a barra e ajuste com
**← / →**. Brilho, volumes e preferências de animação e abertura são
aplicados na hora e salvos neste computador. Ao voltar das opções abertas na pausa,
a partida continua pausada.

Para capturas e testes, use `--screen title`, `--screen main`, `--screen settings`, `--screen intro`
ou `--skip-intro`. O modo `--headless` inicia direto no menu por padrão.

## Controles, menu e pausa

Cada controle conectado ocupa uma vaga estável. O teclado **WASD fica com a primeira
vaga humana sem controle**: com três controles em P1–P3, WASD controla P4. As vagas
restantes recebem setas, J/L e teclado numérico, nessa ordem. Conectar ou remover
um controle não troca as vagas dos outros controles.

**Só P1 navega nos menus.** Se P1 usa controle, os outros controles, teclado e mouse
não alteram suas opções. Qualquer jogador pode pausar; **somente o dispositivo que
pausou pode navegar na pausa**, inclusive na ajuda aberta por ela. Se esse controle
for desconectado, a pausa libera setas + Enter no teclado para permitir continuar.

No lobby, **BOT: DESLIGADO** ativa CPU; **DESATIVAR BOT** devolve a vaga a um humano.
A dificuldade do bot fica em um botão separado. A escolha é salva.

Para mirar para cima, segure **Q** no layout WASD. Combine com A/D para mirar na
diagonal sem precisar pular. Os outros layouts usam **Page Up / T / Num 9**.
No Xbox, o analógico direito mira livremente em qualquer direção. Arma e mira
acompanham a direção do disparo.

## Infectados: mapas próprios e tela dividida

Escolha **Arena → Infectados**. Os três cenários exclusivos têm andares, atalhos,
cobertura e rotas para despistar a perseguição:

| Mapa | Dimensão | Rotas |
| --- | --- | --- |
| Sanatório 13 | 3840 × 1680 | Enfermarias, sala de cirurgia e escadas de serviço |
| Último Metrô | 4480 × 1560 | Vagões, mezaninos, cabines e trilhos |
| Estufa Zero | 4000 × 1840 | Copas, raízes, depósitos e plantas que impulsionam |

Dois jogadores usam duas telas; três ou quatro usam quadrantes, cada um com câmera
e HUD próprios. Paredes bloqueiam a visão e a mira automática, e nenhum marcador
entrega um oponente fora da tela ou escondido. Sobreviventes vencem após três minutos;
quem morre vira infectado.

Use **E / LB** (ou a interação do seu layout) próximo de um esconderijo para entrar.
Você pode ficar até **15 segundos**, saindo ao se mover, pular, atacar, usar poder
ou interagir novamente. Infectados usam a interação para revistar e expulsar quem
está dentro. Uma arma próxima tem prioridade na interação; pegue-a antes de entrar.

## Ondas: monte sua build

São dez ondas, com chefes nas ondas **3, 5 e 7** e uma dupla na **10**. Cinco das seis
criaturas aparecem por partida, com ordem variável e Verma sempre presente:

- **Náxia, Rainha do Enxame:** alien flutuante, esporos em leque, ácido e filhotes.
- **Gólia, Devorador de Pedra:** monstro com investidas e ondas de impacto saltáveis.
- **Azrak, Senhor das Brasas:** demônio com rajadas de fogo e erupções sinalizadas.
- **Verma, Devoradora do Subsolo:** enterra-se e irrompe sob os jogadores.
- **Aracna, Mãe das Teias:** percorre o teto, despenca e prende com teias.
- **Zéfira, Olho da Tempestade:** teleporta, chama raios e lança orbes perseguidores.

Abaixo de 45% da vida, o chefe entra em uma segunda fase mais agressiva.
Ácido, raízes e fogo mostram a região perigosa antes de ativar. Cada ativação
pode atingir uma pessoa uma vez; zonas ainda não ativadas somem quando o chefe morre.

**Ondas não tem fogo amigo:** tiros atravessam aliados; golpes, explosões e poderes
não tiram a vida nem empurram colegas. Fuga mantém a sabotagem entre jogadores.

Depois das ondas **2, 4, 6 e 8**, cada jogador recebe três cartas em seu próprio
quadrante e escolhe **ao mesmo tempo**, sem ordem de turnos. Use seu analógico / D-pad + A;
no teclado, use seu movimento horizontal + ataque ou interação. Enter e mouse
confirmam somente para o primeiro jogador do teclado. A escolha fica travada em
PRONTO e o combate retoma quando todos confirmam. CPU escolhe automaticamente.
Combate, projéteis, cronômetros e itens ficam congelados; Esc / Start pausa e
preserva as escolhas pendentes.

Há **12 melhorias**, incluindo quatro poderes ativos:

| Poder | Efeito | Recarga base |
| --- | --- | --- |
| Nova Gélida | Dano em área e movimento dos inimigos reduzido por 3,5s | 7s |
| Passo Fantasma | Dash longo com invulnerabilidade e impacto | 5s |
| Chuva de Meteoros | Três explosões sobre o alvo; atravessam plataformas | 9s |
| Pulso Médico | Recupera 32 HP seus e de aliados próximos; escudo breve | 12s |

O poder escolhido substitui o poder atual, no mesmo botão (**G** para P1, **Y / RB** no Xbox).
As outras oito cartas são passivas: vampirismo, velocidade, salto extra, cadência,
economia de munição, vida máxima, dano e recarga. A carta informa o limite de níveis.
As melhorias duram até o fim da partida e sobrevivem ao renascimento; a revanche começa sem build.

## Fuga: três perseguidores

No lobby, escolha o perseguidor ou deixe **Aleatório**, que muda na revanche:

- **Serpe do Vazio:** alien que cospe uma rajada de projéteis.
- **Cão do Apocalipse:** demônio de três cabeças que marca colunas de fogo à frente.
- **Titã do Pântano:** monstro que faz raízes nascerem no trajeto, ferindo e atrasando o grupo.

Eles avançam continuamente. Fuja e alcance a extração; o perseguidor não é um alvo derrotável.
Suprimentos periódicos aparecem à frente dos corredores, fora do alcance imediato do chefe.

## Dificuldade e itens

Selecione **Fácil / Médio / Difícil** no lobby. A preferência fica salva.

| Dificuldade | Armas de fogo / kits | Corpo a corpo | Vida / dano dos inimigos cooperativos |
| --- | --- | --- | --- |
| Fácil | A cada 5s | A cada 6s | 85% / 80% |
| Médio | A cada 8s | A cada 8s | 100% / 100% |
| Difícil | A cada 13s | A cada 16s | 120% / 120% |

Os intervalos são de geração durante o combate: as escolhas e pausas não avançam o relógio.
Armas corpo a corpo param de repor quando já há seis no cenário. Itens iniciais,
recompensas de fim de onda e drops de inimigos complementam esses intervalos.
Drops são mais frequentes no Fácil e mais raros no Difícil. O dano entre jogadores
dos modos versus não muda com essa opção.

## Prévias e verificação

[Criaturas](assets/previews/creatures.png) · [Escolha de habilidades](assets/previews/wave_upgrades.png)
· [Infectados em quatro telas](assets/previews/infected_split.png)
· [Metrô](assets/previews/infected_metro.png) · [Estufa](assets/previews/infected_garden.png)
· [Lobby de Infectados](assets/previews/infected_lobby.png) · [Fuga](assets/previews/escape_boss.png).
As criaturas são desenhos animados pelo renderer em código; nenhuma imagem remota é necessária.

Use o mesmo caminho de bibliotecas do atalho para executar os testes:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path '.venv\Lib\site-packages'
python -B -m unittest discover -s tests -q
```

Preferências e skins pessoais continuam em `user_data/`. Fotos e atlases da turma permanecem preservados.
