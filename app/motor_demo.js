/*
 * Motor de la demo: reproduce en JavaScript el baseline entrenado en Python
 * (TF-IDF de palabras y de caracteres + regresión logística), de modo que corra en el navegador sin servidor.
 * Debe dar las mismas probabilidades que scikit-learn (se verifica con src/verificar_demo.py).
 */
(function (root) {
  'use strict';

  function tokensPalabra(t) {            // equivale al patrón r"(?u)\b\w\w+\b" de scikit-learn
    return t.toLowerCase().match(/[\p{L}\p{N}_]{2,}/gu) || [];
  }

  function ngramasChar(texto, nmin, nmax) {   // equivale a analyzer='char_wb'
    const salida = [];
    for (const p of texto.toLowerCase().split(/\s+/).filter(Boolean)) {
      const w = Array.from(' ' + p + ' '), L = w.length;   // Array.from separa por caracteres Unicode (emojis incluidos)
      for (let n = nmin; n <= nmax; n++) {
        let off = 0;
        salida.push(w.slice(off, off + n).join(''));
        while (off + n < L) { off++; salida.push(w.slice(off, off + n).join('')); }
        if (off === 0) break;                              // una palabra más corta que n se cuenta una sola vez
      }
    }
    return salida;
  }

  function vectorizar(terminos, vocab, offset) {          // TF sublineal * IDF, norma L2
    const cuentas = new Map();
    for (const t of terminos) if (Object.prototype.hasOwnProperty.call(vocab, t)) cuentas.set(t, (cuentas.get(t) || 0) + 1);
    const items = [];
    let s = 0;
    for (const [t, c] of cuentas) {
      const [idx, idf] = vocab[t];
      const v = (1 + Math.log(c)) * idf;
      items.push({ term: t, idx: offset + idx, v });
      s += v * v;
    }
    const norma = Math.sqrt(s) || 1;
    for (const it of items) it.v /= norma;
    return items;
  }

  function Motor(modelo) {
    this.m = modelo;
    this.ood = new Set(modelo.vocab_ood);
  }

  Motor.prototype.cobertura = function (texto) {
    const k = tokensPalabra(texto);
    const conocidas = k.filter(w => this.ood.has(w)).length;
    return { total: k.length, conocidas, fraccion: k.length ? conocidas / k.length : 0 };
  };

  Motor.prototype.probabilidades = function (texto) {
    const m = this.m, rasgos = [];
    for (const bloque of m.bloques) {
      const terminos = bloque.tipo === 'palabra'
        ? (() => { const t = tokensPalabra(texto), g = t.slice(); for (let i = 0; i < t.length - 1; i++) g.push(t[i] + ' ' + t[i + 1]); return g; })()
        : ngramasChar(texto, bloque.ngram[0], bloque.ngram[1]);
      for (const it of vectorizar(terminos, bloque.vocab, bloque.offset)) { it.tipo = bloque.tipo; rasgos.push(it); }
    }
    const logits = m.intercepto.slice();
    for (let k = 0; k < logits.length; k++) for (const r of rasgos) logits[k] += r.v * m.coef[k][r.idx];
    const mx = Math.max(...logits), e = logits.map(z => Math.exp(z - mx)), s = e.reduce((a, b) => a + b, 0);
    return { probs: e.map(x => x / s), rasgos };
  };

  /* Analiza un comentario: clase, confianza, decisión y evidencia. */
  Motor.prototype.analizar = function (texto, tau) {
    const m = this.m, { probs, rasgos } = this.probabilidades(texto);
    let k = 0; for (let i = 1; i < probs.length; i++) if (probs[i] > probs[k]) k = i;
    const conf = probs[k], cob = this.cobertura(texto), motivos = [];
    if (conf < tau) motivos.push('confianza baja (' + conf.toFixed(2) + ' es menor que ' + tau.toFixed(2) + ')');
    if (cob.fraccion < m.regla.cobertura_min || cob.conocidas < m.regla.min_conocidas)
      motivos.push('el texto no se parece a las reseñas de entrenamiento (' + cob.conocidas + ' de ' + cob.total + ' palabras conocidas)');
    // Evidencia: palabras y frases que más empujan hacia la clase elegida (solo rasgos de palabras)
    const evidencia = rasgos.filter(r => r.tipo === 'palabra')
      .map(r => ({ term: r.term, aporte: r.v * m.coef[k][r.idx] }))
      .sort((a, b) => b.aporte - a.aporte);
    return {
      clase: m.clases[k], indice: k, confianza: conf, probs: probs, automatica: motivos.length === 0, motivos,
      a_favor: evidencia.filter(e => e.aporte > 0).slice(0, 5),
      en_contra: evidencia.filter(e => e.aporte < 0).slice(-3).reverse()
    };
  };

  const api = { Motor, tokensPalabra, ngramasChar };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.MotorDemo = api;
})(typeof window !== 'undefined' ? window : globalThis);
