"""Usado pelo GitHub Actions: grava apoio.json a partir da variável APOIO_JSON e confere se está válido."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import apoio  # noqa: E402

texto = os.environ.get("APOIO_JSON", "").strip()
if not texto:
    print("APOIO_JSON vazia: build sem a aba Apoie.")
    sys.exit(0)
try:
    json.loads(texto)
except ValueError as e:
    sys.exit(f"APOIO_JSON não é um JSON válido: {e}")
Path("apoio.json").write_text(texto, encoding="utf-8")
r = apoio.carregar(Path("."))
if not r.get("ativo"):
    sys.exit("APOIO_JSON não tem nenhuma forma de apoio válida (Pix com erro, links sem https ou cripto incompleta).")
print("Apoio configurado:", ", ".join(k for k in ("payload", "cartao", "internacional") if r.get(k)), f"+ {len(r['cripto'])} cripto")
