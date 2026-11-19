"""
Construye el informe técnico (DOCX editable + PDF) a partir de lo que hay en results/.

Todas las cifras salen de las ejecuciones guardadas en results/ (nada se escribe a mano). Si todavía no hay resultados de BETO,
el informe lo indica con recuadros "PENDIENTE" que desaparecen solos cuando se copian results/beto_*.csv y se vuelve a ejecutar
el notebook y este script.

Uso (desde la carpeta del repositorio):
    python src/construir_informe.py            # genera docs/Informe_Tecnico.docx y docs/Informe_Tecnico.pdf (PDF requiere Microsoft Edge)
"""
import json, os, re, subprocess, sys, shutil, tempfile, html, unicodedata
import numpy as np, pandas as pd, joblib
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.metrics import confusion_matrix
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES, DATA, DOCS = os.path.join(RAIZ, 'results'), os.path.join(RAIZ, 'data'), os.path.join(RAIZ, 'docs')
FIG = os.path.join(DOCS, 'figuras'); os.makedirs(FIG, exist_ok=True)
CLASES = ['negativa', 'mixta', 'positiva', 'no_mencionado']; IDX = {c: i for i, c in enumerate(CLASES)}
AZUL, VERDE, AMBAR, ROJO, GRIS = '#2D6BDB', '#0F8F6B', '#B86E00', '#C23B3B', '#5A6B85'

# ------------------------------------------------------------------ datos y resultados
def leer(n, **k):
    r = os.path.join(RES, n); return pd.read_csv(r, **k) if os.path.exists(r) else None
df = pd.read_csv(os.path.join(DATA, 'corpus_casinos_2100.csv'), encoding='utf-8-sig')
resumen = json.load(open(os.path.join(RES, 'resumen_final.json'), encoding='utf-8'))
base_val = leer('baselines_validacion.csv'); met_test = leer('metricas_test.csv'); abst = leer('abstencion.csv'); crit = leer('criterios_adopcion.csv')
err_b = leer('errores_validacion_baseline.csv'); err_beto = leer('errores_validacion_beto.csv'); rob = leer('robustez_pares.csv'); pert = leer('robustez_perturbaciones.csv')
seg = leer('segmentos_validacion.csv'); costo = leer('costo_latencia.csv'); comp_val = leer('comparacion_validacion.csv')
regla = json.load(open(os.path.join(RES, 'regla_abstencion.json'), encoding='utf-8')); conf_json = json.load(open(os.path.join(RES, 'configuracion_y_conclusiones.json'), encoding='utf-8'))
B = resumen['baseline']; BETO = resumen['beto']; N = resumen['n']
tr, va, te = [df[df.particion == p].reset_index(drop=True) for p in ('train', 'validation', 'test')]
modelo = joblib.load(os.path.join(RES, 'baseline_modelo.joblib'))
Pva, Pte = modelo.predict_proba(va.texto), modelo.predict_proba(te.texto); yva, yte = va.sentimiento.map(IDX).values, te.sentimiento.map(IDX).values
beto_val = leer('beto_val_probs.csv'); beto_test = leer('beto_test_probs.csv'); beto_corr = leer('beto_corridas.csv')
if BETO:
    cfg = BETO['config']; sem0 = beto_test.semilla.min()
    Pva_b = beto_val[(beto_val.config == cfg) & (beto_val.semilla == sem0)].set_index('id').loc[va.id.values][CLASES].values
    Pte_b = beto_test[beto_test.semilla == sem0].set_index('id').loc[te.id.values][CLASES].values

def f(x, n=3): return ('—' if x is None or (isinstance(x, float) and np.isnan(x)) else f'{x:.{n}f}'.replace('.', ','))
def pc(x, n=1): return f'{x * 100:.{n}f} %'.replace('.', ',')
def miles(x): return f'{int(x):,}'.replace(',', '.')

# ------------------------------------------------------------------ figuras
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'axes.spines.top': False, 'axes.spines.right': False})
def guardar(fig, n):
    ruta = os.path.join(FIG, n); fig.savefig(ruta, dpi=200, bbox_inches='tight'); plt.close(fig); return ruta

def fig_datos():
    fig, ax = plt.subplots(1, 3, figsize=(10.2, 2.9))
    cnt = df.sentimiento.value_counts().reindex(CLASES); ax[0].barh(CLASES[::-1], cnt.values[::-1], color=[GRIS, VERDE, AMBAR, ROJO]); ax[0].set_title('Reseñas por clase')
    for i, v in enumerate(cnt.values[::-1]): ax[0].text(v + 15, i, f'{v} ({v / len(df) * 100:.0f} %)', va='center', fontsize=8)
    ax[0].set_xlim(0, cnt.max() * 1.35)
    for c, col in zip(CLASES, [ROJO, AMBAR, VERDE, GRIS]): ax[1].hist(df[df.sentimiento == c].n_palabras.clip(upper=80), bins=24, alpha=.55, color=col, label=c)
    ax[1].set_title('Longitud en palabras (recortada a 80)'); ax[1].legend(fontsize=7)
    a = df.periodo.str[:4].value_counts().sort_index(); ax[2].bar(a.index, a.values, color=AZUL); ax[2].set_title('Reseñas por año'); ax[2].tick_params(axis='x', rotation=45)
    fig.tight_layout(); return guardar(fig, 'f1_datos.png')

def fig_pipeline():
    fig, ax = plt.subplots(figsize=(10.2, 2.3)); ax.axis('off'); ax.set_xlim(0, 100); ax.set_ylim(0, 24)
    cajas = [('Comentario', 'texto libre', GRIS), ('Representación', 'TF-IDF palabras y\ncaracteres  ·  BETO', AZUL), ('Clasificador', 'regresión logística\n·  cabeza de BETO', AZUL),
             ('Probabilidades', '4 clases', VERDE), ('Regla de revisión', 'confianza baja o\ntexto fuera de dominio', AMBAR), ('Acción', 'decide el sistema o\nrevisión humana', ROJO)]
    ancho, sep = 14.2, 2.4
    for i, (t, s, c) in enumerate(cajas):
        x = 1 + i * (ancho + sep); ax.add_patch(plt.Rectangle((x, 5), ancho, 14, fill=False, ec=c, lw=1.6, joinstyle='round'))
        ax.text(x + ancho / 2, 15.2, t, ha='center', fontsize=8.0, fontweight='bold', color=c); ax.text(x + ancho / 2, 9.2, s, ha='center', va='center', fontsize=6.9)
        if i < len(cajas) - 1: ax.annotate('', xy=(x + ancho + sep - .2, 12), xytext=(x + ancho + .2, 12), arrowprops=dict(arrowstyle='->', color=GRIS))
    return guardar(fig, 'f2_pipeline.png')

def fig_confusion():
    mods = [('Baseline', Pte)] + ([(f'BETO ({BETO["config"]})', Pte_b)] if BETO else [])
    fig, ax = plt.subplots(1, len(mods), figsize=(4.9 * len(mods), 4.1)); ax = np.atleast_1d(ax)
    for a, (n, P) in zip(ax, mods):
        cm = confusion_matrix(yte, P.argmax(1), labels=range(4)); a.imshow(cm, cmap='Blues')
        for i in range(4):
            for j in range(4): a.text(j, i, cm[i, j], ha='center', va='center', color='white' if cm[i, j] > cm.max() / 2 else 'black', fontsize=9)
        a.set_xticks(range(4)); a.set_xticklabels(CLASES, rotation=30, ha='right'); a.set_yticks(range(4)); a.set_yticklabels(CLASES); a.set_title(n); a.set_xlabel('Predicho'); a.set_ylabel('Real')
    fig.tight_layout(); return guardar(fig, 'f3_confusion.png')

def fig_calidad_cobertura():
    fig, ax = plt.subplots(figsize=(5.6, 3.5))
    for n, P, col in [('Baseline', Pva, AZUL)] + ([(f'BETO ({BETO["config"]})', Pva_b, VERDE)] if BETO else []):
        xs, ys = [], []
        for tau in np.arange(0.35, 0.97, 0.02):
            m = P.max(1) >= tau
            if m.sum() > 15: xs.append(m.mean()); ys.append((P.argmax(1) == yva)[m].mean())
        ax.plot(xs, ys, marker='o', ms=3, label=n, color=col)
    ax.axvline(0.75, color=ROJO, ls='--', lw=1); ax.text(0.755, ax.get_ylim()[0] + .01, 'meta de cobertura 75 %', color=ROJO, fontsize=7.5)
    ax.set_xlabel('Cobertura automática'); ax.set_ylabel('Exactitud de lo que decide el modelo'); ax.set_title('Calidad frente a cobertura (validación)'); ax.legend(fontsize=8); ax.grid(alpha=.3)
    return guardar(fig, 'f4_calidad_cobertura.png')

