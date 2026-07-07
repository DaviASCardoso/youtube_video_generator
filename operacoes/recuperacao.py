"""Recuperação de runs interrompidos por um reinício.

O scheduler é in-memory: se o processo cai (reboot, deploy, crash) no meio de uma
geração, o registro daquele run fica preso em `status="executando"` para sempre — o
job que o tocava morreu junto. Na subida, `recuperar_execucoes` varre o histórico por
esses órfãos e os **re-enfileira reusando a mesma pasta**: o checkpoint da Geração pula
os estágios que já produziram artefato válido, então o run **retoma de onde parou** em
vez de recomeçar (e sem gastar de novo com o que já foi feito).

Não cria registro novo (reusa o `executando` órfão, respeitando o invariante de um run
por tipo) e não depende de jobstore/DB — só do histórico que já existe. O `enfileirar`
é injetado pelo scheduler (que sabe agendar no executor), mantendo este módulo testável
sem um scheduler em execução.
"""


def recuperar_execucoes(enfileirar) -> list[dict]:
    """Re-enfileira os runs deixados em 'executando' por um reinício anterior.

    Args:
        enfileirar: `(tipo_id, tema, execucao, output_path) -> None` — agenda o run no
            executor (o scheduler passa o seu). `execucao` é o registro órfão em si (para
            reusá-lo, sem `iniciar()` de novo); `output_path` é a pasta do run (ou None se
            não localizável, caso em que a Geração começa numa pasta nova).

    Returns:
        A lista dos registros recuperados (vazia num start limpo).
    """
    from operacoes.execucoes import historico, pasta_da_execucao

    recuperados = []
    for reg in historico.listar():
        if reg.get("status") != "executando":
            continue
        pasta = pasta_da_execucao(reg)
        historico.marcar_recuperado(reg["id"])
        enfileirar(reg["tipo_id"], reg["tema"], reg, str(pasta) if pasta else None)
        recuperados.append(reg)
    return recuperados
