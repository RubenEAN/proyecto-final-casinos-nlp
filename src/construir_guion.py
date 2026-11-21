"""
Genera el guion de la sustentación de 20 minutos (DOCX y PDF): reparto por rol, texto por diapositiva, guion de la demo,
preguntas probables y lista de verificación. Las cifras salen de results/, igual que el informe y la presentación.

Uso (desde la carpeta del repositorio):
    python src/construir_guion.py
"""
import html, json, os, re, shutil, subprocess, tempfile
import pandas as pd
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES, DATA, DOCS = os.path.join(RAIZ, 'results'), os.path.join(RAIZ, 'data'), os.path.join(RAIZ, 'docs')
EDGE = next((e for e in [r'C:\Program Files\Google\Chrome\Application\chrome.exe', r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe', r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', r'C:\Program Files\Microsoft\Edge\Application\msedge.exe'] if os.path.exists(e)), None)
J = lambda n: json.load(open(os.path.join(RES, n), encoding='utf-8'))
resumen = J('resumen_final.json'); B, BE, N, META = resumen['baseline'], resumen['beto'], resumen['n'], resumen['meta']
ab_b, ab_e = resumen['abstencion'][0], resumen['abstencion'][1]
lat = J('beto_latencia.json'); costo = pd.read_csv(os.path.join(RES, 'costo_latencia.csv')); lat_b = float(costo.iloc[0]['latencia_p95_ms']); cr = pd.read_csv(os.path.join(RES, 'carga_revision_validacion.csv'))
pert = pd.read_csv(os.path.join(RES, 'robustez_perturbaciones.csv')); rob = pd.read_csv(os.path.join(RES, 'robustez_pares.csv'))
df = pd.read_csv(os.path.join(DATA, 'corpus_casinos_2100.csv'), encoding='utf-8-sig')
err_e = pd.read_csv(os.path.join(RES, 'errores_validacion_beto.csv')); err_b = pd.read_csv(os.path.join(RES, 'errores_validacion_baseline.csv'))
assert resumen['decision'] == 'piloto_ambos_modelos', 'El guion se escribió para la recomendación: piloto con ambos modelos'

def f(x, n=3): return f'{x:.{n}f}'.replace('.', ',')
def pc(x, n=1): return f'{x * 100:.{n}f} %'.replace('.', ',')
def miles(x): return f'{int(x):,}'.replace(',', '.')
g = lambda m, k, c: cr[(cr.modelo == m) & (cr.revision_pct == k)].iloc[0][c]
pb = pert[pert.modelo == 'BETO'].set_index('variante')
nq = int((df.sentimiento == 'negativa').sum()); mp = int(df.n_palabras.median())
q_b, q_e = int(round(ab_b['recall_queja_con_revision_test'] * N['quejas_test'])), int(round(ab_e['recall_queja_con_revision_test'] * N['quejas_test']))
q_b_dir = int(round(B['recall_test'] * N['quejas_test']))
amb = int(err_e.causa_probable.str.contains('ambigua').sum())
horas = lambda cob, n_=3000, m_=3: n_ * cob * m_ / 60
dm = BE['f1_test_media'] - B['f1_test']