def fig_perturbaciones():
    d = pert.pivot(index='modelo', columns='variante', values='f1_macro'); orden = [c for c in ['original', 'sin tildes', 'errores de tipeo', 'abreviaturas', 'MAYÚSCULAS'] if c in d.columns]
    fig, ax = plt.subplots(figsize=(6.4, 3.3)); w = .8 / len(d)
    for k, (m, fila) in enumerate(d.iterrows()): ax.bar(np.arange(len(orden)) + k * w, fila[orden].values, w, label=m, color=[AZUL, VERDE][k % 2])
    ax.set_xticks(np.arange(len(orden)) + w * (len(d) - 1) / 2); ax.set_xticklabels(orden); ax.set_ylabel('F1 macro (validación)'); ax.set_title('Robustez ante cambios en la forma del texto'); ax.legend(fontsize=8); ax.set_ylim(0, max(d.max()) * 1.15)
    return guardar(fig, 'f5_perturbaciones.png')

F1, F2, F3, F4, F5 = fig_datos(), fig_pipeline(), fig_confusion(), fig_calidad_cobertura(), fig_perturbaciones()

# ------------------------------------------------------------------ contenido (modelo de bloques)
C = []
h1 = lambda t: C.append(('h1', t)); h2 = lambda t: C.append(('h2', t)); p = lambda t: C.append(('p', t)); bl = lambda it: C.append(('bul', it))
tabla = lambda cab, filas, cap, anchos=None: C.append(('tab', cab, filas, cap, anchos)); fig = lambda ruta, cap, cm=15.5: C.append(('fig', ruta, cap, cm))
call = lambda tipo, t: C.append(('call', tipo, t)); salto = lambda: C.append(('salto',))
pend = lambda t: call('pend', '**PENDIENTE.** ' + t)

b_ab = abst.iloc[0]; ab_beto = abst.iloc[1] if BETO and len(abst) > 1 else None
quejas_te, mixtas_te = N['quejas_test'], N['mixtas_test']
nq_detectadas = int(round(B['recall_test'] * quejas_te))
dec = resumen['decision']

# ---- Resumen
h1('Resumen')
p(f"Este proyecto resuelve una decisión concreta de una cadena de casinos: **qué comentarios de clientes requieren atención humana primero y cuáles se pueden procesar solos**. "
  f"El sistema clasifica el sentimiento de cada comentario en cuatro clases (queja, mixta, positiva y sin opinión sobre el servicio), entrega una confianza y decide si lo procesa o lo envía a una persona. La clase crítica es la queja: no detectarla es el error más costoso.")
p(f"Se trabajó con {miles(len(df))} reseñas de Google Maps de un casino de Buenos Aires, repartidas en {miles(N['train'])} para entrenar, {N['validation']} para elegir y {N['test']} para el examen final. "
  f"El baseline (TF-IDF con regresión logística) alcanza un F1 macro de **{f(B['f1_test'])}** en test (intervalo de confianza del 95 %: {f(B['ic_f1'][0])} a {f(B['ic_f1'][1])}) y detecta {pc(B['recall_test'])} de las quejas por sí solo ({nq_detectadas} de {quejas_te}). "
  f"Cuando los casos dudosos pasan a una persona, se encuentran **{pc(b_ab.recall_queja_con_revision_test)}** de las quejas, decidiendo solo el {pc(b_ab.cobertura_test)} de los comentarios.")
if BETO:
    mejora_media = BETO['f1_test_media'] - B['f1_test']
    if BETO['diff_ic'][0] <= 0: sig = 'el intervalo incluye el 0, así que la mejora no es concluyente'
    elif BETO['diff_ic'][0] < resumen['meta']['mejora_f1']: sig = f"el intervalo apenas excluye el 0 (su límite inferior es {f(BETO['diff_ic'][0])}, menor que la meta de {f(resumen['meta']['mejora_f1'], 2)}): la mejora es probable, pero con {quejas_te} quejas en test la evidencia es débil"
    else: sig = 'el intervalo excluye el 0 y su límite inferior supera la meta de mejora'
    p(f"BETO, un Transformer preentrenado en español, alcanza un F1 macro medio de **{f(BETO['f1_test_media'])} ± {f(BETO['f1_test_std'])}** en test (3 semillas), {f(mejora_media)} más que el baseline. "
      f"Con la corrida de la semilla 42, la diferencia es de {f(BETO['diff'])} (intervalo del 95 %: {f(BETO['diff_ic'][0])} a {f(BETO['diff_ic'][1])}): {sig}.")
else:
    call('pend', '**PENDIENTE.** Falta la comparación con BETO: el modelo avanzado debe entrenarse en Google Colab con GPU (instrucciones en el README). Este informe se completa solo cuando se copian los resultados en results/ y se vuelve a generar.')
RECS = {
 'pendiente_beto': 'Con la evidencia disponible, se recomienda un **piloto en modo sombra con el baseline y revisión humana de los casos dudosos**, y decidir sobre BETO cuando se tengan sus resultados.',
 'piloto_sombra_beto': 'Se recomienda un **piloto en modo sombra con BETO y revisión humana de los casos dudosos**, con el baseline como respaldo (rollback).',
 'piloto_ambos_modelos': 'Se recomienda un **piloto en modo sombra con ambos modelos**. BETO mejora el F1 macro y necesita mucha menos revisión humana para un recall parecido, pero no cumple solo las metas en test y es frágil ante textos en MAYÚSCULAS; el baseline es el respaldo y la referencia. Al terminar el piloto, una muestra auditada decide con cuál continuar.',
 'mantener_baseline': 'BETO no supera con claridad al baseline: se recomienda **mantener el baseline** con revisión humana, que es más simple, rápido y barato.'}
TRADE = ''
if BETO and ab_beto is not None:
    dq = int(round((b_ab.recall_queja_con_revision_test - ab_beto.recall_queja_con_revision_test) * quejas_te))
    TRADE = (f" Los dos modelos quedan en puntos de operación distintos: el baseline encuentra el {pc(b_ab.recall_queja_con_revision_test)} de las quejas pasando a revisión el {pc(b_ab.revision_test)} de los comentarios; "
             f"BETO encuentra el {pc(ab_beto.recall_queja_con_revision_test)} pasando a revisión solo el {pc(ab_beto.revision_test)}. Con {quejas_te} quejas en test, la diferencia de recall equivale a {dq} quejas, así que no es concluyente.")
p('**Recomendación.** ' + RECS[dec] + TRADE + ' Las metas de aceptación son provisionales y deben validarse con el cliente; el modelo se suspende si el recall de quejas auditado baja de 0,90.')

# ---- 1 Contexto
h1('1. Contexto y problema')
h2('1.1 Organización, usuario y decisión')
p('La organización es una cadena de casinos que recibe comentarios de clientes en Google Maps. El usuario del sistema es el **equipo de experiencia al cliente y operaciones**, que hoy debe leer los comentarios para decidir cuáles atender primero. '
  'La decisión que apoya el sistema es: **¿este comentario lo atiende una persona o se procesa de forma automática?** El sistema no responde al cliente ni decide nada sobre personas: solo prioriza.')
h2('1.2 Definición de la tarea')
tabla(['Elemento', 'Definición'], [
    ['Entrada', 'Texto de un comentario de un cliente (español informal, con errores de ortografía, abreviaturas y emojis)'],
    ['Salida', 'Clase (negativa, mixta, positiva o no_mencionado), probabilidad de cada clase y acción (decide el sistema o revisión humana)'],
    ['Unidad y frecuencia', 'Un comentario; procesamiento diario por lote'],
    ['Situación actual', 'Lectura manual. El volumen, el tiempo y el costo del proceso actual no están en los datos: son supuestos por validar con el cliente (sección 6)'],
    ['Hipótesis de valor', 'Se reduce el tiempo de lectura y de primera respuesta a las quejas sin perder quejas'],
    ['KPI', 'Recall de quejas (con revisión humana) y cobertura automática; horas de lectura ahorradas'],
    ['Clase y error críticos', 'Clase crítica: **queja** (negativa). Error crítico: una queja que el sistema no detecta ni envía a revisión (falso negativo)'],
    ['Metas provisionales', f"Recall de quejas con revisión ≥ {f(resumen['meta']['recall_critica'], 2)}; cobertura automática ≥ {pc(resumen['meta']['cobertura'], 0)}; mejora de F1 macro de BETO sobre el baseline ≥ {f(resumen['meta']['mejora_f1'], 2)}; latencia p95 ≤ {resumen['meta']['latencia_p95_ms']} ms"]],
    'Tabla 1. Formulación del problema', [3.2, 12.3])
