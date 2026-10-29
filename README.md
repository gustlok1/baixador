# Baixador de Vídeos

Baixe vídeos e áudios direto para a sua pasta, com fila, pausa, histórico e modo compacto. Gratuito e de código aberto (licença MIT). Feito com [yt-dlp](https://github.com/yt-dlp/yt-dlp), [ffmpeg](https://ffmpeg.org) e [pywebview](https://pywebview.flowrl.com).

## Rodar pelo código

```
pip install -r requirements.txt
python main.py
```

No Windows é preciso o Microsoft Edge WebView2 Runtime (já vem no Windows 10 e 11 atualizados).

## Gerar o .exe

Execute `gerar_exe.bat`. O arquivo sai em `dist\Baixador.exe`.

## ffmpeg

Na primeira execução o app procura o ffmpeg e, no Windows, oferece baixar automaticamente (cerca de 90 MB, guardado em `~/.baixador_videos/ffmpeg`). Sem ele funcionam só mp4 e m4a, em qualidade reduzida.

## Convite de apoio (opcional)

Ao abrir, o app mostra um recado gratuito com QR code Pix. Para ativar na sua cópia:

1. Copie `apoio.exemplo.json` para `apoio.json`.
2. Cole o seu Pix copia e cola.
3. Gere o .exe de novo (o `apoio.json` vai embutido).

O `apoio.json` está no `.gitignore`: não publique a sua chave. Dica: use uma chave Pix aleatória, porque o nome do recebedor aparece no app do banco de quem paga.

## Testes

```
python -m unittest discover tests
python tests/rodar.py /tmp/prints   # interface no Chromium, com a API simulada (precisa de playwright)
```

## Aviso

Use apenas para conteúdo que você tem direito de baixar. Respeite os termos dos sites e os direitos autorais. As fontes Montserrat e Michroma são distribuídas sob a licença OFL.
# baixador
# baixador
