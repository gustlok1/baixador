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


def _link(v) -> str:
    v = str(v or "").strip()
    return v if v.lower().startswith("https://") else ""


def carregar(pasta: Path) -> dict:
    """
    Lê <pasta>/apoio.json. Sem o arquivo, ou com tudo vazio, a aba Apoie e o recado ficam desligados.

    Campos (todos opcionais):
      pix_copia_e_cola   texto do Pix copia e cola (vira QR code)
      cartao_link        link de pagamento para cartão (ex.: Mercado Pago)
      mensal_link        apoio mensal recorrente (ex.: campanha no APOIA.se)
      internacional_link link para quem está fora do Brasil (ex.: Ko-fi)
      cripto             lista de {"moeda", "rede", "endereco"}
      link               nome antigo de cartao_link (ainda aceito)
    """
    arq = Path(pasta) / "apoio.json"
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
        if not isinstance(dados, dict):
            raise ValueError
    except Exception:
        return {"ativo": False}

    payload = str(dados.get("pix_copia_e_cola", "")).strip()
    if payload.upper().startswith("COLE_AQUI"):
        payload = ""
    pix_ok = pix_valido(payload) if payload else False
    if payload and not pix_ok:
        payload = ""  # um Pix com erro de digitação não chega a quem quer pagar
    cartao = _link(dados.get("cartao_link") or dados.get("link"))
    internacional = _link(dados.get("internacional_link"))
    mensal = _link(dados.get("mensal_link"))

    cripto = []
    for c in dados.get("cripto") or []:
        if not isinstance(c, dict):
            continue
        end = str(c.get("endereco", "")).strip()
        moeda = str(c.get("moeda", "")).strip()
        rede = str(c.get("rede", "")).strip()
        if not end or not moeda or not rede or len(end) > 200 or any(ch.isspace() for ch in end):
            continue
        try:
            svg = qr_svg(end)
        except Exception:
            svg = ""
        cripto.append({"moeda": moeda[:40], "rede": rede[:60], "endereco": end, "svg": svg})

    if not (payload or cartao or mensal or internacional or cripto):
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
        "svg": svg,
        "link": cartao,  # o recado de abertura usa este nome
        "cartao": cartao,
        "mensal": mensal,
        "internacional": internacional,
        "cripto": cripto,
    }
