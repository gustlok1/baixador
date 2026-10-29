// Simula window.pywebview.api para testar a interface sem Python.
(function () {
  const cfg = { formato:'mp4', qualidade:'1080p', pasta:'C:\\Users\\voce\\Downloads', playlist:false, simultaneos:2, limite:'Sem limite', template:'%(title)s.%(ext)s', legendas:false, embutir:true, idiomas:'pt, en', cookies:'Não usar', ffmpeg_dir:'', tema:'dark', compacto:false, avisar:true, abrir_pasta:false, convite:true, onboarded:true };
  const now = Date.now()/1000;
  const it = (id, st, o) => Object.assign({ id, url:'https://youtu.be/'+id, titulo:'Vídeo de exemplo '+id, canal:'Canal X', dur:'12:34', thumb:'', idx:'', sub:'', formato:'mp4', qualidade:'1080p', rotulo:'mp4 · 1080p', status:st, pct:0, esq:'', dir:'', indet:false, erro:'', erro_titulo:'', erro_msg:'', parou_em:0, criado:now, fim:null, pasta:'', arquivo:'' }, o);
  const fila = [
    it('a','baixando',{pct:42,esq:'42% · 38 MB de 90 MB',dir:'5,2 MB/s · 0:12 restantes'}),
    it('b','convertendo',{pct:100,indet:true,esq:'Convertendo',dir:'quase lá'}),
    it('c','aguardando'), it('d','pausado',{pct:60,esq:'60%',dir:'Pausado'}),
    it('e','erro',{erro:'ERROR: Video unavailable',erro_titulo:'Vídeo indisponível',erro_msg:'O vídeo foi removido.',parou_em:12,fim:now-60}),
    it('f','concluido',{pct:100,esq:'88 MB',fim:now-30,arquivo:'x.mp4'}),
  ];
  const hist = [1,2,3].map(i => ({id:'h'+i, ts:now-i*86400*i, titulo:'Item de histórico '+i, canal:'Canal', dur:'3:21', fmt:i==2?'mp3':'mp4', qual:i==2?'':'1080p', pasta:'C:\\Downloads', arquivo:'', url:'https://youtu.be/h'+i, thumb:''}));
  const ok = { ok:true, tipo:'video', titulo:'Como funciona o yt-dlp', canal:'Canal Dev', dur:'12:34', seg:754, thumb:'', tier:true, qualidades:['Melhor','1080p','720p','480p','360p'] };
  const pl = { ok:true, tipo:'playlist', titulo:'Minha playlist', canal:'Canal', total:3, seg_total:600, thumb:'', itens:[1,2,3].map(n=>({n, titulo:'Faixa '+n, dur:'3:20', seg:200, thumb:''})) };
  window.__calls = [];
  const rec = (n, v) => (...a) => { window.__calls.push([n, ...a]); return Promise.resolve(typeof v === 'function' ? v(...a) : v); };
  const q = new URLSearchParams(location.search);
  if (q.get('light')) cfg.tema = 'light';
  if (q.get('onb')) cfg.onboarded = false;
  const ff = q.get('noff') ? {estado:'ausente',caminho:'',versao:'',pode_baixar:true} : {estado:'path',caminho:'/usr/bin/ffmpeg',versao:'7.1',pode_baixar:true};
  window.pywebview = { api: {
    init: rec('init', () => ({ app:{versao:'2.0.0',repo:'https://github.com/x/y',releases:'https://github.com/x/y/releases'}, config:cfg, ffmpeg:ff, ytdlp:{versao:'2026.10.01'}, apoio:{ativo:true,payload:'0002...',link:'',svg:'<svg viewBox="0 0 10 10" width="160" height="160"><rect width="10" height="10" fill="#fff"/><rect x="2" y="2" width="6" height="6"/></svg>'}, historico:q.get('vazio')?[]:hist, fila:q.get('vazio')?[]:fila, ffmpeg_dl:{}, ytdlp_up:{}, primeira_vez:!cfg.onboarded })),
    config_salvar: rec('config_salvar', (p) => Object.assign(cfg, p)),
    barra_titulo: rec('barra_titulo', null), escolher_pasta: rec('escolher_pasta', {ok:false}),
    inspecionar: rec('inspecionar', (u) => /list=/.test(u) ? pl : u.includes('bad') ? {ok:false,erro:'Sem acesso.'} : ok),
    adicionar: rec('adicionar', {ok:true}), adicionar_rapido: rec('adicionar_rapido', {ok:true,adicionados:1}),
    ler_clipboard: rec('ler_clipboard', ''), copiar: rec('copiar', true), abrir_link: rec('abrir_link', true),
    compacto: rec('compacto', null), sair: rec('sair', null),
    cancelar_atuais: rec('x'), parar_tudo: rec('x'), cancelar: rec('x'), pausar: rec('x'), retomar: rec('x'), tentar_de_novo: rec('x'), remover: rec('x'), limpar_concluidos: rec('x'),
    abrir_item: rec('abrir_item',{ok:true}), historico_abrir: rec('ha',{ok:true}), historico_limpar: rec('hl'), historico_baixar_de_novo: rec('hb',{ok:true}),
    ffmpeg_verificar: rec('fv', ff), ffmpeg_baixar: rec('fb'), ffmpeg_apontar: rec('fa',{ok:false}), ffmpeg_usar_path: rec('fp', ff), ytdlp_atualizar: rec('ya'),
  }};
  window.__push = () => window.__baixador.recebe({tipo:'estado', fila, ffmpeg_dl:{}, ytdlp_up:{}, eventos:[]});
  setTimeout(() => window.dispatchEvent(new Event('pywebviewready')), 10);
})();