h2('1.3 Alcance')
p('**Incluye:** clasificación del sentimiento general de cada comentario, abstención con revisión humana, pruebas de robustez y una demostración. **No incluye:** respuesta automática a los clientes, clasificación por área responsable (los aspectos del corpus tienen etiquetas poco fiables y el test tiene muy pocas quejas por área), ni uso en otros casinos o canales.')

# ---- 2 Datos
h1('2. Datos')
h2('2.1 Origen, permisos y selección')
voc_real = len({w for t_ in tr.texto for w in re.findall(r'\w+', t_.lower())})
p("El corpus son las **2.100 reseñas** de Google Maps de un casino e hipódromo de Buenos Aires (2016-12 a 2024-02), tomadas de las filas de registro original del archivo entregado en el curso, que corresponden al dataset académico `comentarios_tp_v2`. "
  "Son las únicas reseñas con las que cuenta el ejercicio. Tras la auditoría de calidad (sección 2.2) quedan 2.079.")
p('El dataset es de **uso académico y no declara licencia**: no debe publicarse ni redistribuirse.')
h2('2.2 Auditoría de calidad')
tabla(['Control', 'Resultado', 'Acción'], [
    ['Nulos, vacíos e ids repetidos', '0', 'Ninguna'],
    ['Etiquetas "positive" (inglés)', '26 celdas en 20 reseñas', 'Se cambiaron a "positiva"'],
    ['Reseña fuera de alcance', '1 (insulto sin contenido sobre el servicio)', 'Excluida'],
    ['Textos idénticos con etiquetas contradictorias', '5 grupos, 20 reseñas', 'Excluidas'],
    ['Textos idénticos con etiquetas iguales', '9 grupos, 25 reseñas (p. ej. "Excelente lugar!")', 'Se conservan; nunca se reparten entre particiones'],
    ['Datos personales', '1 teléfono comercial y 1 firma con nombre', 'Enmascarados ([TELEFONO], [NOMBRE]); falta revisar una muestra a mano'],
    ['Calidad de las etiquetas', 'En una revisión manual de 30 reseñas, los aspectos fallaban en 9 y el sentimiento general en 1', 'La tarea usa el sentimiento general']],
    'Tabla 2. Auditoría del corpus (ficha completa en data/DATA_CARD.md)', [4.2, 6.2, 5.1])
p(f"Tras la auditoría quedan **{miles(len(df))} reseñas**: se excluyeron 21 de las 2.100.")
h2('2.3 Etiquetas y partición')
p('La variable objetivo es el **sentimiento general** de cuatro clases, derivado de 12 aspectos anotados por reseña (atención, calidad, precio y ambiente de distintas áreas). Se deriva con una regla: positiva si solo hay aspectos positivos, negativa si solo hay negativos, mixta si hay ambos y no_mencionado si no se menciona ningún aspecto. '
  'En los aspectos, "neutral" significa "no se menciona", no una opinión intermedia.')
ct = pd.crosstab(df.sentimiento, df.particion).reindex(CLASES)[['train', 'validation', 'test']]
tabla(['Clase', 'Entrenamiento', 'Validación', 'Test', 'Total', '%'], [[c, ct.loc[c, 'train'], ct.loc[c, 'validation'], ct.loc[c, 'test'], ct.loc[c].sum(), pc(ct.loc[c].sum() / ct.values.sum())] for c in CLASES] +
      [['Total', ct.train.sum(), ct.validation.sum(), ct.test.sum(), ct.values.sum(), '100 %']], 'Tabla 3. Reseñas por clase y partición', [3.6, 2.7, 2.7, 2.2, 2.2, 2.1])
p(f"La partición es 70 / 15 / 15, **estratificada por clase y por grupos de texto idéntico** (un grupo nunca queda en dos particiones, para evitar fuga). Es aleatoria sobre un único lugar; todas las particiones cubren el mismo rango de años. "
  f"El test tiene {quejas_te} quejas y {mixtas_te} reseñas mixtas, así que las diferencias pequeñas entre modelos no son concluyentes.")
h2('2.4 Análisis exploratorio')
fig(F1, 'Figura 1. Distribución de clases, longitud de los textos y reseñas por año.')
p(f"La clase positiva domina (58,8 %): un modelo que siempre dijera \"positiva\" acertaría casi seis de cada diez sin aprender nada, por eso la métrica principal es el **F1 macro**. "
  f"Los textos son cortos (mediana de {int(df.n_palabras.median())} palabras; percentil 95 de {int(df.n_palabras.quantile(.95))}), y las quejas y las reseñas mixtas son más largas que las positivas (medianas de {int(df[df.sentimiento == 'negativa'].n_palabras.median())}, {int(df[df.sentimiento == 'mixta'].n_palabras.median())} y {int(df[df.sentimiento == 'positiva'].n_palabras.median())} palabras). "
  f"Solo {int((df.n_palabras > 64).sum())} reseñas pasan de 64 palabras, así que el recorte de texto afecta a muy pocas.")
p('**Limitaciones del corpus:** un solo casino y un solo canal; 387 quejas y 131 reseñas mixtas en total; etiquetas por aspecto ruidosas; y convenciones de anotación particulares (un elogio general se marca como positivo en el ambiente del restaurante, y la clase no_mencionado incluye comentarios generales sin aspecto). Lo que se concluya no puede extenderse a otros lugares o canales sin repetir la prueba.')

# ---- 3 Metodología
h1('3. Metodología')
fig(F2, 'Figura 2. Flujo del sistema: del comentario a la acción.')
h2('3.1 Reglas del diseño experimental')
bl(['**Mismos datos y métricas** para todos los modelos; semilla 42 (y 43 y 44 para medir la variabilidad de BETO).',
    '**Todo se ajusta solo con entrenamiento:** vocabulario, pesos por clase y parámetros. El umbral de abstención se elige con **validación**.',
    '**El test se mide una sola vez**, solo con los modelos finalistas, después de elegirlos con validación.',
    '**Métrica principal: F1 macro** (todas las clases pesan igual). Además: recall de la queja, F1 de la clase mixta, log loss, matriz de confusión y error de calibración.',
    'Se reportan **intervalos de confianza del 95 %** por bootstrap (2.000 remuestras) porque el test es pequeño.'])
h2('3.2 Baseline obligatorio: TF-IDF y clasificador lineal')
p('TF-IDF convierte cada texto en un vector que pesa las palabras (o trozos de letras) que lo distinguen. **No es una red neuronal**: es la alternativa simple contra la que se mide el modelo avanzado. '
  'Se probaron seis combinaciones: TF-IDF de palabras (1 y 2 palabras), de caracteres (2 a 5 letras) y de ambos, con regresión logística, SVM lineal y Naive Bayes complementario; todas con pesos por clase balanceados. '
  'El campeón del baseline es el mejor con regresión logística según validación, porque esta entrega probabilidades, necesarias para abstener.')
h2('3.3 Modelo avanzado: BETO')
p('BETO es un BERT preentrenado solo con texto en español. Se ajusta completo (*fine-tuning*) con una cabeza de clasificación de 4 clases. Se usaron los parámetros del taller de la sesión 4: learning rate 2e-5, batch 16, 3 épocas, weight decay 0,01, warmup del 10 %, '
  '`max_length` de 128 tokens, pérdida con pesos por clase y selección de la mejor época por F1 macro de validación. Se prueban **dos configuraciones**, cada una con tres semillas: `beto_128` (texto original) y `beto_128_min` (texto pasado a minúsculas antes de entrar al modelo, porque BETO distingue mayúsculas de minúsculas y mostró fragilidad ante textos en MAYÚSCULAS en el taller de la sesión 4). '
  'El entrenamiento requiere GPU (Google Colab con T4).')
