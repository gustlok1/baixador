# -*- coding: utf-8 -*-
"""
Conversão de arquivos que já estão no computador (extrair áudio, trocar de formato).

Usa o ffmpeg direto, um arquivo por vez. Não conhece a interface: quem usa passa
`obter_ffmpeg()` (devolve (ffmpeg, ffprobe) ou None) e `marcar()` (avisa que o estado mudou).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

import sistema

VIDEO = ["mp4", "mkv", "webm"]
AUDIO = ["mp3", "m4a", "wav", "opus", "flac"]
ENTRADAS = {
    "mp4", "mkv", "webm", "mov", "avi", "wmv", "flv", "m4v", "mpg", "mpeg", "ts", "3gp",
    "mp3", "m4a", "wav", "opus", "flac", "ogg", "aac", "wma", "aiff",
}
NIVEIS = ["Alta", "Média", "Pequena"]
CRF_H264 = {"Alta": 18, "Média": 23, "Pequena": 28}
CRF_VP9 = {"Alta": 28, "Média": 33, "Pequena": 40}
KBPS_AUDIO = {"Alta": 256, "Média": 192, "Pequena": 128}
EM_CURSO = ("aguardando", "convertendo")


def _fmt_tempo(seg: float) -> str:
    seg = int(max(0, seg))
    h, r = divmod(seg, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fmt_bytes(n: float) -> str:
    n = float(n or 0)
    for un in ("B", "KB", "MB", "GB"):
        if n < 1024 or un == "GB":
            return f"{n:.0f} {un}" if un == "B" else f"{n:.1f} {un}".replace(".", ",")
        n /= 1024
    return ""


def argumentos(formato: str, nivel: str) -> list[str]:
    """Parâmetros de codificação do ffmpeg para o formato de saída."""
    nivel = nivel if nivel in NIVEIS else "Média"
    kb = KBPS_AUDIO[nivel]
    if formato == "mp4":
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(CRF_H264[nivel]), "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
    if formato == "mkv":
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(CRF_H264[nivel]), "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k"]
    if formato == "webm":
        return ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", str(CRF_VP9[nivel]), "-row-mt", "1", "-cpu-used", "4",
                "-c:a", "libopus", "-b:a", "128k"]
    if formato == "mp3":
        return ["-vn", "-c:a", "libmp3lame", "-b:a", f"{kb}k"]
    if formato == "m4a":
        return ["-vn", "-c:a", "aac", "-b:a", f"{kb}k"]
    if formato == "opus":
        return ["-vn", "-c:a", "libopus", "-b:a", f"{min(kb, 160)}k"]
    if formato == "wav":
        return ["-vn", "-c:a", "pcm_s16le"]
    if formato == "flac":
        return ["-vn", "-c:a", "flac"]
    raise ValueError(formato)


def caminho_livre(pasta: Path, nome: str, ext: str) -> Path:
    alvo = pasta / f"{nome}.{ext}"
    n = 2
    while alvo.exists():
        alvo = pasta / f"{nome} ({n}).{ext}"
        n += 1
    return alvo


class Trabalho:
    def __init__(self, tid: str, origem: str, formato: str, nivel: str, pasta: str):
        self.id = tid
        self.origem = origem
        self.nome = Path(origem).name
        self.formato = formato
        self.nivel = nivel
        self.pasta = pasta  # vazio = mesma pasta do arquivo
        self.status = "aguardando"
        self.pct = 0.0
        self.esq = ""
        self.dir = ""
        self.indet = False
        self.erro = ""
        self.saida = ""
        self.tem_video = None
        self.dur = 0.0
        self.motivo = ""
        self.proc: subprocess.Popen | None = None
        self.cancel = threading.Event()

    def publico(self) -> dict:
        return {
            "id": self.id, "nome": self.nome, "origem": self.origem, "formato": self.formato,
            "nivel": self.nivel, "status": self.status, "pct": round(self.pct, 1), "esq": self.esq,
            "dir": self.dir, "indet": self.indet, "erro": self.erro,
            "saida": Path(self.saida).name if self.saida else "",
            "pasta_saida": str(Path(self.saida).parent) if self.saida else "",
            "video": self.tem_video, "dur": _fmt_tempo(self.dur) if self.dur else "",
            "audio_formato": self.formato in AUDIO,
        }


class Conversor:
    def __init__(self, obter_ffmpeg, marcar):
        self._ffmpeg = obter_ffmpeg
        self._marcar = marcar
        self._lock = threading.RLock()
        self.itens: list[Trabalho] = []
        self._cont = 0
        self._acorda = threading.Event()
        self._parar = threading.Event()
        threading.Thread(target=self._laco, daemon=True).start()

    # ------------------------------------------------------------------ público
    def snapshot(self) -> list[dict]:
        with self._lock:
            return [t.publico() for t in self.itens]

    def tem_rodando(self) -> bool:
        with self._lock:
            return any(t.status in EM_CURSO for t in self.itens)

    def sondar(self, caminhos: list[str]) -> list[dict]:
        """Lê cada arquivo escolhido (duração, se tem vídeo/áudio) antes de converter."""
        out = []
        bins = self._ffmpeg()
        for c in caminhos:
            p = Path(c)
            if not p.is_file():
                out.append({"caminho": c, "nome": p.name, "ok": False, "erro": "Arquivo não encontrado."})
                continue
            if p.suffix.lower().lstrip(".") not in ENTRADAS:
                out.append({"caminho": c, "nome": p.name, "ok": False, "erro": "Esse tipo de arquivo não é de vídeo nem de áudio."})
                continue
            info = self._probe(bins[1], c) if bins else None
            tam = _fmt_bytes(p.stat().st_size)
            if info is None:
                out.append({"caminho": c, "nome": p.name, "ok": True, "video": None, "audio": None, "dur": "", "tamanho": tam})
            else:
                out.append({"caminho": c, "nome": p.name, "ok": True, "video": info["video"], "audio": info["audio"],
                            "dur": _fmt_tempo(info["dur"]) if info["dur"] else "", "tamanho": tam})
        return out

    def adicionar(self, arquivos: list[str], formato: str, nivel: str, pasta: str = "") -> dict:
        if formato not in VIDEO + AUDIO:
            return {"ok": False, "erro": "Escolha um formato de saída."}
        if not self._ffmpeg():
            return {"ok": False, "erro": "O ffmpeg não está instalado. Instale em Configurações › Sistema."}
        if pasta and not Path(pasta).is_dir():
            try:
                Path(pasta).mkdir(parents=True, exist_ok=True)
            except OSError:
                return {"ok": False, "erro": "Não consegui usar essa pasta de destino."}
        n = 0
        with self._lock:
            for a in arquivos:
                p = Path(a)
                if not p.is_file() or p.suffix.lower().lstrip(".") not in ENTRADAS:
                    continue
                self._cont += 1
                self.itens.append(Trabalho(f"c{self._cont}", str(p), formato, nivel, pasta))
                n += 1
        if not n:
            return {"ok": False, "erro": "Nenhum arquivo de vídeo ou áudio válido."}
        self._acorda.set()
        self._marcar()
        return {"ok": True, "adicionados": n}

    def cancelar(self, tid: str) -> None:
        with self._lock:
            t = self._achar(tid)
            if not t:
                return
            if t.status == "aguardando":
                t.status = "cancelado"
            elif t.status == "convertendo":
                t.motivo = "cancelar"
                t.cancel.set()
                self._matar(t)
        self._marcar()

    def cancelar_todos(self, motivo: str = "cancelar") -> None:
        with self._lock:
            for t in self.itens:
                if t.status == "aguardando":
                    t.status = "cancelado"
                elif t.status == "convertendo":
                    t.motivo = motivo
                    t.cancel.set()
                    self._matar(t)
        self._marcar()

    def tentar_de_novo(self, tid: str) -> None:
        with self._lock:
            t = self._achar(tid)
            if t and t.status in ("erro", "cancelado"):
                t.status, t.pct, t.erro, t.esq, t.dir, t.indet = "aguardando", 0.0, "", "", "", False
                t.cancel = threading.Event()
                t.motivo = ""
        self._acorda.set()
        self._marcar()

    def remover(self, ids: list[str]) -> None:
        with self._lock:
            for tid in ids:
                t = self._achar(tid)
                if t and t.status == "convertendo":
                    t.motivo = "remover"
                    t.cancel.set()
                    self._matar(t)
            self.itens = [t for t in self.itens if t.id not in ids]
        self._marcar()

    def limpar_finalizados(self) -> None:
        with self._lock:
            self.itens = [t for t in self.itens if t.status in EM_CURSO]
        self._marcar()

    def abrir(self, tid: str, o_que: str) -> dict:
        with self._lock:
            t = self._achar(tid)
            saida = t.saida if t else ""
        if saida and Path(saida).is_file():
            return {"ok": sistema.abrir_arquivo(saida) if o_que == "arquivo" else sistema.mostrar_no_explorador(saida)}
        return {"ok": False, "erro": "O arquivo não está mais nesse lugar."}

    def encerrar(self) -> None:
        self._parar.set()
        self._acorda.set()

    # ----------------------------------------------------------------- internos
    def _achar(self, tid: str) -> Trabalho | None:
        return next((t for t in self.itens if t.id == tid), None)

    @staticmethod
    def _matar(t: Trabalho) -> None:
        p = t.proc
        if p and p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass

    @staticmethod
    def _probe(ffprobe: str, caminho: str) -> dict | None:
        try:
            r = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "stream=codec_type:format=duration", "-of", "json", caminho],
                capture_output=True, text=True, timeout=20, creationflags=sistema.SEM_JANELA)
            d = json.loads(r.stdout or "{}")
        except Exception:
            return None
        tipos = [s.get("codec_type") for s in d.get("streams", [])]
        try:
            dur = float((d.get("format") or {}).get("duration") or 0)
        except ValueError:
            dur = 0.0
        return {"video": "video" in tipos, "audio": "audio" in tipos, "dur": dur}

    def _laco(self) -> None:
        while not self._parar.is_set():
            self._acorda.wait(timeout=1.0)
            if self._parar.is_set():
                break
            while True:
                with self._lock:
                    t = next((x for x in self.itens if x.status == "aguardando"), None)
                    if t:
                        t.status = "convertendo"
                        t.indet = True
                if not t or self._parar.is_set():
                    break
                self._marcar()
                try:
                    self._converter(t)
                except Exception as e:  # nunca derruba o laço
                    self._falhar(t, f"Algo deu errado na conversão: {e}")
                self._marcar()
            self._acorda.clear()

    def _falhar(self, t: Trabalho, msg: str) -> None:
        with self._lock:
            t.status, t.erro, t.indet, t.esq, t.dir = "erro", msg, False, "", ""

    def _converter(self, t: Trabalho) -> None:
        bins = self._ffmpeg()
        if not bins:
            return self._falhar(t, "O ffmpeg não está instalado. Instale em Configurações › Sistema.")
        ffmpeg, ffprobe = bins
        origem = Path(t.origem)
        if not origem.is_file():
            return self._falhar(t, "O arquivo de origem não existe mais.")
        info = self._probe(ffprobe, t.origem)
        if info is None:
            return self._falhar(t, "Não consegui ler esse arquivo. Ele pode estar corrompido.")
        t.tem_video, t.dur = info["video"], info["dur"]
        if not info["audio"] and t.formato in AUDIO:
            return self._falhar(t, "Esse arquivo não tem faixa de áudio para extrair.")
        if not info["video"] and t.formato in VIDEO:
            return self._falhar(t, "Esse arquivo não tem vídeo. Escolha um formato de áudio.")

        pasta = Path(t.pasta) if t.pasta else origem.parent
        try:
            pasta.mkdir(parents=True, exist_ok=True)
        except OSError:
            return self._falhar(t, "Não consegui criar a pasta de destino.")
        base = origem.stem
        if pasta == origem.parent and origem.suffix.lower().lstrip(".") == t.formato:
            base += " (convertido)"
        final = caminho_livre(pasta, base, t.formato)
        parcial = final.with_name(final.stem + ".convertendo" + final.suffix)
        t.saida = ""

        cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-i", t.origem]
        if t.formato in VIDEO:
            cmd += ["-map", "0:v:0", "-map", "0:a:0?"]
        else:
            cmd += ["-map", "0:a:0"]
        cmd += argumentos(t.formato, t.nivel) + ["-progress", "pipe:1", "-nostats", str(parcial)]

        inicio = time.time()
        try:
            t.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                      encoding="utf-8", errors="replace", creationflags=sistema.SEM_JANELA)
        except OSError as e:
            return self._falhar(t, f"Não consegui iniciar o ffmpeg: {e}")

        erros: list[str] = []
        threading.Thread(target=lambda: erros.extend((t.proc.stderr.read() or "").splitlines()[-12:]), daemon=True).start()
        rx = re.compile(r"out_time_(?:us|ms)=(\d+)")
        ultimo = 0.0
        for linha in t.proc.stdout:
            m = rx.match(linha.strip())
            if not m or not t.dur:
                continue
            feito = int(m.group(1)) / 1_000_000
            ag = time.time()
            if ag - ultimo < 0.25:
                continue
            ultimo = ag
            with self._lock:
                t.indet = False
                t.pct = max(0.0, min(99.0, feito / t.dur * 100))
                dec = ag - inicio
                vel = feito / dec if dec > 0 else 0
                t.esq = f"{t.pct:.0f}% · {_fmt_tempo(feito)} de {_fmt_tempo(t.dur)}"
                t.dir = (f"{vel:.1f}x · {_fmt_tempo((t.dur - feito) / vel)} restantes" if vel > 0.05 else "")
            self._marcar()
        codigo = t.proc.wait()
        time.sleep(0.05)
        for fl in (t.proc.stdout, t.proc.stderr):
            try: fl.close()
            except Exception: pass

        if t.cancel.is_set():
            parcial.unlink(missing_ok=True)
            with self._lock:
                t.status, t.indet, t.pct, t.esq, t.dir = "cancelado", False, 0.0, "", ""
            return
        if codigo != 0 or not parcial.is_file():
            parcial.unlink(missing_ok=True)
            detalhe = "\n".join(l for l in erros if l.strip())
            return self._falhar(t, "O ffmpeg não conseguiu converter este arquivo." + (f"\n{detalhe}" if detalhe else ""))
        os.replace(parcial, final)
        with self._lock:
            t.saida = str(final)
            t.status, t.pct, t.indet, t.dir = "concluido", 100.0, False, "agora"
            t.esq = _fmt_bytes(final.stat().st_size)
