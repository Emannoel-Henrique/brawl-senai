# A turma no AFTERSHIFT

Seis skins originais inspiradas nas 18 fotografias fornecidas pelo usuário na
pasta `fotos para skins`. Os nomes são os rótulos dos arquivos de referência.
As fotos originais não foram alteradas.

| Skin | Sprite | Detalhes preservados das referências |
| --- | --- | --- |
| EMANNOEL | `emannoel.png` | Cabelo bem curto, bigode discreto, camisa vermelho/branco, calça preta e tênis azul. |
| JOHN | `john.png` | Cabelo ondulado volumoso, camisa vermelho/branco, calça preta e tênis preto. |
| JULIO | `julio.png` | Cabelo cacheado, camiseta creme, calça preta com filete vermelho e tênis branco. |
| LUIZ | `luiz.png` | Cabelo curto com franja e laterais baixas, bigode, camiseta creme, bermuda preta e tênis preto/azul. |
| VINI | `vini.png` | Rabo de cavalo baixo, óculos redondos, bigode e barba discretos, mangas cinzas sob a camisa e tênis verde-lima. |
| YAN | `yan.png` | Franja preta, moletom preto, calça com filete vermelho e tênis preto/branco/vermelho. |

Criadas em 23/10/2026 com a ferramenta integrada **image_gen.imagegen**, com
três referências por pessoa e pedido de fundo transparente. Não foi usado CLI
ou chave de API. Os seis PNG RGBA foram copiados integralmente para esta pasta,
preservando o canal alpha gerado; não houve recorte, recoloração ou alteração
das fotos com scripts. Algumas ilustrações incluem uma leve aura translúcida
gerada ao redor do contorno. Os cantos dos seis arquivos são transparentes.

Todos os personagens têm as mãos vazias: armas, escudos, golpes e efeitos são
desenhados pelo jogo. Os seis PNGs desta pasta continuam sendo os sprites base
originais, preservados para seleção e para referência.

`brawl/skins.py` inclui as seis skins entre os visuais disponíveis de fábrica;
os caminhos são resolvidos a partir da pasta do pacote para acompanhar uma
cópia do projeto. Nenhum cadastro em `user_data` é necessário.

O conjunto exato dos prompts e os nomes das 18 referências estão em
[`manifest.json`](manifest.json), para facilitar futuras revisões.

## Animações da versão 3.2

Cada pessoa agora tem uma folha própria em [`animations/`](animations), com
**16 poses desenhadas individualmente**: quatro de respiração/piscar, seis de
corrida com braços e pernas alternados, subida e descida do salto, preparação
e impacto de golpe, e duas de comemoração. A corrida e os golpes articulam os
membros; não são cópias do sprite base apenas deslocadas ou rotacionadas.

As seis folhas RGBA têm 1254 × 1254 pixels, organizadas em quatro colunas e
quatro fileiras. Foram criadas em 23/10/2026 com a ferramenta integrada
**image_gen.imagegen**, usando o sprite pronto de cada pessoa como referência
para preservar rosto, cabelo, roupas e acessórios. Os PNGs gerados foram
copiados integralmente, com seu alpha original, sem recorte ou transformação
por scripts. As fotos e os sprites base não foram modificados.

O [manifesto das animações](manifest_animation.json) registra cada prompt,
caminho, sequência, frequência e repetição. Também contém os retângulos exatos
dos 16 personagens, pivôs de pés por fileira e posição da mão nos golpes.
Essas medidas corrigem pequenas variações de alinhamento da folha gerada sem
alterar o PNG: o jogo usa uma escala comum e remove fragmentos de células
vizinhas ao carregar cada frame. Os pivôs preservam a altura intencional dos
saltos e o balanço da corrida.

Arquivos de animação:

| Skin | Folha de animação |
| --- | --- |
| EMANNOEL | [`animations/emannoel.png`](animations/emannoel.png) |
| JOHN | [`animations/john.png`](animations/john.png) |
| JULIO | [`animations/julio.png`](animations/julio.png) |
| LUIZ | [`animations/luiz.png`](animations/luiz.png) |
| VINI | [`animations/vini.png`](animations/vini.png) |
| YAN | [`animations/yan.png`](animations/yan.png) |

`tests/test_animation_assets.py` valida os seis conjuntos, o alpha, os
retângulos e pivôs, além de verificar que os frames de corrida têm silhuetas
diferentes mesmo depois de remover diferenças de posição e tamanho.

## Derrotas por colocação

Em 27/10/2026 foram adicionados 72 quadros de derrota: segundo lugar aplaude
desapontado, terceiro leva a mão ao rosto e quarto se senta exausto.
As seis novas folhas ficam em [`defeats/`](defeats/README.md); o jogo usa o
[`manifesto de derrota`](manifest_defeat.json) com os prompts, recortes e pivôs.
Veja a [prévia das reações](defeats/preview.png) e o [pódio completo](defeats/podium_preview.png).
Vitória e empate mantêm animações próprias, sem comemoração dos derrotados.