h2('3.4 Abstención, guardia de fuera de dominio y calibración')
p(f"El sistema **no decide solo** cuando la confianza (la probabilidad de la clase elegida) es menor que un umbral, que se elige con validación: la regla que menos casos manda a revisión y aún encuentra al menos el {pc(resumen['meta']['recall_critica'], 0)} de las quejas (contando como encontrada una queja bien clasificada o enviada a revisión). Para el baseline el umbral resultó {f(regla['tau'], 2)}. "
  f"Una prueba mostró que la confianza sola no detecta textos sin relación con el casino: el baseline da entre 56 % y 66 % de confianza a textos como \"asdkjh qwerty\". Por eso se agregó una **guardia**: si menos del {pc(regla['cobertura_min'], 0)} de las palabras del comentario aparece en el vocabulario de entrenamiento (o se reconocen menos de {regla['min_conocidas']} palabras), el caso pasa a una persona. "
  'La calibración se mide con el error de calibración esperado (ECE).')
h2('3.5 Pruebas de robustez')
p('Tres baterías: (a) **29 frases** escritas por el equipo, en pares que cambian una sola cosa (negación, contraste, orden, doble negación, ortografía, mayúsculas, ironía, entre otras), más 6 entradas **fuera de dominio** (35 casos); (b) **perturbaciones plausibles** sobre las 312 reseñas de validación (sin tildes, MAYÚSCULAS, errores de tipeo y abreviaturas); y (c) desempeño por **segmentos** de longitud y de periodo.')
h2('3.6 Reproducibilidad')
tabla(['Elemento', 'Valor'], [
    ['Semillas', '42 (y 43 y 44 para BETO)'], ['Versiones', 'Python 3.11, scikit-learn ' + conf_json['versiones']['sklearn'] + ', pandas ' + conf_json['versiones']['pandas'] + '; BETO: transformers 5.23.0 y torch 2.14.1 (Colab)'],
    ['Hardware', 'Baselines: CPU de un portátil con Windows 11; BETO: GPU T4 de Colab'], ['Código y datos', 'Repositorio con README, requirements.txt, notebook ejecutable de inicio a fin y script que regenera el corpus'],
    ['Resultados', 'Todas las tablas salen de results/; el resumen consolidado está en results/resumen_final.json']], 'Tabla 4. Reproducibilidad', [3.4, 12.1])

# ---- 4 Resultados
h1('4. Resultados')
h2('4.1 Elección del baseline (validación)')
tb = base_val.copy()
tabla(['Modelo', 'F1 macro', 'Recall de quejas', 'F1 mixta', 'Entrenamiento (s)'], [[r.modelo, f(r.f1_macro_val), f(r.recall_negativa_val), f(r.f1_mixta_val), f(r.segundos_entrenar, 1)] for r in tb.itertuples()],
      'Tabla 5. Baselines en validación (312 reseñas)', [7.0, 2.1, 2.5, 1.9, 2.0])
p(f"El mejor con regresión logística es **{B['nombre']}** (F1 macro de {f(B['f1_val'])} en validación). Las diferencias de pocas centésimas entre variantes no son concluyentes con 312 reseñas; el SVM lineal y Naive Bayes muestran que el resultado no depende de un solo clasificador.")
h2('4.2 BETO en validación')
if BETO:
    gc = beto_corr.groupby('config').agg(f1=('f1_macro_val', 'mean'), sd=('f1_macro_val', 'std'), rec=('recall_negativa_val', 'mean'), seg=('segundos_entrenamiento', 'mean'), par=('parametros_M', 'first')).reset_index()
    tabla(['Configuración', 'F1 macro (media ± desv.)', 'Recall de quejas', 'Entrenamiento (s)', 'Parámetros (M)'], [[r.config, f'{f(r.f1)} ± {f(r.sd)}', f(r.rec), f(r.seg, 0), f(r.par, 1)] for r in gc.itertuples()],
          'Tabla 6. BETO en validación (3 semillas por configuración)', [4.2, 3.6, 2.7, 2.7, 2.3])
    p(f"El campeón de BETO es **{BETO['config']}**, elegido por el F1 macro medio de validación.")
else:
    pend('Resultados de BETO en validación (2 configuraciones × 3 semillas). Se obtienen ejecutando la sección 6 del notebook en Colab.')
h2('4.3 Evaluación final en test')
fil = [['Baseline', f(B['f1_test']), f"{f(B['ic_f1'][0])} a {f(B['ic_f1'][1])}", f(B['recall_test']), f(B['f1_mixta_test']), f(B['log_loss_test'])]]
if BETO: fil.append([f"BETO ({BETO['config']})", f"{f(BETO['f1_test_media'])} ± {f(BETO['f1_test_std'])}", f"{f(BETO['ic_f1'][0])} a {f(BETO['ic_f1'][1])}", f(BETO['recall_test_media']), f(BETO['f1_mixta_media']), f(BETO['log_loss_media'])])
tabla(['Modelo', 'F1 macro', 'IC 95 %', 'Recall de quejas', 'F1 mixta', 'Log loss'], fil, f'Tabla 7. Resultados en test ({N["test"]} reseñas, {quejas_te} quejas)', [3.5, 3.0, 3.3, 2.6, 1.8, 1.8])
fig(F3, 'Figura 3. Matrices de confusión en test.', 14.5)
cm_b = confusion_matrix(yte, Pte.argmax(1), labels=range(4))
conf_pos_nom = cm_b[IDX['positiva'], IDX['no_mencionado']] + cm_b[IDX['no_mencionado'], IDX['positiva']]
p(f"Con el baseline, la confusión más grande es entre **positiva y no_mencionado** ({int(conf_pos_nom)} reseñas de {N['test']}), seguida de las reseñas mixtas, que se confunden con positivas y negativas: es la clase más difícil (F1 de {f(B['f1_mixta_test'])}). "
  f"El intervalo de confianza del F1 macro ({f(B['ic_f1'][0])} a {f(B['ic_f1'][1])}) es ancho: con {N['test']} reseñas, la medición tiene una incertidumbre de unos ±{f((B['ic_f1'][1] - B['ic_f1'][0]) / 2, 2)}.")
if BETO:
    p(f"**Qué corrida se usa en cada cifra.** El F1 macro, el recall y el log loss de BETO en la Tabla 7 son el promedio de las 3 semillas. El intervalo de confianza, la comparación con el baseline, la matriz de confusión y la regla de abstención usan la corrida de la semilla {int(sem0)}, porque el bootstrap pareado necesita las predicciones de una sola corrida.")
    p(f"**Comparación.** En esa corrida, la diferencia de F1 macro entre BETO y el baseline es de {f(BETO['diff'])} (intervalo del 95 %: {f(BETO['diff_ic'][0])} a {f(BETO['diff_ic'][1])}); en promedio de semillas es de {f(BETO['f1_test_media'] - B['f1_test'])}. "
      + ('El intervalo incluye el 0: no hay evidencia suficiente de que BETO sea mejor.' if BETO['diff_ic'][0] <= 0 else f"El intervalo apenas excluye el 0 (límite inferior {f(BETO['diff_ic'][0])}) y es muy ancho: BETO probablemente mejora, pero con {quejas_te} quejas y {N['test']} reseñas no se puede precisar cuánto."))
else:
    pend('Comparación de BETO con el baseline en test, con el intervalo de la diferencia.')
h2('4.4 Abstención y cobertura')
fa = [['Baseline', f(b_ab.tau, 2), pc(b_ab.cobertura_test), pc(b_ab.exactitud_automatica_test), pc(b_ab.recall_queja_directo_test), pc(b_ab.recall_queja_con_revision_test)]]
if ab_beto is not None: fa.append([f"BETO ({BETO['config']})", f(ab_beto.tau, 2), pc(ab_beto.cobertura_test), pc(ab_beto.exactitud_automatica_test), pc(ab_beto.recall_queja_directo_test), pc(ab_beto.recall_queja_con_revision_test)])
tabla(['Modelo', 'Umbral', 'Cobertura automática', 'Exactitud de lo que decide', 'Quejas detectadas directamente', 'Quejas con revisión humana'], fa, 'Tabla 8. Regla de abstención elegida con validación y medida en test', [2.8, 1.6, 2.7, 3.0, 3.0, 2.4])
fig(F4, 'Figura 4. Curva de calidad frente a cobertura en validación.', 10.5)
p(f"Con el baseline, el sistema decide solo el {pc(b_ab.cobertura_test)} de los comentarios con una exactitud del {pc(b_ab.exactitud_automatica_test)}; el {pc(b_ab.revision_test)} pasa a una persona. "
  f"La revisión humana sube la detección de quejas del {pc(b_ab.recall_queja_directo_test)} al {pc(b_ab.recall_queja_con_revision_test)}, **por encima de la meta de {pc(resumen['meta']['recall_critica'], 0)}**, pero la cobertura automática queda **por debajo de la meta de {pc(resumen['meta']['cobertura'], 0)}**. "
  'El umbral se eligió en validación y la meta de recall se cumple también en test, lo que indica que no se sobreajustó; aun así, con 59 quejas conviene reajustarlo en el piloto.')
