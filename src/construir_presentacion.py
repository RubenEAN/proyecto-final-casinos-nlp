"""
Construye la presentación final (PPTX editable + PDF) a partir de results/ y de las figuras del informe.

Requisitos: haber ejecutado el notebook y src/construir_informe.py (que deja las figuras en docs/figuras/).
Las cifras salen de results/; si no hay resultados de BETO, la diapositiva 9 lo indica y se completa al volver a ejecutar.
El PDF se genera con Chrome o Edge (solo para revisar y repartir; el entregable es el PPTX).

Uso (desde la carpeta del repositorio):
    python src/construir_presentacion.py
"""
import html, json, os, re, shutil, subprocess, sys, tempfile, zipfile
import numpy as np, pandas as pd
from xml.sax.saxutils import escape

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES, DATA, DOCS = os.path.join(RAIZ, 'results'), os.path.join(RAIZ, 'data'), os.path.join(RAIZ, 'docs'); FIG = os.path.join(DOCS, 'figuras')
EDGE = next((e for e in [r'C:\Program Files\Google\Chrome\Application\chrome.exe', r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe', r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', r'C:\Program Files\Microsoft\Edge\Application\msedge.exe'] if os.path.exists(e)), None)
W_IN, H_IN, EMU = 13.333, 7.5, 914400
INK, MUTED, LINE, PANEL, BG = '17233B', '55637D', 'D5DDEA', 'FFFFFF', 'F4F7FB'
AZUL, VERDE, AMBAR, ROJO, NAVY = '2D6BDB', '0F8F6B', 'B86E00', 'C23B3B', '1F3A6E'
ROL = {'G': ('Gerencia IA', AMBAR), 'D': ('Ciencia de Datos', VERDE), 'M': ('Machine Learning', AZUL), 'T': ('Todo el equipo', NAVY)}

def leer(n):
    r = os.path.join(RES, n); return pd.read_csv(r) if os.path.exists(r) else None
resumen = json.load(open(os.path.join(RES, 'resumen_final.json'), encoding='utf-8'))
regla = json.load(open(os.path.join(RES, 'regla_abstencion.json'), encoding='utf-8'))
B, BETO, N, META = resumen['baseline'], resumen['beto'], resumen['n'], resumen['meta']; AB = resumen['abstencion']; b_ab = AB[0]; ab_beto = AB[1] if len(AB) > 1 else None
base_val, rob, pert, seg, costo = leer('baselines_validacion.csv'), leer('robustez_pares.csv'), leer('robustez_perturbaciones.csv'), leer('segmentos_validacion.csv'), leer('costo_latencia.csv')
err_b, err_beto = leer('errores_validacion_baseline.csv'), leer('errores_validacion_beto.csv'); E = err_beto if (BETO and err_beto is not None) else err_b
df = pd.read_csv(os.path.join(DATA, 'corpus_casinos_2100.csv'), encoding='utf-8-sig')
def f(x, n=3): return ('—' if x is None else f'{x:.{n}f}'.replace('.', ','))
def pc(x, n=1): return f'{x * 100:.{n}f} %'.replace('.', ',')
def miles(x): return f'{int(x):,}'.replace(',', '.')
img = lambda n: os.path.join(FIG, n)

# ------------------------------------------------------------------ captura de la demo
def capturar_demo():
    if not EDGE: return
    demo = os.path.join(RAIZ, 'app', 'demo.html')
    if not os.path.exists(demo): return
    base = open(demo, encoding='utf-8').read()
    casos = {'demo_uno.png': "document.getElementById('texto').value='Muy buena atención, pero las máquinas no pagan nada';document.getElementById('analizar').click();window.scrollTo(0,0);",
             'demo_fuera.png': "document.getElementById('texto').value='asdkjh qwerty';document.getElementById('analizar').click();",
             'demo_lote.png': "document.getElementById('tab-lote').click();document.getElementById('ejemplo-lote').click();document.getElementById('analizar-lote').click();"}
    for nombre, js in casos.items():
        d = tempfile.mkdtemp(); h = os.path.join(d, 'p.html')
        open(h, 'w', encoding='utf-8').write(base.replace('</body>', f'<script>setTimeout(function(){{{js}}},200)</script></body>'))
        subprocess.run([EDGE, '--headless=new', '--disable-gpu', f'--user-data-dir={d}', '--hide-scrollbars', '--window-size=900,1180', '--virtual-time-budget=3000', f'--screenshot={os.path.join(FIG, nombre)}', 'file:///' + h.replace('\\', '/')], capture_output=True, timeout=120)
        shutil.rmtree(d, ignore_errors=True)

# ------------------------------------------------------------------ modelo de escena
class Slide:
    def __init__(self): self.el = []
def rich(t, size, color, bold=False):
    return [(s, dict(size=size, color=color, bold=(bold or i % 2 == 1))) for i, s in enumerate(re.split(r'\*\*', t)) if s]
def P(t, size=16, color=INK, bold=False, align='l', bullet=False, space=5):
    return dict(runs=rich(t, size, color, bold), align=align, bullet=bullet, space=space, size=size)
def rect(s, x, y, w, h, fill=None, line=None, lw=1.0, r=0.0): s.el.append(('rect', x, y, w, h, fill, line, lw, r))
def text(s, x, y, w, h, paras, anchor='t', fill=None, line=None, pad=0.08, r=0.0): s.el.append(('text', x, y, w, h, paras, anchor, fill, line, pad, r))
def pic(s, x, y, w, h, ruta): s.el.append(('pic', x, y, w, h, ruta))
def tabla(s, x, y, w, cols, filas, size=12, rh=0.36, head=NAVY, zebra=True): s.el.append(('tab', x, y, w, cols, filas, size, rh, head, zebra))

def marco(s, titulo, rol=None, n=None):
    rect(s, 0, 0, W_IN, 0.12, fill=NAVY)
    text(s, 0.55, 0.32, 10.6, 0.95, [P(titulo, 27, NAVY, True, space=0)], anchor='t')
    if rol:
        nom, col = ROL[rol]; text(s, 11.25, 0.38, 1.6, 0.34, [P(nom, 11, 'FFFFFF', True, 'c', space=0)], anchor='m', fill=col, r=0.5, pad=0.04)
    text(s, 0.55, 7.08, 9, 0.3, [P('Procesamiento de Lenguaje Natural · Universidad EAN · Proyecto final', 10, MUTED, space=0)])
    if n: text(s, 12.0, 7.08, 0.8, 0.3, [P(str(n), 10, MUTED, align='r', space=0)])

def tile(s, x, y, w, h, grande, chico, color=AZUL, gs=30, pie=None):
    rect(s, x, y, w, h, fill=PANEL, line=LINE, r=0.12)
    text(s, x, y + 0.12, w, h * 0.55, [P(grande, gs, color, True, 'c', space=0)], anchor='m'); text(s, x + 0.1, y + h * 0.58, w - 0.2, h * 0.4, [P(l_, 12.5, MUTED, align='c', space=0) for l_ in chico.split(chr(10))] + ([P(pie, 11, INK, True, 'c', space=0)] if pie else []), anchor='t')

# ------------------------------------------------------------------ diapositivas
S = []
def nueva(titulo, rol=None):
    s = Slide(); marco(s, titulo, rol, len(S) + 1); S.append(s); return s

# 1 Portada
s = Slide(); S.append(s)
rect(s, 0, 0, W_IN, H_IN, fill=NAVY); rect(s, 0.7, 2.0, 0.09, 2.2, fill=AMBAR)
text(s, 1.0, 1.9, 11.2, 1.6, [P('Clasificación de comentarios de clientes de un casino', 38, 'FFFFFF', True, space=0)], anchor='t')
text(s, 1.0, 3.55, 11, 0.6, [P('Baseline TF-IDF frente a BETO, con abstención y revisión humana', 20, 'C9D6EE', space=0)])
text(s, 1.0, 4.85, 11, 1.4, [P('Edwin Alexander Alfonso Romero · Bresleny Yanira Benavides Cabiche', 15, 'FFFFFF', space=2), P('Rubén Darío Barbosa Brugés · Marissa Tatiana Alvarado Sampedro', 15, 'FFFFFF', space=8),
                           P('Procesamiento de Lenguaje Natural · Universidad EAN · Docente: Gerson José Moreno Morales · Noviembre de 2026', 12.5, 'C9D6EE', space=0)])
