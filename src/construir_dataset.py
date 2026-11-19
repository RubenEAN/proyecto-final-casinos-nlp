"""
Construye el corpus del proyecto final a partir del CSV original (las 2.100 reseñas de registro original).

Reglas (todas quedan registradas en data/excluidas.csv y data/DATA_CARD.md):
  1. Se conservan solo las filas con casino "No especificado (registro original)" (reseñas de Google Maps).
  2. "positive" (inglés) -> "positiva".
  3. Se excluye la fila que la auditoría de la clase 3 ya había excluido (insulto sin contenido sobre el servicio).
  4. Se normalizan espacios y se enmascaran datos personales (teléfonos y una firma con nombre).
  5. El sentimiento de 4 clases se deriva de los 12 aspectos (positiva, negativa, mixta si hay ambas, no_mencionado si no hay ninguna).
  6. Se excluyen los grupos de texto idéntico con etiquetas contradictorias (no se sabe cuál es la correcta).
  7. Partición 70 / 15 / 15 estratificada por sentimiento y por grupos: los textos idénticos quedan siempre juntos.

Uso (desde la carpeta del repositorio):
    python src/construir_dataset.py --entrada RUTA/train_ampliado_102220.csv --salida data
"""
import argparse, os, re, unicodedata
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

SEMILLA = 42
ASPECTOS = ['atencion#gastronomia', 'atencion#parking', 'atencion#atencion_cliente', 'calidad#gastronomia', 'calidad#slot',
            'calidad#limpieza', 'calidad#seguridad', 'precio#gastronomia', 'precio#slot', 'precio#parking',
            'ambiente_restaurate#gastronomia', 'ambiente_sala#slots']
EXCLUIR_ID = {3754: 'fuera de alcance: insulto sin contenido sobre el servicio (excluida también en la auditoría de la clase 3)'}


def clave_texto(s):
    s = unicodedata.normalize('NFC', str(s)).lower()
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', s)).strip()


def anonimizar(t):
    t = re.sub(r'\d{4}\s?-\s?\d{4}', '[TELEFONO]', t)                       # teléfonos locales (xxxx-xxxx)
    t = re.sub(r'\b[Aa]rte\.\s*M[óo]nica Saha\.?', 'Arte. [NOMBRE]', t)      # firma con nombre propio
    return re.sub(r'\s+', ' ', t).strip()


def derivar_sentimiento(fila):
    v = set(fila[ASPECTOS]); pos = 'positiva' in v; neg = 'negativa' in v
    return 'mixta' if pos and neg else ('positiva' if pos else ('negativa' if neg else 'no_mencionado'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--entrada', required=True); ap.add_argument('--salida', default='data')
    a = ap.parse_args()
    d = pd.read_csv(a.entrada, low_memory=False)
    n_total = len(d)
    o = d[d.Casino.str.startswith('No especificado')].copy().reset_index(drop=True)          # regla 1
    for c in ASPECTOS: o[c] = o[c].replace({'positive': 'positiva'})                          # regla 2
    o = o.rename(columns={'Review_Tranformada': 'texto', 'Periodo': 'periodo'})
    excl = []
    for i, motivo in EXCLUIR_ID.items():                                                       # regla 3
        for _, r in o[o.id == i].iterrows(): excl.append(dict(id=int(r.id), texto=r.texto, motivo=motivo))
    o = o[~o.id.isin(EXCLUIR_ID)].copy()
    o['texto'] = o.texto.map(anonimizar)                                                       # regla 4
    o['sentimiento'] = o.apply(derivar_sentimiento, axis=1)                                    # regla 5
    o['clave'] = o.texto.map(clave_texto)
    # regla 6: grupos de texto idéntico con etiquetas distintas
    firma = o[ASPECTOS].astype(str).agg('|'.join, axis=1)
    conflicto = o.assign(f=firma).groupby('clave').f.nunique()
    claves_conf = set(conflicto[conflicto > 1].index)
    for _, r in o[o.clave.isin(claves_conf)].iterrows():
        excl.append(dict(id=int(r.id), texto=r.texto, motivo='texto idéntico a otra reseña con etiquetas contradictorias'))
    o = o[~o.clave.isin(claves_conf)].copy()
    # regla 7: partición estratificada por grupos
    o['grupo_texto'] = o.clave.astype('category').cat.codes
    o = o.reset_index(drop=True)
    sgk = StratifiedGroupKFold(n_splits=20, shuffle=True, random_state=SEMILLA)
    fold = np.zeros(len(o), int)
    for k, (_, idx) in enumerate(sgk.split(o, o.sentimiento, o.grupo_texto)): fold[idx] = k
    o['particion'] = np.where(fold < 3, 'validation', np.where(fold < 6, 'test', 'train'))
    o['n_palabras'] = o.texto.str.split().str.len()
    cols = ['id', 'periodo', 'texto', 'sentimiento'] + ASPECTOS + ['n_palabras', 'grupo_texto', 'particion']
    out = o[cols].sort_values('id').reset_index(drop=True)
    # controles de integridad
    assert out.id.is_unique and out.texto.notna().all() and (out.texto.str.len() > 0).all()
    assert set(out.particion) == {'train', 'validation', 'test'}
    g = out.groupby('grupo_texto').particion.nunique(); assert (g == 1).all(), 'un grupo de textos idénticos quedó en dos particiones'
    assert set(out[ASPECTOS].stack().unique()) <= {'positiva', 'negativa', 'neutral'}
    os.makedirs(a.salida, exist_ok=True)
    out.to_csv(os.path.join(a.salida, 'corpus_casinos_2100.csv'), index=False, encoding='utf-8-sig')
    pd.DataFrame(excl).to_csv(os.path.join(a.salida, 'excluidas.csv'), index=False, encoding='utf-8-sig')
    print(f'Filas del archivo original: {n_total} | en el corpus: {len(out)} | excluidas: {len(excl)}')
    print(pd.crosstab(out.sentimiento, out.particion)[['train', 'validation', 'test']])
    print(out.particion.value_counts().to_dict())


if __name__ == '__main__':
    main()