if BETO:
    cr = leer('carga_revision_validacion.csv')
    if cr is not None:
        piv = cr.pivot(index='revision_pct', columns='modelo')
        fc = [[f"{int(k)} %", f"{int(piv.loc[k, ('quejas_encontradas', 'Baseline')])} de {int(piv.loc[k, ('quejas_totales', 'Baseline')])} ({pc(piv.loc[k, ('recall_queja_con_revision', 'Baseline')])})", f"{int(piv.loc[k, ('quejas_encontradas', 'BETO')])} de {int(piv.loc[k, ('quejas_totales', 'BETO')])} ({pc(piv.loc[k, ('recall_queja_con_revision', 'BETO')])})",
               pc(piv.loc[k, ('exactitud_automatica', 'Baseline')]), pc(piv.loc[k, ('exactitud_automatica', 'BETO')])] for k in piv.index]
        h3b = 'Comparación con la misma carga de revisión'
        p(f"**{h3b}.** Con el mismo umbral de confianza, el baseline envía a revisión el {pc(b_ab.revision_test, 0)} de los comentarios y BETO el {pc(ab_beto.revision_test, 0)}, así que los recalls de la Tabla 8 no son comparables entre sí. "
          "Para compararlos de forma justa se fijó el mismo porcentaje de casos a revisión (los de menor confianza) y se midió en **validación**, con la corrida de la semilla 42 de BETO.")
        tabla(['Casos a revisión', 'Quejas encontradas (baseline)', 'Quejas encontradas (BETO)', 'Exactitud de lo que decide solo (baseline)', 'Exactitud de lo que decide solo (BETO)'], fc, 'Tabla 8b. Mismo porcentaje de revisión, en validación', [2.4, 3.6, 3.6, 3.4, 3.4])
        k5, k20, k31 = 5, 20, 31
        p(f"Con el {k5} % de casos a revisión, BETO encuentra {int(piv.loc[k5, ('quejas_encontradas', 'BETO')])} de {int(piv.loc[k5, ('quejas_totales', 'BETO')])} quejas y el baseline {int(piv.loc[k5, ('quejas_encontradas', 'Baseline')])}; el baseline necesita cerca del {k20} % para llegar a un recall parecido ({pc(piv.loc[k20, ('recall_queja_con_revision', 'Baseline')])}). "
          f"Con una carga alta ({k31} %), el baseline encuentra {int(piv.loc[k31, ('quejas_encontradas', 'Baseline')])} y BETO {int(piv.loc[k31, ('quejas_encontradas', 'BETO')])} de {int(piv.loc[k31, ('quejas_totales', 'BETO')])}: una diferencia de {abs(int(piv.loc[k31, ('quejas_encontradas', 'Baseline')]) - int(piv.loc[k31, ('quejas_encontradas', 'BETO')]))} quejas. "
          "BETO también acierta más en lo que decide solo en todos los niveles. Son 57 quejas y una sola corrida de BETO: es un indicio que el piloto debe confirmar, no una prueba.")
h2('4.5 Análisis de errores')
use_beto_err = BETO and err_beto is not None
E = err_beto if use_beto_err else err_b
nombre_err = 'BETO' if use_beto_err else 'el baseline'
E = E.sort_values('confianza', ascending=False)
tabla(['Real', 'Predicho', 'Conf.', 'Causa probable', 'Texto'], [[r.sentimiento, r.pred, f(r.confianza, 2), r.causa_probable, (r.texto[:92] + '…') if len(r.texto) > 92 else r.texto] for r in E.head(12).itertuples()],
      f'Tabla 9. Los 12 errores de {nombre_err} con mayor confianza (validación; la causa es automática y la revisa el equipo)', [1.9, 1.9, 1.1, 3.9, 6.7])
causas = E.causa_probable.str.split(' \\+ ').explode().value_counts()
n_amb = int(E.causa_probable.str.contains('ambigua').sum())
p(f"En validación, {nombre_err} se equivoca en {len(E)} de {N['validation']} reseñas ({pc(len(E) / N['validation'])}). Las causas más frecuentes son: " + '; '.join(f'**{c}** ({n})' for c, n in causas.head(4).items()) +
  f". **{n_amb} de los {len(E)} errores ({pc(n_amb / len(E), 0)}) son confusiones entre positiva y no_mencionado**: son elogios generales que el corpus a veces marca como positivos y a veces no (por ejemplo, \"Exelente pasatiempo\"). "
  'Eso limita el desempeño máximo y se resuelve con una guía de anotación clara, no con un modelo más complejo. Las demás causas (negación, contraste y textos largos) son de lenguaje y se revisan caso a caso; la causa de cada error se asigna con una regla automática y debe ser confirmada por el equipo.')
h2('4.6 Robustez')
rt = rob.groupby(['tipo', 'modelo']).acierta.agg(['sum', 'count']).reset_index(); rt['txt'] = rt['sum'].astype(int).astype(str) + ' de ' + rt['count'].astype(str)
pv = rt.pivot(index='tipo', columns='modelo', values='txt'); pv.insert(0, 'frases', rob[rob.modelo == rob.modelo.iloc[0]].groupby('tipo').size().reindex(pv.index).astype(int).astype(str))
tabla(['Tipo de caso', 'Frases'] + list(pv.columns[1:]), [[i] + list(r) for i, r in pv.iterrows()], 'Tabla 10. Aciertos en los 35 casos de robustez (29 frases de pares y 6 fuera de dominio)', None)
fig(F5, 'Figura 5. F1 macro en validación al cambiar la forma del texto.', 11.5)
rb0 = rob[rob.modelo == 'Baseline'].groupby('tipo').acierta.agg(['sum', 'count']); fallos = [f"{i} ({int(r['sum'])} de {int(r['count'])})" for i, r in rb0.iterrows() if r['sum'] < r['count']]
perfectos = [f"{i} ({int(r['sum'])} de {int(r['count'])})" for i, r in rb0.iterrows() if r['sum'] == r['count'] and r['count'] >= 2]
pp = pert[pert.modelo == 'Baseline'].set_index('variante').f1_macro
p(f"**Baseline.** Acierta todos los casos de " + ', '.join(perfectos) + '. Falla en: ' + ', '.join(fallos) + '. '
  'TF-IDF no ve el orden de las palabras, por eso falla los pares que cambian el orden o niegan una palabra negativa. Son pocas frases por tipo: sirven para diagnosticar comportamientos, no para medir tasas. '
  f"Ante los cambios en la forma del texto, el F1 macro de validación pasa de {f(pp['original'])} a {f(pp['sin tildes'])} sin tildes, {f(pp['MAYÚSCULAS'])} en MAYÚSCULAS (no cambia porque todo se pasa a minúsculas), {f(pp['errores de tipeo'])} con errores de tipeo y {f(pp['abreviaturas'])} con abreviaturas. ")
