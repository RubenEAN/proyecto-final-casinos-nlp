# Clasificación de comentarios de un casino: baseline TF-IDF frente a BETO

Proyecto final de **Procesamiento de Lenguaje Natural** · Universidad EAN · Perfiles: Machine Learning, Ciencia de Datos y Gerencia en IA.

**Integrantes:** Edwin Alexander Alfonso Romero · Bresleny Yanira Benavides Cabiche · Rubén Darío Barbosa Brugés · Marissa Tatiana Alvarado Sampedro

**Repositorio:** https://github.com/RubenEAN/proyecto-final-casinos-nlp (privado; el acceso se concede por invitación)

## Qué resuelve

Un sistema que lee un comentario de un cliente de un casino, clasifica su sentimiento general (`negativa`, `mixta`, `positiva`, `no_mencionado`) y decide si lo procesa solo o lo envía a una persona. La **queja** (`negativa`) es la clase crítica: el error más costoso es no detectarla.

La pregunta del proyecto es si un Transformer preentrenado en español (**BETO**) justifica su costo y complejidad frente a un baseline simple (**TF-IDF + regresión logística**), y qué parte de los comentarios se puede decidir sin ayuda humana.

## Estructura

```
proyecto_final_casinos_nlp/
├── data/
│   ├── corpus_casinos_2100.csv     Corpus real (2.079 reseñas; train 1.455 · validación 312 · test 312)
│   ├── diccionario_datos.csv       Descripción de cada columna
│   ├── DATA_CARD.md                Ficha del dataset: origen, auditoría, privacidad y límites
│   ├── excluidas.csv               Reseñas excluidas y el motivo
│   └── casos_robustez.csv          29 frases de prueba (pares de negación, contraste, orden, ortografía...)
├── notebooks/
│   └── Proyecto_Final_Casinos_NLP.ipynb   Notebook principal (EDA, modelos, evaluación, errores, robustez, conclusiones)
├── src/
│   ├── construir_dataset.py        Regenera el corpus desde el CSV original (semilla 42)
│   ├── construir_informe.py        Genera el informe técnico (DOCX y PDF) desde results/
│   ├── construir_presentacion.py   Genera la presentación (PPTX editable y PDF) desde results/
│   ├── construir_guion.py          Genera el guion de la sustentación de 20 minutos (DOCX y PDF)
│   ├── exportar_modelo_demo.py     Exporta el baseline a la demo del navegador
│   └── verificar_demo.py           Comprueba que la demo da lo mismo que Python
├── app/                            Demostración (prototipo)
├── results/                        Tablas y modelos que genera el notebook
├── docs/                           Informe técnico, presentación y matriz de riesgos
├── requirements.txt · requirements-colab.txt · environment.yml · .env.example · LICENSE
```

## Cómo ejecutarlo

**1. En tu computador (CPU, sin GPU).** Requiere Python 3.11.

```bash
python -m venv .venv
.venv\Scripts\activate          # en Linux o Mac: source .venv/bin/activate
pip install -r requirements.txt
cd notebooks
jupyter nbconvert --to notebook --execute --inplace Proyecto_Final_Casinos_NLP.ipynb
```

El notebook se ejecuta de inicio a fin en unos 15 segundos. Entrena y mide los baselines, y la sección de BETO **lee** los resultados guardados en `results/beto_*` si existen.

**2. Entrenar BETO en Google Colab (GPU T4).**
1. Sube `notebooks/Proyecto_Final_Casinos_NLP.ipynb`, `data/corpus_casinos_2100.csv` y `data/casos_robustez.csv` a Colab y activa la GPU.
2. Ejecuta todas las celdas (6 corridas: 2 configuraciones × 3 semillas; unos 10 a 15 minutos).
3. Descarga la carpeta `results` generada (archivos `beto_*.csv` y `beto_latencia.json`) y cópiala en `results/` de este repositorio.
4. Vuelve a ejecutar el notebook en tu computador: ya incluye BETO en las comparaciones.

**3. Regenerar el corpus (opcional).** Requiere el CSV original `train_ampliado_102220.csv` del curso:

```bash
python src/construir_dataset.py --entrada RUTA/train_ampliado_102220.csv --salida data
```

## Reproducibilidad

| Elemento | Valor |
| --- | --- |
| Semilla | 42 (y 43 y 44 para medir la variabilidad de BETO) |
| Partición | 70 / 15 / 15 estratificada por sentimiento y por grupos de texto idéntico |
| Test | Se mide **una sola vez**, solo con los modelos finalistas |
| Versiones | `requirements.txt` (local) y `requirements-colab.txt` (Colab) |
| Hardware de referencia | Baselines: CPU de un portátil con Windows 11, 11 segundos para todo el notebook. BETO: GPU T4 de Colab |
| Credenciales | No se necesitan. `.env.example` solo documenta un token opcional de Hugging Face |
| Rutas | Relativas; el notebook las busca desde `notebooks/` o en `/content` (Colab) |

## Datos

- **Corpus:** las 2.100 reseñas de Google Maps de un casino e hipódromo de Buenos Aires del archivo entregado en el curso; tras la auditoría quedan 2.079.
- **Anonimizados:** se enmascararon un teléfono comercial y una firma con nombre propio. Falta una revisión manual de una muestra.
- **Licencia:** el código usa MIT. Los datos son de **uso académico** y no deben publicarse ni redistribuirse (ver `data/DATA_CARD.md` y `LICENSE`).

## Resultados

Resultados en test (59 quejas; el test se midió una sola vez):

| Modelo | F1 macro | Quejas detectadas sin revisión | Quejas detectadas con revisión humana | Comentarios que pasan a revisión |
| --- | --- | --- | --- | --- |
| Baseline TF-IDF + regresión logística | 0,626 (IC 95 %: 0,554 a 0,690) | 79,7 % (47 de 59) | 93,2 % (55 de 59) | 31,4 % |
| BETO (`beto_128`, media de 3 semillas) | 0,707 ± 0,011 | 86,4 % (51 de 59) | 88,1 % (52 de 59) | 5,1 % |

BETO mejora el F1 en unos 0,08, pero con 59 quejas la diferencia es apenas distinguible del azar (intervalo de la diferencia con la semilla 42: 0,003 a 0,145). La recomendación es un **piloto en modo sombra con ambos modelos** antes de decidir. Los detalles están en `docs/Informe_Tecnico.pdf` y en las tablas de `results/`.

## Límites

Un solo casino y un solo canal; 2.079 reseñas, con 387 quejas y 131 mixtas; etiquetas por aspecto poco fiables (por eso la tarea usa el sentimiento general); el test tiene 59 quejas, así que las diferencias pequeñas no son concluyentes. Las metas de aceptación son provisionales y deben validarse con el cliente.

## Declaración de uso de IA generativa

El equipo usó un asistente de IA (Claude) para generar borradores del código, el notebook y los documentos. El equipo es responsable del contenido: debe verificar el código, las referencias, las cifras y las afirmaciones. Solo las cifras que salen de ejecuciones guardadas en `results/` se presentan como evidencia experimental. No se enviaron datos confidenciales a servicios externos: el corpus es de reseñas públicas de Google Maps y se procesó localmente y en Colab.
