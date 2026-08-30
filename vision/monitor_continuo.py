# asyncio é usado pelo MonitorTelaContinuo para rodar o loop
# de captura em segundo plano sem bloquear quem o utiliza.
import asyncio
# time mede o tempo decorrido para controlar o timeout
# automático da visualização contínua.
import time

# Função que captura um frame da tela e retorna a imagem em bytes.
from vision.screen_capture import capturar_tela_bytes


# Intervalo padrão entre capturas consecutivas, em segundos.
INTERVALO_PADRAO_VISUALIZACAO = 1.5

# Tempo máximo padrão de execução contínua, em segundos,
# antes do encerramento automático por segurança.
TIMEOUT_PADRAO_VISUALIZACAO = 90


# Captura frames da tela em loop, em intervalos regulares,
# até ser interrompido manualmente ou atingir o tempo máximo.
# Não depende do Gemini nem do PySide: recebe apenas um callback
# assíncrono chamado a cada frame capturado, podendo ser
# reaproveitado em qualquer outro projeto assíncrono.
class MonitorTelaContinuo:

    def __init__(
        self,
        callback_frame,
        intervalo_segundos=INTERVALO_PADRAO_VISUALIZACAO,
        timeout_segundos=TIMEOUT_PADRAO_VISUALIZACAO,
        callback_encerrado=None,
    ):
        # Função assíncrona chamada a cada frame capturado,
        # recebendo os bytes JPEG do frame.
        self.callback_frame = callback_frame
        # Intervalo entre capturas consecutivas.
        self.intervalo_segundos = intervalo_segundos
        # Tempo máximo de execução antes do encerramento automático.
        self.timeout_segundos = timeout_segundos
        # Função assíncrona opcional chamada quando o monitor se
        # encerra sozinho por timeout, sem parar() ter sido chamado.
        self.callback_encerrado = callback_encerrado

        # Indica se o loop de captura está em execução.
        self.ativo = False
        # Referência para a tarefa asyncio do loop de captura.
        self._tarefa = None

    @property
    def esta_ativo(self):
        return self.ativo

    # Inicia o loop de captura em segundo plano.
    # Não faz nada se o monitor já estiver ativo.
    async def iniciar(self):
        if self.ativo:
            return

        self.ativo = True

        self._tarefa = asyncio.create_task(
            self._executar()
        )

    # Interrompe o loop de captura manualmente.
    # Não dispara callback_encerrado, pois o encerramento
    # não ocorreu por timeout.
    async def parar(self):
        if not self.ativo:
            return

        self.ativo = False

        if self._tarefa:
            self._tarefa.cancel()

            try:
                await self._tarefa

            except asyncio.CancelledError:
                pass

            self._tarefa = None

    # Loop principal: captura um frame, aguarda o intervalo
    # configurado e repete, até ser cancelado ou atingir o timeout.
    async def _executar(self):
        # Marca o instante inicial para controlar o timeout.
        inicio = time.monotonic()

        while self.ativo:
            # Encerra automaticamente ao atingir o tempo máximo,
            # mesmo que parar() nunca tenha sido chamado.
            if (
                time.monotonic() - inicio
                >= self.timeout_segundos
            ):
                self.ativo = False

                if self.callback_encerrado:
                    await self.callback_encerrado()

                break

            # A captura é síncrona e bloqueante, por isso roda
            # em uma thread separada para não travar o loop.
            frame_bytes = await asyncio.to_thread(
                capturar_tela_bytes
            )

            await self.callback_frame(
                frame_bytes
            )

            await asyncio.sleep(
                self.intervalo_segundos
            )
