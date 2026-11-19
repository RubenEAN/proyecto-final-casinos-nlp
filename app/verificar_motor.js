// Compara las probabilidades del motor de la demo con las de scikit-learn. Lo invoca src/verificar_demo.py
const fs = require('fs'), path = require('path');
const { Motor } = require('./motor_demo.js');
const modelo = JSON.parse(fs.readFileSync(path.join(__dirname, 'modelo_demo.json'), 'utf-8'));
const esp = JSON.parse(fs.readFileSync(process.argv[2], 'utf-8'));
const motor = new Motor(modelo);
let maxDiff = 0, peor = '', difClase = 0;
esp.textos.forEach((t, i) => {
  const { probs } = motor.probabilidades(t);
  const d = Math.max(...probs.map((p, k) => Math.abs(p - esp.probs[i][k])));
  if (d > maxDiff) { maxDiff = d; peor = t; }
  const kj = probs.indexOf(Math.max(...probs)), kp = esp.probs[i].indexOf(Math.max(...esp.probs[i]));
  if (kj !== kp) difClase++;
});
console.log(`Textos comparados: ${esp.textos.length}`);
console.log(`Diferencia máxima de probabilidad (JavaScript contra Python): ${maxDiff.toExponential(2)}`);
console.log(`Textos con clase distinta: ${difClase}`);
if (maxDiff > 1e-3 || difClase > 0) { console.error('FALLA: el navegador no reproduce el modelo. Peor caso:', JSON.stringify(peor)); process.exit(1); }
console.log('OK: la demo reproduce el modelo de Python.');