if not BETO: text(s, 1.0, 6.45, 6.4, 0.45, [P('BORRADOR: faltan los resultados de BETO (diapositiva 9)', 12.5, 'FFFFFF', True, 'c', space=0)], anchor='m', fill=AMBAR, r=0.3)

# 2 Decisión
s = nueva('Una decisión concreta: qué comentario atiende una persona primero', 'G')
for i, (t, d, c) in enumerate([('Usuario', 'Equipo de experiencia al cliente y operaciones de una cadena de casinos', AZUL),
                               ('Decisión', 'Este comentario, ¿lo atiende una persona o se procesa de forma automática?', VERDE),
                               ('Clase crítica', 'La **queja**. El error más costoso es no detectarla ni enviarla a revisión', ROJO)]):
    x = 0.55 + i * 4.1; rect(s, x, 1.55, 3.9, 2.35, fill=PANEL, line=c, lw=2, r=0.08)
    text(s, x + 0.2, 1.65, 3.5, 0.5, [P(t, 19, c, True, space=0)]); text(s, x + 0.2, 2.2, 3.5, 1.6, [P(d, 16.5, INK, space=0)])
rect(s, 0.55, 4.2, 12.2, 1.75, fill=PANEL, line=LINE, r=0.06)
text(s, 0.8, 4.3, 11.7, 0.45, [P('Qué medimos para saber si sirve (metas provisionales, por validar con el cliente)', 15, MUTED, True, space=0)])
text(s, 0.8, 4.8, 3.9, 1.1, [P(f"≥ {f(META['recall_critica'], 2)}", 30, ROJO, True, 'c', space=0), P('de las quejas detectadas, con revisión humana', 13, MUTED, align='c', space=0)])
text(s, 4.8, 4.8, 3.9, 1.1, [P(f"≥ {pc(META['cobertura'], 0)}", 30, AZUL, True, 'c', space=0), P('de comentarios que el sistema decide solo', 13, MUTED, align='c', space=0)])
text(s, 8.8, 4.8, 3.9, 1.1, [P(f"≥ +{f(META['mejora_f1'], 2)}", 30, VERDE, True, 'c', space=0), P('de F1 macro de BETO para justificar su costo', 13, MUTED, align='c', space=0)])
text(s, 0.55, 6.2, 12.2, 0.7, [P('El sistema **solo prioriza**: no responde a los clientes ni toma decisiones sobre personas.', 16, INK, space=0)])

# 3 Cómo funciona
s = nueva('Cómo funciona: del comentario a una acción con confianza', 'G')
pic(s, 0.55, 1.45, 12.2, 2.75, img('f2_pipeline.png'))
for i, (t, d, c) in enumerate([('Entra', 'Un comentario en español informal, con faltas de ortografía, abreviaturas y emojis', AZUL),
                               ('Sale', 'Una clase, la probabilidad de cada clase y una acción: decide el sistema o revisión humana', VERDE),
                               ('Cuándo no decide solo', 'Si la confianza es menor que el umbral, o si el texto no se parece a las reseñas de entrenamiento', AMBAR)]):
    x = 0.55 + i * 4.1; rect(s, x, 4.5, 3.9, 2.25, fill=PANEL, line=LINE, r=0.08); rect(s, x, 4.5, 0.09, 2.25, fill=c)
    text(s, x + 0.25, 4.58, 3.5, 0.5, [P(t, 17, c, True, space=0)]); text(s, x + 0.25, 5.1, 3.5, 1.6, [P(d, 15, INK, space=0)])

# 4 Datos
s = nueva('Los datos: 2.100 reseñas de Google Maps de un casino de Buenos Aires', 'D')
nq = int((df.sentimiento == 'negativa').sum()); mp = int(df.n_palabras.median())
tile(s, 0.55, 1.5, 3.7, 1.55, miles(len(df)), 'reseñas tras la auditoría (de las 2.100 del corpus)', VERDE, 36)
tile(s, 0.55, 3.25, 3.7, 1.55, f"{nq} ({pc(nq / len(df), 0)})", 'quejas: la clase crítica y minoritaria', ROJO, 32)
tile(s, 0.55, 5.0, 3.7, 1.55, f"{mp} palabras", 'mediana de longitud: textos cortos e informales', AZUL, 30)
rect(s, 4.6, 1.5, 8.2, 3.1, fill=PANEL, line=LINE, r=0.06)
text(s, 4.8, 1.58, 7.8, 0.45, [P('Qué contiene el corpus', 16, NAVY, True, space=0)])
text(s, 4.8, 2.1, 7.8, 2.5, [P(f"Reseñas de **{df.periodo.min()[:4]} a {df.periodo.max()[:4]}** sobre un casino e hipódromo, en español rioplatense", 15, INK, bullet=True),
                          P('Cada reseña trae etiquetas de **12 aspectos** (atención, calidad, precio, ambiente...)', 15, INK, bullet=True),
                          P('Para una decisión simple se derivó **un sentimiento general**: negativa, mixta, positiva o no_mencionado', 15, INK, bullet=True),
                          P('Hay faltas de ortografía, abreviaturas, MAYÚSCULAS y emojis', 15, INK, bullet=True)])
rect(s, 4.6, 4.8, 8.2, 1.75, fill='FFF3DC', line=None, r=0.06)
text(s, 4.8, 4.85, 7.8, 1.7, [P('Fuente y permisos', 14.5, AMBAR, True, space=3),
                          P('Dataset académico del curso (comentarios_tp_v2), usado en las clases 1 a 4. **Sin licencia declarada: uso académico, no se publica ni se redistribuye.**', 14, INK, space=0)])

# 5 Auditoría y partición
s = nueva('Auditoría y partición: sin fuga y con la incertidumbre a la vista', 'D')
tabla(s, 0.55, 1.5, 7.4, [2.9, 2.6, 1.9], [['Control', 'Resultado', 'Acción'], ['Etiquetas "positive" (inglés)', '26 celdas en 20 reseñas', 'Corregidas'], ['Reseña fuera de alcance', '1', 'Excluida'],
                                         ['Textos idénticos, etiquetas contradictorias', '5 grupos · 20 reseñas', 'Excluidas'], ['Textos idénticos, etiquetas iguales', '9 grupos · 25 reseñas', 'Juntos en una partición'],
                                         ['Datos personales', '1 teléfono · 1 firma', 'Enmascarados']], size=12.5, rh=0.55)
rect(s, 8.3, 1.5, 4.5, 3.35, fill=PANEL, line=LINE, r=0.06)
text(s, 8.5, 1.58, 4.1, 0.45, [P('Partición 70 / 15 / 15', 16, NAVY, True, space=0)])
ct = pd.crosstab(df.sentimiento, df.particion)
tabla(s, 8.5, 2.1, 4.1, [1.5, 0.9, 0.9, 0.8], [['Clase', 'Train', 'Val.', 'Test']] + [[c, int(ct.loc[c, 'train']), int(ct.loc[c, 'validation']), int(ct.loc[c, 'test'])] for c in ['negativa', 'mixta', 'positiva', 'no_mencionado']], size=12, rh=0.42)
text(s, 0.55, 5.2, 12.2, 1.7, [P(f"Estratificada por clase y **por grupos de texto idéntico**: un grupo nunca queda en dos particiones.", 15.5, INK, bullet=True),
                              P(f"El test tiene solo **{N['quejas_test']} quejas** y {N['mixtas_test']} mixtas: las diferencias pequeñas entre modelos **no son concluyentes**.", 15.5, INK, bullet=True),
                              P('Etiquetas por aspecto poco fiables (fallaban en 9 de 30 reseñas revisadas a mano): por eso la tarea usa el sentimiento general.', 15.5, INK, bullet=True)])

# 6 EDA
s = nueva('Qué dicen los datos: pocas quejas, textos cortos y una clase ambigua', 'D')
pic(s, 0.55, 1.4, 12.2, 3.5, img('f1_datos.png'))
text(s, 0.55, 5.1, 12.2, 1.9, [P('La clase positiva es el **59 %**: un modelo que siempre dijera "positiva" acertaría casi 6 de cada 10 sin aprender nada, por eso la métrica es el **F1 macro**.', 15.5, INK, bullet=True),
                              P('Mediana de **9 palabras**: el 98 % tiene 64 palabras o menos. Las quejas (mediana de 14) y las mixtas (21) son más largas que las positivas.', 15.5, INK, bullet=True),
                              P('**Límite:** un solo casino y un solo canal. Lo que se concluya no se extiende a otros lugares sin repetir la prueba.', 15.5, INK, bullet=True)])

