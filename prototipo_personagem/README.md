# Protótipo — personagem + fundo (YouTube Shorts)

> **✅ INTEGRADO AO PIPELINE OFICIAL.** Esta ideia virou o modo `personagem`
> (`imagens.modo` no config do tipo): a lógica agora vive em
> `scripts/compositor.py`, `scripts/pexels.py` e `scripts/generate_scene.py`,
> os PNGs do personagem em `tipos/<id>/assets/personagens/`, e tudo é
> configurável pelo painel web. Esta pasta fica só como referência histórica.

Ideia nova para as imagens: em vez de gerar tudo por IA (que estava trocando e
deformando o personagem), a cena é montada assim:

```
fundo (imagem de banco / stock)  +  PNG do personagem por cima, no canto
```

O personagem é **sempre o mesmo** — você gera os PNGs **manualmente**, um para
cada emoção. Durante o vídeo, a emoção troca conforme o que está sendo dito.
O personagem fica no **canto inferior esquerdo**, que é o único canto livre da
interface do Shorts (a direita tem os botões e a faixa de baixo tem o
título/descrição).

## O que você precisa gerar

Coloque os PNGs em `personagens/`. Formato ideal:

- **PNG com fundo transparente** (recorte só o personagem, sem cenário).
- Personagem **de corpo/busto inteiro, em pé**, virado mais ou menos para a
  câmera. O compositor encosta a base dele na parte de baixo e alinha à
  esquerda — então deixe o personagem "de pé" dentro do PNG, sem muito espaço
  vazio nas laterais.
- Resolução alta (ex.: altura de 1500 px ou mais) para não ficar serrilhado.
- **O mesmo personagem em todas as emoções** — mude só a expressão/pose, não a
  roupa nem a aparência.

### Nomes dos arquivos (exatamente assim)

| Emoção | Nome do arquivo | Quando é usada |
|---|---|---|
| Neutro | `personagem_neutro.png` | Narração comum, padrão |
| Feliz | `personagem_feliz.png` | Momentos positivos, boas notícias |
| Sério | `personagem_serio.png` | Afirmações firmes, alertas |
| Pensativo | `personagem_pensativo.png` | Reflexão, "pense sobre isso" |
| Surpreso | `personagem_surpreso.png` | Revelações, dados inesperados |
| Cético | `personagem_cetico.png` | Dúvida/ironia — a cara da persona |
| Confiante | `personagem_confiante.png` | Conclusões, chamada para ação |

> O **neutro é obrigatório** (é o fallback quando uma emoção específica não
> existe). As outras são opcionais no começo — comece pelo `neutro` e `feliz`
> se quiser testar rápido.

## Fundos (Pexels)

Os fundos são **fotos do Pexels**, buscadas automaticamente. Para cada frase do
roteiro, a IA decide a **emoção** do personagem e um **termo de busca** em
inglês; o pipeline baixa uma foto em retrato do Pexels para esse termo e usa
como fundo.

Você só precisa de uma **chave gratuita** do Pexels
(https://www.pexels.com/api/) no arquivo `.env` da raiz do projeto:

```
PEXELS_API_KEY=sua_chave_aqui
```

> Sem a chave, o pipeline ainda roda, mas usa gradientes de placeholder no lugar
> das fotos. Se quiser, também dá para jogar imagens manuais em `fundos/` — o
> `compositor.py` (prévia estática) usa essas quando existem.

## Rodar o vídeo completo

```
python -m prototipo_personagem.pipeline_proto
```

Isso executa o pipeline inteiro e gera um **vídeo vertical** (Shorts, 1080x1920)
em `saida/video_<data-hora>/video_final.mp4`, junto com o roteiro, os áudios e
os quadros de cada cena. As etapas:

1. **Roteiro** (Groq) — mesma persona "Cético Prático" de sempre.
2. **Emoção + busca por frase** (Groq) — a chamada que antes gerava prompts de
   imagem agora devolve `{emocao, busca}` para cada frase.
3. **Narração** (Google TTS) — um áudio por frase.
4. **Cena** — foto do Pexels (fundo) + PNG do personagem da emoção, no canto.
5. **Montagem** — cada cena dura o tempo do áudio dela; tudo é concatenado.

O que você precisa fornecer: **os PNGs do personagem** (em `personagens/`) e a
**PEXELS_API_KEY** no `.env`. O resto é automático.

## Só a prévia estática (sem gerar vídeo)

Para conferir só o enquadramento, sem gastar API:

```
python -m prototipo_personagem.compositor
```

Gera, em `saida/`, uma prévia por emoção em dois formatos:

- `previa_<emocao>.png` — a cena limpa (como o espectador veria).
- `previa_<emocao>_com_guias.png` — com as **zonas da UI do Shorts** marcadas em
  vermelho, para conferir que o rosto do personagem nunca fica atrás da
  interface.

## Status

Isto é um **protótipo isolado** — não mexe no pipeline oficial (`scripts/`,
`api/`) nem no tipo `cetico_pratico`. Serve para você validar a nova direção
visual (foto de fundo + personagem por emoção). Se aprovar, o próximo passo é
levar essa lógica para o pipeline principal e o painel web.
