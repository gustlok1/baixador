/* Funções de apoio da interface: texto, datas, ícones e a ilustração das "órbitas". */
window.U = (function () {
  'use strict';

  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const ehUrl = (s) => /^https?:\/\/\S+$/i.test(String(s || '').trim());

  const icone = (nome, tam, extra) =>
    '<svg class="ic ' + (extra || '') + '" width="' + (tam || 20) + '" height="' + (tam || 20) +
    '" aria-hidden="true"><use href="#i-' + nome + '"/></svg>';

  const plural = (n, um, varios) => (n === 1 ? um : varios);

  // 754 -> "12:34" ; 5025 -> "1:23:45"
  function dur(seg) {
    seg = Math.round(seg || 0);
    if (!seg) return '';
    const h = Math.floor(seg / 3600), m = Math.floor((seg % 3600) / 60), s = seg % 60;
    return h ? h + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0') : m + ':' + String(s).padStart(2, '0');
  }

  // 767 -> "12 min 47 s" ; 8040 -> "2 h 14 min"
  function durLonga(seg) {
    seg = Math.round(seg || 0);
    if (!seg) return '';
    const h = Math.floor(seg / 3600), m = Math.floor((seg % 3600) / 60), s = seg % 60;
    if (h) return h + ' h' + (m ? ' ' + m + ' min' : '');
    if (m) return m + ' min' + (s ? ' ' + s + ' s' : '');
    return s + ' s';
  }

  const hhmm = (d) => String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  const mesmoDia = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

  // "Hoje, 14:20" / "Ontem, 22:14" / "12/10, 09:02" / "12/10/2025, 09:02"
  function quando(ts) {
    if (!ts) return '';
    const d = new Date(ts * 1000), agora = new Date();
    const ontem = new Date(agora); ontem.setDate(agora.getDate() - 1);
    if (mesmoDia(d, agora)) return 'Hoje, ' + hhmm(d);
    if (mesmoDia(d, ontem)) return 'Ontem, ' + hhmm(d);
    const dm = String(d.getDate()).padStart(2, '0') + '/' + String(d.getMonth() + 1).padStart(2, '0');
    return (d.getFullYear() === agora.getFullYear() ? dm : dm + '/' + d.getFullYear()) + ', ' + hhmm(d);
  }

  function grupo(ts) {
    if (!ts) return 'Mais antigos';
    const d = new Date(ts * 1000), agora = new Date();
    const ontem = new Date(agora); ontem.setDate(agora.getDate() - 1);
    if (mesmoDia(d, agora)) return 'Hoje';
    if (mesmoDia(d, ontem)) return 'Ontem';
    return (agora - d) / 86400000 < 7 ? 'Últimos 7 dias' : 'Mais antigos';
  }

  function relativo(ts) {
    if (!ts) return '';
    const s = Math.max(0, Date.now() / 1000 - ts);
    if (s < 45) return 'Agora mesmo';
    if (s < 3600) return 'Há ' + Math.max(1, Math.round(s / 60)) + ' min';
    if (s < 86400) return 'Há ' + Math.round(s / 3600) + ' h';
    return quando(ts);
  }

  // Desenha as órbitas das telas vazias. data-orbit="tamanho:x,y:x,y:x,y"
  function orbita(el) {
    const p = el.getAttribute('data-orbit').split(':');
    const S = parseFloat(p[0]), c = S / 2;
    const pts = p.slice(1).map((t) => t.split(',').map(parseFloat));
    let raios = [c - 2, Math.round(c * 0.69), Math.round(c * 0.4)];
    if (S === 160) raios = [78, 52];
    if (S === 120) raios = [56, 36];
    const aneis = raios.map((r, i) =>
      '<circle cx="' + c + '" cy="' + c + '" r="' + r + '" style="fill:none;stroke:var(' + (i === 1 ? '--line-strong' : '--line') + ');stroke-width:1"/>').join('');
    const pontos = pts.map((q, i) =>
      '<circle cx="' + q[0] + '" cy="' + q[1] + '" r="' + [3.5, 2.5, 2][i] + '" style="fill:var(' + (i === 0 ? '--accent' : '--line-strong') + ')"/>').join('');
    el.insertAdjacentHTML('afterbegin',
      '<span class="orbit__glow" aria-hidden="true"></span><svg class="orbit__rings" viewBox="0 0 ' + S + ' ' + S +
      '" width="100%" height="100%" aria-hidden="true">' + aneis + pontos + '</svg>');
  }

  return { esc, ehUrl, icone, plural, dur, durLonga, quando, grupo, relativo, orbita };
})();
