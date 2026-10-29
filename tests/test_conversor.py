"""Testes da conversão com o ffmpeg de verdade (pulam se o ffmpeg não existir). Rode: python -m unittest discover tests"""
import shutil, subprocess, sys, tempfile, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import conversor

FF, FP = shutil.which("ffmpeg"), shutil.which("ffprobe")


@unittest.skipUnless(FF and FP, "ffmpeg não instalado")
class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = Path(tempfile.mkdtemp())
        cls.video = cls.d / "clipe.mp4"
        cls.mudo = cls.d / "mudo.mp4"
        cls.audio = cls.d / "som.wav"
        subprocess.run([FF, "-v", "error", "-f", "lavfi", "-i", "testsrc=d=2:s=160x120:r=15", "-f", "lavfi", "-i", "sine=d=2",
                        "-shortest", "-c:v", "libx264", "-c:a", "aac", str(cls.video)], check=True)
        subprocess.run([FF, "-v", "error", "-f", "lavfi", "-i", "testsrc=d=1:s=160x120:r=15", "-c:v", "libx264", str(cls.mudo)], check=True)
        subprocess.run([FF, "-v", "error", "-f", "lavfi", "-i", "sine=d=1", str(cls.audio)], check=True)

    def setUp(self):
        self.avisos = 0
        self.c = conversor.Conversor(lambda: (FF, FP), lambda: None)

    def tearDown(self): self.c.encerrar()

    def esperar(self, n=1, limite=60):
        for _ in range(limite * 10):
            s = self.c.snapshot()
            if len(s) >= n and all(i["status"] not in ("aguardando", "convertendo") for i in s):
                return s
            time.sleep(0.1)
        self.fail("demorou demais")

    def test_extrair_mp3(self):
        self.assertTrue(self.c.adicionar([str(self.video)], "mp3", "Média")["ok"])
        s = self.esperar()
        self.assertEqual(s[0]["status"], "concluido", s[0]["erro"])
        self.assertTrue((self.d / "clipe.mp3").is_file())

    def test_video_para_mkv_e_nome_nao_sobrescreve(self):
        self.c.adicionar([str(self.video)], "mkv", "Pequena"); self.esperar()
        self.c.adicionar([str(self.video)], "mkv", "Pequena")
        s = self.esperar(2)
        self.assertTrue(all(i["status"] == "concluido" for i in s))
        self.assertTrue((self.d / "clipe.mkv").is_file() and (self.d / "clipe (2).mkv").is_file())

    def test_mesmo_formato_nao_sobrescreve_original(self):
        antes = self.video.stat().st_size
        self.c.adicionar([str(self.video)], "mp4", "Média"); s = self.esperar()
        self.assertEqual(s[0]["status"], "concluido")
        self.assertEqual(self.video.stat().st_size, antes)
        self.assertTrue((self.d / "clipe (convertido).mp4").is_file())

    def test_sem_audio_da_erro_claro(self):
        self.c.adicionar([str(self.mudo)], "mp3", "Média"); s = self.esperar()
        self.assertEqual(s[0]["status"], "erro"); self.assertIn("áudio", s[0]["erro"])

    def test_audio_para_video_da_erro_claro(self):
        self.c.adicionar([str(self.audio)], "mp4", "Média"); s = self.esperar()
        self.assertEqual(s[0]["status"], "erro"); self.assertIn("vídeo", s[0]["erro"])

    def test_pasta_de_destino(self):
        out = self.d / "saida"
        self.c.adicionar([str(self.audio)], "flac", "Alta", str(out)); self.esperar()
        self.assertTrue((out / "som.flac").is_file())

    def test_arquivo_invalido_e_sonda(self):
        txt = self.d / "a.txt"; txt.write_text("oi")
        self.assertFalse(self.c.adicionar([str(txt)], "mp3", "Média")["ok"])
        r = self.c.sondar([str(self.video), str(txt)])
        self.assertTrue(r[0]["video"] and r[0]["audio"]); self.assertFalse(r[1]["ok"])

    def test_cancelar_limpa_parcial(self):
        grande = self.d / "grande.mp4"
        subprocess.run([FF, "-v", "error", "-f", "lavfi", "-i", "testsrc=d=120:s=1280x720:r=30", "-c:v", "libx264", "-preset", "ultrafast", str(grande)], check=True)
        self.c.adicionar([str(grande)], "webm", "Alta")
        for _ in range(50):
            if self.c.snapshot()[0]["status"] == "convertendo": break
            time.sleep(0.1)
        time.sleep(0.8); self.c.cancelar(self.c.snapshot()[0]["id"])
        s = self.esperar()
        self.assertEqual(s[0]["status"], "cancelado")
        self.assertFalse(list(self.d.glob("*.convertendo.*")))


if __name__ == "__main__":
    unittest.main()
