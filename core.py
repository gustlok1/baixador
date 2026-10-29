# -*- coding: utf-8 -*-
"""
Núcleo do baixador: fila, yt-dlp, ffmpeg, histórico e configurações.

Não conhece a interface. Quem usa (main.py) passa uma função `emitir(dict)` que recebe
o estado da fila e os avisos; aqui dentro só há lógica, o que permite testar sem janela.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

import sistema

VERSAO = "1.0.0"
PASTA_DADOS = Path.home() / ".baixador_videos"

FORMATOS_VIDEO = ["mp4", "mkv", "webm"]
FORMATOS_AUDIO = ["mp3", "m4a", "wav", "opus", "flac"]
QUALIDADES = ["Melhor", "4K", "1440p", "1080p", "720p", "480p", "360p"]
ALTURA = {"4K": 2160, "1440p": 1440, "1080p": 1080, "720p": 720, "480p": 480, "360p": 360}
LIMITES = {"Sem limite": 0, "1 MB/s": 1 << 20, "5 MB/s": 5 << 20, "10 MB/s": 10 << 20}
NAVEGADORES = ["Não usar", "Chrome", "Edge", "Firefox", "Brave"]
TEMAS = ["dark", "light", "system"]
MAX_HISTORICO = 500

# Builds do ffmpeg mantidas pelo projeto yt-dlp (o mesmo que o yt-dlp recomenda). A "shared" tem ~90 MB.
FFMPEG_URLS = [
    "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip",
    "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
]
YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"

PADRAO = {
    "formato": "mp4",
    "qualidade": "1080p",
    "pasta": str(Path.home() / "Downloads"),
    "playlist": False,
    "simultaneos": 2,
    "limite": "Sem limite",
    "template": "%(title)s.%(ext)s",
    "legendas": False,
    "embutir": True,
    "idiomas": "pt, en",
    "cookies": "Não usar",
    "ffmpeg_dir": "",
    "tema": "dark",
    "compacto": False,
    "avisar": True,
    "abrir_pasta": False,
    "convite": True,
    "onboarded": False,
}

ANSI = re.compile(r"\x1b\[[0-9;]*m")


class Interrompido(Exception):
    """Levantada dentro dos hooks do yt-dlp para parar um download a pedido do usuário."""


# ===================================================================== Utilitários
def limpar(texto) -> str:
    return ANSI.sub("", str(texto)).strip()


def eh_url(texto) -> bool:
    return bool(re.match(r"https?://\S+$", str(texto or "").strip(), re.I))


def vtupla(versao: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", versao or ""))


def fmt_bytes(n) -> str:
    n = float(n or 0)
    unidades = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while n >= 1024 and i < len(unidades) - 1:
        n /= 1024
        i += 1
    texto = f"{n:.0f}" if i <= 1 or n >= 100 else f"{n:.1f}"
    return f"{texto.replace('.', ',')} {unidades[i]}"


def fmt_tempo(seg) -> str:
    seg = int(seg or 0)
    if seg < 60:
        return f"{seg} s"
    if seg < 3600:
        return f"{seg // 60} min {seg % 60} s" if seg % 60 else f"{seg // 60} min"
    return f"{seg // 3600} h {(seg % 3600) // 60} min"


def fmt_dur(seg) -> str:
    if not seg:
        return ""
    seg = int(seg)
    h, resto = divmod(seg, 3600)
    m, s = divmod(resto, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def ler_json(caminho: Path, padrao):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except Exception:
        return padrao


def salvar_json(caminho: Path, dados) -> None:
    """Grava por arquivo temporário, para não corromper se o app fechar no meio."""
    try:
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = caminho.with_suffix(caminho.suffix + ".tmp")
        tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, caminho)
    except Exception:
        pass


def versao_no_zip(arquivo: Path) -> str:
    """Lê a versão do yt-dlp dentro do arquivo único (zipapp) baixado."""
    with zipfile.ZipFile(arquivo) as z:
        codigo = z.read("yt_dlp/version.py").decode("utf-8", "replace")
    m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", codigo)
    return m.group(1) if m else ""


def carregar_ytdlp(pasta_dados: Path = PASTA_DADOS):
    """Importa o yt-dlp. Se o app já baixou uma versão mais nova, usa essa no lugar da embutida."""
    import yt_dlp as embutido

    arq = Path(pasta_dados) / "yt-dlp" / "yt-dlp"
    if not arq.is_file():
        return embutido
    try:
        nova = versao_no_zip(arq)
        atual = getattr(embutido.version, "__version__", "")
        if nova and vtupla(nova) > vtupla(atual):
            for nome in [n for n in sys.modules if n == "yt_dlp" or n.startswith("yt_dlp.")]:
                del sys.modules[nome]
            sys.path.insert(0, str(arq))
            import yt_dlp as novo

            return novo
    except Exception:
        # volta para a versão embutida
        try:
            sys.path.remove(str(arq))
        except ValueError:
            pass
        for nome in [n for n in sys.modules if n == "yt_dlp" or n.startswith("yt_dlp.")]:
            del sys.modules[nome]
        import yt_dlp as embutido2

        return embutido2
    return embutido


def validar_config(entrada: dict, base: dict) -> dict:
    """Aplica `entrada` sobre `base` aceitando só chaves e valores válidos (serve também de migração)."""
    cfg = dict(base)
    for k, v in (entrada or {}).items():
        if k not in PADRAO:
            continue
        if k == "formato":
            f = str(v).split()[0].lower() if str(v).strip() else ""
            if f in FORMATOS_VIDEO + FORMATOS_AUDIO:
                cfg[k] = f
        elif k == "qualidade":
            q = str(v)
            q = "Melhor" if q.startswith("Melhor") else "4K" if q.startswith("2160") else q
            if q in QUALIDADES:
                cfg[k] = q
        elif k == "simultaneos":
            try:
                cfg[k] = max(1, min(5, int(v)))
            except (TypeError, ValueError):
                pass
        elif k == "limite":
            if v in LIMITES:
                cfg[k] = v
        elif k == "cookies":
            if v in NAVEGADORES:
                cfg[k] = v
        elif k == "tema":
            if v in TEMAS:
                cfg[k] = v
        elif k == "template":
            s = str(v).strip()
            if s:
                cfg[k] = s if "%(ext)s" in s else s + ".%(ext)s"
        elif k == "pasta":
            if str(v).strip():
                cfg[k] = str(v).strip()
        elif isinstance(PADRAO[k], bool):
            cfg[k] = bool(v)
        elif isinstance(PADRAO[k], str):
            cfg[k] = str(v)
    return cfg


# ---------------------------------------------------------------------- Erros
ERROS = [
    (r"confirm your age|age-restricted|inappropriate for some",
     "Não foi possível baixar este vídeo",
     "O site pediu login para confirmar a idade. Ative os cookies do navegador em Configurações e tente de novo.",
     "o vídeo exige login"),
    (r"not a bot|confirm you.?re not",
     "O site pediu uma verificação",
     "O site achou o acesso automático e pediu para confirmar que você não é um robô. Ative os cookies do navegador em Configurações › Sistema e tente de novo.",
     "verificação anti-robô"),
    (r"Sign in|log ?in required|private video|members-only|Join this channel",
     "Esse vídeo precisa de login",
     "O vídeo é privado ou exclusivo para membros. Se você tem acesso, ative os cookies do navegador em Configurações › Sistema.",
     "o vídeo exige login"),
    (r"Video unavailable|has been removed|no longer available|does not exist|not available in your country|not made this video available",
     "Vídeo indisponível",
     "O vídeo foi removido, está privado ou não está liberado na sua região.",
     "vídeo indisponível"),
    (r"(ffmpeg|ffprobe).{0,40}(not found|not installed|not available)|ffmpeg.{0,10}is not",
     "ffmpeg não encontrado",
     "Essa conversão precisa do ffmpeg. Instale em Configurações › Sistema e tente de novo.",
     "falta o ffmpeg"),
    (r"HTTP Error 429|Too Many Requests",
     "Muitas tentativas",
     "O site limitou os acessos por um tempo. Espere alguns minutos e tente de novo.",
     "limite do site"),
    (r"HTTP Error 403|Forbidden",
     "Acesso negado pelo site",
     "O site recusou o download (erro 403). Atualize o yt-dlp em Configurações › Sistema e tente de novo.",
     "acesso negado"),
    (r"Unsupported URL|not a valid URL",
     "Link não suportado",
     "Esse endereço não parece ser de um vídeo que o baixador consiga ler.",
     "link não suportado"),
    (r"getaddrinfo|name resolution|Unable to download (webpage|API|video data)|timed out|Connection (reset|refused|aborted)|Network is unreachable|URLError",
     "Sem conexão",
     "Não foi possível falar com o site. Confira sua internet e tente de novo.",
     "sem conexão"),
    (r"Requested format is not available",
     "Qualidade indisponível",
     "O formato ou a qualidade escolhida não existe para este vídeo. Tente \"Melhor\" ou outra qualidade.",
     "qualidade indisponível"),
    (r"No space left|Errno 28|not enough space",
     "Disco cheio",
     "Não há espaço livre na pasta de destino.",
     "disco cheio"),
    (r"Permission denied|Errno 13|Access is denied",
     "Sem permissão para salvar",
     "O baixador não conseguiu gravar na pasta de destino. Escolha outra pasta em Configurações.",
     "sem permissão na pasta"),
]
ERRO_PADRAO = (
    "Não foi possível baixar este vídeo",
    "Algo deu errado no download. Veja o log técnico abaixo. Se o erro se repetir, atualize o yt-dlp em Configurações › Sistema.",
    "erro no download",
)


def traduzir_erro(texto: str) -> tuple[str, str, str]:
    """(título, mensagem amigável, motivo curto) para um erro do yt-dlp."""
    for padrao, titulo, msg, curto in ERROS:
        if re.search(padrao, texto or "", re.I):
            return titulo, msg, curto
    return ERRO_PADRAO


# ------------------------------------------------------------ Qualidade e opções
def tier_de_formatos(formatos) -> int:
    """Maior qualidade (2160, 1440, 1080...) que o vídeo realmente oferece, 0 se não deu para saber.
    Usa a largura também, porque filmes em tela larga têm altura menor que o nome da qualidade."""
    melhor = 0
    for f in formatos or []:
        h, w = f.get("height") or 0, f.get("width") or 0
        if not h or f.get("vcodec") == "none":
            continue
        efetiva = max(h, round(w * 9 / 16)) if w >= h else h
        melhor = max(melhor, efetiva)
    for h in (2160, 1440, 1080, 720, 480, 360):
        if melhor >= h * 0.97:
            return h
    return 0


def qualidades_disponiveis(tier: int) -> list[str]:
    if not tier:
        return list(QUALIDADES)
    return ["Melhor"] + [q for q, h in ALTURA.items() if h <= tier]


def rotulo_formato(formato: str, qualidade: str) -> str:
    if formato in FORMATOS_AUDIO:
        return f"{formato} · 192 kbps" if formato in ("mp3", "m4a", "opus") else formato
    return f"{formato} · {'melhor' if qualidade == 'Melhor' else qualidade}"


def montar_opcoes(*, formato, qualidade, pasta, template, playlist, legendas, embutir, idiomas,
                  cookies, limite_bps, ffmpeg_dir, ffmpeg_ok) -> dict:
    """Opções do yt-dlp para um item. Função pura, para poder testar sem baixar nada."""
    opc: dict = {
        "outtmpl": str(Path(pasta).expanduser() / template),
        "noplaylist": not playlist,
        "quiet": True, "no_warnings": True, "noprogress": True,
        "continuedl": True, "socket_timeout": 20, "retries": 5,
    }
    if limite_bps:
        opc["ratelimit"] = int(limite_bps)
    if cookies and cookies != "Não usar":
        opc["cookiesfrombrowser"] = (cookies.lower(),)
    if ffmpeg_dir:
        opc["ffmpeg_location"] = ffmpeg_dir

    audio = formato in FORMATOS_AUDIO
    if not ffmpeg_ok:
        # Sem ffmpeg não há como juntar nem converter: só o que já vem pronto do site.
        if audio:
            opc["format"] = "bestaudio[ext=m4a]/bestaudio"
        else:
            h = ALTURA.get(qualidade)
            filtro = f"[height<={h}]" if h else ""
            opc["format"] = f"best[ext=mp4]{filtro}/best{filtro}/best"
        return opc

    if audio:
        opc["format"] = "bestaudio/best"
        opc["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": formato,
                                  "preferredquality": "192"}]
        return opc

    h = ALTURA.get(qualidade)
    if h:
        opc["format"] = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
    else:
        opc["format"] = "bestvideo+bestaudio/best"
    opc["merge_output_format"] = formato
    if formato == "mp4":
        opc["format_sort"] = ["res", "ext:mp4:m4a"]  # prefere H.264/AAC, que toca em qualquer lugar
    elif formato == "webm":
        opc["format_sort"] = ["res", "ext:webm:webm"]

    pps = []
    if legendas:
        langs = [x.strip() for x in idiomas.split(",") if x.strip()]
        opc.update(writesubtitles=True, writeautomaticsub=True, subtitleslangs=langs or ["pt", "en"])
        pps.append({"key": "FFmpegSubtitlesConvertor", "format": "srt"})
        if embutir and formato in ("mp4", "mkv"):
            pps.append({"key": "FFmpegEmbedSubtitle"})
    if pps:
        opc["postprocessors"] = pps
    return opc


# ===================================================================== Item da fila
class Item:
    def __init__(self, **kw):
        self.id = ""
        self.url = ""
        self.formato = "mp4"
        self.qualidade = "Melhor"
        self.pasta = ""
        self.playlist = False
        self.legendas = False
        self.embutir = True
        self.idiomas = "pt, en"
        self.titulo = ""
        self.canal = ""
        self.dur = ""
        self.thumb = ""
        self.idx = ""
        self.sub = ""
        self.status = "aguardando"  # aguardando baixando convertendo pausado concluido cancelado erro
        self.pct = 0.0
        self.esq = ""
        self.dir = ""
        self.indet = False
        self.erro = ""
        self.erro_titulo = ""
        self.erro_msg = ""
        self.erro_curto = ""
        self.parou_em = 0
        self.criado = time.time()
        self.fim = None
        self.arquivo = ""
        self.tamanho = 0
        self.removido = False
        self.motivo = ""
        self.cancel = threading.Event()
        self.thread = None
        self._parciais: set[str] = set()
        self._fn = None
        self._feito = 0
        self._atual = 0
        self.__dict__.update(kw)

    def publico(self) -> dict:
        return {
            "id": self.id, "url": self.url, "titulo": self.titulo, "canal": self.canal,
            "dur": self.dur, "thumb": self.thumb, "idx": self.idx, "sub": self.sub,
            "formato": self.formato, "qualidade": self.qualidade,
            "rotulo": rotulo_formato(self.formato, self.qualidade),
            "status": self.status, "pct": round(self.pct, 1), "esq": self.esq, "dir": self.dir,
            "indet": self.indet, "erro": self.erro, "erro_titulo": self.erro_titulo,
            "erro_msg": self.erro_msg, "parou_em": self.parou_em,
            "criado": self.criado, "fim": self.fim, "pasta": self.pasta,
            "arquivo": os.path.basename(self.arquivo) if self.arquivo else "",
        }


ATIVOS = ("aguardando", "baixando", "convertendo")
EM_CURSO = ("baixando", "convertendo")
ENCERRADOS = ("concluido", "cancelado", "erro")


# ======================================================================== Núcleo
class Nucleo:
    def __init__(self, emitir=None, pasta_dados: Path = PASTA_DADOS, yt=None):
        self.emitir = emitir or (lambda _msg: None)
        self.dados = Path(pasta_dados)
        self.arq_config = self.dados / "config.json"
        self.arq_hist = self.dados / "historico.json"
        self.yt = yt if yt is not None else carregar_ytdlp(self.dados)

        self._lock = threading.RLock()
        self.cfg = validar_config(ler_json(self.arq_config, {}), PADRAO)
        self.itens: list[Item] = []
        self._ativos: set[Item] = set()
        self._contador = 0
        self._eventos: list[dict] = []
        self._rodada = 0  # downloads concluídos desde que a fila esvaziou
        self._ultima_pasta = ""
        self.hist: list[dict] = self._carregar_hist()
        self.ffmpeg = self.verificar_ffmpeg()
        self.ffmpeg_dl = {"estado": "ocioso", "pct": 0, "mb": 0, "total_mb": 0, "erro": ""}
        self.ytdlp_up = {"estado": "ocioso", "versao": "", "erro": ""}

        self._sujo = threading.Event()
        self._parar = threading.Event()
        self._emissor = threading.Thread(target=self._loop_emissor, daemon=True)
        self._emissor.start()

    # ------------------------------------------------------------- Emissão para a UI
    def _marcar(self) -> None:
        self._sujo.set()

    def _evento(self, tipo: str, **dados) -> None:
        with self._lock:
            self._eventos.append({"tipo": tipo, **dados})
        self._marcar()

    def _loop_emissor(self) -> None:
        while not self._parar.is_set():
            self._sujo.wait(timeout=1.0)
            if self._parar.is_set():
                break
            if not self._sujo.is_set():
                continue
            time.sleep(0.15)  # junta várias mudanças numa só mensagem
            self._sujo.clear()
            self.empurrar()

    def snapshot(self) -> dict:
        with self._lock:
            msg = {
                "tipo": "estado",
                "fila": [i.publico() for i in self.itens],
                "ffmpeg_dl": dict(self.ffmpeg_dl),
                "ytdlp_up": dict(self.ytdlp_up),
                "eventos": self._eventos,
            }
            self._eventos = []
        return msg

    def empurrar(self) -> None:
        try:
            self.emitir(self.snapshot())
        except Exception:
            pass

    def encerrar(self) -> None:
        self._parar.set()
        self._sujo.set()

    # ------------------------------------------------------------------ Configurações
    def config(self) -> dict:
        with self._lock:
            return dict(self.cfg)

    def salvar_config(self, parcial: dict) -> dict:
        with self._lock:
            self.cfg = validar_config(parcial, self.cfg)
            salvar_json(self.arq_config, self.cfg)
            cfg = dict(self.cfg)
        if "ffmpeg_dir" in (parcial or {}):
            self.ffmpeg = self.verificar_ffmpeg()
        if "simultaneos" in (parcial or {}):
            self._bombear()
        return cfg

    # ------------------------------------------------------------------------ ffmpeg
    def _exe(self, pasta: Path, nome: str) -> Path | None:
        arq = nome + (".exe" if sys.platform.startswith("win") else "")
        for sub in ("", "bin", "ffmpeg/bin"):
            p = Path(pasta) / sub / arq if sub else Path(pasta) / arq
            if p.is_file():
                return p
        return None

    def _pasta_do_programa(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parent

    def verificar_ffmpeg(self) -> dict:
        """estado: 'path' (no PATH), 'pasta' (numa pasta específica) ou 'ausente'."""
        achado: tuple[str, str] | None = None
        explicita = self.cfg.get("ffmpeg_dir", "")
        if explicita and (self._exe(explicita, "ffmpeg") and self._exe(explicita, "ffprobe")):
            achado = ("pasta", str(self._exe(explicita, "ffmpeg").parent))
        elif shutil.which("ffmpeg") and shutil.which("ffprobe"):
            achado = ("path", shutil.which("ffmpeg") or "")
        else:
            for pasta in (self.dados / "ffmpeg", self._pasta_do_programa()):
                if self._exe(pasta, "ffmpeg") and self._exe(pasta, "ffprobe"):
                    achado = ("pasta", str(self._exe(pasta, "ffmpeg").parent))
                    break
        info = {"estado": "ausente", "caminho": "", "versao": "",
                "pode_baixar": sys.platform.startswith("win")}
        if achado:
            estado, caminho = achado
            exe = caminho if estado == "path" else str(self._exe(caminho, "ffmpeg"))
            info.update(estado=estado, caminho=caminho if estado == "pasta" else exe, versao=self._versao_ffmpeg(exe))
        return info

    def _versao_ffmpeg(self, exe: str) -> str:
        try:
            r = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=8,
                               creationflags=sistema.SEM_JANELA)
            m = re.search(r"version\s+(\S+)", r.stdout or "")
            if not m:
                return ""
            v = m.group(1)
            return v if re.match(r"^\d+(\.\d+)*", v) else "compilação " + v[:18]
        except Exception:
            return ""

    def _ffmpeg_dir_ytdlp(self) -> str:
        f = self.ffmpeg
        return f["caminho"] if f["estado"] == "pasta" else ""

    def ffmpeg_ok(self) -> bool:
        return self.ffmpeg["estado"] != "ausente"

    def apontar_ffmpeg(self, pasta: str) -> dict:
        if not (self._exe(pasta, "ffmpeg") and self._exe(pasta, "ffprobe")):
            return {"ok": False, "erro": "Não achei o ffmpeg e o ffprobe nessa pasta."}
        self.salvar_config({"ffmpeg_dir": str(self._exe(pasta, "ffmpeg").parent)})
        return {"ok": True, "ffmpeg": self.ffmpeg}

    def usar_ffmpeg_do_path(self) -> dict:
        self.salvar_config({"ffmpeg_dir": ""})
        return self.ffmpeg

    def baixar_ffmpeg(self) -> None:
        """Baixa o ffmpeg para a pasta do app, em segundo plano (só Windows)."""
        with self._lock:
            if self.ffmpeg_dl["estado"] in ("baixando", "extraindo"):
                return
            self.ffmpeg_dl = {"estado": "baixando", "pct": 0, "mb": 0, "total_mb": 0, "erro": ""}
        self._marcar()
        threading.Thread(target=self._baixar_ffmpeg, daemon=True).start()

    def _set_dl(self, **kw) -> None:
        with self._lock:
            self.ffmpeg_dl.update(kw)
        self._marcar()

    def _baixar_ffmpeg(self) -> None:
        if not sys.platform.startswith("win"):
            self._set_dl(estado="erro", erro="Neste sistema, instale o ffmpeg pelo gerenciador de pacotes (apt, brew...).")
            return
        destino = self.dados / "ffmpeg"
        zip_tmp = self.dados / "ffmpeg_download.zip.part"
        ultimo_erro = ""
        try:
            self.dados.mkdir(parents=True, exist_ok=True)
            for url in FFMPEG_URLS:
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": f"baixador/{VERSAO}"})
                    with urllib.request.urlopen(req, timeout=30) as resp, open(zip_tmp, "wb") as saida:
                        total = int(resp.headers.get("Content-Length") or 0)
                        lido = 0
                        t0 = 0.0
                        while True:
                            bloco = resp.read(256 * 1024)
                            if not bloco:
                                break
                            saida.write(bloco)
                            lido += len(bloco)
                            if time.time() - t0 > 0.2:
                                t0 = time.time()
                                self._set_dl(estado="baixando", mb=round(lido / 1048576),
                                             total_mb=round(total / 1048576),
                                             pct=round(lido / total * 100, 1) if total else 0)
                    break
                except Exception as e:  # tenta a próxima origem
                    ultimo_erro = str(e)
                    zip_tmp.unlink(missing_ok=True)
            else:
                raise RuntimeError(ultimo_erro or "download falhou")

            self._set_dl(estado="extraindo", pct=100)
            destino.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_tmp) as z:
                for nome in z.namelist():
                    p = Path(nome)
                    if "bin" in p.parts and p.suffix.lower() in (".exe", ".dll") and p.name:
                        with z.open(nome) as src, open(destino / p.name, "wb") as dst:
                            shutil.copyfileobj(src, dst)
            zip_tmp.unlink(missing_ok=True)
            novo = self.verificar_ffmpeg()
            if novo["estado"] == "ausente":
                raise RuntimeError("O arquivo baixado não tinha o ffmpeg esperado.")
            self.ffmpeg = novo
            self._set_dl(estado="pronto", pct=100)
        except Exception as e:
            zip_tmp.unlink(missing_ok=True)
            self._set_dl(estado="erro", erro=limpar(e)[:300])

    # ------------------------------------------------------------------------ yt-dlp
    def versao_ytdlp(self) -> str:
        return getattr(getattr(self.yt, "version", None), "__version__", "") or ""

    def atualizar_ytdlp(self) -> None:
        with self._lock:
            if self.ytdlp_up["estado"] == "verificando":
                return
            self.ytdlp_up = {"estado": "verificando", "versao": "", "erro": ""}
        self._marcar()
        threading.Thread(target=self._atualizar_ytdlp, daemon=True).start()

    def _set_up(self, **kw) -> None:
        with self._lock:
            self.ytdlp_up.update(kw)
        self._marcar()

    def _atualizar_ytdlp(self) -> None:
        pasta = self.dados / "yt-dlp"
        tmp = pasta / "yt-dlp.part"
        try:
            pasta.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(YTDLP_URL, headers={"User-Agent": f"baixador/{VERSAO}"})
            with urllib.request.urlopen(req, timeout=40) as resp, open(tmp, "wb") as saida:
                shutil.copyfileobj(resp, saida)
            if not zipfile.is_zipfile(tmp):
                raise RuntimeError("O arquivo baixado não é um yt-dlp válido.")
            nova = versao_no_zip(tmp)
            if not nova:
                raise RuntimeError("Não consegui ler a versão do arquivo baixado.")
            if vtupla(nova) > vtupla(self.versao_ytdlp()):
                os.replace(tmp, pasta / "yt-dlp")
                self._set_up(estado="atualizado", versao=nova)
            else:
                tmp.unlink(missing_ok=True)
                self._set_up(estado="em_dia", versao=self.versao_ytdlp())
        except Exception as e:
            tmp.unlink(missing_ok=True)
            self._set_up(estado="erro", erro=limpar(e)[:300])

    # ---------------------------------------------------------------------- Histórico
    def _carregar_hist(self) -> list[dict]:
        bruto = ler_json(self.arq_hist, [])
        saida = []
        for i, e in enumerate(bruto if isinstance(bruto, list) else []):
            if not isinstance(e, dict):
                continue
            ts = e.get("ts")
            if not ts and e.get("data"):  # histórico do app antigo: "29/10/2026 14:20"
                try:
                    ts = datetime.strptime(e["data"], "%d/%m/%Y %H:%M").timestamp()
                except ValueError:
                    ts = 0
            fmt = str(e.get("fmt") or e.get("formato") or "").lower()
            saida.append({
                "id": e.get("id") or f"h{int(ts or 0)}-{i}",
                "ts": ts or 0, "titulo": e.get("titulo", ""), "canal": e.get("canal", ""),
                "dur": e.get("dur", ""), "fmt": fmt, "qual": e.get("qual", ""),
                "pasta": e.get("pasta", ""), "arquivo": e.get("arquivo", ""),
                "url": e.get("url", ""), "thumb": e.get("thumb", ""),
            })
        return saida[:MAX_HISTORICO]

    def historico(self) -> list[dict]:
        with self._lock:
            return list(self.hist)

    def _registrar_historico(self, it: Item) -> dict:
        e = {
            "id": f"h{int(time.time() * 1000)}", "ts": time.time(), "titulo": it.titulo or it.url,
            "canal": it.canal, "dur": it.dur, "fmt": it.formato,
            "qual": it.qualidade if it.formato in FORMATOS_VIDEO else "",
            "pasta": str(Path(it.arquivo).parent) if it.arquivo else it.pasta,
            "arquivo": it.arquivo, "url": it.url, "thumb": it.thumb,
        }
        with self._lock:
            self.hist.insert(0, e)
            del self.hist[MAX_HISTORICO:]
            salvar_json(self.arq_hist, self.hist)
        return e

    def limpar_historico(self) -> None:
        with self._lock:
            self.hist.clear()
            salvar_json(self.arq_hist, self.hist)

    def _entrada_hist(self, hid: str) -> dict | None:
        with self._lock:
            return next((e for e in self.hist if e["id"] == hid), None)

    def abrir_historico(self, hid: str, o_que: str) -> dict:
        e = self._entrada_hist(hid)
        if not e:
            return {"ok": False, "erro": "Item não encontrado."}
        return self._abrir(e.get("arquivo", ""), e.get("pasta", ""), o_que)

    def baixar_de_novo(self, hid: str) -> dict:
        e = self._entrada_hist(hid)
        if not e or not eh_url(e.get("url")):
            return {"ok": False, "erro": "Esse item não tem um link guardado."}
        formato = e["fmt"] if e["fmt"] in FORMATOS_VIDEO + FORMATOS_AUDIO else self.cfg["formato"]
        return self.adicionar({
            "url": e["url"], "formato": formato, "qualidade": e.get("qual") or "Melhor",
            "meta": {"titulo": e["titulo"], "canal": e["canal"], "dur": e["dur"], "thumb": e["thumb"]},
        })

    def _abrir(self, arquivo: str, pasta: str, o_que: str) -> dict:
        if o_que == "arquivo":
            if arquivo and Path(arquivo).is_file():
                return {"ok": sistema.abrir_arquivo(arquivo)}
            return {"ok": False, "erro": "O arquivo não está mais nesse lugar."}
        if arquivo and Path(arquivo).is_file():
            return {"ok": sistema.mostrar_no_explorador(arquivo)}
        if pasta and Path(pasta).is_dir():
            return {"ok": sistema.abrir_pasta(pasta)}
        return {"ok": False, "erro": "A pasta não existe mais."}

    # -------------------------------------------------------------------- Inspeção
    def _base_ydl(self) -> dict:
        opc = {"quiet": True, "no_warnings": True, "socket_timeout": 15, "skip_download": True}
        c = self.cfg["cookies"]
        if c != "Não usar":
            opc["cookiesfrombrowser"] = (c.lower(),)
        return opc

    @staticmethod
    def _url_da_entrada(e: dict) -> str:
        u = e.get("url") or e.get("webpage_url") or ""
        if eh_url(u):
            return u
        if e.get("id") and "youtube" in str(e.get("ie_key") or e.get("extractor") or "").lower():
            return f"https://www.youtube.com/watch?v={e['id']}"
        return ""

    @staticmethod
    def _thumb_da_entrada(e: dict) -> str:
        if e.get("thumbnail"):
            return e["thumbnail"]
        ts = [t.get("url") for t in e.get("thumbnails") or [] if t.get("url")]
        if ts:
            return ts[-1]
        if e.get("id") and "youtube" in str(e.get("ie_key") or e.get("extractor") or "").lower():
            return f"https://i.ytimg.com/vi/{e['id']}/mqdefault.jpg"
        return ""

    def inspecionar(self, url: str) -> dict:
        """Lê o link sem baixar: título, canal, duração, miniatura e as qualidades que existem."""
        url = (url or "").strip()
        if not eh_url(url):
            return {"ok": False, "erro": "Esse link não é válido."}
        opc = self._base_ydl()
        opc.update(extract_flat="in_playlist", noplaylist=not self.cfg["playlist"])
        try:
            with self.yt.YoutubeDL(opc) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            titulo, msg, _ = traduzir_erro(limpar(e))
            return {"ok": False, "erro": msg, "erro_titulo": titulo, "detalhe": limpar(e)[:500]}
        if not info:
            return {"ok": False, "erro": "Não consegui ler esse link."}

        if info.get("_type") == "playlist" or info.get("entries") is not None:
            entradas = []
            soma = 0
            for n, e in enumerate([x for x in (info.get("entries") or []) if x], start=1):
                u = self._url_da_entrada(e)
                if not u:
                    continue
                soma += int(e.get("duration") or 0)
                entradas.append({"n": n, "titulo": e.get("title") or u, "dur": fmt_dur(e.get("duration")),
                                 "seg": int(e.get("duration") or 0), "url": u, "thumb": self._thumb_da_entrada(e)})
            if not entradas:
                return {"ok": False, "erro": "Essa playlist está vazia ou não pôde ser lida."}
            return {
                "ok": True, "tipo": "playlist", "titulo": info.get("title") or "Playlist",
                "canal": info.get("uploader") or info.get("channel") or "",
                "thumb": self._thumb_da_entrada(info) or entradas[0]["thumb"],
                "total": len(entradas), "seg_total": soma, "itens": entradas,
            }

        tier = tier_de_formatos(info.get("formats"))
        return {
            "ok": True, "tipo": "video", "titulo": info.get("title") or url,
            "canal": info.get("uploader") or info.get("channel") or "",
            "dur": fmt_dur(info.get("duration")), "seg": int(info.get("duration") or 0),
            "thumb": self._thumb_da_entrada(info),
            "qualidades": qualidades_disponiveis(tier), "tier": tier,
        }

    # ------------------------------------------------------------------------- Fila
    def _coagir(self, formato, qualidade) -> tuple[str, str]:
        formato = str(formato or self.cfg["formato"]).lower()
        if formato not in FORMATOS_VIDEO + FORMATOS_AUDIO:
            formato = "mp4"
        qualidade = qualidade if qualidade in QUALIDADES else "Melhor"
        if not self.ffmpeg_ok():  # sem ffmpeg: só mp4 e m4a, que já vêm prontos
            formato = "m4a" if formato in FORMATOS_AUDIO else "mp4"
        return formato, qualidade

    def _novo(self, url, formato, qualidade, **kw) -> Item:
        self._contador += 1
        c = self.cfg
        return Item(id=str(self._contador), url=url, formato=formato, qualidade=qualidade,
                    pasta=c["pasta"], legendas=c["legendas"], embutir=c["embutir"],
                    idiomas=c["idiomas"], **kw)

    def adicionar(self, spec: dict) -> dict:
        url = (spec.get("url") or "").strip()
        if not eh_url(url):
            return {"ok": False, "erro": "Esse link não é válido."}
        formato, qualidade = self._coagir(spec.get("formato"), spec.get("qualidade"))
        entradas = spec.get("itens") or []
        novos: list[Item] = []
        with self._lock:
            if entradas:
                total = int(spec.get("total") or len(entradas))
                for e in entradas:
                    if not eh_url(e.get("url")):
                        continue
                    novos.append(self._novo(
                        e["url"], formato, qualidade, titulo=e.get("titulo", ""), dur=e.get("dur", ""),
                        thumb=e.get("thumb", ""), idx=f"[{e.get('n')}/{total}]",
                        sub=spec.get("playlist_titulo", ""), canal=spec.get("canal", "")))
            else:
                m = spec.get("meta") or {}
                novos.append(self._novo(
                    url, formato, qualidade, titulo=m.get("titulo", ""), canal=m.get("canal", ""),
                    dur=m.get("dur", ""), thumb=m.get("thumb", ""), playlist=self.cfg["playlist"]))
            if not novos:
                return {"ok": False, "erro": "Nenhum vídeo para adicionar."}
            self.itens.extend(novos)
        self._bombear()
        self._marcar()
        return {"ok": True, "adicionados": len(novos)}

    def adicionar_rapido(self, url: str, formato: str, qualidade: str) -> dict:
        """Modo compacto: lê o link e já põe na fila (playlists entram inteiras)."""
        info = self.inspecionar(url)
        if not info.get("ok"):
            # não deu para ler, mas o yt-dlp pode conseguir baixar mesmo assim
            if eh_url(url):
                return self.adicionar({"url": url, "formato": formato, "qualidade": qualidade})
            return info
        if info["tipo"] == "playlist":
            return self.adicionar({"url": url, "formato": formato, "qualidade": qualidade,
                                   "itens": info["itens"], "total": info["total"],
                                   "playlist_titulo": info["titulo"], "canal": info["canal"]})
        return self.adicionar({"url": url, "formato": formato, "qualidade": qualidade,
                               "meta": {"titulo": info["titulo"], "canal": info["canal"],
                                        "dur": info["dur"], "thumb": info["thumb"]}})

    def _por_id(self, iid: str) -> Item | None:
        return next((i for i in self.itens if i.id == iid), None)

    def _bombear(self) -> None:
        """Inicia itens da fila até o limite de downloads simultâneos."""
        with self._lock:
            livres = self.cfg["simultaneos"] - len(self._ativos)
            for it in self.itens:
                if livres <= 0:
                    break
                if it.status == "aguardando" and not it.removido and it not in self._ativos:
                    it.status = "baixando"
                    it.esq, it.dir, it.pct, it.indet = "Iniciando…", "", 0.0, False
                    it.cancel.clear()
                    it.motivo = ""
                    self._ativos.add(it)
                    it.thread = threading.Thread(target=self._executar, args=(it,), daemon=True)
                    it.thread.start()
                    livres -= 1
        self._marcar()

    def cancelar_atuais(self) -> None:
        with self._lock:
            for it in self.itens:
                if it.status in EM_CURSO:
                    it.motivo = "cancelar"
                    it.cancel.set()
        self._marcar()

    def parar_tudo(self) -> None:
        with self._lock:
            for it in self.itens:
                if it.status == "aguardando":
                    self._marcar_cancelado(it)
                elif it.status in EM_CURSO:
                    it.motivo = "cancelar"
                    it.cancel.set()
        self._marcar()

    def _marcar_cancelado(self, it: Item) -> None:
        it.status = "cancelado"
        it.indet = False
        it.fim = time.time()
        it.esq = f"Cancelado em {int(it.pct)}%" if it.pct else "Cancelado"
        it.dir = "Arquivo parcial apagado" if it.pct else ""

    def cancelar(self, iid: str) -> None:
        with self._lock:
            it = self._por_id(iid)
            if not it:
                return
            if it.status in EM_CURSO:
                it.motivo = "cancelar"
                it.cancel.set()
            elif it.status in ("aguardando", "pausado"):
                self._marcar_cancelado(it)
        self._marcar()

    def pausar(self, iid: str) -> None:
        """Pausa interrompendo o download e mantendo o arquivo parcial; retomar continua de onde parou."""
        with self._lock:
            it = self._por_id(iid)
            if not it:
                return
            if it.status == "baixando":
                it.motivo = "pausar"
                it.cancel.set()
            elif it.status == "aguardando":
                it.status, it.esq, it.dir = "pausado", "Pausado", "Clique em retomar para continuar"
        self._marcar()

    def retomar(self, iid: str) -> None:
        with self._lock:
            it = self._por_id(iid)
            if it and it.status == "pausado":
                it.status = "aguardando"
                it.esq, it.dir = "Na fila", ""
        self._bombear()

    def tentar_de_novo(self, iid: str) -> None:
        with self._lock:
            it = self._por_id(iid)
            if it and it.status in ("erro", "cancelado"):
                it.status, it.pct, it.indet = "aguardando", 0.0, False
                it.erro = it.erro_titulo = it.erro_msg = ""
                it.fim, it._fn, it._feito, it._atual = None, None, 0, 0
                it.esq, it.dir = "Na fila", ""
        self._bombear()

    def remover(self, ids: list[str]) -> None:
        with self._lock:
            for iid in ids:
                it = self._por_id(iid)
                if not it:
                    continue
                it.removido = True
                if it in self._ativos:
                    it.motivo = "remover"
                    it.cancel.set()
                self.itens.remove(it)
        self._marcar()

    def limpar_concluidos(self) -> None:
        with self._lock:
            self.itens = [i for i in self.itens if i.status not in ENCERRADOS]
        self._marcar()

    def tem_rodando(self) -> bool:
        with self._lock:
            return any(i.status in EM_CURSO for i in self.itens)

    def cancelar_para_sair(self) -> None:
        with self._lock:
            for it in self.itens:
                if it in self._ativos:
                    it.motivo = "sair"
                    it.cancel.set()

    def abrir_item(self, iid: str, o_que: str) -> dict:
        with self._lock:
            it = self._por_id(iid)
            if not it:
                return {"ok": False, "erro": "Item não encontrado."}
            arquivo, pasta = it.arquivo, it.pasta
        return self._abrir(arquivo, pasta, o_que)

    # -------------------------------------------------------------- Execução (threads)
    def _opcoes(self, it: Item) -> dict:
        c = self.cfg
        Path(it.pasta).expanduser().mkdir(parents=True, exist_ok=True)
        opc = montar_opcoes(
            formato=it.formato, qualidade=it.qualidade, pasta=it.pasta, template=c["template"],
            playlist=it.playlist, legendas=it.legendas, embutir=it.embutir, idiomas=it.idiomas,
            cookies=c["cookies"], limite_bps=LIMITES.get(c["limite"], 0) // max(1, c["simultaneos"]),
            ffmpeg_dir=self._ffmpeg_dir_ytdlp(), ffmpeg_ok=self.ffmpeg_ok())
        opc["progress_hooks"] = [lambda d, i=it: self._hook(d, i)]
        opc["postprocessor_hooks"] = [lambda d, i=it: self._hook_pos(d, i)]
        return opc

    def _executar(self, it: Item) -> None:
        try:
            with self.yt.YoutubeDL(self._opcoes(it)) as ydl:
                info = ydl.extract_info(it.url, download=True)
            self._concluir(it, info)
        except Interrompido:
            self._interrompido(it)
        except Exception as e:
            if it.cancel.is_set():
                self._interrompido(it)
            else:
                self._falhou(it, limpar(e))
        finally:
            with self._lock:
                self._ativos.discard(it)
                ativos_restantes = any(i.status in ATIVOS for i in self.itens)
                if not ativos_restantes:
                    rodada, self._rodada = self._rodada, 0
                    pasta = self._ultima_pasta
                else:
                    rodada, pasta = 0, ""
            if rodada and self.cfg["abrir_pasta"] and pasta:
                sistema.abrir_pasta(pasta)
            self._bombear()
            self._marcar()

    def _hook(self, d: dict, it: Item) -> None:
        if it.cancel.is_set():
            raise Interrompido(it.motivo)
        info = d.get("info_dict") or {}
        if info.get("title") and not it.titulo:
            it.titulo = info["title"]
        if not it.canal:
            it.canal = info.get("uploader") or info.get("channel") or ""
        if not it.dur and info.get("duration"):
            it.dur = fmt_dur(info["duration"])
        if not it.thumb and info.get("thumbnail"):
            it.thumb = info["thumbnail"]
        if info.get("playlist_index") and info.get("n_entries") and not it.idx:
            it.idx = f"[{info['playlist_index']}/{info['n_entries']}]"

        arq = d.get("filename") or ""
        for nome in (d.get("tmpfilename"), arq):
            if nome:
                it._parciais.add(nome)

        if d.get("status") == "finished":
            it._feito += d.get("total_bytes") or d.get("downloaded_bytes") or 0
            it._fn = None
            return
        if d.get("status") != "downloading":
            return

        if arq and arq != it._fn:  # começou outro fluxo (vídeo, depois áudio)
            it._fn = arq
        atual = d.get("downloaded_bytes") or 0
        parcial_total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        esperado = 0
        formatos = info.get("requested_formats") or []
        if formatos:
            tamanhos = [f.get("filesize") or f.get("filesize_approx") or 0 for f in formatos]
            if all(tamanhos):
                esperado = sum(tamanhos)
        total = esperado or (it._feito + parcial_total if parcial_total else 0)
        feito = it._feito + atual
        it.status = "baixando"
        vel = d.get("speed")
        eta = d.get("eta")
        if total:
            it.indet = False
            it.pct = min(99.9, feito / total * 100)
            it.esq = f"{it.pct:.0f}% · {fmt_bytes(feito)} de {fmt_bytes(total)}"
        else:
            it.indet = True
            it.esq = f"{fmt_bytes(feito)} baixados"
        partes = []
        if vel:
            partes.append(f"{fmt_bytes(vel)}/s")
        if eta is not None and total:
            partes.append(f"{fmt_tempo(eta)} restantes")
        it.dir = " · ".join(partes)
        self._marcar()

    def _hook_pos(self, d: dict, it: Item) -> None:
        if d.get("status") != "started":
            return
        nome = d.get("postprocessor") or ""
        textos = {
            "FFmpegExtractAudio": f"Convertendo para {it.formato} com o ffmpeg",
            "Merger": "Juntando vídeo e áudio com o ffmpeg",
            "FFmpegMerger": "Juntando vídeo e áudio com o ffmpeg",
            "FFmpegEmbedSubtitle": "Embutindo as legendas",
            "FFmpegSubtitlesConvertor": "Convertendo as legendas",
        }
        it.status = "convertendo"
        it.indet = True
        it.esq = textos.get(nome, "Finalizando o arquivo")
        it.dir = f"Download concluído · {fmt_bytes(it._feito)}" if it._feito else ""
        self._marcar()

    @staticmethod
    def _achar_arquivo(info) -> str:
        if not info:
            return ""
        for r in info.get("requested_downloads") or []:
            fp = r.get("filepath") or r.get("_filename")
            if fp:
                return fp
        for e in info.get("entries") or []:
            p = Nucleo._achar_arquivo(e)
            if p:
                return p
        return info.get("filepath") or info.get("_filename") or ""

    def _concluir(self, it: Item, info) -> None:
        if it.removido:
            return
        if info:
            it.titulo = info.get("title") or it.titulo
            it.canal = info.get("uploader") or info.get("channel") or it.canal
            if info.get("duration") and not it.dur:
                it.dur = fmt_dur(info["duration"])
            it.thumb = info.get("thumbnail") or it.thumb
        arq = self._achar_arquivo(info)
        it.arquivo = arq if arq and Path(arq).exists() else ""
        try:
            it.tamanho = Path(it.arquivo).stat().st_size if it.arquivo else 0
        except OSError:
            it.tamanho = 0
        it.status, it.pct, it.indet, it.fim = "concluido", 100.0, False, time.time()
        pasta_final = str(Path(it.arquivo).parent) if it.arquivo else it.pasta
        it.esq = f"{fmt_bytes(it.tamanho)} · salvo em {pasta_final}" if it.tamanho else f"Salvo em {pasta_final}"
        it.dir = ""
        with self._lock:
            self._rodada += 1
            self._ultima_pasta = pasta_final
        entrada = self._registrar_historico(it)
        self._evento("concluido", id=it.id, titulo=it.titulo or it.url, arquivo=it.arquivo,
                     nome=os.path.basename(it.arquivo) if it.arquivo else "", entrada=entrada)

    def _interrompido(self, it: Item) -> None:
        motivo = it.motivo
        if motivo == "pausar":
            it.status, it.indet = "pausado", False
            it.esq, it.dir = f"Pausado em {int(it.pct)}%", "Clique em retomar para continuar"
        elif motivo == "sair":
            it.status = "cancelado"
        else:  # cancelar ou remover: apaga o que sobrou do arquivo
            self._apagar_parciais(it)
            if not it.removido:
                self._marcar_cancelado(it)
            it._parciais.clear()
        it.cancel.clear()

    def _falhou(self, it: Item, texto: str) -> None:
        if it.removido:
            return
        titulo, msg, curto = traduzir_erro(texto)
        it.status, it.indet, it.fim = "erro", False, time.time()
        it.erro, it.erro_titulo, it.erro_msg = texto, titulo, msg
        it.parou_em = int(it.pct)
        it.esq = f"Parou em {it.parou_em}%: {curto}" if it.parou_em else f"Falhou: {curto}"
        it.dir = "Duplo clique para ver detalhes"

    @staticmethod
    def _apagar_parciais(it: Item) -> None:
        """Remove só arquivos temporários (.part e .ytdl) deste download, nunca um arquivo pronto."""
        for nome in list(it._parciais):
            candidatos = {nome, nome + ".part", nome + ".ytdl"}
            try:
                candidatos.update(str(p) for p in Path(nome).parent.glob(Path(nome).name + ".part-Frag*"))
            except OSError:
                pass
            for c in candidatos:
                if c.endswith((".part", ".ytdl")) or ".part-Frag" in c:
                    try:
                        Path(c).unlink(missing_ok=True)
                    except OSError:
                        pass
