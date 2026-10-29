"""Teste de interface: abre web/index.html no Chromium com a API simulada e tira prints de cada tela."""
import sys, pathlib
from playwright.sync_api import sync_playwright
RAIZ = pathlib.Path(__file__).resolve().parent.parent
SAIDA = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/prints"); SAIDA.mkdir(parents=True, exist_ok=True)
mock = (RAIZ/"tests"/"mock_api.js").read_text()
erros = []
BR = None
def novo(p, query=""):
    p = BR
    pg = p.new_page(viewport={"width":1100,"height":760})
    pg.on("console", lambda m: erros.append(m.text) if m.type in ("error","warning") else None)
    pg.on("pageerror", lambda e: erros.append("PAGEERROR "+str(e)))
    pg.add_init_script(mock)
    pg.goto((RAIZ/"web"/"index.html").as_uri()+query)
    pg.wait_for_timeout(300)
    return pg
with sync_playwright() as p:
    b = p.chromium.launch(); BR = b
    for tema in ("", "?light=1"):
        n = "claro" if tema else "escuro"
        pg = novo(p, tema)
        pg.wait_for_timeout(1800)  # convite de apoio
        pg.screenshot(path=str(SAIDA/f"{n}-apoio.png"))
        pg.keyboard.press("Escape")
        pg.fill("#link", "https://youtu.be/abc"); pg.wait_for_timeout(1200)
        pg.screenshot(path=str(SAIDA/f"{n}-baixar-preview.png"))
        pg.fill("#link", "https://youtube.com/watch?v=1&list=PL"); pg.wait_for_timeout(1200)
        pg.screenshot(path=str(SAIDA/f"{n}-baixar-playlist.png"))
        pg.fill("#link", "nada"); pg.wait_for_timeout(900)
        pg.screenshot(path=str(SAIDA/f"{n}-baixar-invalido.png"))
        for nav in ("fila","historico","config"):
            pg.click(f'.tab[data-nav="{nav}"]'); pg.wait_for_timeout(200)
            pg.screenshot(path=str(SAIDA/f"{n}-{nav}.png"))
        pg.click('.tab[data-nav="fila"]'); pg.dblclick('li[data-id="e"] .qcard'); pg.wait_for_timeout(200)
        pg.screenshot(path=str(SAIDA/f"{n}-drawer.png"))
        pg.close()
    pg = novo(p, "?onb=1&noff=1"); pg.screenshot(path=str(SAIDA/"onboarding.png")); pg.close()
    pg = novo(p, "?vazio=1"); pg.wait_for_timeout(1800); pg.keyboard.press("Escape")
    pg.click('.tab[data-nav="fila"]'); pg.screenshot(path=str(SAIDA/"fila-vazia.png"))
    pg.click('.tab[data-nav="historico"]'); pg.screenshot(path=str(SAIDA/"hist-vazio.png")); pg.close()
    pg = novo(p, ""); pg.wait_for_timeout(1800); pg.keyboard.press("Escape")
    pg.set_viewport_size({"width":560,"height":300})
    pg.evaluate("document.querySelector('[data-act=compacto-on]').click()"); pg.wait_for_timeout(300)
    pg.screenshot(path=str(SAIDA/"compacto.png"))
    # fluxo: adicionar
    pg.evaluate("document.querySelector('[data-act=compacto-off]').click()"); pg.set_viewport_size({"width":1100,"height":760})
    pg.fill("#link","https://youtu.be/zzz"); pg.wait_for_timeout(1200); pg.click("#cta"); pg.wait_for_timeout(300)
    chamadas = pg.evaluate("window.__calls.map(c=>c[0])")
    print("chamadas:", chamadas)
    assert "adicionar" in chamadas
    b.close()
print("ERROS DE CONSOLE:", erros or "nenhum")