# --------------------------------------------------------------- contenido
ROLES = {'G': 'Gerencia en IA', 'D': 'Ciencia de Datos', 'M': 'Machine Learning'}
# (n, titulo, rol, bloque, minutos, texto, [transicion])
S = [
 (1, 'Portada', 'G', 'Problema', 0.75,
  "Buenas tardes. Somos el equipo del proyecto, con los perfiles de Machine Learning, Ciencia de Datos y Gerencia en IA. Hoy presentamos un sistema que ayuda al equipo de atención al cliente de un casino a decidir qué comentarios debe leer una persona primero. "
  "Comparamos un modelo simple, TF-IDF con regresión logística, contra BETO, un modelo de lenguaje preentrenado en español, y medimos cuánto trabajo se le puede dejar al sistema sin perder las quejas. "
  "Vamos a ver el problema, los datos, los modelos, una demo, los riesgos y una recomendación.", None),
 (2, 'Una decisión concreta', 'G', 'Problema', 1.25,
  "El usuario es el equipo de experiencia al cliente de una cadena de casinos. La decisión es esta: dado un comentario, ¿lo atiende una persona o se procesa de forma automática? "
  "La clase crítica es la **queja**: no detectarla es el error más costoso. "
  f"Para saber si el sistema sirve fijamos tres metas, todas provisionales y por validar con el cliente: encontrar al menos el **{pc(META['recall_critica'], 0)} de las quejas** contando la revisión humana; que el sistema decida solo al menos el **{pc(META['cobertura'], 0)}** de los comentarios; "
  f"y que BETO mejore el F1 macro en al menos {f(META['mejora_f1'], 2)} sobre el baseline, que es lo que justificaría su costo. "
  "Una aclaración importante: el sistema solo prioriza. No responde a los clientes ni toma decisiones sobre personas.", None),
 (3, 'Cómo funciona', 'G', 'Problema', 1.0,
  "Entra un comentario en español informal, con faltas de ortografía, abreviaturas y emojis. Sale una de cuatro clases, la probabilidad de cada una y una acción: decide el sistema o pasa a revisión humana. "
  "El sistema **no decide solo en dos casos**: si la confianza es menor que un umbral, o si el texto no se parece a las reseñas con las que se entrenó. "
  "Esa regla de abstención es la pieza que convierte un clasificador en una herramienta que se puede usar sin que el error recaiga sobre los clientes. "
  "Los dos modelos que comparamos son intercambiables dentro de este mismo flujo.", "Ahora el perfil de Ciencia de Datos les cuenta de dónde salen los datos."),
 (4, 'Los datos', 'D', 'Datos', 1.0,
  f"El corpus son 2.100 reseñas de Google Maps de un casino e hipódromo de Buenos Aires, entre {df.periodo.min()[:4]} y {df.periodo.max()[:4]}. Tras la auditoría quedan **{miles(len(df))}**. "
  f"De ellas, {nq} son quejas, el {pc(nq / len(df), 0)}: la clase crítica es minoritaria. La mediana es de {mp} palabras, o sea textos cortos e informales. "
  "Cada reseña viene etiquetada en 12 aspectos, como atención, calidad y precio; a partir de ahí derivamos un sentimiento general en cuatro clases: negativa, mixta, positiva y no mencionado. "
  "Es un dataset académico del curso, sin licencia declarada: lo usamos solo con fines académicos y no lo publicamos.", None),
 (5, 'Auditoría y partición', 'D', 'Datos', 1.0,
  "Antes de modelar auditamos los datos. Corregimos 26 celdas escritas en inglés, excluimos una reseña fuera de alcance y cinco grupos de textos idénticos con etiquetas contradictorias, y enmascaramos un teléfono y una firma con nombre propio. "
  "Partimos 70, 15 y 15 estratificando por clase y **por grupos de texto idéntico**, para que una misma reseña nunca esté en entrenamiento y en prueba: así evitamos la fuga de información. "
  f"El límite que debemos decir de entrada: el conjunto de prueba tiene solo **{N['quejas_test']} quejas y {N['mixtas_test']} mixtas**, así que las diferencias pequeñas entre modelos no son concluyentes. "
  "Además, las etiquetas por aspecto son poco fiables: fallaban en 9 de 30 reseñas que revisamos a mano. Por eso la tarea usa el sentimiento general.", None),
 (6, 'Qué dicen los datos', 'D', 'Datos', 1.0,
  "La clase positiva es el 59 %. Un modelo que siempre respondiera positiva acertaría casi 6 de cada 10 sin aprender nada; por eso la métrica principal es el **F1 macro**, que da el mismo peso a las cuatro clases. "
  f"El 98 % de los textos tiene 64 palabras o menos. Las quejas son más largas que las positivas: la mediana es de 14 palabras frente a 9, y la de las mixtas es de 21. "
  "El segundo límite: es un solo casino y un solo canal. Lo que concluyamos no se extiende a otros lugares sin repetir la prueba.", "Con esto, el perfil de Machine Learning explica cómo comparamos los modelos."),
 (7, 'Cómo comparamos', 'M', 'Modelado', 1.5,
  "Comparamos dos enfoques. El **baseline** es TF-IDF de palabras y caracteres con regresión logística; no es una red neuronal, es la vara de medir. Probamos 6 variantes y elegimos con validación. "
  "El segundo es **BETO**, un BERT preentrenado en español que ajustamos con las reseñas: dos configuraciones, con tres semillas cada una, en una GPU de Colab. "
  "Cuidamos que la comparación sea justa: mismos datos y métricas, todo se ajusta solo con entrenamiento, el umbral se elige con validación y **el conjunto de prueba se mide una sola vez**. "
  "Como la prueba es pequeña, damos intervalos de confianza del 95 % con bootstrap y probamos robustez con frases en pares, textos fuera de dominio y perturbaciones.", None),
 (8, 'Resultado del baseline', 'M', 'Modelado', 1.5,
  f"El baseline logra un F1 macro de **{f(B['f1_test'])}** en prueba, con un intervalo de {f(B['ic_f1'][0])} a {f(B['ic_f1'][1])}. Ojo con la tabla: son las seis variantes en validación, solo para elegir la mejor; los recuadros de arriba son el resultado en prueba. "
  f"Veamos las quejas. De {N['quejas_test']} quejas en prueba, el modelo etiqueta {q_b_dir} como queja, el {pc(B['recall_test'], 0)}. Otras {q_b - q_b_dir} pasan a una persona porque el modelo no está seguro. Eso da **{q_b} de {N['quejas_test']}, el {pc(ab_b['recall_queja_con_revision_test'])}**, y cumple la meta de 0,90. "
  f"Se nos escapan {N['quejas_test'] - q_b}, que el modelo clasificó con seguridad como otra cosa. Y para lograrlo se revisa casi un tercio de los comentarios: el sistema decide solo el {pc(ab_b['cobertura_test'])}, por debajo de la meta del 75 %. "
  f"La clase más difícil es la mixta, con F1 de {f(B['f1_mixta_test'])}, y en prueba solo hay {N['mixtas_test']}.", None),
 (9, 'BETO frente al baseline', 'M', 'Modelado', 2.0,
  f"BETO obtiene un F1 macro medio de **{f(BE['f1_test_media'])}**, con una desviación de {f(BE['f1_test_std'])} entre semillas: {f(dm)} más que el baseline. "
  f"Con la corrida de la semilla 42, la diferencia es de {f(BE['diff'])} y su intervalo va de **{f(BE['diff_ic'][0])} a {f(BE['diff_ic'][1])}**. Ese intervalo apenas excluye el cero y es muy ancho: BETO probablemente mejora, pero con {N['quejas_test']} quejas no podemos precisar cuánto. "
  f"Los dos quedan en puntos de operación distintos. BETO decide solo el {pc(ab_e['cobertura_test'], 0)} y deja el {pc(ab_e['revision_test'], 0)} a revisión; el baseline deja el {pc(ab_b['revision_test'], 0)}. "
  f"Con esa revisión, BETO encuentra el {pc(ab_e['recall_queja_con_revision_test'])} de las quejas, {q_e} de {N['quejas_test']}: {q_b - q_e} menos que el baseline, bajo la meta de 0,90, aunque esa diferencia no es concluyente. "
  f"El costo de BETO: unos 110 millones de parámetros y una GPU para responder en cerca de {lat['gpu_p95']:.0f} milisegundos; en CPU tarda unos {lat['cpu_p95']:.0f}.", None),
 (10, 'Dónde se equivoca', 'D', 'Resultados', 1.0,
  f"Miremos los errores en validación: el baseline se equivoca en {len(err_b)} de {N['validation']} reseñas y BETO en {len(err_e)}. "
  f"En BETO, **{amb} de {len(err_e)} errores** son confusiones entre positiva y no mencionado: son elogios generales, como \"excelente pasatiempo\", que a veces se anotaron como positivos y a veces no. "
  "Es un problema de etiquetas, no de modelo. Se arregla con una guía de anotación, no con un modelo más grande. Las causas que mostramos las asigna una regla automática y el equipo debe revisarlas.", None),
 (11, 'Cuánto decide solo el sistema', 'D', 'Resultados', 1.0,
  "Como cada modelo usa un umbral distinto, comparar sus recalls directamente confunde. Entonces fijamos **la misma carga de revisión** y lo medimos en validación. "
  f"Con el 5 % de casos a revisión, BETO encuentra {int(g('BETO', 5, 'quejas_encontradas'))} de {int(g('BETO', 5, 'quejas_totales'))} quejas y el baseline {int(g('Baseline', 5, 'quejas_encontradas'))}; el baseline necesita cerca del 20 % para igualarlo. "
  f"Con una carga alta, del 31 %, el baseline gana por {int(g('Baseline', 31, 'quejas_encontradas') - g('BETO', 31, 'quejas_encontradas'))} quejas. Y en todos los niveles BETO acierta más en lo que decide solo. "
  "Son 57 quejas y una sola corrida de BETO: es un indicio que el piloto debe confirmar.", None),
 (12, 'Robustez', 'D', 'Resultados', 1.0,
  "Probamos 35 casos escritos por nosotros. El baseline acierta todos los de contraste, pero falla en orden de palabras y en doble negación, porque TF-IDF no ve el orden. BETO sí acierta el orden, 2 de 2. "
  f"Pero BETO tiene una fragilidad: en MAYÚSCULAS su F1 macro cae de {f(pb.loc['original', 'f1_macro'])} a **{f(pb.loc['MAYÚSCULAS', 'f1_macro'])}**, y cambia el {str(pb.loc['MAYÚSCULAS', 'cambian_pct']).replace('.', ',')} % de las predicciones. "
  "Pasar el texto a minúsculas debería corregirlo, pero falta medirlo. "
  "Con textos sin sentido, el baseline les asigna una clase con 56 % a 66 % de confianza, sobre el umbral, así que la confianza sola los dejaría pasar; la **guardia de vocabulario** los envía a revisión, 6 de 6, y solo marca el 3,5 % de las reseñas reales.",
  "Y ahora el perfil de Machine Learning nos muestra el sistema funcionando."),
 (13, 'Demostración', 'M', 'Demo', 2.0, 'Ver el guion de la demo en la sección 4.', "Volvemos a las diapositivas: el perfil de Gerencia IA cierra con costos, riesgos y la recomendación."),
 (14, 'Costo y caso de valor', 'G', 'Modelado', 1.0,
  f"El baseline pesa menos de 1 megabyte y responde en unos {lat_b:.0f} milisegundos en una CPU común. BETO tiene unos 110 millones de parámetros y necesita GPU para ser rápido. "
  f"Un ejemplo ilustrativo: con 3.000 comentarios al mes y 3 minutos por comentario, el baseline ahorra unas {horas(ab_b['cobertura_test']):.0f} horas de lectura al mes y BETO unas {horas(ab_e['cobertura_test']):.0f}. "
  "Son supuestos nuestros: no tenemos el volumen ni el costo por hora reales del cliente. Y el valor desaparece si el recall de quejas baja de 0,90.", None),
 (15, 'Riesgos y gobierno', 'G', 'Riesgos', 2.0,
  "La matriz de riesgos del archivo de Excel tiene 17 riesgos con su control. Los principales: quejas no detectadas, revisión por encima de la capacidad del equipo, errores con confianza alta o fuera de dominio, etiquetas ambiguas con muestra pequeña, licencia y uso de los datos, y uso en otro lugar sin probar. "
  "Para controlarlos: revisión humana, modo sombra, calibración, auditoría y la guardia de vocabulario. "
  "El gobierno: el dueño del modelo es Gerencia IA, con un suplente de Machine Learning. Se monitorean ocho indicadores, entre ellos el recall auditado, la proporción enviada a revisión y la confianza mediana. "
  "El modelo se **suspende** si el recall auditado baja de 0,90, si la revisión supera la capacidad del equipo o si cambia el tipo de comentarios; el respaldo es el baseline con revisión humana. "
  "En privacidad, enmascaramos teléfonos y nombres, y todavía falta revisar a mano una muestra.", None),
 (16, 'Recomendación', 'G', 'Recomendación', 1.0,
  "Nuestra recomendación es un **piloto en modo sombra con ambos modelos**: corren en paralelo sin decidir nada, así que probar los dos no añade riesgo. BETO es el candidato principal porque necesita mucha menos revisión para un recall parecido; el baseline es el respaldo. "
  f"Para elegir BETO pedimos tres condiciones: un recall de quejas de al menos {f(META['recall_critica'], 2)} en una muestra auditada; medir la versión en minúsculas frente a las MAYÚSCULAS; y contar con GPU o aceptar unos {lat['cpu_p95']:.0f} milisegundos en CPU. "
  "Si no se cumplen, seguimos con el baseline. Antes falta validar las metas con el cliente, confirmar la licencia y revisar los datos personales. Gracias; quedamos atentos a sus preguntas.", None),
]
EXTRA = {8: ("**Si preguntan por 0,646 y 0,626:** es el mismo modelo en dos conjuntos distintos. 0,646 es en validación, con el que se eligió entre seis variantes; 0,626 es en prueba, medido una sola vez. La diferencia está dentro del intervalo de confianza. "
             f"**Si preguntan por el {pc(ab_b['recall_queja_con_revision_test'], 0)}:** supone que la persona que revisa reconoce las quejas que le llegan; de los {int(round(ab_b['revision_test'] * N['test']))} comentarios que van a revisión, solo unos 18 son quejas, y ese es el costo de revisar.")}
