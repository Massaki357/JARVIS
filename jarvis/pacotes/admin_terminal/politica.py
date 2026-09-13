import re
from dataclasses import dataclass

from . import whitelist

_PADRAO_ENCADEAMENTO = re.compile(r"[&|;`\n]|\$\(|<|>")

_PADRAO_RISCO_ELEVADO = re.compile(
    r"\bcurl\b|\bwget\b|invoke-webrequest|\biwr\b|start-process"
    r"|\.msi\b|\.exe\b",
    re.IGNORECASE,
)


@dataclass
class Decisao:
    automatico: bool
    risco_elevado: bool
    motivo: str


def avaliar_comando(comando):
    comando = (comando or "").strip()

    if not comando:
        return Decisao(False, False, "Comando vazio.")

    risco_elevado = bool(_PADRAO_RISCO_ELEVADO.search(comando))
    encadeado = bool(_PADRAO_ENCADEAMENTO.search(comando))

    if encadeado:
        return Decisao(
            False,
            risco_elevado,
            "O comando contém caracteres de encadeamento ou "
            "redirecionamento (&, |, ;, `, $(), <, >) — nunca é "
            "executado automaticamente, mesmo que pareça bater com "
            "um item da whitelist.",
        )

    if risco_elevado:
        return Decisao(
            False,
            True,
            "O comando parece baixar ou executar algo de uma fonte "
            "que não é o winget/gerenciador oficial (curl, wget, "
            "Invoke-WebRequest, ou um instalador .exe/.msi direto) "
            "— isso sempre exige confirmação, mesmo que o pedido "
            "pareça inofensivo.",
        )

    if whitelist.corresponde(comando):
        return Decisao(True, False, "Comando corresponde à whitelist.")

    return Decisao(
        False,
        False,
        "Comando não está na lista de aprovação automática.",
    )
