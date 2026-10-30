# Reações de derrota

Atlases transparentes criados com imagegen integrado em 27/10/2026, preservando
os sprites e as fotos originais. Cada pessoa recebe quatro quadros para cada reação:

- Segundo lugar: palmas lentas e expressão de decepção.
- Terceiro lugar: mão no rosto e frustração.
- Quarto lugar: sentado, exausto, cobrindo o rosto e suspirando.

Os prompts, referências, recortes e pivôs ficam em `../manifest_defeat.json`.
As imagens geradas são copiadas integralmente; o jogo faz os recortes em memória.

Arquivos: `emannoel.png`, `john.png`, `julio.png`, `luiz.png`, `vini.png` e `yan.png`.
São 72 novos quadros. `preview.png` mostra as reações renderizadas pelo jogo;
`podium_preview.png` mostra a tela final com as quatro colocações.

## Classificação

Pódio e tabela usam a mesma classificação. O objetivo da partida define o vencedor;
entre as demais posições, dano causado e menos quedas desempatam pontuações iguais.
Empates exatos compartilham a colocação. Em sobrevivência e batata quente, quem é
eliminado por último fica à frente de quem caiu antes. Duplas e grupos compartilham
suas colocações; derrota em ondas/fuga usa a reação de cansaço para a equipe inteira,
sem inventar colocações individuais. Empates não exibem derrota nem comemoração.

Os trajes originais usam braços e pernas articulados pelo renderer. PNGs importados
continuam funcionando com uma animação por partes em memória, preservando a textura.