# 7 Diseño experimental
s = nueva('Cómo comparamos: un baseline simple contra un Transformer en español', 'M')
for i, (t, d, c) in enumerate([('Baseline', 'TF-IDF de palabras y caracteres + regresión logística. **No es una red neuronal**: es la vara de medir. Se probaron 6 variantes y se eligió con validación.', AZUL),
                               ('BETO', 'BERT preentrenado en español, ajustado con las reseñas. 2 configuraciones × 3 semillas, entrenado en una GPU de Colab.', VERDE)]):
    x = 0.55 + i * 6.2; rect(s, x, 1.5, 6.0, 2.2, fill=PANEL, line=c, lw=2, r=0.08); text(s, x + 0.2, 1.6, 5.6, 0.5, [P(t, 20, c, True, space=0)]); text(s, x + 0.2, 2.15, 5.6, 1.5, [P(d, 15.5, INK, space=0)])
text(s, 0.55, 4.0, 12.2, 0.45, [P('Reglas que protegen la comparación', 17, NAVY, True, space=0)])
for i, t in enumerate(['**Mismos datos y métricas** para todos; semilla 42 (y 43 y 44 para BETO)', '**Todo se ajusta solo con entrenamiento**; el umbral de revisión se elige con validación',
                       '**El test se mide una sola vez**, solo con los finalistas', 'Métrica principal **F1 macro**, más recall de quejas y calibración',
                       '**Intervalos de confianza del 95 %** por bootstrap, porque el test es pequeño', 'Robustez: 29 frases en pares, 6 textos fuera de dominio y 4 perturbaciones']):
    x = 0.55 + (i % 2) * 6.2; y = 4.5 + (i // 2) * 0.82; rect(s, x, y, 6.0, 0.7, fill=PANEL, line=LINE, r=0.1); text(s, x + 0.15, y, 5.7, 0.7, [P(t, 13.5, INK, space=0)], anchor='m')

# 8 Baseline
lr_ = base_val[base_val.modelo.str.contains('regresión')].f1_macro_val
s = nueva('Resultado del baseline: detecta 4 de 5 quejas y, con revisión, más de 9 de 10', 'M')
tile(s, 0.55, 1.5, 2.9, 1.7, f(B['f1_test']), f"F1 macro en test\nIC 95 %: {f(B['ic_f1'][0])} a {f(B['ic_f1'][1])}", AZUL, 34)
tile(s, 3.65, 1.5, 2.9, 1.7, pc(B['recall_test'], 0), f"de las quejas, directo\n({int(round(B['recall_test'] * N['quejas_test']))} de {N['quejas_test']})", ROJO, 34)
tile(s, 6.75, 1.5, 2.9, 1.7, pc(b_ab['recall_queja_con_revision_test'], 0), 'de las quejas, con revisión\nhumana de los casos dudosos', VERDE, 34)
tile(s, 9.85, 1.5, 2.9, 1.7, pc(b_ab['cobertura_test'], 0), f"decide solo el sistema\n(meta: {pc(META['cobertura'], 0)})", AMBAR, 34)
tabla(s, 0.55, 3.5, 7.6, [4.2, 1.1, 1.1, 1.2], [['Variantes en validación (312 reseñas, para elegir)', 'F1 macro', 'Recall', 'F1 mixta']] + [[r.modelo.replace('TF-IDF ', '').replace(' + ', ' + '), f(r.f1_macro_val), f(r.recall_negativa_val), f(r.f1_mixta_val)] for r in base_val.itertuples()], size=11.5, rh=0.42)
text(s, 0.55, 6.5, 7.6, 0.45, [P('Los recuadros de arriba son el resultado en prueba (test), medido una sola vez; la tabla es validación, solo para elegir la variante.', 11.5, MUTED, True, space=0)])
text(s, 8.5, 3.45, 4.3, 3.4, [P('Cómo leerlo', 16, NAVY, True, space=4), P('El recall con revisión **cumple la meta** de 0,90; la cobertura **no llega** a 75 %.', 14.5, INK, bullet=True), P(f"Las 3 regresiones logísticas quedan juntas (F1 de {f(lr_.min(), 2)} a {f(lr_.max(), 2)}): con 312 reseñas esa diferencia es ruido. Naive Bayes tiene el mayor recall, pero no acierta ninguna mixta.", 14.5, INK, bullet=True),
                          P(f"La clase mixta es la más difícil (F1 de {f(B['f1_mixta_test'])}): solo hay {N['mixtas_test']} en test.", 14.5, INK, bullet=True)])

# 9 BETO
s = nueva('BETO frente al baseline: ¿justifica su costo?', 'M')
if BETO:
    dm = BETO['f1_test_media'] - B['f1_test']; lo = BETO['diff_ic'][0]
    q_dir_b = int(round(b_ab['recall_queja_directo_test'] * N['quejas_test'])); q_dir_e = int(round(ab_beto['recall_queja_directo_test'] * N['quejas_test']))
    q_rev_b = int(round(b_ab['recall_queja_con_revision_test'] * N['quejas_test'])); q_rev_e = int(round(ab_beto['recall_queja_con_revision_test'] * N['quejas_test']))
    tile(s, 0.55, 1.5, 2.9, 1.9, f(BETO['f1_test_media']), f"BETO: F1 macro en test\nmedia de 3 semillas ± {f(BETO['f1_test_std'])}", AZUL, 34, pie=f"Baseline: {f(B['f1_test'])} (BETO {dm:+.3f})".replace('.', ','))
    tile(s, 3.65, 1.5, 2.9, 1.9, pc(ab_beto['recall_queja_directo_test'], 0), f"BETO: de las quejas, directo\n({q_dir_e} de {N['quejas_test']})", ROJO, 34, pie=f"Baseline: {pc(b_ab['recall_queja_directo_test'], 0)} ({q_dir_b} de {N['quejas_test']})")
    tile(s, 6.75, 1.5, 2.9, 1.9, pc(ab_beto['recall_queja_con_revision_test'], 0), f"BETO: de las quejas, con\nrevisión humana ({q_rev_e} de {N['quejas_test']})", VERDE, 34, pie=f"Baseline: {pc(b_ab['recall_queja_con_revision_test'], 0)} ({q_rev_b} de {N['quejas_test']})")
    tile(s, 9.85, 1.5, 2.9, 1.9, pc(ab_beto['cobertura_test'], 0), f"BETO: decide solo el sistema\n(meta: {pc(META['cobertura'], 0)})", AMBAR, 34, pie=f"Baseline: {pc(b_ab['cobertura_test'], 0)}")
    tabla(s, 0.55, 3.65, 7.3, [2.4, 1.6, 1.6, 1.7], [['Test', 'Baseline', 'BETO', 'Meta']] + [['F1 macro', f(B['f1_test']), f(BETO['f1_test_media']), f"+{f(META['mejora_f1'], 2)}"], ['Decide solo', pc(b_ab['cobertura_test']), pc(ab_beto['cobertura_test']), '≥ ' + pc(META['cobertura'], 0)],
          ['Quejas con revisión', pc(b_ab['recall_queja_con_revision_test']), pc(ab_beto['recall_queja_con_revision_test']), '≥ ' + f(META['recall_critica'], 2)], ['A revisión humana', pc(b_ab['revision_test']), pc(ab_beto['revision_test']), '—']], size=12.5, rh=0.5)
    text(s, 8.2, 3.6, 4.6, 3.3, [P('Cómo leerlo', 16, NAVY, True, space=4),
          P((f"El intervalo de la diferencia de F1 (semilla 42: {f(lo)} a {f(BETO['diff_ic'][1])}) **apenas excluye el 0**: BETO probablemente mejora, pero con 59 quejas no se puede precisar cuánto." if 0 < lo < META['mejora_f1'] else ('El intervalo **incluye el 0**: no hay evidencia suficiente de que BETO sea mejor.' if lo <= 0 else 'El intervalo **excluye el 0** con margen.')), 14, INK, bullet=True),
          P(f"Son **puntos de operación distintos**: BETO decide solo el {pc(ab_beto['cobertura_test'], 0)} y deja {pc(ab_beto['revision_test'], 0)} a revisión; el baseline deja {pc(b_ab['revision_test'], 0)}.", 14, INK, bullet=True),
          P(f"Recall de BETO {pc(ab_beto['recall_queja_con_revision_test'])}: unas {int(round((b_ab['recall_queja_con_revision_test'] - ab_beto['recall_queja_con_revision_test']) * N['quejas_test']))} quejas menos que el baseline en test, bajo la meta de {f(META['recall_critica'], 2)}.", 14, INK, bullet=True)])
    text(s, 0.55, 6.3, 7.3, 0.7, [P('F1: media de 3 semillas; las demás cifras de BETO, con la semilla 42. Costo de BETO: unos 110 millones de parámetros; GPU para responder en ~9 ms (CPU: 143 ms).', 12.5, MUTED, True, space=0)])
else:
    rect(s, 0.55, 1.5, 6.1, 5.3, fill='FFF3DC', line=AMBAR, lw=2, r=0.06)
    text(s, 0.8, 1.6, 5.6, 0.5, [P('PENDIENTE: ejecutar BETO en Colab', 18, AMBAR, True, space=0)])
    text(s, 0.8, 2.2, 5.6, 4.5, [P('El modelo avanzado necesita GPU y no puede entrenarse en un computador sin ella.', 14.5, INK, bullet=True), P('Subir el notebook y los datos a Google Colab (T4) y ejecutar todo: 6 corridas, unos 10 a 15 minutos.', 14.5, INK, bullet=True),
                              P('Copiar los archivos beto_* en la carpeta results/ del repositorio.', 14.5, INK, bullet=True), P('Volver a ejecutar el notebook, el informe y esta presentación: esta diapositiva se llena sola con las cifras.', 14.5, INK, bullet=True)])
    text(s, 6.95, 1.5, 5.8, 0.5, [P('Lo que se reportará aquí', 17, NAVY, True, space=0)])
    tabla(s, 6.95, 2.1, 5.8, [2.6, 3.2], [['Cifra', 'Para qué'], ['F1 macro de BETO en test', 'Comparar con 0,626 del baseline'], ['Intervalo de la diferencia', '¿Es mejor con claridad o es ruido?'], ['Recall de quejas con revisión', 'Meta: ≥ 0,90'],
                                       ['Cobertura automática', 'Meta: ≥ 75 %'], ['Latencia y costo', 'GPU frente a CPU'], ['Robustez ante MAYÚSCULAS', 'Fragilidad vista en el taller 4']], size=12.5, rh=0.5)
    text(s, 6.95, 5.8, 5.8, 1.0, [P('Hasta tenerlo, la recomendación se apoya solo en el baseline.', 14.5, MUTED, True, space=0)])

# 9b Peso y tiempo de procesamiento
cb = costo.set_index('modelo'); cbase, cbeto = cb.loc['Baseline'], cb.loc['BETO'] if 'BETO' in cb.index else None
def num_(x): return float(re.findall(r'[\d.]+', str(x))[0])
try:
    import joblib
    pipe_ = joblib.load(os.path.join(RES, 'baseline_modelo.joblib')); nf_w, nf_c = [len(tr_.vocabulary_) for _, tr_ in pipe_.steps[0][1].transformer_list]
except Exception: nf_w = nf_c = None
if cbeto is not None:
    s = nueva('Peso y tiempo de procesamiento: BETO es mucho más pesado que el baseline', 'M')
    p_b, p_e = num_(cbase['parametros']), num_(cbeto['parametros']); m_b, m_e = num_(cbase['tamano_MB']), num_(cbeto['tamano_MB'])
    e_b, e_e = num_(cbase['entrenamiento_s']), num_(cbeto['entrenamiento_s']); l_b = num_(cbase['latencia_p95_ms'])
    l_gpu = float(re.search(r'GPU ([\d.]+)', str(cbeto['latencia_p95_ms'])).group(1)); l_cpu = float(re.search(r'CPU ([\d.]+)', str(cbeto['latencia_p95_ms'])).group(1))
    veces = lambda a, b: ('≈ ' + miles(round(b / a, -1 if b / a >= 100 else 0)) + ' veces') if b / a >= 1.5 else 'similar'
    filas = [['Qué se mide', 'Baseline', 'BETO', 'BETO es…'],
             ['Parámetros', f"{f(p_b, 2)} M", f"{f(p_e, 0)} M", veces(p_b, p_e)], ['Tamaño del modelo', f"{f(m_b, 1)} MB", f"≈ {int(m_e)} MB", veces(m_b, m_e)],
             ['Entrenamiento (una corrida)', f"{f(e_b, 1)} s en CPU", f"{f(e_e, 0)} s en GPU", veces(e_b, e_e)],
             ['Respuesta por comentario (p95), CPU', f"{f(l_b, 1)} ms", f"{f(l_cpu, 0)} ms", veces(l_b, l_cpu)], ['Respuesta por comentario (p95), GPU', '—', f"{f(l_gpu, 1)} ms", 'necesita GPU']]
    tabla(s, 0.55, 1.4, 7.4, [3.4, 1.4, 1.4, 1.5], filas, size=12.5, rh=0.46)
    # barras: latencia p95 por comentario (escala lineal)
    text(s, 0.55, 4.35, 7.4, 0.4, [P('Tiempo de respuesta por comentario (p95, milisegundos)', 13.5, NAVY, True, space=0)])
    for k_, (nom_, val_, col_) in enumerate([('Baseline · CPU', l_b, AZUL), ('BETO · GPU', l_gpu, VERDE), ('BETO · CPU', l_cpu, ROJO)]):
        y_ = 4.85 + k_ * 0.55; ancho = max(0.08, 4.4 * val_ / l_cpu)
        text(s, 0.55, y_, 1.7, 0.4, [P(nom_, 12.5, INK, space=0)], anchor='m'); rect(s, 2.3, y_ + 0.05, ancho, 0.3, fill=col_); text(s, 2.3 + ancho + 0.08, y_, 1.2, 0.4, [P(f"{f(val_, 1 if val_ < 20 else 0)} ms", 12.5, INK, True, space=0)], anchor='m')
    rect(s, 8.3, 1.4, 4.5, 5.1, fill=PANEL, line=LINE, r=0.06)
    text(s, 8.5, 1.48, 4.1, 0.45, [P('Por qué pesa más', 16, NAVY, True, space=0)])
    bl = [P('**BETO:** cada palabra pasa por 12 capas de atención con 110 millones de pesos. Entrenarlo y responder rápido exige una GPU.', 13, INK, bullet=True, space=5),
          P(f"**Baseline:** multiplica un vector de TF-IDF por una tabla de {miles(nf_w + nf_c) if nf_w else '~17.000'} características × 4 clases: unos {miles(round((nf_w + nf_c) * 4, -3)) if nf_w else '70.000'} coeficientes. Es una cuenta simple en cualquier CPU.", 13, INK, bullet=True, space=5)]
    if nf_w: bl.append(P(f"**Dentro del baseline** pesan más los n-gramas de caracteres ({miles(nf_c)} características) que los de palabras ({miles(nf_w)}); la regresión logística entrena más lento que Naive Bayes o SVM.", 13, INK, bullet=True, space=5))
    bl.append(P('**Consecuencia:** servir BETO exige GPU o aceptar unos ' + f"{f(l_cpu, 0)} ms en CPU; el baseline corre en cualquier equipo.", 13, INK, bullet=True, space=0))
    text(s, 8.5, 2.0, 4.1, 4.4, bl)
    text(s, 0.55, 6.5, 7.4, 0.5, [P('Baseline medido en este equipo (CPU); BETO en una GPU T4 de Colab. Los tiempos varían un poco de una ejecución a otra.', 11, MUTED, True, space=0)])

# 10 Errores
s = nueva('Dónde se equivoca: la mayor parte de los errores es una etiqueta ambigua', 'D')
pic(s, 0.55, 1.4, 6.2, 5.1, img('f3_confusion.png'))
n_amb = int(E.causa_probable.str.contains('ambigua').sum()); causas = E.causa_probable.str.split(' \\+ ').explode().value_counts()
tile(s, 7.1, 1.5, 2.75, 1.5, f"{n_amb} de {len(E)}", ('errores de BETO: ' if BETO else 'errores: ') + 'positiva contra no_mencionado', AMBAR, 28); tile(s, 10.0, 1.5, 2.75, 1.5, f"{len(E)}", f"{'errores de BETO' if BETO else 'errores'} en {N['validation']} reseñas de validación ({pc(len(E) / N['validation'], 0)})", ROJO, 28)
text(s, 7.1, 3.2, 5.7, 3.7, [P('Causas probables (reglas automáticas, a revisar por el equipo)', 14, NAVY, True, space=3)] + [P(f"**{c}**: {n}", 13.5, INK, bullet=True, space=2) for c, n in causas.head(4).items()] +
                          [P('Los elogios generales ("Exelente pasatiempo") se anotan a veces como positivos y a veces no. Se arregla con una **guía de anotación**, no con un modelo más grande.', 14, INK, space=0)])

# 11 Abstención
s = nueva('Cuánto decide solo el sistema y cuánto pasa a una persona', 'D')
pic(s, 0.55, 1.4, 6.4, 4.1, img('f4_calidad_cobertura.png'))
filas = [['Modelo', 'Umbral', 'Decide solo', 'Quejas directo', 'Quejas con revisión'], ['Baseline', f(b_ab['tau'], 2), pc(b_ab['cobertura_test']), pc(b_ab['recall_queja_directo_test']), pc(b_ab['recall_queja_con_revision_test'])]]
if ab_beto: filas.append([f"BETO ({BETO['config']})", f(ab_beto['tau'], 2), pc(ab_beto['cobertura_test']), pc(ab_beto['recall_queja_directo_test']), pc(ab_beto['recall_queja_con_revision_test'])])
tabla(s, 7.2, 1.5, 5.6, [1.5, 0.8, 1.0, 1.1, 1.2], filas, size=11.5, rh=0.5)
cr = leer('carga_revision_validacion.csv')
if cr is not None:
    g_ = lambda m_, k_, c_: cr[(cr.modelo == m_) & (cr.revision_pct == k_)].iloc[0][c_]
    b1 = P(f"**Con la misma carga de revisión (validación):** a 5 %, BETO encuentra {int(g_('BETO', 5, 'quejas_encontradas'))} de {int(g_('BETO', 5, 'quejas_totales'))} quejas y el baseline {int(g_('Baseline', 5, 'quejas_encontradas'))}; el baseline necesita ~20 % para igualarlo. A 31 %, el baseline gana por {int(g_('Baseline', 31, 'quejas_encontradas') - g_('BETO', 31, 'quejas_encontradas'))} quejas.", 13.5, INK, bullet=True)
else:
    b1 = P(f"La regla se elige en **validación**: la que menos casos manda a revisión y aún encuentra el {pc(META['recall_critica'], 0)} de las quejas.", 14, INK, bullet=True)
text(s, 7.2, 3.3, 5.6, 3.5, [b1,
                          P(f"En test, el baseline cumple la meta de recall ({pc(b_ab['recall_queja_con_revision_test'])}) pero **no la de cobertura** ({pc(b_ab['cobertura_test'], 0)})." + (f" BETO cumple la cobertura ({pc(ab_beto['cobertura_test'], 0)}) pero queda en **{pc(ab_beto['recall_queja_con_revision_test'])}** de recall." if ab_beto else ''), 14, INK, bullet=True),
                          P(f"La carga de revisión es de **{pc(b_ab['revision_test'], 0)}** con el baseline" + (f" y de **{pc(ab_beto['revision_test'], 0)}** con BETO" if ab_beto else '') + ': el equipo debe poder atenderla.', 14, INK, bullet=True)])
text(s, 0.55, 5.7, 6.4, 1.2, [P('Pedir más confianza mejora la exactitud de lo que el sistema decide, pero deja menos casos automáticos.', 14, MUTED, True, space=0)])

# 12 Robustez
s = nueva('Robustez: BETO entiende el orden, pero se rompe con MAYÚSCULAS' if BETO else 'Robustez: acierta contraste y ortografía, falla orden y doble negación', 'D')
orden = ['contraste', 'ortografía', 'mayúsculas y emojis', 'negación', 'ironía', 'orden', 'doble negación', 'fuera de dominio']
g = rob.groupby(['tipo', 'modelo']).acierta.agg(['sum', 'count']).unstack('modelo')
filas = [['Tipo de caso', 'Frases', 'Baseline'] + (['BETO'] if BETO else [])]
for o in orden:
    if o in g.index:
        n_ = int(g.loc[o, ('count', 'Baseline')]); fila = [o, n_, f"{int(g.loc[o, ('sum', 'Baseline')])} de {n_}"]
        if BETO: fila.append(f"{int(g.loc[o, ('sum', 'BETO')])} de {n_}")
        filas.append(fila)
tabla(s, 0.55, 1.5, 5.9, [2.6, 1.0, 1.1, 1.0] if BETO else [3.2, 1.3, 1.4], filas, size=12.5, rh=0.46)
pic(s, 6.8, 1.45, 6.0, 3.1, img('f5_perturbaciones.png'))
pp = pert[pert.modelo == 'Baseline'].set_index('variante').f1_macro
bl = [P(f"**Baseline:** cambiar la forma del texto casi no mueve el F1 macro ({f(pp['original'])}); los errores de tipeo bajan a {f(pp['errores de tipeo'])}.", 13, INK, bullet=True)]
if BETO:
    pb = pert[pert.modelo == 'BETO'].set_index('variante')
    bl.append(P(f"**BETO:** estable con tildes, tipeo y abreviaturas, pero **en MAYÚSCULAS el F1 macro cae de {f(pb.loc['original', 'f1_macro'])} a {f(pb.loc['MAYÚSCULAS', 'f1_macro'])}** ({str(pb.loc['MAYÚSCULAS', 'cambian_pct']).replace('.', ',')} % de predicciones cambian). Pasar el texto a minúsculas debería corregirlo, pero falta medirlo.", 13, INK, bullet=True))
bl.append(P('**Fuera de dominio:** la confianza sola deja pasar textos sin sentido (56 % a 66 %). La **guardia de vocabulario** los envía a revisión (6 de 6) con cualquiera de los dos modelos y marca solo el 3,5 % de las reseñas.', 13, INK, bullet=True))
text(s, 6.8, 4.65, 6.0, 2.3, bl)
text(s, 0.55, 6.0, 5.9, 0.8, [P('Pocas frases por tipo: es un diagnóstico, no una tasa.', 13, MUTED, True, space=0)])

# 13 Demo
s = nueva('Demostración: pegar un comentario y ver la decisión', 'M')
for i, (arch, t) in enumerate([('demo_uno.png', 'Un comentario: clase, confianza, decisión y palabras clave'), ('demo_fuera.png', 'Texto sin sentido: pasa a revisión aunque la confianza sea alta'), ('demo_lote.png', 'Varios comentarios: resumen agregado')]):
    x = 0.55 + i * 4.1; pic(s, x, 1.4, 3.9, 4.55, img(arch)); text(s, x, 6.0, 3.9, 0.9, [P(t, 13.5, INK, align='c', space=0)])

# 14 Costo y valor
s = nueva('Costo y caso de valor: horas de lectura que se ahorran', 'G')
cst = costo.fillna('—')
tabla(s, 0.55, 1.5, 6.4, [1.2, 1.5, 1.2, 1.2, 1.3], [['Modelo', 'Parámetros', 'Tamaño (MB)', 'Latencia p95 (ms)', 'Hardware']] + [[r.modelo, r.parametros, r.tamano_MB, r.latencia_p95_ms, r.hardware] for r in cst.itertuples()], size=11, rh=0.62)
cob = b_ab['cobertura_test']
cob_b = ab_beto['cobertura_test'] if ab_beto else None
filas = [['Comentarios al mes', 'Min. por comentario', 'Horas: baseline'] + (['Horas: BETO'] if cob_b else [])] + [[miles(n_), f'{m} min', f(n_ * cob * m / 60, 0)] + ([f(n_ * cob_b * m / 60, 0)] if cob_b else []) for n_ in (1000, 3000, 6000) for m in (1, 3)]
tabla(s, 7.2, 1.5, 5.6, [1.6, 1.5, 1.3, 1.2] if cob_b else [1.8, 1.9, 1.9], filas, size=12, rh=0.42)
text(s, 7.2, 4.5, 5.6, 0.6, [P(f"Cobertura de {pc(cob)} (baseline)" + (f" y {pc(cob_b)} (BETO), pero BETO deja menos quejas detectadas. " if cob_b else '. ') + f"**Supuestos ilustrativos**: no hay datos del cliente.", 12.5, MUTED, True, space=0)])
text(s, 0.55, 3.7, 6.4, 3.2, [P('Costos: casi nulos para el baseline; **GPU** para servir BETO; revisión humana de los casos dudosos; monitoreo y reentrenamiento.', 14, INK, bullet=True),
                              P('Beneficios no monetarios: menos tiempo hasta atender una queja y menos quejas olvidadas.', 14, INK, bullet=True), P('El valor desaparece si el recall de quejas baja de 0,90.', 14, INK, bullet=True)])
text(s, 7.2, 5.2, 5.6, 1.6, [P('Horas ahorradas = comentarios × cobertura × minutos ÷ 60. Para pasarlo a dinero falta el costo por hora y el volumen reales del cliente.', 13.5, INK, space=0)])

# 15 Riesgos y gobierno
s = nueva('Riesgos y gobierno: cómo se controla y cuándo se apaga', 'G')
tabla(s, 0.55, 1.5, 7.6, [2.7, 3.4, 1.5], [['Riesgo', 'Control', 'Residual'], ['Quejas no detectadas', 'Revisión humana, modo sombra y suspensión', 'Medio'], ['Revisión por encima de la capacidad', 'Umbral según la capacidad real', 'Medio'],
                                         ['Errores con confianza alta o fuera de dominio', 'Calibración, auditoría y guardia', 'Medio'], ['Etiquetas ambiguas, muestra pequeña', 'Sentimiento general, intervalos, guía', 'Medio'],
                                         ['Licencia y uso de los datos', 'Solo uso académico; confirmar', 'Medio'], ['Uso en otro lugar sin probar', 'Piloto en modo sombra', 'Medio']], size=11.5, rh=0.55)
rect(s, 8.45, 1.5, 4.35, 4.1, fill=PANEL, line=LINE, r=0.06)
text(s, 8.65, 1.58, 4.0, 0.45, [P('Gobierno del modelo', 16, NAVY, True, space=0)])
text(s, 8.65, 2.1, 4.0, 3.5, [P('**Dueño:** Gerencia IA, con suplente de ML', 13, INK, bullet=True, space=3), P('**Monitoreo:** recall auditado, % a revisión, confianza, guardia, % de quejas', 13, INK, bullet=True, space=3),
                            P('**Suspender si:** recall auditado < 0,90, la revisión supera la capacidad o cambia el tipo de comentarios', 13, INK, bullet=True, space=3), P('**Rollback:** baseline con revisión humana', 13, INK, bullet=True, space=3)])
text(s, 0.55, 5.6, 7.6, 1.3, [P('La matriz completa (17 riesgos, mapa de calor y 8 indicadores de monitoreo) está en el archivo de Excel entregado.', 14, INK, space=0)])
text(s, 8.45, 5.75, 4.35, 1.1, [P('Privacidad: teléfonos y nombres enmascarados; falta revisar una muestra a mano.', 13, MUTED, True, space=0)])

# 16 Recomendación
RECS = {'pendiente_beto': ('Piloto en modo sombra con el baseline y revisión humana', 'La decisión sobre BETO queda pendiente de sus resultados.'),
        'piloto_sombra_beto': ('Piloto en modo sombra con BETO y revisión humana', 'El baseline queda como respaldo (rollback).'),
        'piloto_ambos_modelos': ('Piloto en modo sombra con ambos modelos', 'BETO necesita mucha menos revisión para un recall parecido, pero es frágil ante MAYÚSCULAS y no cumple solo las metas en test.'),
        'mantener_baseline': ('Mantener el baseline con revisión humana', 'BETO no supera con claridad al baseline.')}
t_rec, t_sub = RECS[resumen['decision']]
s = nueva('Recomendación: ' + t_rec.lower(), 'G')
rect(s, 0.55, 1.55, 12.2, 1.25, fill=NAVY, r=0.06); text(s, 0.85, 1.55, 11.6, 1.25, [P(t_rec, 22, 'FFFFFF', True, space=3), P(t_sub, 15, 'C9D6EE', space=0)], anchor='m')
pa = resumen['decision'] == 'piloto_ambos_modelos'
for i, (t, d, c) in enumerate([(('Para elegir BETO' if pa else 'Condición'), ("Recall de quejas ≥ 0,90 en una muestra auditada (ajustando el umbral); medir la versión en minúsculas frente a MAYÚSCULAS; contar con GPU o aceptar ~143 ms en CPU. Si no, baseline (revisión: " + pc(b_ab['revision_test'], 0) + ")." if pa else f"Recall de quejas con revisión ≥ {f(META['recall_critica'], 2)} y una carga de revisión que el equipo pueda atender (hoy {pc(b_ab['revision_test'], 0)})."), VERDE),
                               ('Qué falta', 'Revisar a mano una muestra de errores y de datos personales, una guía de anotación, confirmar la licencia y validar las metas con el cliente' + ('' if BETO else ', y comparar con BETO.'), AMBAR),
                               ('Siguiente experimento', 'Más reseñas anotadas con una guía clara: es la mejora más segura. Después, repetir la comparación.', AZUL)]):
    x = 0.55 + i * 4.1; rect(s, x, 3.1, 3.9, 2.55, fill=PANEL, line=c, lw=2, r=0.08); text(s, x + 0.2, 3.2, 3.5, 0.5, [P(t, 18, c, True, space=0)]); text(s, x + 0.2, 3.75, 3.5, 1.85, [P(d, 14.5, INK, space=0)])
text(s, 0.55, 5.95, 12.2, 0.9, [P('**Se suspende** si el recall de quejas auditado baja de 0,90, si la revisión supera la capacidad del equipo o si cambia el tipo de comentarios.', 15.5, INK, space=0)])

# 17 Anexo
s = nueva('Anexo: reproducibilidad y uso de IA generativa', 'T')
tabla(s, 0.55, 1.5, 6.6, [1.9, 4.7], [['Elemento', 'Valor'], ['Semillas', '42 (y 43 y 44 para BETO)'], ['Datos', '2.079 reseñas; 1.455 / 312 / 312'], ['Código', 'Repositorio con README, requirements y notebook ejecutable'], ['Resultados', 'Todo sale de results/; resumen en resumen_final.json'], ['Demo', 'demo.html verificada contra Python (662 textos, diferencia máxima 6e-6)']], size=12, rh=0.62)
rect(s, 7.45, 1.5, 5.35, 3.7, fill='FFF3DC', r=0.06)
text(s, 7.65, 1.6, 4.95, 0.45, [P('Declaración de uso de IA generativa', 16, AMBAR, True, space=0)])
text(s, 7.65, 2.1, 4.95, 3.1, [P('Un asistente de IA (Claude) generó borradores del código, el notebook y los documentos.', 13.5, INK, bullet=True), P('El equipo verifica el código, las cifras y las afirmaciones.', 13.5, INK, bullet=True),
                            P('Solo se presentan como evidencia las cifras guardadas en results/.', 13.5, INK, bullet=True), P('No se enviaron datos confidenciales a servicios externos.', 13.5, INK, bullet=True)])

# 18-19 Observabilidad (imágenes completas de respaldo, hechas por el equipo)
try:
    from PIL import Image as _Im
except Exception: _Im = None
for _n in (1, 2):
    _ruta = img(f'observabilidad{_n}.png')
    if os.path.exists(_ruta):
        s = Slide(); S.append(s)
        if _Im is not None: _c = _Im.open(_ruta).convert('RGB').getpixel((2, 2)); rect(s, 0, 0, W_IN, H_IN, fill='%02X%02X%02X' % _c)
        pic(s, 0, 0, W_IN, H_IN, _ruta)

# ------------------------------------------------------------------ render HTML
def px(v): return v * 96
def run_html(txt, st):
    css = f"font-size:{st['size']}pt;color:#{st['color']};" + ('font-weight:700;' if st['bold'] else ''); return f'<span style="{css}">{html.escape(txt)}</span>'
def par_html(pr):
    pad = 'padding-left:1.1em;text-indent:-1.1em;' if pr['bullet'] else ''
    pre = '<span style="display:inline-block;width:1.1em;text-indent:0">•</span>' if pr['bullet'] else ''
    return f'<div style="text-align:{ {"l": "left", "c": "center", "r": "right"}[pr["align"]] };margin-bottom:{pr["space"]}pt;line-height:1.2;{pad}">{pre}' + ''.join(run_html(t, st) for t, st in pr['runs']) + '</div>'
def slide_html(sl):
    out = ['<section class="sl">']
    for e in sl.el:
        k = e[0]
        if k == 'rect':
            _, x, y, w, h, fill, line, lw, r = e
            out.append(f'<div style="position:absolute;left:{px(x)}px;top:{px(y)}px;width:{px(w)}px;height:{px(h)}px;' + (f'background:#{fill};' if fill else '') + (f'border:{lw}px solid #{line};' if line else '') + f'border-radius:{min(px(r), px(min(w, h)) / 2)}px;box-sizing:border-box"></div>')
        elif k == 'text':
            _, x, y, w, h, paras, anchor, fill, line, pad, r = e
            jc = {'t': 'flex-start', 'm': 'center', 'b': 'flex-end'}[anchor]
            out.append(f'<div style="position:absolute;left:{px(x)}px;top:{px(y)}px;width:{px(w)}px;height:{px(h)}px;display:flex;flex-direction:column;justify-content:{jc};padding:{px(pad)}px;box-sizing:border-box;overflow:hidden;' +
                       (f'background:#{fill};' if fill else '') + (f'border:1px solid #{line};' if line else '') + f'border-radius:{min(px(r), px(min(w, h)) / 2)}px">' + ''.join(par_html(p) for p in paras) + '</div>')
        elif k == 'pic':
            _, x, y, w, h, ruta = e
            if os.path.exists(ruta): out.append(f'<img src="file:///{ruta.replace(chr(92), "/")}" style="position:absolute;left:{px(x)}px;top:{px(y)}px;width:{px(w)}px;height:{px(h)}px;object-fit:contain">')
        elif k == 'tab':
            _, x, y, w, cols, filas, size, rh, head, zebra = e
            tot = sum(cols); cg = ''.join(f'<col style="width:{c / tot * 100:.2f}%">' for c in cols)
            body = ''.join('<tr style="height:' + str(px(rh)) + 'px">' + ''.join((f'<th style="background:#{head};color:#fff;text-align:left;font-size:{size}pt;padding:2px 7px;border:1px solid #{head}">{html.escape(str(c))}</th>' if i == 0 else
                           f'<td style="font-size:{size}pt;padding:2px 7px;border:1px solid #{LINE};background:#{"F4F7FB" if (zebra and i % 2 == 0) else "FFFFFF"};color:#{INK}">{html.escape(str(c))}</td>') for c in fila) + '</tr>' for i, fila in enumerate(filas))
            out.append(f'<table style="position:absolute;left:{px(x)}px;top:{px(y)}px;width:{px(w)}px;border-collapse:collapse;table-layout:fixed">{cg}{body}</table>')
    out.append('</section>'); return ''.join(out)

def render_html(ruta):
    css = f'@page{{size:{W_IN}in {H_IN}in;margin:0}}*{{margin:0;padding:0}}body{{font-family:Calibri,"Segoe UI",sans-serif;background:#{BG}}}.sl{{position:relative;width:{px(W_IN)}px;height:{px(H_IN)}px;background:#{BG};overflow:hidden;page-break-after:always;break-after:page}}'
    open(ruta, 'w', encoding='utf-8').write('<!doctype html><html><head><meta charset="utf-8"><style>' + css + '</style></head><body>' + ''.join(slide_html(sl) for sl in S) + '</body></html>')

# ------------------------------------------------------------------ render PPTX
def emu(v): return int(round(v * EMU))
NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'); HDR = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
GRP = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
def rels(items): return HDR + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(f'<Relationship Id="{i}" Type="{REL}/{t}" Target="{d}"/>' for i, t, d in items) + '</Relationships>'
def solid(c): return f'<a:solidFill><a:srgbClr val="{c}"/></a:solidFill>'
def runs_xml(pr):
    return ''.join(f'<a:r><a:rPr lang="es-CO" sz="{int(st["size"] * 100)}" b="{1 if st["bold"] else 0}" dirty="0">{solid(st["color"])}<a:latin typeface="Calibri"/><a:cs typeface="Calibri"/></a:rPr><a:t>{escape(t)}</a:t></a:r>' for t, st in pr['runs']) or f'<a:endParaRPr lang="es-CO" sz="{int(pr["size"] * 100)}"/>'
def para_xml(pr):
    algn = {'l': 'l', 'c': 'ctr', 'r': 'r'}[pr['align']]
    bu = ('marL="228600" indent="-228600"><a:buFont typeface="Arial"/><a:buChar char="•"/>' if pr['bullet'] else '><a:buNone/>')
    return f'<a:p><a:pPr algn="{algn}" {bu}<a:spcAft><a:spcPts val="{int(pr["space"] * 100)}"/></a:spcAft></a:pPr>' .replace('<a:spcAft>', '<a:spcAft>', 1) + runs_xml(pr) + '</a:p>'
def para_xml(pr):   # orden correcto de hijos de a:pPr: spcAft antes de buFont/buChar
    algn = {'l': 'l', 'c': 'ctr', 'r': 'r'}[pr['align']]; mar = ' marL="228600" indent="-228600"' if pr['bullet'] else ''
    bu = '<a:buFont typeface="Arial"/><a:buChar char="•"/>' if pr['bullet'] else '<a:buNone/>'
    return f'<a:p><a:pPr algn="{algn}"{mar}><a:lnSpc><a:spcPct val="100000"/></a:lnSpc><a:spcAft><a:spcPts val="{int(pr["space"] * 100)}"/></a:spcAft>{bu}</a:pPr>' + runs_xml(pr) + '</a:p>'
def geom(r, w, h):
    if r <= 0: return '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
    adj = int(min(50000, r / max(0.01, min(w, h)) * 100000)); return f'<a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val {adj}"/></a:avLst></a:prstGeom>'
def sp_xml(i, x, y, w, h, fill, line, lw, r, tx=None, txbox=False, anchor='t', pad=0.08):
    ln = f'<a:ln w="{int(lw * 12700)}">{solid(line)}</a:ln>' if line else '<a:ln><a:noFill/></a:ln>'
    body = (f'<p:txBody><a:bodyPr wrap="square" lIns="{emu(pad)}" tIns="{emu(pad)}" rIns="{emu(pad)}" bIns="{emu(pad)}" anchor="{ {"t": "t", "m": "ctr", "b": "b"}[anchor] }"><a:noAutofit/></a:bodyPr><a:lstStyle/>' + ''.join(para_xml(p) for p in tx) + '</p:txBody>') if tx else '<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:endParaRPr lang="es-CO"/></a:p></p:txBody>'
    tb = ' txBox="1"' if txbox else ''; nom = 'Texto' if txbox else 'Forma'
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="{nom} {i}"/><p:cNvSpPr{tb}/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="{emu(x)}" y="{emu(y)}"/><a:ext cx="{emu(w)}" cy="{emu(h)}"/></a:xfrm>{geom(r, w, h)}'
            + (solid(fill) if fill else '<a:noFill/>') + ln + f'</p:spPr>{body}</p:sp>')