DEMO = [
 ('0:00', 'Cambiar al navegador con `app/demo.html` ya abierto (zoom al 125 %).', '"Esta es la demo: un solo archivo HTML que funciona sin internet y sin enviar datos a ningún servidor. Pega un comentario y devuelve la decisión."'),
 ('0:15', 'Escribir **Las máquinas no pagan nunca** y pulsar Analizar.', '"Una queja clara: lo clasifica como queja con 95 % de confianza y **lo decide el sistema**. Abajo muestra las palabras que empujan la decisión."'),
 ('0:35', 'Escribir **Muy buena atención, pero las máquinas no pagan nada**.', '"Una reseña mixta: elogio y queja a la vez. La clasifica como mixta con 63 %. Este es el caso difícil del que hablamos."'),
 ('0:55', 'Mover el control de confianza mínima de 0,50 a **0,70** y volver a analizar el mismo texto.', '"Si el equipo decide ser más exigente, este mismo comentario ya no lo decide el sistema: pasa a revisión humana por confianza baja. El umbral lo fija el equipo según su capacidad."'),
 ('1:20', 'Volver el control a 0,50. Escribir **asdkjh qwerty**.', '"Un texto sin sentido. El modelo igual le da 60 % a una clase, pero la guardia de vocabulario ve que no se parece a las reseñas y lo envía a revisión humana. La confianza sola no lo habría detenido."'),
 ('1:45', 'Cerrar y volver a las diapositivas.', '"Eso es todo: clase, confianza, motivo y acción. En la pestaña de varios comentarios se puede procesar una lista y descargar el resultado."'),
]
PREG = [
 ('¿Qué decisión mejora el sistema y quién la toma?', 'Mejora la priorización: qué comentario atiende primero una persona y cuál se procesa de forma automática. La toma el equipo de experiencia al cliente. El sistema solo prioriza: no responde a los clientes ni decide sobre personas.'),
 ('¿Qué datos no debería procesar el sistema?', 'Datos personales como nombres, teléfonos o identificadores del autor, que enmascaramos o no usamos. No sirve para evaluar a personas ni empleados individuales, ni para decisiones que afecten a clientes sin revisión humana, ni para otros canales o lugares sin volver a probarlo.'),
 ('¿Cómo se monitoreará el drift?', 'Con seis indicadores sin etiquetas, que se revisan con una alerta: la proporción enviada a revisión, la confianza mediana, los comentarios marcados por la guardia de vocabulario, la proporción de quejas y la longitud mediana; y con el recall de quejas auditado sobre una muestra. Dos alertas seguidas, o 500 comentarios nuevos anotados, disparan el reentrenamiento.'),
 ('¿BETO es mejor que el baseline?', f"En F1 macro probablemente sí: {f(dm)} más en promedio de 3 semillas. Pero el intervalo de la diferencia va de {f(BE['diff_ic'][0])} a {f(BE['diff_ic'][1])}: apenas excluye el cero. Con {N['quejas_test']} quejas en prueba no podemos precisar cuánto. Por eso proponemos confirmarlo en un piloto."),
 ('¿Por qué no recomiendan simplemente BETO, si es mejor?', f"Porque con el umbral elegido en validación no cumple solo la meta de recall en prueba ({pc(ab_e['recall_queja_con_revision_test'])} frente a 0,90), es frágil ante MAYÚSCULAS y exige GPU. Si esas condiciones se cumplen en el piloto, BETO pasa a ser el principal."),
 ('¿Por qué no recomiendan el baseline, si cumple la meta de recall?', f"Lo cumple pasando a revisión el {pc(ab_b['revision_test'], 0)} de los comentarios, y no cumple la meta de cobertura del 75 %. BETO necesita mucho menos revisión para un recall parecido: con 5 % de revisión encuentra {int(g('BETO', 5, 'quejas_encontradas'))} de {int(g('BETO', 5, 'quejas_totales'))} quejas en validación. Lo que decide es cuánta revisión puede atender el equipo."),
 ('¿Cómo evitaron la fuga de información?', 'Partimos por grupos de texto idéntico: una reseña repetida nunca queda en entrenamiento y en prueba a la vez. El umbral se eligió con validación y el conjunto de prueba se midió una sola vez.'),
 ('¿Por qué el conjunto de prueba es tan pequeño?', 'Porque el corpus del ejercicio tiene 2.100 reseñas. Por eso reportamos intervalos de confianza y no sacamos conclusiones sobre diferencias pequeñas.'),
 ('¿Cómo se eligió el umbral de confianza?', 'En validación: la regla que menos casos manda a revisión y aún encuentra el 90 % de las quejas. Quedó en 0,50 para los dos modelos. En el piloto conviene reajustarlo con una muestra auditada.'),
 ('¿Qué pasa con textos que no son del casino?', 'La confianza sola no los detiene: el baseline les da entre 56 % y 66 %. La guardia de vocabulario los envía a revisión, 6 de 6 en nuestras pruebas, y solo marca el 3,5 % de las reseñas reales.'),
 ('¿Probaron con un modelo de lenguaje grande o con otros Transformers?', 'No. Comparamos el baseline con BETO, que es el modelo en español visto en clase. Otros modelos quedan como siguiente experimento una vez haya más datos anotados.'),
 ('¿Qué privacidad tienen los datos?', 'Usamos solo texto y fecha, sin identificador del autor, y enmascaramos un teléfono y una firma. Falta revisar a mano una muestra por si queda algún nombre propio. El dataset es de uso académico y no se publica.'),
 ('¿Cuál es el siguiente paso con más impacto?', 'Más reseñas anotadas con una guía clara, sobre todo para distinguir positiva de no mencionado, que es la mitad de los errores. Después, repetir la comparación.'),
]
CHECK = ['Abrir `app/demo.html` en el navegador antes de empezar y probar los tres textos de la demo.', 'Tener la presentación en modo presentador y el PDF de respaldo (`docs/Presentacion_Final.pdf`) abierto por si falla PowerPoint.',
         'Cronometrar un ensayo completo: debe cerrar en 20 minutos o menos; si se pasa, cortar las frases marcadas como opcionales en el texto de cada persona.', 'Acordar quién responde cada tipo de pregunta: datos (Ciencia de Datos), modelos y demo (Machine Learning), riesgos y negocio (Gerencia IA).',
         'No leer las diapositivas: cada una tiene una cifra principal; decirla y explicarla con el texto del guion.']

