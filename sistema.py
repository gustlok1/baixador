# -*- coding: utf-8 -*-
"""Cola com o sistema operacional: área de transferência, abrir arquivos e pastas,
barra de título escura no Windows. Tudo aqui falha em silêncio: nada disso pode derrubar o app."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

WINDOWS = sys.platform.startswith("win")
MAC = sys.platform == "darwin"
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0) if WINDOWS else 0


# ------------------------------------------------------------ Área de transferência
def _win_api():
    import ctypes
    from ctypes import wintypes

    u32 = ctypes.WinDLL("user32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    u32.OpenClipboard.argtypes = [wintypes.HWND]
    u32.OpenClipboard.restype = wintypes.BOOL
    u32.CloseClipboard.restype = wintypes.BOOL
    u32.EmptyClipboard.restype = wintypes.BOOL
    u32.GetClipboardData.argtypes = [wintypes.UINT]
    u32.GetClipboardData.restype = wintypes.HANDLE
    u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    u32.SetClipboardData.restype = wintypes.HANDLE
    k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k32.GlobalAlloc.restype = wintypes.HGLOBAL
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalLock.restype = wintypes.LPVOID
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalUnlock.restype = wintypes.BOOL
    return ctypes, u32, k32


def _win_abrir_clipboard(u32) -> bool:
    for _ in range(15):
        if u32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def ler_clipboard() -> str | None:
    """Texto da área de transferência, ou None se não der para ler."""
    try:
        if WINDOWS:
            ctypes, u32, k32 = _win_api()
            if not _win_abrir_clipboard(u32):
                return None
            try:
                h = u32.GetClipboardData(13)  # CF_UNICODETEXT
                if not h:
                    return ""
                p = k32.GlobalLock(h)
                if not p:
                    return ""
                try:
                    return ctypes.wstring_at(p)
                finally:
                    k32.GlobalUnlock(h)
            finally:
                u32.CloseClipboard()
        comandos = [["pbpaste"]] if MAC else [["wl-paste", "-n"], ["xclip", "-selection", "clipboard", "-o"]]
        for cmd in comandos:
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=2)
                if r.returncode == 0:
                    return r.stdout.decode("utf-8", "replace")
            except Exception:
                continue
    except Exception:
        pass
    return None


def copiar_clipboard(texto: str) -> bool:
    try:
        if WINDOWS:
            ctypes, u32, k32 = _win_api()
            dados = (texto + "\0").encode("utf-16-le")
            h = k32.GlobalAlloc(0x0002, len(dados))  # GMEM_MOVEABLE
            if not h:
                return False
            p = k32.GlobalLock(h)
            ctypes.memmove(p, dados, len(dados))
            k32.GlobalUnlock(h)
            if not _win_abrir_clipboard(u32):
                return False
            try:
                u32.EmptyClipboard()
                return bool(u32.SetClipboardData(13, h))
            finally:
                u32.CloseClipboard()
        comandos = [["pbcopy"]] if MAC else [["wl-copy"], ["xclip", "-selection", "clipboard"]]
        for cmd in comandos:
            try:
                r = subprocess.run(cmd, input=texto.encode("utf-8"), timeout=2)
                if r.returncode == 0:
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


# --------------------------------------------------------------- Abrir arquivo/pasta
def abrir_pasta(pasta: str | Path) -> bool:
    try:
        pasta = str(pasta)
        if WINDOWS:
            os.startfile(pasta)  # type: ignore[attr-defined]
        elif MAC:
            subprocess.Popen(["open", pasta])
        else:
            subprocess.Popen(["xdg-open", pasta])
        return True
    except Exception:
        return False


def abrir_arquivo(caminho: str | Path) -> bool:
    return abrir_pasta(caminho)  # o sistema abre com o programa padrão


def mostrar_no_explorador(arquivo: str | Path) -> bool:
    """Abre a pasta com o arquivo selecionado (Windows); nos outros, só abre a pasta."""
    arquivo = Path(arquivo)
    try:
        if WINDOWS and arquivo.exists():
            subprocess.Popen(["explorer", f"/select,{arquivo}"])
            return True
    except Exception:
        pass
    return abrir_pasta(arquivo.parent if arquivo.suffix else arquivo)


# -------------------------------------------------------------- Barra de título
def barra_de_titulo(titulo: str, escura: bool) -> None:
    """Pinta a barra de título do Windows 10/11 para combinar com o tema."""
    if not WINDOWS:
        return
    try:
        import ctypes

        hwnd = ctypes.windll.user32.FindWindowW(None, titulo)
        if not hwnd:
            return
        dwm = ctypes.windll.dwmapi

        def attr(codigo: int, valor: int) -> int:
            v = ctypes.c_int(valor)
            return dwm.DwmSetWindowAttribute(hwnd, codigo, ctypes.byref(v), ctypes.sizeof(v))

        if attr(20, 1 if escura else 0) != 0:  # DWMWA_USE_IMMERSIVE_DARK_MODE
            attr(19, 1 if escura else 0)  # Windows 10 antigo
        # Windows 11: cor da barra e do texto (COLORREF = 0x00BBGGRR)
        attr(35, 0x00070505 if escura else 0x00F2F4F4)  # = fundo do tema
        attr(36, 0x00F8F6F5 if escura else 0x000D0B0A)  # = cor do texto
    except Exception:
        pass


def aviso_nativo(titulo: str, texto: str) -> None:
    """Caixa de mensagem simples, para erros antes de a interface existir."""
    try:
        if WINDOWS:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, texto, titulo, 0x10)
            return
    except Exception:
        pass
    print(f"{titulo}: {texto}", file=sys.stderr)
