import asyncio
import time

from jarvis.servicos.visao.captura_tela import capturar_tela_bytes


INTERVALO_PADRAO_VISUALIZACAO = 1.5

TIMEOUT_PADRAO_VISUALIZACAO = 90


class MonitorTelaContinuo:
    def __init__(
        self,
        callback_frame,
        intervalo_segundos=INTERVALO_PADRAO_VISUALIZACAO,
        timeout_segundos=TIMEOUT_PADRAO_VISUALIZACAO,
        callback_encerrado=None,
        funcao_captura=capturar_tela_bytes,
    ):
        self.callback_frame = callback_frame
        self.intervalo_segundos = intervalo_segundos
        self.timeout_segundos = timeout_segundos
        self.callback_encerrado = callback_encerrado
        self.funcao_captura = funcao_captura

        self.ativo = False
        self._tarefa = None

    @property
    def esta_ativo(self):
        return self.ativo

    async def iniciar(self):
        if self.ativo:
            return

        self.ativo = True

        self._tarefa = asyncio.create_task(
            self._executar()
        )

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

    async def _executar(self):
        inicio = time.monotonic()

        while self.ativo:
            if (
                time.monotonic() - inicio
                >= self.timeout_segundos
            ):
                self.ativo = False

                if self.callback_encerrado:
                    await self.callback_encerrado()

                break

            frame_bytes = await asyncio.to_thread(
                self.funcao_captura
            )

            await self.callback_frame(
                frame_bytes
            )

            await asyncio.sleep(
                self.intervalo_segundos
            )