# --------------------------------------------------------------- estructura
doc_items = []
def H1(t): doc_items.append(('h1', t))
def H2(t): doc_items.append(('h2', t))
def Pp(t): doc_items.append(('p', t))
def Q(t): doc_items.append(('q', t))
def TAB(cols, rows, w=None): doc_items.append(('tab', cols, rows, w))
def BUL(xs): doc_items.append(('bul', xs))
def NOTE(t): doc_items.append(('note', t))

H1('Guion de la sustentación · 20 minutos')
Pp('Clasificación de comentarios de clientes de un casino: baseline TF-IDF frente a BETO, con abstención y revisión humana. Proyecto final de Procesamiento de Lenguaje Natural, Universidad EAN.')
NOTE('Las cifras salen de results/ (las mismas del informe y la presentación). El reparto por rol es una propuesta: el equipo debe ajustarlo y decidir quién presenta cada bloque.')
H2('1. Reparto por bloques y por rol')
acum, filas = 0.0, []
for n, t, r, bl, mi, _, _ in S:
    acum += mi; filas.append([n, t, bl, ROLES[r], f'{int(mi)}:{int(round((mi % 1) * 60)):02d}', f'{int(acum)}:{int(round((acum % 1) * 60)):02d}'])
TAB(['Diap.', 'Título', 'Bloque', 'Rol que presenta', 'Minutos', 'Acumulado'], filas, [1.2, 5.6, 3.2, 3.8, 1.8, 2.2])
tot = {r: sum(mi for _, _, rr, _, mi, _, _ in S if rr == r) for r in ROLES}; blq = {}
for _, _, _, bl, mi, _, _ in S: blq[bl] = blq.get(bl, 0) + mi
TAB(['Rol', 'Minutos', 'Diapositivas'], [[ROLES[r], f'{tot[r]:g}', ', '.join(str(n) for n, _, rr, *_ in S if rr == r)] for r in ROLES], [5, 2.5, 8])
Pp('**Distribución por bloques pedida en los lineamientos:** problema ' + f"{blq['Problema']:g}" + ' min, datos ' + f"{blq['Datos']:g}" + ', modelado ' + f"{blq['Modelado']:g}" + ', resultados ' + f"{blq['Resultados']:g}" + ', demo ' + f"{blq['Demo']:g}" + ', riesgos ' + f"{blq['Riesgos']:g}" + ', recomendación ' + f"{blq['Recomendación']:g}" + f". Total: {sum(blq.values()):g} minutos. El costo y el caso de valor (diapositiva 14) cuentan dentro del bloque de modelado y se presentan después de la demo. La diapositiva 17 (anexo) no se presenta: queda de respaldo para preguntas.")
Pp('**Si el equipo tiene cuatro voces:** el bloque de Machine Learning se puede repartir. Una persona presenta las diapositivas 7 a 9 (modelado) y otra hace la demostración (13), que es práctica y se beneficia de un ritmo distinto.')