def tabla_xml(i, x, y, w, cols, filas, size, rh, head, zebra):
    tot = sum(cols); cw = [emu(c / tot * w) for c in cols]; borde = lambda c: ''.join(f'<a:{t} w="9525">{solid(c)}</a:{t}>' for t in ('lnL', 'lnR', 'lnT', 'lnB'))
    rows = []
    for ri, fila in enumerate(filas):
        cells = []
        for c in fila:
            col = 'FFFFFF' if ri == 0 else INK; fill = head if ri == 0 else ('F4F7FB' if (zebra and ri % 2 == 0) else 'FFFFFF')
            cells.append(f'<a:tc><a:txBody><a:bodyPr/><a:lstStyle/><a:p><a:pPr algn="l"/><a:r><a:rPr lang="es-CO" sz="{int(size * 100)}" b="{1 if ri == 0 else 0}" dirty="0">{solid(col)}<a:latin typeface="Calibri"/></a:rPr><a:t>{escape(str(c))}</a:t></a:r></a:p></a:txBody>'
                         f'<a:tcPr marL="73152" marR="73152" marT="27432" marB="27432" anchor="ctr">{borde(head if ri == 0 else LINE)}{solid(fill)}</a:tcPr></a:tc>')
        rows.append(f'<a:tr h="{emu(rh)}">' + ''.join(cells) + '</a:tr>')
    return (f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{i}" name="Tabla {i}"/><p:cNvGraphicFramePr><a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr><p:nvPr/></p:nvGraphicFramePr>'
            f'<p:xfrm><a:off x="{emu(x)}" y="{emu(y)}"/><a:ext cx="{sum(cw)}" cy="{emu(rh) * len(filas)}"/></p:xfrm><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table">'
            f'<a:tbl><a:tblPr firstRow="1" bandRow="1"/><a:tblGrid>' + ''.join(f'<a:gridCol w="{c}"/>' for c in cw) + '</a:tblGrid>' + ''.join(rows) + '</a:tbl></a:graphicData></a:graphic></p:graphicFrame>')