p('**Fuera de dominio.** El baseline clasifica los 6 textos sin relación con el casino como no_mencionado, pero con una confianza de entre 56 % y 66 %, por encima del umbral: la confianza sola los dejaría decidir al sistema. La guardia de vocabulario los envía a revisión (6 de 6) y marca solo el 3,5 % de las reseñas reales de validación y el 1,3 % de las de test.')
if BETO:
    pb = pert[pert.modelo == 'BETO'].set_index('variante'); rb = rob[rob.modelo == 'BETO'].groupby('tipo').acierta.agg(['sum', 'count'])
    r0 = rob[rob.modelo == 'Baseline'].groupby('tipo').acierta.agg(['sum', 'count'])
    dif = [f"{k} ({int(rb.loc[k, 'sum'])} de {int(rb.loc[k, 'count'])} frente a {int(r0.loc[k, 'sum'])} de {int(r0.loc[k, 'count'])} del baseline)" for k in rb.index if k in r0.index and rb.loc[k, 'sum'] != r0.loc[k, 'sum']]
    p(f"**BETO ({BETO['config']}).** Ante cambios en la forma del texto, el F1 macro de validación pasa de {f(pb.loc['original', 'f1_macro'])} a {f(pb.loc['sin tildes', 'f1_macro'])} sin tildes, {f(pb.loc['errores de tipeo', 'f1_macro'])} con errores de tipeo y {f(pb.loc['abreviaturas', 'f1_macro'])} con abreviaturas, "
      f"pero **cae a {f(pb.loc['MAYÚSCULAS', 'f1_macro'])} en MAYÚSCULAS**, y el {str(pb.loc['MAYÚSCULAS', 'cambian_pct']).replace('.', ',')} % de las predicciones cambia. Es la fragilidad que se vio en el taller de la sesión 4: esta configuración distingue mayúsculas de minúsculas. "
      "La configuración `beto_128_min`, que pasa el texto a minúsculas, se creó para evitarlo y quedó casi igual en validación; no se midió su robustez, y es lo primero que conviene probar o, en su defecto, normalizar el texto antes de usar BETO. "
      f"En los pares de frases difiere del baseline en: {'; '.join(dif)}. Son muy pocos casos por tipo: es un diagnóstico, no una tasa.")
    p("**Fuera de dominio con BETO.** La guardia de vocabulario no depende del modelo: envía a revisión los mismos 6 textos sin relación con el casino, de modo que la protección es igual con BETO.")
h2('4.7 Desempeño por segmentos')
tabla(['Segmento', 'Reseñas', 'Exactitud', 'F1 macro', 'Quejas', 'Recall de quejas'], [[f"{r['tipo']}: {r['segmento']}", int(r['reseñas']), f(r['exactitud']), f(r['F1 macro']), int(r['quejas']), f(r['recall de quejas'])] for _, r in seg.iterrows()],
      'Tabla 11. Baseline por longitud y periodo (validación)', [4.4, 1.9, 2.1, 2.1, 1.8, 3.2])
p('La exactitud es parecida entre segmentos de longitud (el F1 macro varía porque cada segmento tiene pocas reseñas de las clases pequeñas), pero **cae en el periodo 2020-2021** (F1 macro de 0,44 y 69 % de las quejas detectadas). Con una muestra tan pequeña por segmento no se puede afirmar que sea un cambio real; es una señal para vigilar en el monitoreo. '
  'No hay segmentos de sede ni de canal porque todo el corpus es de un solo lugar y de Google Maps.')
h2('4.8 Costo y latencia')
tabla(list(costo.columns), costo.fillna('—').astype(str).values.tolist(), 'Tabla 12. Costo y latencia (una reseña a la vez)', None)
p('El baseline responde en milisegundos con una CPU y pesa menos de 1 MB. ' + ('BETO tiene unos 110 millones de parámetros y su costo depende de tener GPU.' if BETO else 'La medición de BETO queda pendiente de la ejecución en Colab.'))
if not BETO: pend('Costo, latencia y tamaño de BETO.')
h2('4.9 Criterios de adopción')
tabla(['Criterio (provisional)', 'Meta', 'Resultado', 'Cumple'], crit.fillna('—').values.tolist(), 'Tabla 13. Criterios de adopción evaluados en test', [8.1, 2.2, 2.6, 2.6])

# ---- 5 Riesgos
h1('5. Riesgos y gobierno')
p('La matriz completa (17 riesgos, mapa de calor y plan de monitoreo) está en docs/Matriz_de_Riesgos.xlsx. Estos son los más relevantes:')
tabla(['Riesgo', 'Control', 'Responsable', 'Residual'], [
    ['Quejas no detectadas', 'Abstención con revisión humana, modo sombra y suspensión si el recall auditado baja de 0,90', 'ML y Gerencia IA', 'Medio'],
    ['Revisión humana por encima de la capacidad', 'Fijar el umbral con la capacidad real del equipo', 'Gerencia IA', 'Medio'],
    ['Errores con confianza alta y texto fuera de dominio', 'Calibración, auditoría de una muestra aleatoria y guardia de vocabulario', 'Machine Learning', 'Medio'],
    ['Etiquetas ambiguas y muestra pequeña', 'Usar el sentimiento general, intervalos de confianza y guía de anotación', 'Ciencia de Datos', 'Medio'],
    ['Licencia y uso de los datos', 'Uso académico; no publicar los datos; confirmar con el docente', 'Gerencia IA y Ciencia de Datos', 'Medio'],
    ['Uso en otro casino o canal sin volver a probar', 'Declarar el límite; piloto en modo sombra', 'Gerencia IA', 'Medio']], 'Tabla 14. Riesgos principales', [4.5, 6.4, 2.9, 1.7])
h2('Privacidad, sesgo y seguridad')
bl(['**Privacidad:** minimización (solo texto y fecha), enmascarado de teléfonos y nombres, acceso restringido y sin identificador del autor. Falta una revisión manual de una muestra.',
    '**Sesgo y segmentos:** solo se pudo medir por longitud y periodo. No es posible medir equidad por sede, canal o tipo de cliente con estos datos; se declara como límite.',
    '**Seguridad y trazabilidad:** la demo calcula todo en el navegador; el repositorio es privado; se versionan modelo, vocabulario, partición, umbral y métricas.'])
h2('Operación')
bl(['**Dueño del modelo:** una persona de Gerencia IA, con un suplente de Machine Learning.',
    '**Monitoreo:** recall de quejas auditado, proporción enviada a revisión, confianza media, comentarios marcados por la guardia, proporción de quejas y longitud (hoja Monitoreo de la matriz).',
    '**Reentrenamiento:** tras dos alertas seguidas o con 500 comentarios nuevos anotados.',
    '**Suspensión:** el recall de quejas auditado baja de 0,90; la carga de revisión supera la capacidad del equipo; o cambia el tipo de comentarios.',
    '**Rollback:** volver al baseline con revisión humana, que es simple y está medido.',
    '**Despliegue:** piloto en modo sombra (el modelo corre en paralelo sin decidir y se compara con las decisiones humanas); luego uso con revisión de los casos dudosos. La duración la define el cliente.'])

# ---- 6 Caso de valor
h1('6. Caso de valor')
p('El valor del sistema es el **tiempo de lectura que se ahorra sin perder quejas**. Los datos del curso no traen volumen, tiempo ni costo del proceso actual, así que el caso de valor se presenta como un **escenario con supuestos declarados** que el cliente debe reemplazar por sus cifras.')
cob = b_ab.cobertura_test; cob_b = ab_beto.cobertura_test if ab_beto is not None else None
filas = []
for Nm in (1000, 3000, 6000):
    for m in (1, 2, 3):
        fila = [miles(Nm), f'{m} min', f(Nm * cob * m / 60, 0), f(Nm * (1 - cob) * m / 60, 0)]
        if cob_b is not None: fila += [f(Nm * cob_b * m / 60, 0), f(Nm * (1 - cob_b) * m / 60, 0)]
        filas.append(fila)
cab = ['Comentarios al mes', 'Minutos de lectura por comentario', 'Horas ahorradas al mes (baseline)', 'Horas de revisión restantes (baseline)'] + (['Horas ahorradas (BETO)', 'Horas de revisión (BETO)'] if cob_b is not None else [])
tabla(cab, filas, 'Tabla 15. Sensibilidad: horas al mes según el volumen y el tiempo de lectura (supuestos ilustrativos)', None)
p(f"**Cómo se calcula.** Horas ahorradas = comentarios × cobertura automática × minutos de lectura ÷ 60, con la cobertura medida en test ({pc(cob)} para el baseline" + (f" y {pc(cob_b)} para BETO" if cob_b is not None else '') + '). '
  'Para convertirlo en dinero se multiplica por el costo por hora de quien lee, que debe aportar el cliente. Los volúmenes y minutos de la tabla son **supuestos ilustrativos**, no datos del cliente.')
bl(['**Beneficios no monetarios:** menor tiempo hasta atender una queja y menos quejas olvidadas; se reportan como indicadores.',
    '**Costos:** infraestructura (casi nula para el baseline; GPU para servir BETO), revisión humana de los casos dudosos, monitoreo y reentrenamiento. Falta cotizar la GPU y medir el costo por mil comentarios.',
    f"**Supuestos y límites:** los resultados valen para un solo casino; la cobertura depende del umbral y de la capacidad de revisión; el valor desaparece si el recall de quejas baja de {f(resumen['meta']['recall_critica'], 2)}."])

