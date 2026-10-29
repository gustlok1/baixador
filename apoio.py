# -*- coding: utf-8 -*-
"""Convite de apoio por Pix: lê o apoio.json, confere o código e gera o QR Code (SVG)."""
from __future__ import annotations

import json
from pathlib import Path


def crc16_pix(texto: str) -> str:
    """CRC16/CCITT-FALSE exigido pelo BR Code do Pix."""
    crc = 0xFFFF
    for b in texto.encode("utf-8"):
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def pix_valido(payload: str) -> bool:
    return (
        len(payload) > 30
        and payload.startswith("000201")
        and "br.gov.bcb.pix" in payload.lower()
        and payload[-8:-4] == "6304"
        and crc16_pix(payload[:-4]) == payload[-4:].upper()
    )


def qr_svg(texto: str) -> str:
    """QR Code em SVG, módulos escuros sobre fundo claro (leitores exigem esse contraste nos dois temas)."""
    import segno

    qr = segno.make(texto, error="m", micro=False)
    return qr.svg_inline(
        scale=1, border=2, dark="#050507", light="#f5f6f8", omitsize=True, xmldecl=False, nl=False,
        svgclass="qr-svg", lineclass=None,
    )


def carregar(pasta: Path) -> dict:
    """Lê <pasta>/apoio.json. Sem o arquivo (ou com ele vazio), o convite fica desligado."""
    arq = Path(pasta) / "apoio.json"
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
    except Exception:
        return {"ativo": False}
    payload = str(dados.get("pix_copia_e_cola", "")).strip()
    link = str(dados.get("link", "")).strip()
    if link and not link.lower().startswith(("https://", "http://")):
        link = ""
    if not payload and not link:
        return {"ativo": False}
    svg = ""
    if payload:
        try:
            svg = qr_svg(payload)
        except Exception:
            svg = ""
    return {
        "ativo": True,
        "payload": payload,
        "link": link,
        "svg": svg,
        "payload_ok": pix_valido(payload) if payload else None,
    }
