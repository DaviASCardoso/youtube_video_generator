"""Motor de formulário schema-driven do Controle.

Em vez de declarar um `Form(...)` e um `<input>` por knob, o painel percorre o dict
de defaults do pilar (`*_PADRAO`) mesclado com o config salvo do tipo e gera a árvore
de campos; um `UI_HINTS` opcional por pilar dá rótulo/ajuda/limites/opções/avançado.
Assim, um knob novo no PADRAO aparece sozinho — Control não precisa ser reeditado.

Duas funções compõem o ciclo:
- `arvore(padrao, atual, hints)` → lista de `Campo`/`Grupo` para a macro renderizar
  (mostra o valor atual, o default e um selo quando o valor sobrescreve o default).
- `reagrupar(form, padrao, hints)` → reconstrói o dict aninhado a partir dos campos
  achatados do POST, coagindo cada folha pelo **tipo do default** no PADRAO. O dict
  resultante é validado pelo Pydantic do pilar e salvo (preservando os blocos irmãos).

O tipo de cada campo é inferido do tipo Python do default: bool→checkbox,
int/float→number, list→lista (texto), str→text (ou select se o hint traz `opcoes`,
ou textarea se `multilinha`), None→campo opcional (texto, vazio vira None).
"""

from dataclasses import dataclass, field


@dataclass
class Campo:
    kind = "campo"
    path: str
    nome: str  # nome achatado do form (path com "__")
    tipo: str  # checkbox | number | text | textarea | select | lista
    valor: object
    default: object
    override: bool
    rotulo: str
    ajuda: str = ""
    opcoes: list = field(default_factory=list)  # [(valor, rotulo)]
    passo: str = ""
    minimo: object = None
    maximo: object = None
    default_exibicao: str = ""


@dataclass
class Grupo:
    kind = "grupo"
    rotulo: str
    avancado: bool
    ajuda: str
    itens: list


def humanizar(chave: str) -> str:
    return chave.replace("_", " ").strip().capitalize()


def _exibir(valor) -> str:
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if valor is None or valor == "":
        return "—"
    if isinstance(valor, list):
        return ", ".join(str(x) for x in valor) if valor else "—"
    return str(valor)


def _tipo_display(dval, hint: dict) -> str:
    if "tipo" in hint:
        return hint["tipo"]
    if isinstance(dval, bool):
        return "checkbox"
    if isinstance(dval, (int, float)):
        return "number"
    if isinstance(dval, list):
        return "lista"
    if dval is None:
        return "text"
    # str
    if hint.get("opcoes"):
        return "select"
    if hint.get("multilinha"):
        return "textarea"
    return "text"


def _opcoes(hint: dict) -> list:
    """Normaliza opções do select em [(valor, rotulo)]."""
    ops = hint.get("opcoes") or []
    rotulos = hint.get("rotulos_opcoes") or {}
    return [(o, rotulos.get(o, o)) for o in ops]


def _campo(path: str, dval, aval, hint: dict) -> Campo:
    tipo = _tipo_display(dval, hint)
    passo = hint.get("passo", "")
    if not passo and tipo == "number":
        passo = "any" if isinstance(dval, float) else "1"
    return Campo(
        path=path,
        nome=path.replace(".", "__"),
        tipo=tipo,
        valor=aval,
        default=dval,
        override=(aval != dval),
        rotulo=hint.get("rotulo", humanizar(path.split(".")[-1])),
        ajuda=hint.get("ajuda", ""),
        opcoes=_opcoes(hint),
        passo=passo,
        minimo=hint.get("min"),
        maximo=hint.get("max"),
        default_exibicao=_exibir(dval),
    )


def arvore(padrao: dict, atual: dict | None, hints: dict | None = None, prefixo: str = "") -> list:
    """Constrói a árvore de campos a partir dos defaults + valores atuais.

    Um dict aninhado vira um `Grupo` (fieldset/details); uma folha vira um `Campo`.
    Campos com hint `oculto` são pulados (ex.: knobs que outra aba já edita).
    """
    hints = hints or {}
    atual = atual if isinstance(atual, dict) else {}
    itens = []
    for chave, dval in padrao.items():
        path = f"{prefixo}.{chave}" if prefixo else chave
        hint = hints.get(path, {})
        if hint.get("oculto"):
            continue
        aval = atual.get(chave, dval)
        if isinstance(dval, dict):
            filhos = arvore(dval, aval, hints, path)
            if filhos:
                itens.append(
                    Grupo(
                        rotulo=hint.get("rotulo", humanizar(chave)),
                        avancado=hint.get("avancado", False),
                        ajuda=hint.get("ajuda", ""),
                        itens=filhos,
                    )
                )
        else:
            itens.append(_campo(path, dval, aval, hint))
    return itens


def _split_lista(texto: str) -> list:
    partes = []
    for bruto in str(texto).replace(",", "\n").split("\n"):
        p = bruto.strip()
        if p:
            partes.append(p)
    return partes


def _to_num(valor, default):
    try:
        if isinstance(default, bool):  # nunca cai aqui (bool tratado antes), guarda
            return bool(valor)
        if isinstance(default, int):
            return int(valor)
        return float(valor)
    except (TypeError, ValueError):
        return default


def reagrupar(form, padrao: dict, hints: dict | None = None, prefixo: str = "") -> dict:
    """Reconstrói o dict de config a partir dos campos achatados do POST.

    Coage cada folha pelo tipo do default no PADRAO (bool por presença do checkbox,
    int/float por cast com fallback ao default, list por split de linhas/vírgulas).
    Só reconstrói chaves presentes no PADRAO — campos desconhecidos são ignorados.
    """
    hints = hints or {}
    out = {}
    for chave, dval in padrao.items():
        path = f"{prefixo}.{chave}" if prefixo else chave
        hint = hints.get(path, {})
        if hint.get("oculto"):
            continue
        if isinstance(dval, dict):
            out[chave] = reagrupar(form, dval, hints, path)
            continue
        nome = path.replace(".", "__")
        if isinstance(dval, bool):
            out[chave] = nome in form
        elif isinstance(dval, (int, float)):
            out[chave] = _to_num(form.get(nome), dval)
        elif isinstance(dval, list):
            out[chave] = _split_lista(form.get(nome, ""))
        elif dval is None:
            bruto = (form.get(nome) or "").strip()
            if not bruto:
                out[chave] = None
            elif hint.get("tipo") == "number":
                out[chave] = _to_num(bruto, None)
            else:
                out[chave] = bruto
        else:  # str
            out[chave] = form.get(nome, dval)
    return out
