"""
Exporta el baseline entrenado (results/baseline_modelo.joblib) al formato que usa la demo del navegador
y arma app/demo.html (un solo archivo, sin dependencias externas).

Uso (desde la carpeta del repositorio):
    python src/exportar_modelo_demo.py
Requiere haber ejecutado antes el notebook (genera results/baseline_modelo.joblib, abstencion.csv,
regla_abstencion.json, metricas_test.csv).
"""
import json, os, sys
import joblib
import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES, APP = os.path.join(RAIZ, 'results'), os.path.join(RAIZ, 'app')
CLASES = ['negativa', 'mixta', 'positiva', 'no_mencionado']


def bloques_desde_modelo(pipe):
    v = pipe.named_steps['v']
    vecs = [t for _, t in v.transformer_list] if hasattr(v, 'transformer_list') else [v]
    bloques, offset = [], 0
    for t in vecs:
        assert t.lowercase and t.strip_accents is None and t.sublinear_tf and t.norm == 'l2' and t.use_idf and t.smooth_idf, 'configuración del vectorizador no soportada'
        if t.analyzer == 'word':
            assert tuple(t.ngram_range) == (1, 2) and t.token_pattern == r"(?u)\b\w\w+\b", 'palabras: solo (1,2) con el patrón por defecto'
            tipo = 'palabra'
        elif t.analyzer == 'char_wb':
            tipo = 'caracter'
        else:
            raise ValueError('analizador no soportado: ' + str(t.analyzer))
        idf = t.idf_
        vocab = {term: [int(i), round(float(idf[i]), 6)] for term, i in t.vocabulary_.items()}
        bloques.append(dict(tipo=tipo, ngram=list(t.ngram_range), offset=offset, vocab=vocab))
        offset += len(t.vocabulary_)
    return bloques, offset


def main():
    pipe = joblib.load(os.path.join(RES, 'baseline_modelo.joblib'))
    clf = pipe.named_steps['c']
    assert list(clf.classes_) == [0, 1, 2, 3], 'las clases deben estar en el orden negativa, mixta, positiva, no_mencionado'
    bloques, n_total = bloques_desde_modelo(pipe)
    assert clf.coef_.shape == (4, n_total)
    regla = json.load(open(os.path.join(RES, 'regla_abstencion.json'), encoding='utf-8'))
    ab = pd.read_csv(os.path.join(RES, 'abstencion.csv')).iloc[0]
    mt = pd.read_csv(os.path.join(RES, 'metricas_test.csv')).iloc[0]
    modelo = dict(
        clases=CLASES, bloques=bloques,
        coef=[[round(float(x), 5) for x in fila] for fila in clf.coef_], intercepto=[round(float(x), 5) for x in clf.intercept_],
        regla=dict(tau=regla['tau'], cobertura_min=regla['cobertura_min'], min_conocidas=regla['min_conocidas']),
        vocab_ood=regla['vocabulario'],
        info=dict(modelo='TF-IDF de palabras y caracteres + regresión logística (no es una red neuronal)',
                  f1_macro_test=round(float(mt.f1_macro), 3), recall_queja_directo_test=round(float(ab.recall_queja_directo_test), 3),
                  recall_queja_revision_test=round(float(ab.recall_queja_con_revision_test), 3), cobertura_test=round(float(ab.cobertura_test), 3)))
    with open(os.path.join(APP, 'modelo_demo.json'), 'w', encoding='utf-8') as f:
        json.dump(modelo, f, ensure_ascii=False, separators=(',', ':'))
    plantilla = open(os.path.join(APP, 'plantilla_demo.html'), encoding='utf-8').read()
    motor = open(os.path.join(APP, 'motor_demo.js'), encoding='utf-8').read()
    modelo_js = json.dumps(modelo, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    html = plantilla.replace('/*__MOTOR__*/', motor).replace('/*__MODELO__*/', 'const MODELO = ' + modelo_js + ';')
    assert '/*__MOTOR__*/' not in html and '/*__MODELO__*/' not in html
    with open(os.path.join(APP, 'demo.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    print('modelo_demo.json:', round(os.path.getsize(os.path.join(APP, 'modelo_demo.json')) / 1e6, 2), 'MB | demo.html:',
          round(os.path.getsize(os.path.join(APP, 'demo.html')) / 1e6, 2), 'MB')


if __name__ == '__main__':
    sys.exit(main())