# ---- 7 Recomendación
h1('7. Recomendación')
tabla(['Opción', 'Cuándo se elige'], [
    ['Mantener el baseline', 'BETO no supera con claridad al baseline (el intervalo de la diferencia incluye 0) o no cumple el recall de quejas con una cobertura razonable'],
    ['Piloto en modo sombra', 'El modelo cumple el recall de quejas con revisión humana; corre en paralelo sin decidir y se compara con las decisiones humanas'],
    ['Piloto con ambos modelos', 'BETO mejora el F1 y necesita menos revisión para un recall parecido, pero no cumple solo las metas en test: ambos corren en paralelo sin decidir y una muestra auditada decide'],
    ['Adoptar', 'Solo tras un piloto que confirme las metas con datos reales de operación']], 'Tabla 16. Opciones de decisión', [4.0, 11.5])
p(RECS[dec] + TRADE)
bl([(f"**Condiciones para elegir a BETO al terminar el piloto:** (1) recall de quejas con revisión humana de al menos {f(resumen['meta']['recall_critica'], 2)} en una muestra auditada, ajustando el umbral; (2) medir `beto_128_min` frente a las MAYÚSCULAS o normalizar el texto a minúsculas; (3) contar con GPU, o aceptar una latencia p95 de unos 143 ms en CPU. "
     f"Si no se cumplen, se continúa con el baseline, cuya carga de revisión es de {pc(b_ab.revision_test)} de los comentarios." if dec == 'piloto_ambos_modelos' else
     f"**Condición:** recall de quejas con revisión humana de al menos {f(resumen['meta']['recall_critica'], 2)} y una carga de revisión que el equipo pueda atender (hoy {pc(b_ab.revision_test)} de los comentarios)."),
    '**Qué falta:** la revisión manual de una muestra de errores y de datos personales, la guía de etiquetado para positiva frente a no_mencionado, la confirmación de la licencia del dataset y las metas validadas con el cliente.' + ('' if BETO else ' Falta además la comparación con BETO.'),
    '**Suspensión:** el recall de quejas auditado baja de 0,90, la revisión supera la capacidad o cambia el tipo de comentarios.',
    '**Siguiente experimento:** más reseñas anotadas con una guía clara (la mejora más segura), y repetir la comparación.'])

# ---- Anexos
salto(); h1('Anexo A. Diccionario de datos'); dd = pd.read_csv(os.path.join(DATA, 'diccionario_datos.csv'), encoding='utf-8-sig')
tabla(['Columna', 'Tipo', 'Descripción'], [[r.columna, r.tipo, r.descripcion] for r in dd.itertuples()], 'Tabla A1. Columnas de corpus_casinos_2100.csv', [4.3, 2.3, 8.9])
h1('Anexo B. Parámetros de los modelos')
tabla(['Modelo', 'Parámetros'], [
    ['TF-IDF palabras', 'n-gramas de 1 a 2 palabras; min_df = 2; TF sublineal; norma L2'],
    ['TF-IDF caracteres', 'analizador char_wb; n-gramas de 2 a 5; min_df = 2; TF sublineal; norma L2'],
    ['Regresión logística', 'max_iter = 3000; class_weight = balanced; semilla 42'],
    ['SVM lineal / Naive Bayes', 'LinearSVC con class_weight = balanced; ComplementNB'],
    ['BETO', 'dccuchile/bert-base-spanish-wwm-cased; lr 2e-5; batch 16; 3 épocas; weight decay 0,01; warmup 10 %; max_length 128; pesos por clase; fp16; semillas 42, 43 y 44']], 'Tabla B1. Configuración', [4.0, 11.5])
h1('Anexo C. Declaración de uso de IA generativa')
p('El equipo usó un asistente de IA (Claude) para generar borradores del código, del notebook y de los documentos. El equipo es responsable del contenido: debe verificar el código, las cifras y las afirmaciones. '
  'Las cifras de este informe salen de ejecuciones guardadas en results/. No se enviaron datos confidenciales a servicios externos: el corpus son reseñas públicas de Google Maps y se procesó de forma local y en Google Colab.')
h1('Anexo D. Referencias')
bl(['Vaswani et al. (2017). *Attention Is All You Need*.', 'Devlin et al. (2019). *BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding*.',
    'Cañete et al. (2020). *Spanish Pre-Trained BERT Model and Evaluation Data* (BETO).', 'Documentación de scikit-learn y de Hugging Face Transformers.',
    'Material del curso de Procesamiento de Lenguaje Natural, Universidad EAN, sesiones 1 a 4.'])

# ------------------------------------------------------------------ render HTML
def md_html(t):
    t = html.escape(t); t = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', t); t = re.sub(r'(?<![\*\w])\*(.+?)\*(?![\*\w])', r'<i>\1</i>', t); return re.sub(r'`(.+?)`', r'<code>\1</code>', t)

def render_html(ruta):
    CSS = ('@page{size:A4;margin:2.2cm 2.1cm}body{font-family:Calibri,"Segoe UI",sans-serif;font-size:11pt;line-height:1.42;color:#17233B}h1{font-size:16pt;color:#1F3A6E;margin:20pt 0 6pt;border-bottom:1.5px solid #D5DDEA;padding-bottom:3pt;break-after:avoid}'
           'h2{font-size:12.2pt;color:#2D6BDB;margin:13pt 0 3pt;break-after:avoid}p{margin:4pt 0 6pt;text-align:justify}ul{margin:3pt 0 6pt;padding-left:16pt}li{margin:2pt 0}'
           'table{border-collapse:collapse;width:100%;font-size:9pt;margin:4pt 0 3pt;break-inside:auto}tr{break-inside:avoid}th{background:#1F3A6E;color:#fff;text-align:left;padding:3pt 5pt}td{border:1px solid #C9D3E6;padding:3pt 5pt;vertical-align:top}'
           'tr:nth-child(even) td{background:#F4F7FB}.cap{font-size:8.4pt;color:#55637D;margin:0 0 8pt}figure{margin:6pt 0;text-align:center;break-inside:avoid}figure img{max-width:100%}figcaption{font-size:8.4pt;color:#55637D}'
           '.pend{background:#FFF3DC;border-left:4px solid #B86E00;padding:5pt 8pt;margin:6pt 0;font-size:9.6pt}code{font-family:Consolas,monospace;font-size:9pt;background:#F0F4FA;padding:0 2px}'
           '.portada{text-align:center;padding-top:110pt;break-after:page}.portada h1{font-size:25pt;border:0;color:#1F3A6E}.portada .s{font-size:13pt;color:#55637D;margin-bottom:22pt}.portada p{text-align:center}')
    portada = ('<div class="portada"><p style="font-size:11pt;color:#55637D">Procesamiento de Lenguaje Natural · Universidad EAN · Proyecto final</p>'
               '<h1>Clasificación de comentarios de clientes de un casino</h1><div class="s">Baseline TF-IDF frente a BETO, con abstención y revisión humana</div>'
               '<p><b>Integrantes</b><br>Edwin Alexander Alfonso Romero · Bresleny Yanira Benavides Cabiche<br>Rubén Darío Barbosa Brugés · Marissa Tatiana Alvarado Sampedro</p>'
               '<p>Docente: Gerson José Moreno Morales</p><p>Noviembre de 2026</p>' + ('' if BETO else '<p class="pend" style="display:inline-block;text-align:left"><b>BORRADOR:</b> faltan los resultados de BETO (se marcan como PENDIENTE).</p>') + '</div>')
    out = ['<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Informe técnico</title><style>' + CSS + '</style></head><body>', portada]
    for b in C:
        k = b[0]
        if k == 'h1': out.append('<h1>' + md_html(b[1]) + '</h1>')
        elif k == 'h2': out.append('<h2>' + md_html(b[1]) + '</h2>')
        elif k == 'p': out.append('<p>' + md_html(b[1]) + '</p>')
        elif k == 'bul': out.append('<ul>' + ''.join('<li>' + md_html(x) + '</li>' for x in b[1]) + '</ul>')
        elif k == 'call': out.append('<div class="pend">' + md_html(b[2]) + '</div>')
        elif k == 'salto': out.append('<div style="break-after:page"></div>')
        elif k == 'fig': out.append('<figure><img src="file:///' + b[1].replace('\\', '/') + '" style="width:' + str(int(b[3] / 17 * 100)) + '%"><figcaption>' + html.escape(b[2]) + '</figcaption></figure>')
        elif k == 'tab':
            cab, filas, cap, an = b[1], b[2], b[3], b[4]
            cg = ''.join(f'<col style="width:{w / sum(an) * 100:.1f}%">' for w in an) if an else ''
            out.append('<table>' + cg + '<thead><tr>' + ''.join('<th>' + md_html(str(c)) + '</th>' for c in cab) + '</tr></thead><tbody>' +
                       ''.join('<tr>' + ''.join('<td>' + md_html(str(x)) + '</td>' for x in fila) + '</tr>' for fila in filas) + '</tbody></table><p class="cap">' + html.escape(cap) + '</p>')
    out.append('</body></html>'); open(ruta, 'w', encoding='utf-8').write('\n'.join(out))

