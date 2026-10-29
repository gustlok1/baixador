"""Baixador de Vídeos: janela (pywebview) + ponte entre a interface HTML e o núcleo (core.py)."""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import apoio
import core
import sistema

VERSAO = "2.1.0"
# Troque pelo endereço do seu repositório quando publicar. Vazio = o link some da tela Sobre.
REPO_URL = ""
RELEASES_URL = (REPO_URL.rstrip("/") + "/releases") if REPO_URL else ""

# Em PyInstaller os arquivos embutidos ficam em sys._MEIPASS.
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
FUNDO = "#050507"


class Api:
    """Tudo que a interface pode chamar. Métodos que começam com _ não ficam visíveis ao JavaScript."""

    def __init__(self) -> None:
        self._window = None
        self._saindo = False
        self._compacto_antes = None
        self._n = core.Nucleo(emitir=self._empurrar)
        self._apoio = apoio.carregar(BASE)

    # ----------------------------------------------------------- infraestrutura
    def _definir_janela(self, w) -> None:
        self._window = w

    def _empurrar(self, msg: dict) -> None:
        w = self._window
        if not w:
            return
        try:
            w.evaluate_js("window.__baixador && window.__baixador.recebe(%s)" % json.dumps(msg, ensure_ascii=False))
        except Exception:
            pass

    def _perguntar_sair(self, qtd: int) -> None:
        try:
            self._window.evaluate_js("window.__baixador && window.__baixador.perguntarSair(%d)" % qtd)
        except Exception:
            self._encerrar()

    def _ao_fechar(self):
        """Evento 'closing': devolve False para cancelar o fechamento e perguntar na interface."""
        if self._saindo:
            return True
        if self._n.tem_rodando():
            qtd = sum(1 for i in self._n.itens if i.status in ("baixando", "convertendo")) + sum(1 for c in self._n.conversor.snapshot() if c["status"] == "convertendo")
            threading.Thread(target=self._perguntar_sair, args=(max(qtd, 1),), daemon=True).start()
            return False
        self._n.cancelar_para_sair()
        self._n.encerrar()
        return True

    def _encerrar(self) -> None:
        self._saindo = True
        self._n.cancelar_para_sair()
        self._n.encerrar()
        if self._window:
            self._window.destroy()

    # --------------------------------------------------------------------- início
    def init(self) -> dict:
        n = self._n
        cfg = n.config()
        return {
            "app": {"versao": VERSAO, "repo": REPO_URL, "releases": RELEASES_URL},
            "config": cfg,
            "ffmpeg": n.ffmpeg,
            "ytdlp": {"versao": n.versao_ytdlp()},
            "apoio": {k: v for k, v in self._apoio.items() if k != "payload_ok"},
            "historico": n.historico(),
            "fila": (lambda s: s["fila"])(n.snapshot()),
            "conversoes": n.conversor.snapshot(),
            "ffmpeg_dl": dict(n.ffmpeg_dl),
            "ytdlp_up": dict(n.ytdlp_up),
            "primeira_vez": not cfg.get("onboarded"),
        }

    # -------------------------------------------------------------- configurações
    def config_salvar(self, parcial: dict) -> dict:
        return self._n.salvar_config(parcial)

    def barra_titulo(self, escura: bool) -> None:
        sistema.barra_de_titulo("Baixador de Vídeos", bool(escura))

    def escolher_pasta(self, atual: str = "") -> dict:
        return self._dialogo_pasta(atual, "pasta")

    def _dialogo_pasta(self, atual: str, chave: str) -> dict:
        import webview
        tipo = getattr(getattr(webview, "FileDialog", None), "FOLDER", None)
        if tipo is None:
            tipo = webview.FOLDER_DIALOG
        try:
            r = self._window.create_file_dialog(tipo, directory=atual or str(Path.home()))
        except Exception as e:
            return {"ok": False, "erro": str(e)}
        if not r:
            return {"ok": False}
        return {"ok": True, "pasta": r[0]}

    # -------------------------------------------------------------------- ffmpeg
    def ffmpeg_verificar(self) -> dict:
        n = self._n
        n.ffmpeg = n.verificar_ffmpeg()
        return n.ffmpeg

    def ffmpeg_apontar(self) -> dict:
        r = self._dialogo_pasta("", "ffmpeg")
        if not r.get("ok"):
            return {"ok": False}
        return self._n.apontar_ffmpeg(r["pasta"])

    def ffmpeg_usar_path(self) -> dict:
        return self._n.usar_ffmpeg_do_path()

    def ffmpeg_baixar(self) -> None:
        threading.Thread(target=self._n.baixar_ffmpeg, daemon=True).start()

    # -------------------------------------------------------------------- yt-dlp
    def ytdlp_atualizar(self) -> None:
        self._n.atualizar_ytdlp()

    # ----------------------------------------------------------------- histórico
    def historico_limpar(self) -> None:
        self._n.limpar_historico()

    def historico_abrir(self, hid: str, o_que: str) -> dict:
        return self._n.abrir_historico(hid, o_que)

    def historico_baixar_de_novo(self, hid: str) -> dict:
        return self._n.baixar_de_novo(hid)

    # ---------------------------------------------------------------------- fila
    def inspecionar(self, url: str) -> dict:
        return self._n.inspecionar(url)

    def adicionar(self, spec: dict) -> dict:
        return self._n.adicionar(spec)

    def adicionar_rapido(self, url: str, formato: str, qualidade: str) -> dict:
        return self._n.adicionar_rapido(url, formato, qualidade)

    def cancelar_atuais(self) -> None:
        self._n.cancelar_atuais()

    def parar_tudo(self) -> None:
        self._n.parar_tudo()

    def cancelar(self, iid: str) -> None:
        self._n.cancelar(iid)

    def pausar(self, iid: str) -> None:
        self._n.pausar(iid)

    def retomar(self, iid: str) -> None:
        self._n.retomar(iid)

    def tentar_de_novo(self, iid: str) -> None:
        self._n.tentar_de_novo(iid)

    def remover(self, ids: list) -> None:
        self._n.remover([str(i) for i in ids])

    def limpar_concluidos(self) -> None:
        self._n.limpar_concluidos()

    def abrir_item(self, iid: str, o_que: str) -> dict:
        return self._n.abrir_item(iid, o_que)

    # ---------------------------------------------------------------- conversão local
    def converter_escolher(self) -> list:
        """Abre o seletor de arquivos e devolve o que foi escolhido, já lido pelo ffprobe."""
        import webview
        tipo = getattr(getattr(webview, "FileDialog", None), "OPEN", None)
        if tipo is None:
            tipo = webview.OPEN_DIALOG
        try:
            r = self._window.create_file_dialog(
                tipo, allow_multiple=True,
                file_types=("Vídeo e áudio (*.mp4;*.mkv;*.webm;*.mov;*.avi;*.wmv;*.flv;*.m4v;*.mpg;*.mpeg;*.ts;*.3gp;*.mp3;*.m4a;*.wav;*.opus;*.flac;*.ogg;*.aac;*.wma;*.aiff)", "Todos os arquivos (*.*)"))
        except Exception:
            return []
        return self._n.conversor.sondar(list(r or []))

    def converter_sondar(self, caminhos: list) -> list:
        return self._n.conversor.sondar([str(c) for c in caminhos])

    def converter_adicionar(self, arquivos: list, formato: str, nivel: str, pasta: str = "") -> dict:
        return self._n.conversor.adicionar([str(a) for a in arquivos], formato, nivel, pasta)

    def converter_cancelar(self, tid: str) -> None:
        self._n.conversor.cancelar(tid)

    def converter_de_novo(self, tid: str) -> None:
        self._n.conversor.tentar_de_novo(tid)

    def converter_remover(self, ids: list) -> None:
        self._n.conversor.remover([str(i) for i in ids])

    def converter_limpar(self) -> None:
        self._n.conversor.limpar_finalizados()

    def converter_abrir(self, tid: str, o_que: str) -> dict:
        return self._n.conversor.abrir(tid, o_que)

    # ------------------------------------------------------------------- sistema
    def ler_clipboard(self):
        return sistema.ler_clipboard()

    def copiar(self, texto: str) -> bool:
        return sistema.copiar_clipboard(str(texto))

    def abrir_link(self, url: str) -> bool:
        """Só abre http(s): o que vem da interface nunca vira comando."""
        import webbrowser
        url = str(url or "")
        if not url.lower().startswith(("https://", "http://")):
            return False
        return webbrowser.open(url)

    def compacto(self, ligado: bool) -> None:
        w = self._window
        if not w:
            return
        try:
            if ligado:
                self._compacto_antes = (w.width, w.height)
                w.resize(560, 300)
            else:
                larg, alt = self._compacto_antes or (1100, 760)
                w.resize(max(larg, 900), max(alt, 640))
        except Exception:
            pass

    def sair(self, confirmado: bool = False) -> None:
        if confirmado:
            threading.Thread(target=self._encerrar, daemon=True).start()


def main() -> None:
    import webview

    api = Api()
    index = BASE / "web" / "index.html"
    janela = webview.create_window(
        "Baixador de Vídeos", url=index.as_uri(), js_api=api,
        width=1100, height=760, min_size=(460, 270), background_color=FUNDO,
    )
    api._definir_janela(janela)
    janela.events.closing += api._ao_fechar
    gui = "edgechromium" if sys.platform.startswith("win") else None
    try:
        webview.start(gui=gui)
    except Exception as e:
        if sys.platform.startswith("win"):
            sistema.aviso_nativo(
                "Baixador de Vídeos",
                "Não foi possível abrir a janela. Instale o Microsoft Edge WebView2 Runtime "
                "(gratuito, da Microsoft) e abra o app de novo.\n\n" + str(e)[:300],
            )
        raise


if __name__ == "__main__":
    main()
