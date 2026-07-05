"""Variação deliberada da Geração — anti-repetição = sobrevivência de política.

Nenhum vídeo pode parecer idêntico ao anterior. A variação atua no **nível do
prompt**: injeta, com probabilidade proporcional ao knob (0..1), uma diretriz de
abertura / estrutura / estilo visual, e escolhe a faixa de música quando há várias.
`0` = identidade (nada muda); `1` = sempre varia. Semeável para testes determinísticos.

Como atua no texto enviado ao LLM (que os testes mockam ignorando o prompt), a suíte
segue verde; só a saída **real** muda — e ela já era não-determinística pelo modelo.
"""

import random

# Diretrizes de abertura anexadas ao system prompt do roteiro.
ABERTURAS = [
    "Comece com uma pergunta provocativa.",
    "Comece com uma afirmação contra-intuitiva.",
    "Comece com uma cena concreta do dia a dia.",
    "Comece com um dado ou número surpreendente.",
    "Comece direto com o conselho mais importante.",
    "Comece com um erro comum que quase todo mundo comete.",
]

# Diretrizes de estrutura do roteiro.
ESTRUTURAS = [
    "Estruture como uma lista de passos.",
    "Estruture como um antes-e-depois.",
    "Estruture como mito versus realidade.",
    "Estruture aprofundando uma única ideia central.",
    "Estruture como pergunta e resposta.",
]

# Modificadores de estilo anexados ao prompt visual.
ESTILOS_VISUAIS = [
    "tom cinematográfico",
    "cores quentes e vibrantes",
    "atmosfera minimalista",
    "contraste dramático",
    "paleta suave e natural",
]


def _sortear(pool: list, intensidade: float, rng: random.Random):
    """Com probabilidade `intensidade`, devolve um item do pool; senão, `None`."""
    if intensidade <= 0 or not pool:
        return None
    if rng.random() >= intensidade:
        return None
    return rng.choice(pool)


class Variacao:
    """Aplica variação a um único run. Semeado a partir de `variacao.semente`
    (ou de um argumento explícito), garantindo determinismo quando se quer.
    """

    def __init__(self, cfg_variacao: dict, semente=None):
        cfg = cfg_variacao or {}
        s = semente if semente is not None else cfg.get("semente")
        self._rng = random.Random(s)
        self._cfg = cfg

    def _knob(self, nome: str) -> float:
        return float(self._cfg.get(nome, 0.0) or 0.0)

    def abertura(self):
        return _sortear(ABERTURAS, self._knob("aberturas"), self._rng)

    def estrutura(self):
        return _sortear(ESTRUTURAS, self._knob("estrutura"), self._rng)

    def estilo_visual(self):
        return _sortear(ESTILOS_VISUAIS, self._knob("estilo_visual"), self._rng)

    def aplicar_ao_roteiro(self, system_prompt: str) -> str:
        """Anexa diretrizes de abertura/estrutura ao system prompt do roteiro.
        Sem variação sorteada, devolve o prompt intacto (identidade)."""
        extras = [d for d in (self.abertura(), self.estrutura()) if d]
        if not extras:
            return system_prompt
        return system_prompt.rstrip() + "\n\n" + "\n".join(extras)

    def aplicar_ao_estilo(self, style_prompt: str) -> str:
        """Anexa um modificador de estilo ao prompt visual. Identidade se nada sorteado."""
        estilo = self.estilo_visual()
        if not estilo:
            return style_prompt
        base = (style_prompt or "").rstrip().rstrip(",")
        return f"{base}, {estilo}" if base else estilo

    def musica(self, arquivos: list):
        """Escolhe uma faixa entre as disponíveis. Lista vazia → `None`; sem variação
        sorteada → a primeira (determinístico)."""
        if not arquivos:
            return None
        escolhido = _sortear(arquivos, self._knob("musica"), self._rng)
        return escolhido if escolhido is not None else arquivos[0]