def slide_xml(sl, imgs):
    out, i = [], 2
    for e in sl.el:
        k = e[0]
        if k == 'rect': out.append(sp_xml(i, e[1], e[2], e[3], e[4], e[5], e[6], e[7], e[8]))
        elif k == 'text': out.append(sp_xml(i, e[1], e[2], e[3], e[4], e[7], e[8], 1, e[10], tx=e[5], txbox=True, anchor=e[6], pad=e[9]))
        elif k == 'pic':
            if os.path.exists(e[5]):
                imgs.append(e[5]); rid = f'rId{len(imgs) + 1}'
                out.append(f'<p:pic><p:nvPicPr><p:cNvPr id="{i}" name="Imagen {i}" descr="Figura de la diapositiva"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
                           f'<p:spPr><a:xfrm><a:off x="{emu(e[1])}" y="{emu(e[2])}"/><a:ext cx="{emu(e[3])}" cy="{emu(e[4])}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>')
        elif k == 'tab': out.append(tabla_xml(i, *e[1:]))
        i += 1
    return HDR + f'<p:sld {NS}><p:cSld><p:spTree>{GRP}' + ''.join(out) + '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'

def ajustar_imagenes():
    """Las imágenes se escalan con 'contain': se calcula el rectángulo real para no deformarlas."""
    from PIL import Image
    for sl in S:
        for j, e in enumerate(sl.el):
            if e[0] == 'pic' and os.path.exists(e[5]):
                iw, ih = Image.open(e[5]).size; _, x, y, w, h, ruta = e; esc = min(w / iw, h / ih); nw, nh = iw * esc, ih * esc
                sl.el[j] = ('pic', x + (w - nw) / 2, y + (h - nh) / 2, nw, nh, ruta)