H2('2. Cómo usar el guion')
BUL(['Cada diapositiva tiene una cifra principal. Se dice la cifra y se explica con el texto de abajo; no se lee la diapositiva.', 'El texto está escrito para hablarse a unas 130 palabras por minuto. Al lado de cada título aparece el tiempo y el acumulado.',
     'La última línea de algunas diapositivas es la transición hacia la persona que sigue.', 'Con solo 20 minutos no hay margen: si el ensayo se pasa, conviene quitar detalles y no acelerar la lectura.'])
H2('3. Guion por diapositiva')
cumm = 0.0
for n, t, r, bl, mi, txt, tr in S:
    cumm += mi
    H2(f'Diapositiva {n} · {t}')
    doc_items.append(('meta', f'{ROLES[r]} · {bl} · {int(mi)}:{int(round((mi % 1) * 60)):02d} min · acumulado {int(cumm)}:{int(round((cumm % 1) * 60)):02d}'))
    if n == 13: Pp('Ver el guion paso a paso en la sección 4. Antes de la diapositiva: avisar "les muestro el sistema funcionando" y cambiar a la ventana del navegador.')
    else: Q(txt)
    if n in EXTRA: Pp(EXTRA[n])
    if tr: Pp('**Transición:** ' + tr)
H1('4. Guion de la demostración (2 minutos)')
Pp('**Preparación:** abrir `app/demo.html` en el navegador (funciona sin internet), dejarlo en la pestaña "Un comentario" y con el control de confianza en 0,50. Los resultados de abajo son los reales de esta versión de la demo.')
TAB(['Tiempo', 'Qué hacer', 'Qué decir'], [[a, b, c] for a, b, c in DEMO], [1.6, 6.2, 9.2])
NOTE('Plan B si la demo falla: volver a la diapositiva 13, que tiene capturas de los tres casos (un comentario, texto sin sentido y varios comentarios), y narrar con ellas. La demo es un prototipo del baseline y decide con la misma regla que el informe; no ejecuta BETO.')
H1('5. Preguntas probables')
for q_, a_ in PREG:
    doc_items.append(('qa', q_, a_))
