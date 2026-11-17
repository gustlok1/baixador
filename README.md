# Baixador de Vídeos

Baixe vídeos e áudios direto para a sua pasta, com fila, pausa, histórico e modo compacto. Gratuito e de código aberto (licença MIT). Feito com [yt-dlp](https://github.com/yt-dlp/yt-dlp), [ffmpeg](https://ffmpeg.org) e [pywebview](https://pywebview.flowrl.com).

## O que faz

- Baixa vídeos e playlists (fila, pausa, retomada, histórico, modo compacto).
- **Converte arquivos do seu computador**: extrai o áudio de um vídeo ou troca o formato (mp4, mkv, webm, mp3, m4a, wav, opus, flac). Arraste os arquivos para a aba Converter. O original nunca é alterado. Precisa do ffmpeg.

## Rodar pelo código

```
pip install -r requirements.txt
python main.py
```

No Windows é preciso o Microsoft Edge WebView2 Runtime (já vem no Windows 10 e 11 atualizados).

## Gerar o .exe

Precisa do Python instalado (python.org, marcando "Add python.exe to PATH"). Execute `gerar_exe.bat`; o arquivo sai em `dist\Baixador.exe`. Quem só vai usar o app não precisa de Python: basta o .exe.

Sem instalar nada: suba o projeto no GitHub e rode o workflow "Build Windows" (aba Actions). O .exe sai como artefato, ou na Release se você criar uma tag `v*`.

## ffmpeg

Na primeira execução o app procura o ffmpeg e, no Windows, oferece baixar automaticamente (cerca de 90 MB, guardado em `~/.baixador_videos/ffmpeg`). Sem ele funcionam só mp4 e m4a, em qualidade reduzida.

## Apoio (opcional)

A aba **Apoie** e o recado que aparece ao abrir o app mostram as formas de apoio configuradas no `apoio.json`. Campos vazios simplesmente não aparecem. Veja o modelo em `apoio.exemplo.json`:

- `pix_copia_e_cola`: o código do Pix (vira QR code). O app confere o código e ignora se estiver errado.
- `cartao_link`: link de pagamento para cartão, como um link do Mercado Pago (precisa ser https).
- `mensal_link`: apoio mensal recorrente, como uma campanha no APOIA.se.
- `internacional_link`: página para quem está fora do Brasil, como o Ko-fi.
- `cripto`: lista de `{"moeda", "rede", "endereco"}`. A rede aparece em destaque, porque enviar na rede errada perde o valor.

**No .exe oficial (GitHub Actions):** o `apoio.json` não vai para o repositório. Em vez disso, cole o conteúdo dele numa variável do repositório chamada `APOIO_JSON` (Settings > Secrets and variables > Actions > aba Variables). O workflow grava o arquivo e o embute no .exe. Sem a variável, a aba Apoie não aparece.

**Na sua máquina:** copie `apoio.exemplo.json` para `apoio.json`, preencha e rode `gerar_exe.bat`.

Dados de pagamento ficam visíveis para quem usa o app. Use uma chave Pix aleatória para não expor CPF ou telefone. O nome do recebedor sempre aparece no app do banco de quem paga.

## Testes

```
python -m unittest discover tests
python tests/rodar.py /tmp/prints   # interface no Chromium, com a API simulada (precisa de playwright)
```

## Aviso

Use apenas para conteúdo que você tem direito de baixar. Respeite os termos dos sites e os direitos autorais. As fontes Montserrat e Michroma são distribuídas sob a licença OFL.
