# Ficha del dataset: comentarios de clientes de un casino

**Archivo:** `corpus_casinos_2100.csv` · **Generado por:** `src/construir_dataset.py` (semilla 42) · **Diccionario:** `diccionario_datos.csv` · **Exclusiones:** `excluidas.csv`

## Origen y permisos

- **Qué son:** 2.079 reseñas de Google Maps sobre un casino e hipódromo de Buenos Aires, de 2016-12 a 2024-02.
- **Fuente:** las 2.100 filas con casino "No especificado (registro original)" del archivo `train_ampliado_102220.csv` entregado para el curso. Corresponden al dataset académico `comentarios_tp_v2`, que se usó en las clases 1 a 4.
- **Licencia y uso:** uso académico. El dataset no declara una licencia explícita, por lo que **no debe publicarse ni redistribuirse** fuera del curso.

## Población y cobertura

| Aspecto | Dato |
| --- | --- |
| Reseñas | 2.079 (1.455 train, 312 validation, 312 test) |
| Periodo | 2016-12 a 2024-02; por año: 2017 (190), 2018 (376), 2019 (370), 2020 (169), 2021 (266), 2022 (338), 2023 (345), 2024 (24) |
| Longitud | Mediana de 9 palabras; percentil 95 de 44; máximo de 256. 46 reseñas pasan de 64 palabras y 9, de 128 |
| Idioma | Español rioplatense, informal, con errores de ortografía, abreviaturas y emojis |
| Un solo lugar | Todas las reseñas son de un único casino. No hay otras sedes, ni canales (solo Google Maps) |

## Etiquetas

La variable objetivo es el **sentimiento general** de cuatro clases, derivado de 12 aspectos (ver `diccionario_datos.csv`). En los aspectos, `neutral` significa "no se menciona", no una opinión intermedia.

| Clase | Reseñas | Porcentaje |
| --- | --- | --- |
| positiva | 1.222 | 58,8 % |
| negativa (clase crítica: la queja) | 387 | 18,6 % |
| no_mencionado | 339 | 16,3 % |
| mixta | 131 | 6,3 % |

Partición: el test tiene 59 quejas y 19 mixtas, y la validación 57 y 21. Con tan pocos casos, las diferencias pequeñas entre modelos no son concluyentes.

## Auditoría de calidad

| Control | Resultado | Acción |
| --- | --- | --- |
| Nulos y vacíos | 0 | Ninguna |
| Identificadores repetidos | 0 | Ninguna |
| Etiquetas "positive" en inglés | 26 celdas en 20 reseñas | Se cambiaron a "positiva" |
| Reseña fuera de alcance | 1 (id 3754, insulto sin contenido sobre el servicio) | Excluida, como en la auditoría de la clase 3 |
| Textos idénticos con etiquetas contradictorias | 5 grupos (20 reseñas) | Excluidas: no se sabe cuál etiqueta es correcta |
| Textos idénticos con etiquetas iguales | 9 grupos (25 reseñas, p. ej. "Excelente lugar!") | Se conservan, pero un grupo nunca se divide entre particiones |
| Calidad de las etiquetas | La auditoría de la clase 3 revisó 30 reseñas a mano: los aspectos fallaban en 9 y el sentimiento general en 1 | Se usa el sentimiento general; los aspectos se consideran ruidosos |

## Privacidad

- Se buscaron correos, enlaces, teléfonos y firmas. Había 1 teléfono comercial (enmascarado como `[TELEFONO]`) y 1 firma con nombre propio (`[NOMBRE]`).
- Quedan nombres de artistas de recitales (figuras públicas) y lugares; no se consideran datos personales de clientes.
- **Pendiente:** una revisión manual de una muestra para detectar nombres propios que una búsqueda automática no encuentre.
- Los comentarios no traen identificador del autor.

## Partición

70 / 15 / 15, estratificada por sentimiento y **por grupos de texto idéntico** (`StratifiedGroupKFold`, semilla 42). Es una partición aleatoria sobre un solo lugar; no es temporal. Las particiones cubren el mismo rango de años.

## Limitaciones y usos no previstos

1. **Un solo casino.** No se puede afirmar que el modelo funcione en otras cadenas, países o canales.
2. **Pocos datos.** 2.079 reseñas, con 131 mixtas y 387 quejas en total.
3. **Etiquetas por aspecto poco fiables.** Por eso la tarea se define sobre el sentimiento general.
4. **Convención de anotación.** Un elogio general se marca como positivo en `ambiente_restaurate#gastronomia`; la clase `no_mencionado` incluye comentarios generales sin aspecto.
5. **Uso no previsto:** no sirve para evaluar a personas ni empleados individuales, ni para decisiones que afecten a clientes sin revisión humana.
6. **Otras fuentes:** si se agregan datos de otro origen, deben documentarse y evaluarse por separado.