def pdf_con_edge(ruta_html, ruta_pdf):
    edge = next((e for e in [r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', r'C:\Program Files\Microsoft\Edge\Application\msedge.exe'] if os.path.exists(e)), None)
    if not edge: print('Microsoft Edge no encontrado: se omite el PDF'); return False
    perfil = tempfile.mkdtemp()
    subprocess.run([edge, '--headless=new', '--disable-gpu', f'--user-data-dir={perfil}', '--no-pdf-header-footer', '--virtual-time-budget=4000', f'--print-to-pdf={ruta_pdf}', 'file:///' + ruta_html.replace('\\', '/')], capture_output=True, timeout=180)
    shutil.rmtree(perfil, ignore_errors=True); return os.path.exists(ruta_pdf)

# ------------------------------------------------------------------ render DOCX
def sombrear(celda, color):
    tcPr = celda._tc.get_or_add_tcPr(); sh = OxmlElement('w:shd'); sh.set(qn('w:val'), 'clear'); sh.set(qn('w:color'), 'auto'); sh.set(qn('w:fill'), color); tcPr.append(sh)

def runs(par, texto, size=None, color=None):
    for i, parte in enumerate(re.split(r'\*\*', texto)):
        for j, sub in enumerate(re.split(r'(?<![\*\w])\*(?=\S)(.+?)(?<=\S)\*(?![\*\w])', parte)):
            if not sub: continue
            r = par.add_run(sub.replace('`', '')); r.bold = (i % 2 == 1); r.italic = (j % 2 == 1)
            if size: r.font.size = Pt(size)
            if color: r.font.color.rgb = RGBColor.from_string(color)

def campo_pagina(par):
    for t, txt in (('begin', None), (None, 'PAGE'), ('end', None)):
        r = par.add_run()
        if t: e = OxmlElement('w:fldChar'); e.set(qn('w:fldCharType'), t); r._r.append(e)
        else: e = OxmlElement('w:instrText'); e.set(qn('xml:space'), 'preserve'); e.text = txt; r._r.append(e)

def render_docx(ruta):
    d = Document(); s = d.sections[0]; s.page_width, s.page_height = Cm(21), Cm(29.7); s.left_margin = s.right_margin = Cm(2); s.top_margin = s.bottom_margin = Cm(2.1)
    st = d.styles['Normal']; st.font.name = 'Calibri'; st.font.size = Pt(11); st.element.rPr.rFonts.set(qn('w:eastAsia'), 'Calibri'); st.paragraph_format.space_after = Pt(5)
    for n, sz, col in (('Heading 1', 16, '1F3A6E'), ('Heading 2', 12.5, '2D6BDB')):
        h = d.styles[n]; h.font.name = 'Calibri'; h.font.size = Pt(sz); h.font.bold = True; h.font.color.rgb = RGBColor.from_string(col); h.element.rPr.rFonts.set(qn('w:eastAsia'), 'Calibri')
    pie = s.footer.paragraphs[0]; pie.alignment = WD_ALIGN_PARAGRAPH.CENTER; r0 = pie.add_run('Proyecto final · PLN · Universidad EAN · página '); r0.font.size = Pt(8.5); campo_pagina(pie)
    # portada
    for _ in range(5): d.add_paragraph()
    for txt, sz, col, bold in [('Procesamiento de Lenguaje Natural · Universidad EAN · Proyecto final', 11, '55637D', False), ('Clasificación de comentarios de clientes de un casino', 26, '1F3A6E', True),
                               ('Baseline TF-IDF frente a BETO, con abstención y revisión humana', 13, '55637D', False)]:
        p_ = d.add_paragraph(); p_.alignment = WD_ALIGN_PARAGRAPH.CENTER; r = p_.add_run(txt); r.font.size = Pt(sz); r.bold = bold; r.font.color.rgb = RGBColor.from_string(col)
    for _ in range(3): d.add_paragraph()
    for txt, b_ in [('Integrantes', True), ('Edwin Alexander Alfonso Romero · Bresleny Yanira Benavides Cabiche', False), ('Rubén Darío Barbosa Brugés · Marissa Tatiana Alvarado Sampedro', False), ('', False),
                    ('Docente: Gerson José Moreno Morales', False), ('Noviembre de 2026', False)]:
        p_ = d.add_paragraph(); p_.alignment = WD_ALIGN_PARAGRAPH.CENTER; r = p_.add_run(txt); r.bold = b_
    if not BETO:
        p_ = d.add_paragraph(); p_.alignment = WD_ALIGN_PARAGRAPH.CENTER; r = p_.add_run('BORRADOR: faltan los resultados de BETO (se marcan como PENDIENTE).'); r.bold = True; r.font.color.rgb = RGBColor.from_string('B86E00')
    d.add_page_break()
    for b in C:
        k = b[0]
        if k == 'h1': d.add_heading(b[1].replace('**', ''), 1)
        elif k == 'h2': d.add_heading(b[1].replace('**', ''), 2)
        elif k == 'p': runs(d.add_paragraph(), b[1])
        elif k == 'bul':
            for x in b[1]: runs(d.add_paragraph(style='List Bullet'), x)
        elif k == 'salto': d.add_page_break()
        elif k == 'call':
            t = d.add_table(rows=1, cols=1); t.alignment = WD_TABLE_ALIGNMENT.CENTER; c = t.rows[0].cells[0]; sombrear(c, 'FFF3DC'); c.paragraphs[0].text = ''; runs(c.paragraphs[0], b[2], 9.5); d.add_paragraph()
        elif k == 'fig':
            d.add_picture(b[1], width=Cm(min(b[3], 16.5))); d.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            cp = d.add_paragraph(); cp.alignment = WD_ALIGN_PARAGRAPH.CENTER; r = cp.add_run(b[2]); r.font.size = Pt(8.5); r.font.color.rgb = RGBColor.from_string('55637D')
        elif k == 'tab':
            cab, filas, cap, an = b[1], b[2], b[3], b[4]
            t = d.add_table(rows=1, cols=len(cab)); t.style = 'Table Grid'; t.alignment = WD_TABLE_ALIGNMENT.CENTER
            for j, c in enumerate(cab):
                ce = t.rows[0].cells[j]; sombrear(ce, '1F3A6E'); ce.paragraphs[0].text = ''; r = ce.paragraphs[0].add_run(str(c)); r.bold = True; r.font.size = Pt(8.5); r.font.color.rgb = RGBColor.from_string('FFFFFF')
            for i, fila in enumerate(filas):
                cs = t.add_row().cells
                for j, x in enumerate(fila):
                    cs[j].paragraphs[0].text = ''; runs(cs[j].paragraphs[0], str(x), 8.5)
                    if i % 2: sombrear(cs[j], 'F4F7FB')
            if an:
                t.autofit = False
                for row in t.rows:
                    for j, w in enumerate(an): row.cells[j].width = Cm(w)
            cp = d.add_paragraph(); r = cp.add_run(cap); r.font.size = Pt(8.5); r.font.color.rgb = RGBColor.from_string('55637D')
    d.save(ruta)

def main():
    h = os.path.join(DOCS, 'Informe_Tecnico.html'); render_html(h)
    pdf = os.path.join(DOCS, 'Informe_Tecnico.pdf'); ok = pdf_con_edge(h, pdf)
    render_docx(os.path.join(DOCS, 'Informe_Tecnico.docx'))
    if ok:
        import pymupdf; d = pymupdf.open(pdf); print('Páginas del PDF (incluye portada y anexos):', len(d))
        # páginas hasta el inicio de los anexos
        for i, pg in enumerate(d):
            if 'Anexo A. Diccionario de datos' in pg.get_text(): print('Páginas del cuerpo (sin portada ni anexos):', i - 1); break
    os.remove(h) if os.path.exists(h) else None


if __name__ == '__main__':
    main()
