# Decide se um comando administrativo roda automaticamente ou exige
# confirmação — a única lógica de decisão do pacote, separada da
# execução (executor.py) e da lista em si (whitelist.py).
import re
from dataclasses import dataclass

from . import whitelist

# Qualquer caractere de encadeamento/redirecionamento de shell — se
# presente, o comando NUNCA roda automaticamente, mesmo que o começo
# dele bata com um prefixo da whitelist (ex: 'winget upgrade --all &
# del /f /q C:\' começa igual ao padrão aprovado, mas não é o mesmo
# comando).
_PADRAO_ENCADEAMENTO = re.compile(r"[&|;`\n]|\$\(|<|>")

# Comandos que baixam ou executam algo fora do winget/gerenciador
# oficial — categoria de atenção extra do pedido original: mesmo que
# pareçam inofensivos, exigem confirmação sempre.
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

    # A checagem de encadeamento vem antes da whitelist de propósito:
    # nunca deixamos um comando com esses caracteres passar batido só
    # porque o início bate com um padrão aprovado.
    if encadeado:
        return Decisao(
            False,
            risco_elevado,
            "O comando contém caracteres de encadeamento ou "
            "redirecionamento (&, |, ;, `, $(), <, >) — nunca é "
            "executado automaticamente, mesmo que pareça bater com "
            "um item da whitelist.",
        )

    # Mesma ideia: risco elevado sempre exige confirmação, mesmo que
    # o comando também bata com a whitelist (não deveria bater, já
    # que nenhuma entrada inicial usa esses padrões, mas a checagem
    # não depende disso continuar sendo verdade no futuro).
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