def render_pptx(ruta):
    N_ = len(S); imgs_por = []; xmls = []
    for sl in S: im = []; xmls.append(slide_xml(sl, im)); imgs_por.append(im)
    ct = (HDR + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>'
          '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/><Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
          '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/><Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
          + ''.join(f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>' for i in range(1, N_ + 1)) +
          '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>')
    root = rels([('rId1', 'officeDocument', 'ppt/presentation.xml')]).replace('</Relationships>', '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                                                                              f'<Relationship Id="rId3" Type="{REL}/extended-properties" Target="docProps/app.xml"/></Relationships>')
    core = (HDR + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Clasificación de comentarios de clientes de un casino</dc:title><dc:creator>Equipo del proyecto final</dc:creator></cp:coreProperties>')
    app = HDR + f'<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Microsoft Office PowerPoint</Application><Slides>{N_}</Slides></Properties>'
    pres = (HDR + f'<p:presentation {NS}><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst>' + ''.join(f'<p:sldId id="{255 + i}" r:id="rId{1 + i}"/>' for i in range(1, N_ + 1)) +
            f'</p:sldIdLst><p:sldSz cx="{emu(W_IN)}" cy="{emu(H_IN)}"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>')
    pres_rels = rels([('rId1', 'slideMaster', 'slideMasters/slideMaster1.xml')] + [(f'rId{1 + i}', 'slide', f'slides/slide{i}.xml') for i in range(1, N_ + 1)] + [(f'rId{N_ + 2}', 'theme', 'theme/theme1.xml')])
    est = lambda tag, sz: f'<{tag}><a:lvl1pPr algn="l"><a:defRPr sz="{sz}"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mn-lt"/></a:defRPr></a:lvl1pPr></{tag}>'
    master = (HDR + f'<p:sldMaster {NS}><p:cSld><p:bg><p:bgPr>{solid(BG)}<a:effectLst/></p:bgPr></p:bg><p:spTree>{GRP}</p:spTree></p:cSld><p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
              '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles>' + est('p:titleStyle', 4400) + est('p:bodyStyle', 1800) + est('p:otherStyle', 1800) + '</p:txStyles></p:sldMaster>')
    layout = HDR + f'<p:sldLayout {NS} type="blank" preserve="1"><p:cSld name="En blanco"><p:spTree>{GRP}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>'
    theme = (HDR + '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Proyecto final"><a:themeElements><a:clrScheme name="Proyecto final"><a:dk1><a:srgbClr val="17233B"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="55637D"/></a:dk2><a:lt2><a:srgbClr val="F4F7FB"/></a:lt2>'
             '<a:accent1><a:srgbClr val="2D6BDB"/></a:accent1><a:accent2><a:srgbClr val="0F8F6B"/></a:accent2><a:accent3><a:srgbClr val="B86E00"/></a:accent3><a:accent4><a:srgbClr val="C23B3B"/></a:accent4><a:accent5><a:srgbClr val="6F95E6"/></a:accent5><a:accent6><a:srgbClr val="A9B6CF"/></a:accent6><a:hlink><a:srgbClr val="2D6BDB"/></a:hlink><a:folHlink><a:srgbClr val="55637D"/></a:folHlink></a:clrScheme>'
             '<a:fontScheme name="Proyecto final"><a:majorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont><a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
             '<a:fmtScheme name="Office"><a:fillStyleLst>' + '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>' * 3 + '</a:fillStyleLst><a:lnStyleLst>' + '<a:ln w="9525" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln>' * 3 +
             '</a:lnStyleLst><a:effectStyleLst>' + '<a:effectStyle><a:effectLst/></a:effectStyle>' * 3 + '</a:effectStyleLst><a:bgFillStyleLst>' + '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>' * 3 + '</a:bgFillStyleLst></a:fmtScheme></a:themeElements></a:theme>')
    with zipfile.ZipFile(ruta, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, c in [('[Content_Types].xml', ct), ('_rels/.rels', root), ('docProps/core.xml', core), ('docProps/app.xml', app), ('ppt/presentation.xml', pres), ('ppt/_rels/presentation.xml.rels', pres_rels), ('ppt/slideMasters/slideMaster1.xml', master),
                     ('ppt/slideMasters/_rels/slideMaster1.xml.rels', rels([('rId1', 'slideLayout', '../slideLayouts/slideLayout1.xml'), ('rId2', 'theme', '../theme/theme1.xml')])), ('ppt/slideLayouts/slideLayout1.xml', layout),
                     ('ppt/slideLayouts/_rels/slideLayout1.xml.rels', rels([('rId1', 'slideMaster', '../slideMasters/slideMaster1.xml')])), ('ppt/theme/theme1.xml', theme)]: z.writestr(n, c)
        k = 0
        for i, (x, im) in enumerate(zip(xmls, imgs_por), 1):
            z.writestr(f'ppt/slides/slide{i}.xml', x); rl = []
            for j, ruta_img in enumerate(im):
                k += 1; z.writestr(f'ppt/media/image{k}.png', open(ruta_img, 'rb').read()); rl.append((f'rId{j + 2}', 'image', f'../media/image{k}.png'))
            z.writestr(f'ppt/slides/_rels/slide{i}.xml.rels', rels([('rId1', 'slideLayout', '../slideLayouts/slideLayout1.xml')] + rl))

def main():
    capturar_demo(); ajustar_imagenes()
    h = os.path.join(DOCS, 'presentacion_tmp.html'); render_html(h)
    pdf = os.path.join(DOCS, 'Presentacion_Final.pdf')
    if EDGE:
        perfil = tempfile.mkdtemp(); subprocess.run([EDGE, '--headless=new', '--disable-gpu', f'--user-data-dir={perfil}', '--no-pdf-header-footer', '--virtual-time-budget=5000', f'--print-to-pdf={pdf}', 'file:///' + h.replace('\\', '/')], capture_output=True, timeout=240); shutil.rmtree(perfil, ignore_errors=True)
    os.remove(h)
    render_pptx(os.path.join(DOCS, 'Presentacion_Final.pptx'))
    print('Diapositivas:', len(S))

if __name__ == '__main__':
    main()
