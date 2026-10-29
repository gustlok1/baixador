"""Testes do núcleo com um yt_dlp falso (sem rede). Rode: python -m unittest discover tests"""
import sys, tempfile, time, types, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core, apoio


class YDL:
    ultimas = []
    def __init__(self, opts): self.opts = opts; YDL.ultimas.append(opts)
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def extract_info(self, url, download=False):
        if "ruim" in url: raise Exception("ERROR: Video unavailable")
        if not download:
            return {"title": "Teste", "uploader": "Canal", "duration": 65, "thumbnail": "", "formats": [{"height": 1080, "vcodec": "avc1"}, {"height": 720, "vcodec": "avc1"}]}
        for h in self.opts.get("progress_hooks", []):
            h({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100, "speed": 10, "eta": 5, "info_dict": {}})
        return {"title": "Teste", "requested_downloads": [{"filepath": str(Path(self.opts["outtmpl"]).parent / "Teste.mp4")}]}


def falso():
    m = types.SimpleNamespace(YoutubeDL=YDL, version=types.SimpleNamespace(__version__="0.0.1"))
    return m


class T(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.msgs = []
        self.n = core.Nucleo(emitir=self.msgs.append, pasta_dados=self.d, yt=falso())

    def tearDown(self): self.n.encerrar()

    def test_config_invalida_volta_ao_padrao(self):
        c = self.n.salvar_config({"simultaneos": 99, "formato": "exe", "tema": "rosa"})
        self.assertTrue(1 <= c["simultaneos"] <= 5)
        self.assertIn(c["formato"], core.FORMATOS_VIDEO + core.FORMATOS_AUDIO)
        self.assertIn(c["tema"], core.TEMAS)

    def test_padrao_1080p(self):
        self.assertEqual(self.n.config()["qualidade"], "1080p")

    def test_inspecionar_erro_traduzido(self):
        r = self.n.inspecionar("https://x.com/ruim")
        self.assertFalse(r["ok"])
        self.assertTrue(r["erro"])

    def test_link_invalido_nao_entra(self):
        self.assertFalse(self.n.adicionar({"url": "nada", "formato": "mp4", "qualidade": "720p"})["ok"])

    def test_fila_conclui_e_vai_ao_historico(self):
        self.n.salvar_config({"pasta": str(self.d)})
        self.assertTrue(self.n.adicionar({"url": "https://x.com/ok", "formato": "mp4", "qualidade": "720p"})["ok"])
        for _ in range(60):
            if self.n.historico(): break
            time.sleep(0.1)
        self.assertEqual(len(self.n.historico()), 1)


class Apoio(unittest.TestCase):
    def test_sem_arquivo_desliga(self):
        self.assertFalse(apoio.carregar(Path(tempfile.mkdtemp()))["ativo"])

    def test_crc_pix(self):
        p = "00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-4266554400005204000053039865802BR5913Fulano de Tal6008BRASILIA62070503***6304"
        self.assertEqual(len(apoio.crc16_pix(p)), 4)
        self.assertTrue(apoio.pix_valido(p + apoio.crc16_pix(p)))


if __name__ == "__main__":
    unittest.main()
