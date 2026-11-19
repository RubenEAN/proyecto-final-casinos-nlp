# Demostración (prototipo)

**Para usarla:** abre `demo.html` con doble clic en cualquier navegador. No necesita instalar nada ni conexión a internet, y ningún comentario sale de tu computador.

## Qué muestra
- **Un comentario:** clase (queja, mixta, positiva o sin opinión), confianza, probabilidad de cada clase, **decisión** (la toma el sistema o pasa a revisión humana con el motivo) y las palabras que más pesaron.
- **Varios comentarios:** pega uno por línea; entrega el resumen agregado (cuántos decide el sistema, cuántos van a revisión, cuántas quejas) y permite descargar un CSV.
- **Confianza mínima:** el control deslizante muestra el costo de pedir más confianza: más casos a revisión humana.
- **Fuera de dominio:** un texto sin relación con las reseñas (por ejemplo, `asdkjh qwerty`) pasa a revisión aunque la confianza sea alta.

## Qué modelo usa
El **baseline** (TF-IDF de palabras y caracteres con regresión logística), copiado a JavaScript. Se verificó con 662 textos (validación, test, frases de robustez y casos límite): diferencia máxima de probabilidad de 6e-6 y ninguna clase distinta respecto de Python. BETO necesita GPU y PyTorch y no corre en un navegador.

## Archivos
| Archivo | Para qué sirve |
| --- | --- |
| `demo.html` | La demo, en un solo archivo (el que se presenta) |
| `plantilla_demo.html` | Diseño de la página |
| `motor_demo.js` | Calcula la predicción en el navegador |
| `modelo_demo.json` | Parámetros del modelo exportados desde Python |
| `verificar_motor.js` | Compara el motor con scikit-learn (lo invoca `src/verificar_demo.py`) |

## Regenerarla y verificarla
Desde la carpeta del repositorio, después de ejecutar el notebook:

```bash
python src/exportar_modelo_demo.py
python src/verificar_demo.py        # requiere Node.js
```

## Para la sustentación (2 minutos)
1. Un comentario claro: *Las máquinas no pagan nunca* → queja con confianza alta; decide el sistema.
2. Uno dudoso: *Muy buena atención, pero las máquinas no pagan nada* → mixta; mostrar las probabilidades.
3. Subir la confianza mínima a 0,70 y repetir: ahora pasa a revisión humana.
4. Texto fuera de dominio: *asdkjh qwerty* → revisión humana por la guardia.
5. Pestaña de varios comentarios: cargar el ejemplo y leer el resumen agregado.
