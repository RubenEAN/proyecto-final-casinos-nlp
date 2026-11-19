"""
Verifica que la demo del navegador (app/motor_demo.js) da las mismas probabilidades que el modelo de Python.
Compara todas las reseñas de validación y test, las frases de robustez y casos límite. Requiere Node.js.

Uso: python src/verificar_demo.py
"""
import json, os, subprocess, sys, tempfile
import joblib
import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASOS_LIMITE = ['', '   ', 'a', 'ñandú', '😀😀😀', 'EXCELENTE LUGAR!!!', 'La comida es muy rica 😍', 'excelente\tlugar\ncon saltos', 'www.casino.com 4778-2800']


def main():
    pipe = joblib.load(os.path.join(RAIZ, 'results', 'baseline_modelo.joblib'))
    c = pd.read_csv(os.path.join(RAIZ, 'data', 'corpus_casinos_2100.csv'))
    robustez = pd.read_csv(os.path.join(RAIZ, 'data', 'casos_robustez.csv')).texto.tolist()
    textos = c[c.particion != 'train'].texto.tolist() + robustez + CASOS_LIMITE
    P = pipe.predict_proba(textos)
    with tempfile.TemporaryDirectory() as d:
        ruta = os.path.join(d, 'esperado.json')
        json.dump(dict(textos=textos, probs=P.tolist()), open(ruta, 'w', encoding='utf-8'), ensure_ascii=False)
        r = subprocess.run(['node', os.path.join(RAIZ, 'app', 'verificar_motor.js'), ruta], capture_output=True, text=True, encoding='utf-8')
    print(r.stdout.strip());
    if r.returncode != 0:
        print(r.stderr.strip()); sys.exit(1)


if __name__ == '__main__':
    main()
