/* baixador: lógica da interface. Fala com o Python por window.pywebview.api e recebe o estado em window.__baixador.recebe(). */
(function () {
  'use strict';

  const { esc, ehUrl, icone, plural } = window.U;
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  const VIDEO = ['mp4', 'mkv', 'webm'];
  const AUDIO = ['mp3', 'm4a', 'wav', 'opus', 'flac'];
  const QUALS = ['Melhor', '4K', '1440p', '1080p', '720p', '480p', '360p'];
  const ROTULO_ST = { aguardando: 'Aguardando', baixando: 'Baixando', convertendo: 'Convertendo', pausado: 'Pausado', concluido: 'Concluído', cancelado: 'Cancelado', erro: 'Erro' };
  const PRESETS = [
    ['mp4', 'Melhor', 'mp4 · melhor qualidade'], ['mp4', '1080p', 'mp4 · 1080p'], ['mp4', '720p', 'mp4 · 720p'],
    ['mkv', 'Melhor', 'mkv · melhor qualidade'], ['mp3', 'Melhor', 'mp3 · 192 kbps'], ['m4a', 'Melhor', 'm4a · 192 kbps'], ['flac', 'Melhor', 'flac · sem perdas'],
  ];

  const S = {
    api: null, pronto: false,
    app: {}, cfg: {}, ffmpeg: { estado: 'ausente' }, ytdlp: { versao: '' }, apoio: { ativo: false },
    fila: [], hist: [], sel: new Set(), ffdl: {}, ytup: {},
    pagina: 'baixar', compacto: false, onb: null,
    formato: 'mp4', qualidade: '1080p',
    prev: { estado: 'vazio', url: '', dados: null, seq: 0, timer: null, erroTimer: null },
    plSel: new Set(), histSel: null, filtro: 'todos', busca: '',
    dialogo: null, apoioTimer: null,
  };

  // ------------------------------------------------------------------ Ponte com o Python
  async function chamar(nome) {
    const args = Array.prototype.slice.call(arguments, 1);
    try {
      return await S.api[nome].apply(S.api, args);
    } catch (e) {
      console.error('api.' + nome, e);
      return null;
    }
  }

  async function copiarTexto(texto) {
    if (S.api && (await chamar('copiar', texto)) === true) return true;
    try { await navigator.clipboard.writeText(texto); return true; } catch (e) { /* tenta o plano B */ }
    try {
      const t = document.createElement('textarea');
      t.value = texto; t.style.position = 'fixed'; t.style.opacity = '0';
      document.body.appendChild(t); t.select();
      const ok = document.execCommand('copy'); t.remove(); return ok;
    } catch (e) { return false; }
  }

  async function lerClipboard() {
    const r = S.api ? await chamar('ler_clipboard') : null;
    if (typeof r === 'string') return r;
    try { return await navigator.clipboard.readText(); } catch (e) { return ''; }
  }

  // ------------------------------------------------------------------------- Tema
  function temaResolvido() {
    const t = S.cfg.tema || 'dark';
    if (t === 'system') return window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    return t;
  }
  function aplicarTema() {
    const r = temaResolvido();
    document.documentElement.setAttribute('data-theme', r);
    if (S.api) chamar('barra_titulo', r === 'dark');
  }
  if (window.matchMedia) {
    const mq = window.matchMedia('(prefers-color-scheme: light)');
    (mq.addEventListener ? mq.addEventListener.bind(mq, 'change') : mq.addListener.bind(mq))(() => { if (S.cfg.tema === 'system') aplicarTema(); });
  }

  // -------------------------------------------------------------------- Navegação
  function irPara(pag) {
    if (S.compacto || S.onb) return;
    S.pagina = pag;
    $$('[data-page]').forEach((el) => { el.hidden = el.dataset.page !== pag; });
    $$('.tab').forEach((b) => { if (b.dataset.nav === pag) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current'); });
    $('.pages').scrollTop = 0;
    if (pag === 'fila') desenharFila();
    if (pag === 'historico') desenharHistorico();
    if (pag === 'config') { preencherConfig(); desenharSistema(); }
    if (pag === 'baixar') setTimeout(() => $('#link').focus(), 0);
  }

  // ===================================================================== BAIXAR
  const ffmpegOk = () => S.ffmpeg && S.ffmpeg.estado !== 'ausente';
  const formatoPermitido = (f) => ffmpegOk() || f === 'mp4' || f === 'm4a';
  const ehAudio = () => AUDIO.indexOf(S.formato) >= 0;

  function qualidadesDisponiveis() {
    const p = S.prev;
    return p.estado === 'pronto' && p.dados.tipo === 'video' ? p.dados.qualidades : QUALS;
  }
  function qualidadeEfetiva() {
    const disp = qualidadesDisponiveis();
    if (disp.indexOf(S.qualidade) >= 0) return S.qualidade;
    for (let j = QUALS.indexOf(S.qualidade) + 1; j < QUALS.length; j++) if (disp.indexOf(QUALS[j]) >= 0) return QUALS[j];
    return 'Melhor';
  }

  function aoDigitar() {
    const v = $('#link').value.trim();
    const p = S.prev;
    p.url = v;
    clearTimeout(p.timer); clearTimeout(p.erroTimer);
    p.seq++;
    if (!v) { definirPreview('vazio'); return; }
    if (!ehUrl(v)) {
      definirPreview('vazio');
      p.erroTimer = setTimeout(() => { if (p.url === v) definirPreview('invalido'); }, 500);
      return;
    }
    p.timer = setTimeout(() => inspecionar(v), 450);
    if (p.estado !== 'pronto' && p.estado !== 'erro') definirPreview('carregando');
  }

  async function inspecionar(url) {
    const seq = ++S.prev.seq;
    definirPreview('carregando');
    const r = await chamar('inspecionar', url);
    if (seq !== S.prev.seq || S.prev.url !== url) return; // o link mudou enquanto lia
    if (!r || !r.ok) { definirPreview('erro', r || { erro: 'Não consegui ler esse link.' }); return; }
    if (r.tipo === 'playlist') S.plSel = new Set(r.itens.map((i) => i.n));
    definirPreview('pronto', r);
  }

  function definirPreview(estado, dados) {
    S.prev.estado = estado;
    S.prev.dados = dados || null;
    desenharBaixar();
  }

  function thumbHtml(thumb, dur, cls, resolvendo) {
    const centro = resolvendo ? icone('link', 20) :
      '<span class="thumb__play">' + icone('play', cls === 'thumb' ? 22 : 16) + '</span>';
    return '<div class="thumb ' + cls + '" role="img" aria-label="Miniatura">' +
      (thumb ? '<img src="' + esc(thumb) + '" alt="" loading="lazy" referrerpolicy="no-referrer">' : '') +
      (cls === 'thumb thumb--row' ? '' : centro) +
      (dur && !resolvendo ? '<span class="thumb__dur">' + esc(dur) + '</span>' : '') + '</div>';
  }

  function previewHtml() {
    const p = S.prev, d = p.dados;
    if (p.estado === 'vazio' || p.estado === 'invalido') {
      return '<section class="preview preview--empty" aria-label="Preview">' +
        '<div class="orbit orbit--sm" data-orbit="120:99.6,20.4:24,60:60,118">' + icone('play', 28, '" style="position:relative') + '</div>' +
        '<div class="preview__text"><h2 class="h3">O preview aparece aqui</h2>' +
        '<p>Assim que você colar um link, mostramos miniatura, título, canal, duração e só as qualidades que o vídeo realmente tem.</p></div></section>';
    }
    if (p.estado === 'carregando') {
      return '<section class="preview" aria-label="Lendo o link" aria-busy="true">' +
        '<div class="thumb skeleton" role="img" aria-label="Carregando"></div>' +
        '<div class="preview__info"><span class="label label--faint">Lendo o link</span>' +
        '<h2 class="h3">Buscando título e qualidades…</h2><p class="soft">Isso leva alguns segundos.</p>' +
        '<div class="bar ob-indet" role="progressbar" aria-label="Lendo o link"></div></div></section>';
    }
    if (p.estado === 'erro') {
      return '<section class="preview" aria-label="Não foi possível ler o link">' +
        '<span class="round round--danger" aria-hidden="true">' + icone('alert', 20) + '</span>' +
        '<div class="preview__info"><h2 class="h3">' + esc(d.erro_titulo || 'Não consegui ler esse link agora') + '</h2>' +
        '<p class="soft">' + esc(d.erro || '') + '</p>' +
        '<p class="help">Você ainda pode tentar baixar mesmo assim: o botão abaixo continua liberado.</p></div></section>';
    }
    if (d.tipo === 'playlist') return playlistHtml(d);

    const efetiva = qualidadeEfetiva();
    const quals = d.tier ? d.qualidades.filter((q) => q !== 'Melhor').map((q) =>
      '<span class="tag ' + (q === efetiva && !ehAudio() ? 'tag--ink' : 'tag--line') + '">' + esc(q) + '</span>').join('') : '';
    return '<section class="preview" aria-label="Preview do vídeo">' + thumbHtml(d.thumb, d.dur, 'thumb') +
      '<div class="preview__info"><div class="tags"><span class="tag tag--line">Vídeo</span>' +
      (d.seg ? '<span class="tag tag--line">' + esc(window.U.durLonga(d.seg)) + '</span>' : '') + '</div>' +
      '<h2 class="h3">' + esc(d.titulo) + '</h2>' + (d.canal ? '<p class="soft">' + esc(d.canal) + '</p>' : '') +
      (quals ? '<div class="preview__quals"><span class="label label--faint">Qualidades disponíveis</span><div class="tags">' + quals + '</div></div>' : '') +
      '</div></section>';
  }

  function playlistHtml(d) {
    const todos = !!S.cfg.playlist;
    const head = '<div class="plist__head">' + thumbHtml(d.thumb, '', 'thumb thumb--pl') +
      '<div class="preview__info"><div class="tags"><span class="tag tag--line">Playlist</span><span class="tag tag--line">' + d.total + ' ' + plural(d.total, 'vídeo', 'vídeos') + '</span></div>' +
      '<h2 class="h3">' + esc(d.titulo) + '</h2><p class="soft">' + esc([d.canal, d.seg_total ? window.U.durLonga(d.seg_total) + ' no total' : ''].filter(Boolean).join(' · ')) + '</p></div></div>';
    if (todos) {
      return '<section class="plist" aria-label="Playlist">' + head +
        '<p class="info-note" style="padding:20px 24px">' + icone('info', 18, '" style="color:var(--accent)') +
        '<span>"Baixar playlist inteira" está ligado: os ' + d.total + ' vídeos entram na fila. Para escolher um por um, desligue em Configurações › Downloads.</span></p></section>';
    }
    const linhas = d.itens.map((i) =>
      '<li><label class="plist__row"><input type="checkbox" data-pl="' + i.n + '"' + (S.plSel.has(i.n) ? ' checked' : '') + '>' +
      '<span class="plist__n">' + String(i.n).padStart(2, '0') + '</span>' + thumbHtml(i.thumb, '', 'thumb thumb--row') +
      '<span class="plist__title ell' + (S.plSel.has(i.n) ? '' : ' is-off') + '">' + esc(i.titulo) + '</span>' +
      '<span class="plist__dur">' + esc(i.dur) + '</span></label></li>').join('');
    return '<section class="plist" aria-label="Itens da playlist">' + head +
      '<div class="plist__bar"><label class="check-label"><input type="checkbox" id="pl-all">Selecionar todos</label>' +
      '<span class="caption" id="pl-resumo"></span></div><ul class="plist__rows">' + linhas + '</ul></section>';
  }

  function plAtualizar() {
    const p = S.prev;
    if (p.estado !== 'pronto' || p.dados.tipo !== 'playlist' || S.cfg.playlist) return;
    const d = p.dados, n = S.plSel.size;
    const seg = d.itens.filter((i) => S.plSel.has(i.n)).reduce((a, i) => a + (i.seg || 0), 0);
    const r = $('#pl-resumo');
    if (r) r.textContent = n + ' de ' + d.total + ' ' + plural(d.total, 'selecionado', 'selecionados') + (seg ? ' · ' + window.U.durLonga(seg) : '');
    const all = $('#pl-all');
    if (all) { all.checked = n === d.total; all.indeterminate = n > 0 && n < d.total; }
    $$('.plist__row').forEach((row) => {
      const cb = $('input', row);
      $('.plist__title', row).classList.toggle('is-off', !cb.checked);
    });
    desenharCta();
  }

  function desenharBaixar() {
    $('#preview').innerHTML = previewHtml();
    $$('#preview [data-orbit]').forEach(window.U.orbita);
    const inv = S.prev.estado === 'invalido';
    $('#field-link').classList.toggle('is-invalid', inv);
    $('#link').setAttribute('aria-invalid', inv ? 'true' : 'false');
    const aj = $('#link-ajuda');
    aj.className = 'help' + (inv ? ' help--danger' : '');
    aj.innerHTML = inv ? icone('alert', 16) + 'Esse link não é válido. Use um endereço que comece com http:// ou https://.' : 'Aceita vídeo ou playlist. Enter adiciona à fila.';
    desenharOpcoes();
    plAtualizar();
  }

  function desenharOpcoes() {
    const mk = (f, grupo) => '<button class="ob-btn chip" data-formato="' + f + '" aria-pressed="' + (S.formato === f) + '"' +
      (formatoPermitido(f) ? '' : ' disabled title="Precisa do ffmpeg (Configurações › Sistema)"') + '>' + f + '</button>';
    $('#chips-video').innerHTML = VIDEO.map(mk).join('');
    $('#chips-audio').innerHTML = AUDIO.map(mk).join('');

    const audio = ehAudio(), disp = qualidadesDisponiveis(), efetiva = qualidadeEfetiva();
    $('#fs-qualidade').disabled = audio;
    $('#tag-so-video').hidden = !audio;
    $('#chips-qualidade').innerHTML = QUALS.map((q) => {
      const indisp = disp.indexOf(q) < 0;
      const cls = 'ob-btn chip' + (indisp && !audio ? ' is-unavailable' : '');
      const dis = audio || indisp;
      const dica = audio ? 'Qualidade vale só para vídeo' : indisp ? 'Indisponível neste vídeo' : q;
      return '<button class="' + cls + '" data-qualidade="' + q + '" aria-pressed="' + (!audio && q === efetiva) + '"' + (dis ? ' disabled' : '') + ' title="' + dica + '">' + q + '</button>';
    }).join('');

    const p = S.prev, pl = p.estado === 'pronto' && p.dados.tipo === 'playlist';
    const temVideo = p.estado === 'pronto' && p.dados.tipo === 'video' && p.dados.tier;
    $('#qualidade-legenda').textContent = audio ? 'Desabilitado para formatos de áudio' :
      pl ? 'Aplicada a cada vídeo da playlist' :
      temVideo ? (disp.length < QUALS.length ? 'Riscadas: o vídeo não tem essa qualidade' : 'O vídeo tem todas as qualidades') :
      'Todas as opções até o link ser lido';

    let nota = 'A qualidade vale só para vídeo. Áudio sai a 192 kbps.';
    if (audio) nota = 'Você escolheu ' + S.formato + ', então a qualidade fica desabilitada. ' + (['wav', 'flac'].indexOf(S.formato) >= 0 ? 'O áudio é extraído sem compressão com perdas.' : 'Áudio sai a 192 kbps.');
    else if (pl) nota = 'Se um vídeo não tiver ' + efetiva + ', usamos a qualidade mais próxima abaixo.';
    else if (temVideo && disp.length < QUALS.length) {
      const falta = QUALS.filter((q) => disp.indexOf(q) < 0);
      nota = 'Mostramos só o que este vídeo oferece: ' + falta.join(' e ') + ' ' + (falta.length > 1 ? 'não estão disponíveis.' : 'não está disponível.');
    }
    if (!ffmpegOk()) nota += ' Sem o ffmpeg, só mp4 e m4a, em qualidade reduzida. Instale em Configurações › Sistema.';
    $('#quality-note').textContent = nota;
    $('#save-path').textContent = S.cfg.pasta || '-';
    desenharCta();
  }

  function desenharCta() {
    const p = S.prev;
    const valido = ehUrl(p.url);
    const pl = p.estado === 'pronto' && p.dados.tipo === 'playlist';
    const n = pl && !S.cfg.playlist ? S.plSel.size : 0;
    const total = pl && S.cfg.playlist ? p.dados.total : 0;
    let label = 'Adicionar à fila e baixar', cap = 'Ao começar, você vai para a Fila', ok = valido;
    if (pl && !S.cfg.playlist) { label = 'Adicionar ' + n + ' à fila e baixar'; if (!n) { ok = false; cap = 'Selecione ao menos um vídeo'; } }
    if (total) label = 'Adicionar ' + total + ' à fila e baixar';
    if (!valido) cap = 'Cole um link válido para continuar';
    $('#cta-label').textContent = label;
    $('#cta-caption').textContent = cap;
    $('#cta').disabled = !ok;
  }

  async function adicionar() {
    const url = $('#link').value.trim();
    if (!ehUrl(url)) {
      if (url) await dialogo({ icone: 'link', cor: 'danger', titulo: 'Esse link não é válido', texto: 'Cole o endereço de um vídeo ou playlist que comece com http:// ou https://.', botoes: [{ rotulo: 'Entendi', tipo: 'solid', valor: true }] });
      return;
    }
    const p = S.prev;
    const spec = { url, formato: S.formato, qualidade: qualidadeEfetiva() };
    if (p.estado === 'pronto' && p.dados.url_ok !== false) {
      const d = p.dados;
      if (d.tipo === 'playlist') {
        const itens = S.cfg.playlist ? d.itens : d.itens.filter((i) => S.plSel.has(i.n));
        if (!itens.length) return;
        Object.assign(spec, { itens, total: d.total, playlist_titulo: d.titulo, canal: d.canal });
      } else {
        spec.meta = { titulo: d.titulo, canal: d.canal, dur: d.dur, thumb: d.thumb };
      }
    }
    const r = await chamar('adicionar', spec);
    if (!r || !r.ok) {
      await dialogo({ icone: 'alert', cor: 'danger', titulo: 'Não foi possível adicionar', texto: (r && r.erro) || 'Tente de novo.', botoes: [{ rotulo: 'Entendi', tipo: 'solid', valor: true }] });
      return;
    }
    await salvarCfg({ formato: S.formato, qualidade: S.qualidade });
    $('#link').value = '';
    S.prev.url = ''; S.prev.seq++;
    definirPreview('vazio');
    irPara('fila');
  }

  // ======================================================================== FILA
  const rotuloStatus = (it) => ROTULO_ST[it.status] || it.status;

  function botoesCard(it) {
    const b = (act, ic, rot) => '<button class="ob-btn btn btn-icon" data-act="' + act + '" aria-label="' + rot + '" title="' + rot + '">' + icone(ic, 18) + '</button>';
    const out = [];
    switch (it.status) {
      case 'baixando': out.push(b('item-pausar', 'pause', 'Pausar'), b('item-cancelar', 'x', 'Cancelar')); break;
      case 'convertendo': out.push(b('item-cancelar', 'x', 'Cancelar')); break;
      case 'aguardando': out.push(b('item-remover', 'trash', 'Remover da fila')); break;
      case 'pausado': out.push(b('item-retomar', 'play', 'Retomar'), b('item-cancelar', 'x', 'Cancelar'), b('item-remover', 'trash', 'Remover da fila')); break;
      case 'erro':
        out.push('<button class="ob-btn btn btn--danger" data-act="item-detalhes">Detalhes</button>', b('item-retry', 'retry', 'Tentar de novo'), b('item-remover', 'trash', 'Remover da fila')); break;
      case 'concluido': out.push(b('item-pasta', 'folder', 'Abrir pasta'), b('item-remover', 'trash', 'Remover da fila')); break;
      case 'cancelado': out.push(b('item-retry', 'retry', 'Tentar de novo'), b('item-remover', 'trash', 'Remover da fila')); break;
    }
    return out.join('');
  }

  function textosCard(it) {
    const primeiro = (S.fila.find((x) => x.status === 'aguardando') || {}).id;
    if (it.status === 'aguardando') return [it.titulo ? 'Aguardando a vez' : 'Buscando título e qualidades…', it.id === primeiro ? 'Próximo da fila' : 'Na fila'];
    if (it.status === 'concluido') return [it.esq, window.U.relativo(it.fim)];
    return [it.esq, it.dir];
  }

  function cardHtml(it) {
    const resolvendo = !it.titulo;
    const [esq, dir] = textosCard(it);
    const barra = it.indet ? '<div class="bar ob-indet" role="progressbar" aria-label="Convertendo"></div>' :
      '<div class="bar st-' + it.status + '" role="progressbar" aria-label="Progresso" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + Math.round(it.pct) + '"><div class="bar__fill" style="width:' + it.pct + '%"></div></div>';
    return '<article class="qcard' + (S.sel.has(it.id) ? ' is-sel' : '') + '" aria-label="' + esc(it.titulo || it.url) + '"' + (it.status === 'erro' ? ' title="Duplo clique para ver detalhes"' : '') + '>' +
      '<input type="checkbox" class="qsel" aria-label="Selecionar item"' + (S.sel.has(it.id) ? ' checked' : '') + '>' +
      thumbHtml(it.thumb, it.dur, 'thumb thumb--sm', resolvendo) +
      '<div class="qcard__main"><div class="qcard__title">' +
      (it.idx ? '<span class="qcard__idx">' + esc(it.idx) + '</span>' : '') +
      '<span class="qcard__name ell' + (resolvendo ? ' is-soft' : '') + '">' + esc(it.titulo || it.url) + '</span></div>' +
      '<div class="qcard__meta"><span class="tag st-' + it.status + '"><span class="dot"></span>' + rotuloStatus(it) + '</span>' +
      '<span class="tag tag--quiet">' + esc(it.rotulo) + '</span>' + (it.sub ? '<span class="caption">' + esc(it.sub) + '</span>' : '') + '</div>' +
      barra +
      '<div class="qcard__lr"><span class="qcard__left' + (it.status === 'erro' ? ' is-danger' : '') + '">' + esc(esq) + '</span><span class="qcard__right">' + esc(dir) + '</span></div></div>' +
      '<div class="qcard__acts">' + botoesCard(it) + '</div></article>';
  }

  // Muda só o que mudou, para não perder o clique quando o progresso atualiza várias vezes por segundo.
  function assinatura(it) {
    return [it.status, it.titulo, it.canal, it.idx, it.sub, it.rotulo, it.thumb, it.dur, it.indet, it.arquivo, it.erro ? 1 : 0].join('|');
  }

  function desenharFila() {
    const ul = $('#queue');
    const ids = S.fila.map((i) => i.id);
    $$('li', ul).forEach((li) => { if (ids.indexOf(li.dataset.id) < 0) li.remove(); });
    S.sel.forEach((id) => { if (ids.indexOf(id) < 0) S.sel.delete(id); });

    S.fila.forEach((it, pos) => {
      let li = $('li[data-id="' + it.id + '"]', ul);
      const sig = assinatura(it);
      if (!li) {
        li = document.createElement('li');
        li.dataset.id = it.id;
        li.dataset.sig = sig;
        li.innerHTML = cardHtml(it);
      } else if (li.dataset.sig !== sig) {
        li.dataset.sig = sig;
        li.innerHTML = cardHtml(it);
      } else {
        const [esq, dir] = textosCard(it);
        $('.qcard__left', li).textContent = esq;
        $('.qcard__right', li).textContent = dir;
        const fill = $('.bar__fill', li);
        if (fill) { fill.style.width = it.pct + '%'; fill.parentNode.setAttribute('aria-valuenow', Math.round(it.pct)); }
      }
      if (ul.children[pos] !== li) ul.insertBefore(li, ul.children[pos] || null);
    });

    const vazio = S.fila.length === 0;
    $('#queue-empty').hidden = !vazio;
    ul.hidden = vazio;
    desenharBarraFila();
  }

  function desenharBarraFila() {
    const f = S.fila, n = f.length;
    const cont = (st) => f.filter((i) => i.status === st).length;
    const partes = [];
    if (n) {
      partes.push(n + ' ' + plural(n, 'item', 'itens'));
      const b = cont('baixando') + cont('convertendo'), w = cont('aguardando'), e = cont('erro'), c = cont('concluido');
      if (b) partes.push(b + ' ' + plural(b, 'baixando', 'baixando'));
      if (w) partes.push(w + ' na fila');
      if (e) partes.push(e + ' com ' + plural(e, 'erro', 'erros'));
      if (c) partes.push(c + ' ' + plural(c, 'concluído', 'concluídos'));
    }
    $('#fila-resumo').textContent = partes.length ? partes.join(' · ') : 'Nenhum download em andamento';

    const ns = S.sel.size;
    $('#sel-all').disabled = !n;
    $('#sel-all').checked = n > 0 && ns === n;
    $('#sel-all').indeterminate = ns > 0 && ns < n;
    $('#sel-all-text').textContent = ns ? ns + ' ' + plural(ns, 'selecionado', 'selecionados') : 'Selecionar todos';
    $('#sel-all-label').style.color = n ? '' : 'var(--ink-faint)';
    $('#btn-remover-sel span').textContent = ns ? 'Remover selecionados (' + ns + ')' : 'Remover selecionados';

    const tem = (...sts) => f.some((i) => sts.indexOf(i.status) >= 0);
    const hab = { 'cancelar-atual': tem('baixando', 'convertendo'), 'parar-tudo': tem('baixando', 'convertendo', 'aguardando'), 'remover-sel': ns > 0, 'limpar-concluidos': tem('concluido', 'cancelado', 'erro') };
    $$('[data-needs-items]').forEach((b) => { b.disabled = !hab[b.dataset.act]; });

    const ativos = f.filter((i) => ['aguardando', 'baixando', 'convertendo', 'pausado'].indexOf(i.status) >= 0).length;
    const badge = $('#badge-fila');
    badge.hidden = !ativos;
    badge.textContent = ativos;
  }

  // ------------------------------------------------------------------ Status global
  function calcularStatus() {
    const f = S.fila;
    const em = f.filter((i) => i.status === 'baixando' || i.status === 'convertendo');
    const baixando = em.filter((i) => i.status === 'baixando');
    const espera = f.filter((i) => i.status === 'aguardando');
    const fim = f.filter((i) => i.fim).sort((a, b) => b.fim - a.fim)[0];
    if (em.length) {
      if (!baixando.length) return { rotulo: 'Convertendo para ' + em[0].formato, cor: 'var(--ink)', indet: true, pct: 0 };
      const media = baixando.reduce((a, i) => a + i.pct, 0) / baixando.length;
      let r = 'Baixando ' + Math.round(media) + '%';
      if (baixando[0].idx) r += ' · ' + baixando[0].idx; else if (espera.length) r += ' · ' + espera.length + ' na fila';
      return { rotulo: r, cor: 'var(--ink)', indet: false, pct: media };
    }
    if (espera.length) return { rotulo: 'Iniciando', cor: 'var(--ink-soft)', indet: false, pct: 0 };
    if (fim) {
      if (fim.status === 'erro') { const n = f.filter((i) => i.status === 'erro').length; return { rotulo: 'Erro em ' + n + ' ' + plural(n, 'item', 'itens'), cor: 'var(--danger)', indet: false, pct: fim.pct }; }
      if (fim.status === 'cancelado') return { rotulo: 'Cancelado · fila parada', cor: 'var(--warn)', indet: false, pct: 0 };
      const n = f.filter((i) => i.status === 'concluido').length;
      return { rotulo: 'Concluído · ' + n + ' ' + plural(n, 'arquivo salvo', 'arquivos salvos'), cor: 'var(--ok)', indet: false, pct: 100 };
    }
    return { rotulo: 'Pronto', cor: 'var(--ink-faint)', indet: false, pct: 0 };
  }

  function desenharStatus() {
    const st = calcularStatus();
    $('#status').style.setProperty('--c', st.cor);
    $('#status-text').textContent = st.rotulo;
    const bar = $('#bar');
    bar.classList.toggle('ob-indet', st.indet);
    bar.setAttribute('aria-valuenow', Math.round(st.pct));
    const fill = $('#bar-fill');
    fill.style.width = st.pct + '%';
    fill.style.setProperty('--c', st.cor);
    const ff = ffmpegOk() ? 'ffmpeg ok' : 'ffmpeg ausente · conversões desativadas';
    $('#status-right').textContent = ff + ' · yt-dlp ' + (S.ytdlp.versao || '');
    $('#dot-config').hidden = ffmpegOk();
    $('#dot-sistema').hidden = ffmpegOk();
    desenharCompactoStatus(st);
  }

  // ------------------------------------------------------------------------ Toasts
  function toast(o) {
    const el = document.createElement('section');
    el.className = 'toast';
    el.setAttribute('aria-label', o.titulo);
    el.innerHTML = '<span class="round round--sm round--' + (o.cor || 'ok') + '" aria-hidden="true">' + icone(o.icone || 'check', 18) + '</span>' +
      '<div class="toast__body"><span class="toast__title">' + esc(o.titulo) + '</span>' +
      (o.texto ? '<span class="toast__text ell">' + esc(o.texto) + '</span>' : '') +
      (o.acoes && o.acoes.length ? '<div class="toast__acts">' + o.acoes.map((a, i) => '<button class="ob-link link-btn" data-toast-act="' + i + '">' + esc(a.rotulo) + '</button>').join('') + '</div>' : '') + '</div>' +
      '<button class="ob-btn btn btn-icon toast__x" data-toast-x aria-label="Fechar aviso">' + icone('x', 16) + '</button>';
    el.addEventListener('click', (e) => {
      const a = e.target.closest('[data-toast-act]');
      if (a) { o.acoes[+a.dataset.toastAct].fn(); el.remove(); }
      if (e.target.closest('[data-toast-x]')) el.remove();
    });
    const box = $('#toasts');
    box.appendChild(el);
    while (box.children.length > 3) box.firstChild.remove();
    setTimeout(() => el.remove(), o.ms || 9000);
  }

  function tratarEvento(ev) {
    if (ev.tipo !== 'concluido') return;
    if (ev.entrada) { S.hist.unshift(ev.entrada); S.hist.length = Math.min(S.hist.length, 500); if (S.pagina === 'historico') desenharHistorico(); }
    if (S.cfg.avisar && !S.onb) {
      toast({
        titulo: 'Download concluído', texto: ev.nome || ev.titulo,
        acoes: [{ rotulo: 'Abrir arquivo', fn: () => abrirComAviso('abrir_item', ev.id, 'arquivo') }, { rotulo: 'Abrir pasta', fn: () => abrirComAviso('abrir_item', ev.id, 'pasta') }],
      });
    }
  }

  async function abrirComAviso(metodo, id, o_que) {
    const r = await chamar(metodo, id, o_que);
    if (r && r.ok === false) toast({ titulo: 'Não foi possível abrir', texto: r.erro, icone: 'alert', cor: 'warn' });
  }

  // ------------------------------------------------------------------ Diálogos
  function dialogo(o) {
    return new Promise((resolve) => {
      const wrap = $('#dialog-wrap');
      const cor = o.cor === 'danger' ? 'danger' : o.cor === 'warn' ? 'warn' : 'line';
      $('#dialog').innerHTML = '<span class="round round--' + cor + '" aria-hidden="true">' + icone(o.icone || 'alert', 20) + '</span>' +
        '<h2 id="dialog-titulo">' + esc(o.titulo) + '</h2><p>' + esc(o.texto) + '</p><div class="modal__btns">' +
        o.botoes.map((b, i) => '<button class="ob-btn btn' + (b.tipo === 'solid' ? ' ob-solid btn--solid' : b.tipo === 'danger' ? ' btn--danger' : '') + '" data-dlg="' + i + '">' + esc(b.rotulo) + '</button>').join('') + '</div>';
      wrap.hidden = false;
      const fechar = (valor) => { wrap.hidden = true; S.dialogo = null; resolve(valor); };
      S.dialogo = { fechar, esc: o.esc };
      $$('[data-dlg]', wrap).forEach((b) => b.addEventListener('click', () => fechar(o.botoes[+b.dataset.dlg].valor)));
      const foco = $('.btn--solid', wrap) || $('[data-dlg]', wrap);
      if (foco) foco.focus();
    });
  }

  // -------------------------------------------------------------------- Detalhes do erro
  function abrirDrawer(id) {
    const it = S.fila.find((i) => i.id === id);
    if (!it || it.status !== 'erro') return;
    const w = $('#drawer-wrap');
    w.innerHTML = '<aside class="drawer" role="dialog" aria-modal="true" aria-labelledby="erro-titulo">' +
      '<div class="drawer__head"><span class="label label--faint">Detalhes do erro</span><button class="ob-btn btn btn-icon" data-act="fechar-drawer" aria-label="Fechar detalhes">' + icone('x', 18) + '</button></div>' +
      '<div class="drawer__body"><div class="stack stack--16"><span class="round round--danger" aria-hidden="true">' + icone('alert', 20) + '</span>' +
      '<h2 id="erro-titulo">' + esc(it.erro_titulo || 'Não foi possível baixar este vídeo') + '</h2><p class="soft">' + esc(it.erro_msg) + '</p></div>' +
      '<dl class="drawer__dl"><dt>Título</dt><dd>' + esc(it.titulo || '-') + '</dd><dt>Link</dt><dd>' + esc(it.url) + '</dd>' +
      '<dt>Formato</dt><dd>' + esc(it.rotulo) + '</dd><dt>Quando</dt><dd>' + esc(window.U.quando(it.fim)) + (it.parou_em ? ' · parou em ' + it.parou_em + '%' : '') + '</dd></dl>' +
      '<details><summary>Log técnico' + icone('chevron', 18, 'ob-chev') + '</summary><pre class="log">' + esc(it.erro) + '</pre></details></div>' +
      '<div class="drawer__foot"><button class="ob-btn btn" data-act="copiar-erro" data-id="' + esc(it.id) + '">' + icone('copy', 16) + '<span>Copiar erro</span></button>' +
      '<button class="ob-btn ob-solid btn btn--solid" data-act="drawer-retry" data-id="' + esc(it.id) + '">' + icone('retry', 16) + 'Tentar de novo</button></div></aside>';
    w.hidden = false;
    $('[data-act="fechar-drawer"]', w).focus();
  }
  const fecharDrawer = () => { $('#drawer-wrap').hidden = true; };

  // ===================================================================== HISTÓRICO
  const ehAudioFmt = (f) => AUDIO.indexOf(f) >= 0;

  function filtrarHist() {
    const q = S.busca.trim().toLowerCase();
    return S.hist.filter((e) => {
      if (S.filtro === 'video' && ehAudioFmt(e.fmt)) return false;
      if (S.filtro === 'audio' && !ehAudioFmt(e.fmt)) return false;
      return !q || (e.titulo + ' ' + (e.canal || '')).toLowerCase().indexOf(q) >= 0;
    });
  }

  function linhaHist(e) {
    const audio = ehAudioFmt(e.fmt);
    const fmt = e.fmt + (e.qual ? ' · ' + e.qual : '');
    return '<li class="hitem" data-hid="' + esc(e.id) + '"><div class="hrow" title="Duplo clique abre a pasta">' +
      '<div class="hrow__title"><span class="thumb thumb--row" aria-hidden="true">' + (e.thumb ? '<img src="' + esc(e.thumb) + '" alt="" loading="lazy" referrerpolicy="no-referrer">' : '') +
      '<span style="position:relative">' + icone(audio ? 'music' : 'play', 16) + '</span>' + (e.dur ? '<span class="thumb__dur">' + esc(e.dur) + '</span>' : '') + '</span>' +
      '<div class="hrow__text"><span class="hrow__name ell">' + esc(e.titulo) + '</span>' + (e.canal ? '<span class="hrow__sub ell">' + esc(e.canal) + '</span>' : '') + '</div></div>' +
      '<span><span class="tag tag--line">' + esc(fmt) + '</span></span><span class="hrow__when">' + esc(window.U.quando(e.ts)) + '</span>' +
      '<span class="hrow__folder">' + icone('folder', 16) + '<span class="ell">' + esc(e.pasta) + '</span></span></div></li>';
  }

  function desenharHistorico() {
    const lista = filtrarHist();
    $('#hist-contagem').textContent = S.hist.length + ' de 500 itens';
    $('#btn-limpar-hist').disabled = !S.hist.length;
    $('#busca').disabled = !S.hist.length;
    const vazio = !lista.length;
    $('#hist-wrap').hidden = vazio;
    $('#hist-empty').hidden = !vazio;
    if (vazio) {
      const filtrado = S.hist.length > 0;
      $('#hist-empty-titulo').textContent = filtrado ? 'Nada encontrado' : 'Seu histórico está vazio';
      $('#hist-empty-texto').textContent = filtrado ? 'Nenhum item combina com a busca ou com o filtro de formato.' : 'Tudo que você baixar fica guardado aqui, até 500 itens, para abrir a pasta ou baixar de novo.';
      $('#hist-empty-cta').hidden = filtrado;
      if (!$('#hist-empty .orbit svg')) $$('#hist-empty [data-orbit]').forEach(window.U.orbita);
      return;
    }
    const grupos = [];
    lista.forEach((e) => {
      const g = window.U.grupo(e.ts);
      let x = grupos.find((y) => y.nome === g);
      if (!x) { x = { nome: g, itens: [] }; grupos.push(x); }
      x.itens.push(e);
    });
    $('#hist-table').innerHTML = '<div class="thead" aria-hidden="true"><span>Título</span><span>Formato</span><span>Data e hora</span><span>Pasta</span></div>' +
      grupos.map((g) => '<section aria-label="' + esc(g.nome) + '"><h2 class="hgroup">' + esc(g.nome) + '</h2><ul>' + g.itens.map(linhaHist).join('') + '</ul></section>').join('');
    S.histSel = null;
  }

  function selecionarHist(li) {
    $$('.hitem.is-sel').forEach((x) => { x.classList.remove('is-sel'); const a = $('.hacts', x); if (a) a.remove(); });
    if (!li) { S.histSel = null; return; }
    S.histSel = li.dataset.hid;
    li.classList.add('is-sel');
    const btn = (act, ic, rot, solid) => '<button class="ob-btn' + (solid ? ' ob-solid btn--solid' : '') + ' btn" data-act="' + act + '">' + icone(ic, 16) + rot + '</button>';
    li.insertAdjacentHTML('beforeend', '<div class="hacts"><div class="hacts__btns">' + btn('h-arquivo', 'play', 'Abrir arquivo', true) + btn('h-pasta', 'folder', 'Abrir pasta') + btn('h-link', 'link', 'Copiar link') + btn('h-de-novo', 'retry', 'Baixar de novo') + '</div><span class="caption">Duplo clique abre a pasta</span></div>');
  }

  // ================================================================== CONFIGURAÇÕES
  function preencherConfig() {
    const c = S.cfg;
    $('#cfg-pasta').value = c.pasta || '';
    $('#cfg-simultaneos').textContent = c.simultaneos;
    $$('[data-cfg]').forEach((el) => {
      const k = el.dataset.cfg;
      if (el.getAttribute('role') === 'switch') el.setAttribute('aria-checked', c[k] ? 'true' : 'false');
      else if (document.activeElement !== el) el.value = c[k];
    });
    $$('[data-tema]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.tema === c.tema)));
    const sobre = S.app;
    $('#sobre-versao').textContent = 'Versão ' + (sobre.versao || '') + ' · código aberto · feito com yt-dlp e ffmpeg';
    $('#lnk-repo').hidden = !sobre.repo;
    $('#lnk-releases').hidden = !sobre.releases;
    $('#lnk-apoio').hidden = !S.apoio.ativo;
    $('#row-convite').hidden = !S.apoio.ativo;
    $('#btn-apoio').hidden = !S.apoio.ativo;
    desenharYtdlp();
  }

  async function salvarCfg(parcial) {
    const r = await chamar('config_salvar', parcial);
    if (r) S.cfg = r;
    preencherConfig();
    desenharOpcoes();
    return S.cfg;
  }

  function desenharYtdlp() {
    const u = S.ytup || {}, b = $('#btn-ytdlp'), d = $('#ytdlp-desc');
    const v = S.ytdlp.versao || '-';
    let txt = 'Versão ' + v + '. O site muda com frequência; atualizar resolve a maioria dos erros.';
    let rot = 'Atualizar yt-dlp';
    b.disabled = false;
    if (u.estado === 'verificando') { rot = 'Verificando…'; b.disabled = true; txt = 'Procurando a versão mais recente…'; }
    else if (u.estado === 'atualizado') txt = 'Atualizado para a versão ' + u.versao + '. Feche e abra o app para usar a nova versão.';
    else if (u.estado === 'em_dia') txt = 'Você já está na versão mais recente (' + v + ').';
    else if (u.estado === 'erro') txt = 'Não foi possível atualizar: ' + u.erro;
    d.textContent = txt;
    $('span', b).textContent = rot;
  }

  function desenharSistema() {
    const f = S.ffmpeg, dl = S.ffdl || {};
    const alvo = $('#ffmpeg-card');
    const verificar = '<button class="ob-btn btn" data-act="ffmpeg-verificar">Verificar de novo</button>';
    if (dl.estado === 'baixando' || dl.estado === 'extraindo') {
      const pct = Math.round(dl.pct || 0);
      alvo.innerHTML = '<div class="sys-card"><div class="sys-card__top"><span class="round round--line" aria-hidden="true">' + icone('download', 20) + '</span>' +
        '<div class="sys-card__txt"><span class="sys-card__title">' + (dl.estado === 'extraindo' ? 'Instalando o ffmpeg…' : 'Baixando o ffmpeg…') + '</span>' +
        '<span class="sys-card__desc">' + (dl.total_mb ? dl.mb + ' de ' + dl.total_mb + ' MB' : 'Aguarde') + '</span></div></div>' +
        '<div class="bar" role="progressbar" aria-valuenow="' + pct + '"><div class="bar__fill" style="width:' + pct + '%"></div></div></div>';
      return;
    }
    if (f.estado === 'ausente') {
      const pode = f.pode_baixar;
      alvo.innerHTML = '<div class="sys-card sys-card--danger"><div class="sys-card__top"><span class="round round--danger" aria-hidden="true">' + icone('alert', 20) + '</span>' +
        '<div class="sys-card__txt"><div class="sys-card__title">ffmpeg não encontrado<span class="tag tag--danger">Erro</span></div>' +
        '<span class="sys-card__desc">Sem ele não dá para converter para mp3, wav, opus ou flac, nem juntar vídeo e áudio em alta qualidade.</span></div></div>' +
        (dl.estado === 'erro' ? '<p class="help help--danger">' + icone('alert', 16) + esc(dl.erro) + '</p>' : '') +
        '<ol>' + (pode ? '<li>Baixe automaticamente pelo botão abaixo (cerca de 90 MB, fica na pasta do app), ou</li>' : '') +
        '<li>instale o ffmpeg' + (pode ? ' e adicione a pasta bin ao PATH do sistema, ou' : ' pelo gerenciador de pacotes do sistema (apt, brew...), ou') + '</li>' +
        '<li>aponte a pasta onde está o ' + (navigator.platform.indexOf('Win') === 0 ? 'ffmpeg.exe' : 'ffmpeg') + '.</li></ol>' +
        '<div class="sys-card__btns">' + (pode ? '<button class="ob-btn ob-solid btn btn--solid" data-act="ffmpeg-baixar">' + icone('download', 16) + 'Baixar ffmpeg</button>' : '') +
        '<button class="ob-btn btn" data-act="ffmpeg-apontar">Apontar pasta</button>' + verificar + '</div></div>';
      return;
    }
    const pasta = f.estado === 'pasta';
    const ver = f.versao ? 'Versão ' + f.versao + '. ' : '';
    alvo.innerHTML = '<div class="sys-card"><div class="sys-card__top"><span class="round round--ok" aria-hidden="true">' + icone('check', 20) + '</span>' +
      '<div class="sys-card__txt"><div class="sys-card__title">' + (pasta ? 'ffmpeg em pasta específica' : 'ffmpeg encontrado no PATH') + '<span class="tag tag--ok">Ok</span></div>' +
      (pasta ? '<span class="sys-card__desc sys-card__desc--mono">' + esc(f.caminho) + '</span>' : '') +
      '<span class="sys-card__desc">' + esc(ver) + 'Conversão de áudio e junção de vídeo em alta qualidade liberadas.</span></div>' +
      '<div class="sys-card__btns">' + (pasta ? '<button class="ob-btn btn" data-act="ffmpeg-apontar">Alterar pasta</button><button class="ob-btn btn" data-act="ffmpeg-path">Usar o do PATH</button>' : verificar) + '</div></div></div>';
  }

  function observarSecoes() {
    const links = $$('[data-spy]');
    const alvos = links.map((a) => document.getElementById(a.dataset.spy));
    const raiz = $('.pages');
    raiz.addEventListener('scroll', () => {
      if (S.pagina !== 'config') return;
      let atual = 0;
      const topo = raiz.getBoundingClientRect().top + 120;
      alvos.forEach((el, i) => { if (el.getBoundingClientRect().top <= topo) atual = i; });
      links.forEach((a, i) => a.setAttribute('aria-current', String(i === atual)));
    }, { passive: true });
  }

  // ====================================================================== APOIO
  function abrirApoio(manual) {
    if (!S.apoio.ativo) { if (manual) toast({ titulo: 'Convite de apoio não configurado', texto: 'Crie o arquivo apoio.json (veja o README).', icone: 'info', cor: 'line' }); return; }
    const a = S.apoio;
    $('#apoio-qr-col').hidden = !a.svg;
    $('#apoio-qr').innerHTML = a.svg || '';
    $('#btn-copiar-pix').hidden = !a.payload;
    $('#btn-link-apoio').hidden = !a.link;
    $('#apoio').hidden = false;
    $('#btn-copiar-pix span').textContent = 'Copiar Pix copia e cola';
    ($('#btn-copiar-pix').hidden ? $('[data-act="fechar-apoio"].link-btn') : $('#btn-copiar-pix')).focus();
  }
  const fecharApoio = () => { $('#apoio').hidden = true; };

  // ===================================================================== COMPACTO
  function desenharCompactoSelect() {
    const sel = $('#c-fmt');
    const atual = S.formato + '|' + qualidadeEfetiva();
    const opcoes = PRESETS.filter((p) => formatoPermitido(p[0]));
    if (!opcoes.some((p) => p[0] + '|' + p[1] === atual) && formatoPermitido(S.formato)) opcoes.unshift([S.formato, qualidadeEfetiva(), S.formato + ' · ' + (ehAudio() ? '192 kbps' : qualidadeEfetiva().toLowerCase())]);
    sel.innerHTML = opcoes.map((p) => '<option value="' + p[0] + '|' + p[1] + '"' + (p[0] + '|' + p[1] === atual ? ' selected' : '') + '>' + esc(p[2]) + '</option>').join('');
  }

  function desenharCompactoStatus(st) {
    if (!S.compacto) return;
    const em = S.fila.filter((i) => i.status === 'baixando' || i.status === 'convertendo');
    const espera = S.fila.filter((i) => i.status === 'aguardando').length;
    const left = $('#c-left');
    left.className = 'compact__left';
    if (em.length) {
      const it = em[0];
      left.textContent = (it.idx ? it.idx + ' ' : '') + (it.status === 'convertendo' ? it.esq : 'Baixando ' + Math.round(it.pct) + '%') + ' · ' + (it.titulo || it.url);
      left.classList.add('is-busy');
      $('#c-right').textContent = (it.dir || '').replace(' restantes', '') || (espera + ' na fila');
    } else {
      left.textContent = S.avisoCompacto || (st.rotulo === 'Pronto' ? 'Pronto · salva em ' + (S.cfg.pasta || '') : st.rotulo);
      if (st.cor === 'var(--danger)') left.classList.add('is-danger');
      $('#c-right').textContent = espera + ' na fila';
    }
    const bar = $('#c-bar');
    bar.classList.toggle('ob-indet', st.indet);
    $('#c-bar-fill').style.width = st.pct + '%';
    bar.setAttribute('aria-valuenow', Math.round(st.pct));
  }

  async function entrarCompacto() {
    S.compacto = true;
    $('#app').hidden = true;
    $('#compact').hidden = false;
    desenharCompactoSelect();
    await chamar('compacto', true);
    desenharStatus();
    $('#c-link').focus();
  }
  async function sairCompacto() {
    S.compacto = false;
    $('#compact').hidden = true;
    $('#app').hidden = false;
    await chamar('compacto', false);
    irPara(S.pagina);
  }

  async function baixarCompacto() {
    const url = $('#c-link').value.trim();
    S.avisoCompacto = '';
    if (!ehUrl(url)) { S.avisoCompacto = url ? 'Esse link não é válido (use http:// ou https://)' : 'Cole um link primeiro'; desenharStatus(); return; }
    const [formato, qualidade] = $('#c-fmt').value.split('|');
    S.formato = formato; S.qualidade = qualidade;
    S.avisoCompacto = 'Lendo o link…'; desenharStatus();
    const r = await chamar('adicionar_rapido', url, formato, qualidade);
    if (r && r.ok) { $('#c-link').value = ''; S.avisoCompacto = r.adicionados > 1 ? r.adicionados + ' vídeos adicionados à fila' : 'Adicionado à fila'; salvarCfg({ formato, qualidade }); }
    else S.avisoCompacto = (r && r.erro) || 'Não foi possível adicionar';
    desenharStatus();
    setTimeout(() => { S.avisoCompacto = ''; desenharStatus(); }, 4000);
  }

  // ================================================================= PRIMEIRA EXECUÇÃO
  function desenharOnboarding() {
    const el = $('#onboarding');
    const f = S.ffmpeg, dl = S.ffdl || {};
    const ok = f.estado !== 'ausente';
    const baixando = dl.estado === 'baixando' || dl.estado === 'extraindo';
    const escolha = S.onb.escolha;
    const pct = Math.round(dl.pct || 0);
    const ffTxt = ok ? 'Encontrado ' + (f.estado === 'path' ? 'no PATH' : 'em ' + f.caminho) + (f.versao ? ' · versão ' + f.versao : '') : 'Procuramos no PATH e nas pastas mais comuns.';
    const cor = ok ? 'ok' : 'danger';
    const pode = f.pode_baixar;
    let cta = ok ? 'Começar a baixar' : escolha === 'baixar' && pode ? 'Baixar ffmpeg e continuar' : 'Apontar pasta e continuar';
    if (baixando) cta = (dl.estado === 'extraindo' ? 'Instalando…' : 'Baixando… ' + pct + '%');
    el.innerHTML =
      '<header class="top"><span class="wordmark">baixador</span><span class="label label--faint">Primeira execução · ' + (ok ? '2 de 2' : '1 de 2') + '</span></header>' +
      '<div class="onb"><main class="onb__main"><div class="onb__hero"><div class="orbit" data-orbit="160:116.8,43.2:2,80">' + icone('download', 28, '" style="position:relative') + '</div>' +
      '<div class="onb__txt"><h1 class="h1">' + (ok ? 'Tudo pronto' : 'Antes de começar') + '</h1><p class="lead">' +
      (ok ? 'Encontramos tudo que o baixador precisa. Já dá para baixar vídeos e converter áudio.' : 'O baixador usa o ffmpeg para converter áudio e juntar vídeo em alta qualidade. Ele não está no seu computador.') + '</p></div></div>' +
      '<ul class="checks" aria-label="Verificação do sistema">' +
      '<li><span class="round round--sm round--ok" aria-hidden="true">' + icone('check', 18) + '</span><div class="checks__txt"><b>yt-dlp</b><span>Incluído no app · versão ' + esc(S.ytdlp.versao) + '</span></div><span class="tag tag--ok">Pronto</span></li>' +
      '<li><span class="round round--sm round--' + cor + '" aria-hidden="true">' + icone(ok ? 'check' : 'alert', 18) + '</span><div class="checks__txt"><b>ffmpeg</b><span>' + esc(ffTxt) + '</span></div><span class="tag tag--' + cor + '">' + (ok ? 'Pronto' : 'Não encontrado') + '</span></li></ul>' +
      (!ok ? '<fieldset class="choices"><legend class="label label--soft">Como você quer resolver</legend>' +
        (pode ? '<label class="choice' + (escolha === 'baixar' ? ' is-on' : '') + '"><input type="radio" name="ffmpeg" value="baixar"' + (escolha === 'baixar' ? ' checked' : '') + '><span class="stack stack--4"><b>Baixar automaticamente<span class="tag tag--accent">Recomendado</span></b><span class="d">Cerca de 90 MB, salvo na pasta do app. Não mexe nas configurações do sistema.</span></span></label>' : '') +
        '<label class="choice' + (escolha === 'apontar' || !pode ? ' is-on' : '') + '"><input type="radio" name="ffmpeg" value="apontar"' + (escolha === 'apontar' || !pode ? ' checked' : '') + '><span class="stack stack--4"><b>Já tenho o ffmpeg</b><span class="d">Aponte a pasta onde está o ' + (navigator.platform.indexOf('Win') === 0 ? 'ffmpeg.exe' : 'ffmpeg') + '.' + (pode ? '' : ' Neste sistema, instale pelo gerenciador de pacotes (apt, brew...).') + '</span></span></label></fieldset>' : '') +
      (baixando ? '<div class="dl-progress"><div class="bar" role="progressbar" aria-valuenow="' + pct + '"><div class="bar__fill" style="width:' + pct + '%"></div></div><span class="caption">' + (dl.total_mb ? dl.mb + ' de ' + dl.total_mb + ' MB' : 'Aguarde') + '</span></div>' : '') +
      (dl.estado === 'erro' && !ok ? '<p class="help help--danger">' + icone('alert', 16) + esc(dl.erro) + '</p>' : '') +
      '<div class="onb__foot">' +
      (!ok ? '<div class="onb__skip"><button class="ob-link link-btn" data-act="onb-pular"' + (baixando ? ' disabled' : '') + '>Pular por enquanto</button><span class="caption">Sem o ffmpeg, só mp4 e m4a, em qualidade reduzida, sem conversão de áudio.</span></div>' : '<span class="caption">Você pode mudar isso depois em Configurações › Sistema.</span>') +
      '<button class="ob-btn ob-solid btn btn-lg btn--solid" data-act="onb-cta"' + (baixando ? ' disabled' : '') + '><span>' + esc(cta) + '</span><span class="btn-lg__arrow" aria-hidden="true">' + icone('arrow', 18) + '</span></button></div></main></div>' +
      '<footer class="foot"><div class="bar"><div class="bar__fill" style="width:' + (ok ? 100 : 50) + '%"></div></div><div class="foot__row"><span class="status" style="--c:' + (ok ? 'var(--ok)' : 'var(--ink-soft)') + '"><span class="dot"></span>' + (ok ? 'Pronto' : 'Verificando o sistema') + '</span><span class="caption">Etapa ' + (ok ? '2 de 2' : '1 de 2') + '</span></div></footer>';
    $$('[data-orbit]', el).forEach(window.U.orbita);
  }

  async function onbCta() {
    if (ffmpegOk()) return concluirOnboarding();
    const f = S.ffmpeg;
    if (S.onb.escolha === 'baixar' && f.pode_baixar) { await chamar('ffmpeg_baixar'); return; }
    const r = await chamar('ffmpeg_apontar');
    if (r && r.ok) { S.ffmpeg = r.ffmpeg; desenharOnboarding(); }
    else if (r && r.erro) toast({ titulo: 'ffmpeg não encontrado', texto: r.erro, icone: 'alert', cor: 'warn' });
  }

  async function concluirOnboarding() {
    await salvarCfg({ onboarded: true });
    S.onb = null;
    $('#onboarding').hidden = true;
    entrarNoApp();
  }

  // ======================================================================= INÍCIO
  function entrarNoApp() {
    desenharTudo();
    if (S.cfg.compacto) { entrarCompacto(); } else { $('#app').hidden = false; irPara('baixar'); }
    if (S.cfg.convite && S.apoio.ativo) {
      clearTimeout(S.apoioTimer);
      S.apoioTimer = setTimeout(() => { if (!S.dialogo && $('#drawer-wrap').hidden) abrirApoio(false); }, 1400);
    }
  }

  function desenharTudo() {
    preencherConfig();
    desenharOpcoes();
    desenharFila();
    desenharStatus();
    desenharSistema();
    desenharBaixar();
    $$('[data-orbit]').forEach((el) => { if (!$('svg.orbit__rings', el) && !el.closest('#preview')) window.U.orbita(el); });
  }

  // ==================================================================== EVENTOS
  const acoes = {
    colar: async () => { const t = (await lerClipboard()).trim(); if (t) { $('#link').value = t; aoDigitar(); } $('#link').focus(); },
    'colar-compacto': async () => { const t = (await lerClipboard()).trim(); if (t) $('#c-link').value = t; $('#c-link').focus(); },
    adicionar,
    'escolher-pasta': async () => { const r = await chamar('escolher_pasta', S.cfg.pasta); if (r && r.ok) await salvarCfg({ pasta: r.pasta }); },
    'alternar-tema': async () => { await salvarCfg({ tema: temaResolvido() === 'dark' ? 'light' : 'dark' }); aplicarTema(); },
    'compacto-on': entrarCompacto,
    'compacto-off': sairCompacto,
    'compacto-baixar': baixarCompacto,
    'abrir-apoio': () => abrirApoio(true),
    'fechar-apoio': fecharApoio,
    'copiar-pix': async () => {
      const ok = await copiarTexto(S.apoio.payload);
      const s = $('#btn-copiar-pix span'); s.textContent = ok ? 'Copiado, obrigado!' : 'Não consegui copiar';
      setTimeout(() => { s.textContent = 'Copiar Pix copia e cola'; }, 2800);
    },
    'abrir-link-apoio': () => chamar('abrir_link', S.apoio.link),
    'abrir-repo': () => chamar('abrir_link', S.app.repo),
    'abrir-releases': () => chamar('abrir_link', S.app.releases),
    'cancelar-atual': () => chamar('cancelar_atuais'),
    'parar-tudo': () => chamar('parar_tudo'),
    'remover-sel': () => { const ids = Array.from(S.sel); S.sel.clear(); return chamar('remover', ids); },
    'limpar-concluidos': () => chamar('limpar_concluidos'),
    'item-pausar': (b) => chamar('pausar', idDe(b)),
    'item-retomar': (b) => chamar('retomar', idDe(b)),
    'item-cancelar': (b) => chamar('cancelar', idDe(b)),
    'item-retry': (b) => chamar('tentar_de_novo', idDe(b)),
    'item-remover': (b) => { S.sel.delete(idDe(b)); return chamar('remover', [idDe(b)]); },
    'item-pasta': (b) => abrirComAviso('abrir_item', idDe(b), 'pasta'),
    'item-detalhes': (b) => abrirDrawer(idDe(b)),
    'fechar-drawer': fecharDrawer,
    'drawer-retry': async (b) => { await chamar('tentar_de_novo', b.dataset.id); fecharDrawer(); },
    'copiar-erro': async (b) => {
      const it = S.fila.find((i) => i.id === b.dataset.id); if (!it) return;
      const ok = await copiarTexto(it.erro_titulo + '\n' + it.url + '\n\n' + it.erro);
      const s = $('span', b); s.textContent = ok ? 'Copiado' : 'Não consegui copiar';
      setTimeout(() => { s.textContent = 'Copiar erro'; }, 2000);
    },
    'limpar-historico': async () => {
      const r = await dialogo({ icone: 'trash', cor: 'line', titulo: 'Limpar o histórico?', texto: 'Os ' + S.hist.length + ' registros são apagados. Os arquivos baixados continuam nas suas pastas.', botoes: [{ rotulo: 'Cancelar', tipo: 'ghost', valor: false }, { rotulo: 'Limpar histórico', tipo: 'danger', valor: true }] });
      if (r) { await chamar('historico_limpar'); S.hist = []; desenharHistorico(); }
    },
    'h-arquivo': () => abrirComAviso('historico_abrir', S.histSel, 'arquivo'),
    'h-pasta': () => abrirComAviso('historico_abrir', S.histSel, 'pasta'),
    'h-link': async () => { const e = S.hist.find((x) => x.id === S.histSel); if (e && (await copiarTexto(e.url))) toast({ titulo: 'Link copiado', icone: 'check', ms: 3000 }); },
    'h-de-novo': async () => {
      const r = await chamar('historico_baixar_de_novo', S.histSel);
      if (r && r.ok) irPara('fila'); else toast({ titulo: 'Não foi possível baixar de novo', texto: (r && r.erro) || '', icone: 'alert', cor: 'warn' });
    },
    'sim-menos': () => salvarCfg({ simultaneos: Math.max(1, S.cfg.simultaneos - 1) }),
    'sim-mais': () => salvarCfg({ simultaneos: Math.min(5, S.cfg.simultaneos + 1) }),
    'ffmpeg-verificar': async () => { S.ffmpeg = (await chamar('ffmpeg_verificar')) || S.ffmpeg; desenharSistema(); desenharOpcoes(); desenharStatus(); },
    'ffmpeg-baixar': () => chamar('ffmpeg_baixar'),
    'ffmpeg-apontar': async () => {
      const r = await chamar('ffmpeg_apontar');
      if (r && r.ok) { S.ffmpeg = r.ffmpeg; desenharSistema(); desenharOpcoes(); desenharStatus(); }
      else if (r && r.erro) toast({ titulo: 'ffmpeg não encontrado', texto: r.erro, icone: 'alert', cor: 'warn' });
    },
    'ffmpeg-path': async () => { S.ffmpeg = (await chamar('ffmpeg_usar_path')) || S.ffmpeg; desenharSistema(); desenharOpcoes(); desenharStatus(); },
    'atualizar-ytdlp': () => chamar('ytdlp_atualizar'),
    'onb-cta': onbCta,
    'onb-pular': concluirOnboarding,
  };
  const idDe = (el) => { const li = el.closest('[data-id]'); return li ? li.dataset.id : el.dataset.id; };

  document.addEventListener('click', (e) => {
    const t = e.target;
    if (t.id === 'apoio') return fecharApoio();
    if (t.id === 'dialog-wrap' && S.dialogo) return S.dialogo.fechar(S.dialogo.esc);
    if (t.id === 'drawer-wrap') return fecharDrawer();
    const nav = t.closest('[data-nav]');
    if (nav) return irPara(nav.dataset.nav);
    const sp = t.closest('[data-spy]');
    if (sp) { e.preventDefault(); const alvo = document.getElementById(sp.dataset.spy); if (alvo) alvo.scrollIntoView({ behavior: 'smooth', block: 'start' }); return; }
    const act = t.closest('[data-act]');
    if (act && !act.disabled && acoes[act.dataset.act]) return acoes[act.dataset.act](act, e);
    const fmt = t.closest('[data-formato]');
    if (fmt && !fmt.disabled) { S.formato = fmt.dataset.formato; desenharBaixar(); desenharCompactoSelect(); return; }
    const q = t.closest('[data-qualidade]');
    if (q && !q.disabled) { S.qualidade = q.dataset.qualidade; desenharBaixar(); return; }
    const tema = t.closest('[data-tema]');
    if (tema) { salvarCfg({ tema: tema.dataset.tema }).then(aplicarTema); return; }
    const filtro = t.closest('[data-filtro]');
    if (filtro) { S.filtro = filtro.dataset.filtro; $$('[data-filtro]').forEach((b) => b.setAttribute('aria-pressed', String(b === filtro))); desenharHistorico(); return; }
    const sw = t.closest('.switch[data-cfg]');
    if (sw) { salvarCfg({ [sw.dataset.cfg]: sw.getAttribute('aria-checked') !== 'true' }); return; }
    const li = t.closest('.hitem');
    if (li && !t.closest('button')) selecionarHist(li.classList.contains('is-sel') ? null : li);
  });

  document.addEventListener('dblclick', (e) => {
    const card = e.target.closest('.qcard');
    if (card && !e.target.closest('button, input')) { const li = card.closest('li'); if (li) abrirDrawer(li.dataset.id); return; }
    const li = e.target.closest('.hitem');
    if (li && !e.target.closest('button')) chamar('historico_abrir', li.dataset.hid, 'pasta');
  });

  document.addEventListener('change', (e) => {
    const t = e.target;
    if (t.classList.contains('qsel')) {
      const li = t.closest('li'); const id = li.dataset.id;
      if (t.checked) S.sel.add(id); else S.sel.delete(id);
      $('.qcard', li).classList.toggle('is-sel', t.checked);
      desenharBarraFila();
    } else if (t.id === 'sel-all') {
      S.sel = t.checked ? new Set(S.fila.map((i) => i.id)) : new Set();
      $$('#queue li').forEach((li) => { const on = S.sel.has(li.dataset.id); $('.qsel', li).checked = on; $('.qcard', li).classList.toggle('is-sel', on); });
      desenharBarraFila();
    } else if (t.dataset.pl) {
      const n = +t.dataset.pl; if (t.checked) S.plSel.add(n); else S.plSel.delete(n);
      plAtualizar();
    } else if (t.id === 'pl-all') {
      const d = S.prev.dados; S.plSel = t.checked ? new Set(d.itens.map((i) => i.n)) : new Set();
      $$('[data-pl]').forEach((cb) => { cb.checked = t.checked; });
      plAtualizar();
    } else if (t.name === 'ffmpeg') {
      S.onb.escolha = t.value; desenharOnboarding();
    } else if (t.dataset.cfg && t.getAttribute('role') !== 'switch') {
      salvarCfg({ [t.dataset.cfg]: t.value });
    } else if (t.id === 'c-fmt') {
      const [f, q] = t.value.split('|'); S.formato = f; S.qualidade = q; desenharOpcoes();
    }
  });

  document.addEventListener('input', (e) => {
    if (e.target.id === 'link') aoDigitar();
    if (e.target.id === 'busca') { S.busca = e.target.value; desenharHistorico(); }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      if (e.target.id === 'link') { e.preventDefault(); adicionar(); }
      if (e.target.id === 'c-link') { e.preventDefault(); baixarCompacto(); }
    }
    if (e.key === 'Escape') {
      if (S.dialogo) return S.dialogo.fechar(S.dialogo.esc);
      if (!$('#drawer-wrap').hidden) return fecharDrawer();
      if (!$('#apoio').hidden) return fecharApoio();
    }
  });

  // Ctrl+V fora de qualquer campo cola o link direto no campo principal.
  document.addEventListener('paste', (e) => {
    const alvo = e.target;
    if (alvo.matches && alvo.matches('input, textarea, select')) return;
    const t = (e.clipboardData && e.clipboardData.getData('text') || '').trim();
    if (!t) return;
    if (S.compacto) { $('#c-link').value = t; $('#c-link').focus(); }
    else if (S.pagina === 'baixar' && !S.onb) { $('#link').value = t; aoDigitar(); $('#link').focus(); }
  });

  // Miniaturas que não carregam (sem internet, bloqueadas) somem e deixam o espaço reservado do design.
  document.addEventListener('error', (e) => { if (e.target && e.target.tagName === 'IMG') e.target.remove(); }, true);

  // ================================================================ Ponte de entrada
  let ultimoFfdl = '';
  let ultimoYtup = '';
  window.__baixador = {
    recebe(msg) {
      if (!S.pronto || !msg || msg.tipo !== 'estado') return;
      S.fila = msg.fila || [];
      S.ffdl = msg.ffmpeg_dl || {};
      S.ytup = msg.ytdlp_up || {};
      (msg.eventos || []).forEach(tratarEvento);

      const ff = JSON.stringify(S.ffdl);
      if (ff !== ultimoFfdl) {
        ultimoFfdl = ff;
        if (S.ffdl.estado === 'pronto') chamar('ffmpeg_verificar').then((r) => { if (r) S.ffmpeg = r; desenharSistema(); desenharOpcoes(); desenharStatus(); if (S.onb) desenharOnboarding(); });
        else { desenharSistema(); if (S.onb) desenharOnboarding(); }
      }
      const yt = JSON.stringify(S.ytup);
      if (yt !== ultimoYtup) {
        ultimoYtup = yt;
        desenharYtdlp();
        if (S.ytup.estado === 'atualizado') toast({ titulo: 'yt-dlp atualizado', texto: 'Versão ' + S.ytup.versao + '. Feche e abra o app para usar.', ms: 12000 });
        else if (S.ytup.estado === 'em_dia') toast({ titulo: 'yt-dlp já está atualizado', texto: 'Versão ' + S.ytup.versao, icone: 'info', cor: 'line', ms: 5000 });
        else if (S.ytup.estado === 'erro') toast({ titulo: 'Não foi possível atualizar', texto: S.ytup.erro, icone: 'alert', cor: 'warn', ms: 10000 });
      }
      if (!S.onb) { if (S.pagina === 'fila' || S.compacto) desenharFila(); else desenharBarraFila(); desenharStatus(); }
    },
    perguntarSair(qtd) {
      dialogo({
        icone: 'download', cor: 'warn', titulo: 'Há downloads em andamento',
        texto: qtd + ' ' + plural(qtd, 'download ainda está rodando', 'downloads ainda estão rodando') + '. Se sair agora, ' + plural(qtd, 'ele é interrompido', 'eles são interrompidos') + '.',
        botoes: [{ rotulo: 'Sair mesmo assim', tipo: 'danger', valor: true }, { rotulo: 'Continuar', tipo: 'solid', valor: false }], esc: false,
      }).then((sair) => { if (sair) chamar('sair', true); });
    },
  };

  setInterval(() => { if (S.pagina === 'fila' && !S.compacto && S.fila.some((i) => i.status === 'concluido')) desenharFila(); }, 30000);

  async function iniciar() {
    const d = await S.api.init();
    S.app = d.app || {}; S.cfg = d.config; S.ffmpeg = d.ffmpeg; S.ytdlp = d.ytdlp || {}; S.apoio = d.apoio || { ativo: false };
    S.hist = d.historico || []; S.fila = d.fila || []; S.ffdl = d.ffmpeg_dl || {}; S.ytup = d.ytdlp_up || {};
    S.formato = S.cfg.formato; S.qualidade = S.cfg.qualidade;
    ultimoFfdl = JSON.stringify(S.ffdl); ultimoYtup = JSON.stringify(S.ytup);
    aplicarTema();
    observarSecoes();
    S.pronto = true;
    if (d.primeira_vez) {
      S.onb = { escolha: S.ffmpeg.pode_baixar ? 'baixar' : 'apontar' };
      $('#onboarding').hidden = false;
      desenharOnboarding();
    } else {
      entrarNoApp();
    }
  }

  let iniciou = false;
  function boot() { if (iniciou) return; iniciou = true; S.api = window.pywebview.api; iniciar(); }
  if (window.pywebview && window.pywebview.api) boot(); else window.addEventListener('pywebviewready', boot);
})();
