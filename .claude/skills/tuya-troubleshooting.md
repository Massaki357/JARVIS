---
name: tuya-troubleshooting
description: Problemas reais já enfrentados e resolvidos (ou identificados) ao integrar o pacote casa_inteligente com a Tuya IoT Platform — consulte antes de assumir que um erro da API Tuya é um bug de código.
---

# Troubleshooting Tuya (casa_inteligente)

Estes são problemas **reais**, confirmados durante o desenvolvimento de
`casa_inteligente/`, não hipóteses. Se um sintoma parecido aparecer de novo, comece por
aqui antes de assumir que é um bug de código — a causa quase sempre foi configuração da
conta/projeto na Tuya IoT Platform, não a lógica em `tuya_client.py`/
`dispositivos_tuya.py`.

**Regra geral do projeto**: nunca adivinhe endpoint, Data Center, DP code ou nome de
key da API Tuya. Confirme ao vivo (painel da IoT Platform, debug de dispositivo, ou
documentação oficial) e deixe o comentário no código citando onde foi confirmado — é
assim que `casa_inteligente/config.py` já documenta `TUYA_API_ENDPOINT` e
`DP_CODE_SWITCH_PADRAO`.

## 1. App "KaBuM Smart" não aparece na lista de apps linkáveis

**Sintoma**: ao tentar usar o fluxo "Link Tuya App Account" da Cloud Project (que
vincula os dispositivos já pareados num app Tuya de terceiros à Cloud Project, pra API
enxergá-los), o app usado para parear o interruptor real — "KaBuM Smart", um app
white-label da KaBuM baseado na plataforma Tuya — não estava na lista de apps que esse
fluxo aceita linkar.

**Causa**: o "Link Tuya App Account" só reconhece uma lista fechada de apps (os
oficiais "Smart Life"/"Tuya Smart" e alguns white-labels específicos autorizados pela
Tuya) — apps white-label de terceiros fora dessa lista, mesmo rodando sobre a mesma
plataforma Tuya por trás, não entram nesse fluxo de vinculação.

**Contorno usado**: resetar o dispositivo físico (o interruptor 3-gang "KaBuM! Smart
Interruptor Inteligente 3") e pareá-lo de novo do zero usando o app oficial "Smart
Life" (ou "Tuya Smart") em vez do KaBuM Smart. Uma vez pareado por um desses apps
oficiais, o "Link Tuya App Account" da Cloud Project encontrou a conta normalmente e os
dispositivos passaram a aparecer em `GET /v1.0/users/{uid}/devices`.

**Se isso acontecer de novo**: antes de investigar código, confirme qual app foi usado
pra parear o dispositivo fisicamente. Se for um app white-label de fabricante (não
"Smart Life"/"Tuya Smart"), o caminho mais confiável é reparear pelo app oficial — não
existe (até onde foi confirmado aqui) uma forma de forçar o "Link Tuya App Account" a
reconhecer um app fora da lista dele.

## 2. `code 28841107` — "No permission. The data center is suspended..."

**Sintoma**: toda chamada de API específica de dispositivo (`.../devices`,
`.../commands`) falhava com `code 28841107`, mesmo com endpoint correto, `device_id`
correto, e o mesmo comando funcionando ao vivo no painel de debug de dispositivo da
própria IoT Platform (rodando em paralelo, sem erro). O Cloud Project mostrava IoT Core
como "authorized" e os dispositivos já linkados via Smart Life.

**Causa mais provável**: atraso de propagação no backend da Tuya para Cloud Projects
recém-criados — não uma assinatura suspensa de verdade (o "suspended" da mensagem é
enganoso) nem um problema de configuração. `TuyaOpenAPI.connect()` retorna
`success: true` (token válido) mesmo quando esse atraso está em vigor, porque o
endpoint de autenticação é mais permissivo que os endpoints de dados de dispositivo —
**um `connect()` bem-sucedido não é prova de que o projeto/endpoint está
correto/liberado**, só de que Access ID/Secret são válidos.

**Como foi confirmado que não era bug de config**: antes de aceitar essa explicação,
foi feita uma prova explícita de que o script de teste estava lendo o `.env` atualizado
(hash SHA-256 do conteúdo do `.env` + mtime + impressão do Access ID/endpoint
exatos usados na chamada que falhava), eliminando a hipótese de estar testando contra
um valor antigo/cacheado. Com isso descartado, e com o endpoint confirmado batendo com
o Data Center real do projeto (ver item 3), sobrou só a explicação de propagação do
lado da Tuya.

**Se isso acontecer de novo**: verifique `code`/`msg` da resposta primeiro. Se for
exatamente `28841107` num Cloud Project criado recentemente, é razoável esperar (sem
prazo confirmado — não foi cronometrado aqui) e testar de novo depois, em vez de
assumir que há algo errado no wiring. Não é um erro tratado especificamente em
`tuya_client.enviar_comando()` — ele cai no caminho genérico de "não teve sucesso" e
retorna a `msg` crua da API, que é o comportamento certo (não mascarar o erro real).

## 3. Data Center: da conta pessoal vs. do Cloud Project

**Sintoma/risco**: existe mais de um "Data Center" possível pra contas Tuya nas
Américas (ex: "Western America" e "Eastern America"), e não é o mesmo conceito que a
região da conta pessoal no app Smart Life — é o Data Center do **Cloud Project**
especificamente, configurado na criação do projeto na IoT Platform.

**Como foi confirmado** (não adivinhado): a aba "Overview" do Cloud Project na Tuya IoT
Platform mostra o Data Center exato do projeto. Para este projeto, é "Western America
Data Center", que corresponde a `https://openapi.tuyaus.com` — confirmado lendo esse
campo diretamente no painel via automação de navegador, não assumido a partir da
localização do usuário/conta.

**Por que importa**: apontar `TUYA_API_ENDPOINT` pro Data Center errado não falha
sempre de forma óbvia — como no item 2, `connect()` pode retornar sucesso mesmo assim.
Só as chamadas de dispositivo revelam o descompasso (dispositivo "não encontrado",
listas vazias, ou o próprio `28841107`).

**Se isso acontecer de novo**: nunca adivinhe o Data Center pelo país/idioma da conta —
confirme na aba Overview do Cloud Project específico sendo usado. Se o projeto for
recriado ou um segundo projeto for adicionado no futuro, repita essa confirmação; não
reaproveite o endpoint de um projeto antigo sem checar.