H1('6. Lista de verificación antes de presentar')
BUL(CHECK)

# --------------------------------------------------------------- DOCX
NAVY = RGBColor(0x1F, 0x3A, 0x6E); GRIS = RGBColor(0x55, 0x63, 0x7D)
def runs(par, t, size=None, color=None, italic=False):
    for i, s in enumerate(re.split(r'\*\*', t)):
        if not s: continue
        for j, s2 in enumerate(re.split(r'`', s)):
            if not s2: continue
            r = par.add_run(s2); r.bold = (i % 2 == 1); r.italic = italic
            if j % 2 == 1: r.font.name = 'Consolas'
            if size: r.font.size = Pt(size)
            if color: r.font.color.rgb = color
def shade(cell, hexcolor):
    pr = cell._tc.get_or_add_tcPr(); sh = OxmlElement('w:shd'); sh.set(qn('w:val'), 'clear'); sh.set(qn('w:color'), 'auto'); sh.set(qn('w:fill'), hexcolor); pr.append(sh)

def to_docx(ruta):
    d = Document(); sec = d.sections[0]; sec.left_margin = sec.right_margin = Cm(2.0); sec.top_margin = sec.bottom_margin = Cm(2.0)
    st = d.styles['Normal']; st.font.name = 'Calibri'; st.font.size = Pt(11)
    for it in doc_items:
        k = it[0]
        if k == 'h1': h = d.add_heading(level=1); runs(h, it[1], 20, NAVY)
        elif k == 'h2': h = d.add_heading(level=2); runs(h, it[1], 14, NAVY)
        elif k == 'p': runs(d.add_paragraph(), it[1])
        elif k == 'meta': runs(d.add_paragraph(), it[1], 10, GRIS, italic=True)
        elif k == 'q':
            p = d.add_paragraph(); p.paragraph_format.left_indent = Cm(0.6); p.paragraph_format.space_after = Pt(6); runs(p, it[1], 11.5)
        elif k == 'note':
            t = d.add_table(rows=1, cols=1); t.alignment = WD_TABLE_ALIGNMENT.CENTER; c = t.rows[0].cells[0]; shade(c, 'FFF3DC'); c.paragraphs[0].text = ''; runs(c.paragraphs[0], it[1], 10); d.add_paragraph()
        elif k == 'bul':
            for x in it[1]: runs(d.add_paragraph(style='List Bullet'), x)
        elif k == 'qa':
            p = d.add_paragraph(); runs(p, '**' + it[1] + '**'); p.paragraph_format.space_after = Pt(0); runs(d.add_paragraph(), it[2])
        elif k == 'tab':
            cols, rows, w = it[1], it[2], it[3]; t = d.add_table(rows=1, cols=len(cols)); t.style = 'Table Grid'; t.alignment = WD_TABLE_ALIGNMENT.CENTER
            for i, c in enumerate(cols):
                cell = t.rows[0].cells[i]; shade(cell, '1F3A6E'); cell.paragraphs[0].text = ''; r = cell.paragraphs[0].add_run(str(c)); r.bold = True; r.font.size = Pt(10); r.font.color.rgb = RGBColor(255, 255, 255)
            for ri, fila in enumerate(rows):
                cells = t.add_row().cells
                for i, c in enumerate(fila):
                    cells[i].paragraphs[0].text = ''; runs(cells[i].paragraphs[0], str(c), 10)
                    if ri % 2 == 1: shade(cells[i], 'F4F7FB')
            if w:
                for row in t.rows:
                    for i, cell in enumerate(row.cells): cell.width = Cm(w[i])
            d.add_paragraph()
    d.save(ruta)

# --------------------------------------------------------------- HTML -> PDF (revisión visual)
def inline(t): return re.sub(r'`([^`]+)`', r'<code>\1</code>', re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html.escape(t)))
def to_html(ruta):
    out = ['<!doctype html><html lang="es"><head><meta charset="utf-8"><style>@page{size:A4;margin:18mm}body{font-family:Calibri,"Segoe UI",sans-serif;font-size:11pt;color:#17233B;line-height:1.35}h1{font-size:20pt;color:#1F3A6E;margin:14px 0 6px}h2{font-size:14pt;color:#1F3A6E;margin:16px 0 4px;break-after:avoid}'
           '.meta{font-size:10pt;color:#55637D;font-style:italic;margin:0 0 4px}.q{margin:0 0 8px 14px}.note{background:#FFF3DC;padding:7px 10px;font-size:10pt;margin:8px 0}table{border-collapse:collapse;width:100%;margin:8px 0;font-size:10pt}th{background:#1F3A6E;color:#fff;text-align:left;padding:4px 6px}td{border:1px solid #D5DDEA;padding:4px 6px;vertical-align:top}tr:nth-child(even) td{background:#F4F7FB}code{font-family:Consolas,monospace}.qa b{display:block}.qa{margin:6px 0 8px}</style></head><body>']
    for it in doc_items:
        k = it[0]
        if k in ('h1', 'h2'): out.append(f'<{k}>{inline(it[1])}</{k}>')
        elif k == 'p': out.append(f'<p>{inline(it[1])}</p>')
        elif k == 'meta': out.append(f'<p class="meta">{inline(it[1])}</p>')
        elif k == 'q': out.append(f'<p class="q">{inline(it[1])}</p>')
        elif k == 'note': out.append(f'<div class="note">{inline(it[1])}</div>')
        elif k == 'bul': out.append('<ul>' + ''.join(f'<li>{inline(x)}</li>' for x in it[1]) + '</ul>')
        elif k == 'qa': out.append(f'<div class="qa"><b>{inline(it[1])}</b>{inline(it[2])}</div>')
        elif k == 'tab':
            out.append('<table><tr>' + ''.join(f'<th>{inline(str(c))}</th>' for c in it[1]) + '</tr>' + ''.join('<tr>' + ''.join(f'<td>{inline(str(c))}</td>' for c in fila) + '</tr>' for fila in it[2]) + '</table>')
    open(ruta, 'w', encoding='utf-8').write(''.join(out) + '</body></html>')

def main():
    # verificación del ritmo: palabras por minuto de cada texto
    print('Diap. | min | palabras | palabras/min')
    tw = 0
    for n, t, r, bl, mi, txt, tr in S:
        if n == 13: continue
        w = len(re.findall(r'\w+', txt + ' ' + (tr or ''))); tw += w; print(f'{n:>5} | {mi:>4} | {w:>8} | {w / mi:>6.0f}')
    print('Total palabras (sin demo):', tw, '· minutos sin demo:', sum(s[4] for s in S) - 2)
    docx_p = os.path.join(DOCS, 'Guion_Sustentacion.docx'); to_docx(docx_p)
    if EDGE:
        h = os.path.join(DOCS, 'guion_tmp.html'); to_html(h); perfil = tempfile.mkdtemp()
        subprocess.run([EDGE, '--headless=new', '--disable-gpu', f'--user-data-dir={perfil}', '--no-pdf-header-footer', f'--print-to-pdf={os.path.join(DOCS, "Guion_Sustentacion.pdf")}', 'file:///' + h.replace(chr(92), '/')], capture_output=True, timeout=240)
        shutil.rmtree(perfil, ignore_errors=True); os.remove(h)

if __name__ == '__main__':
    main()
