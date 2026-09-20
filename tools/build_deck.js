const pptx = require("pptxgenjs");
// Rutas relativas al repositorio: funciona en cualquier máquina (npm install pptxgenjs)
const RUTA = require("path");
const path = RUTA.join(__dirname, "..", "reports", "figures") + RUTA.sep;
const p = new pptx();
p.layout = "LAYOUT_WIDE";                       // 13.3 x 7.5
const VERDE = "2C5F2D", MUSGO = "97BC62", TIERRA = "B85042", CREMA = "F5F5F5",
      TINTA = "1A1A1A", GRIS = "5A5A55", BLANCO = "FFFFFF";
const TIT = "Cambria", CUERPO = "Calibri";

const titulo = (s, texto, sub) => {
  s.addText(texto, {x:0.6, y:0.38, w:12.1, h:0.7, fontSize:34, bold:true, color:VERDE, fontFace:TIT, isTextBox:true});
  if (sub) s.addText(sub, {x:0.6, y:1.06, w:12.1, h:0.42, fontSize:15, color:GRIS, fontFace:CUERPO, isTextBox:true});
};
const pie = (s, texto) => s.addText(texto, {x:0.6, y:6.95, w:12.1, h:0.3, fontSize:10, color:GRIS, italic:true, fontFace:CUERPO, isTextBox:true});
const tarjeta = (s, x, y, w, h, relleno) => s.addShape(p.ShapeType.roundRect, {x, y, w, h, fill:{color:relleno||CREMA}, rectRadius:0.12, line:{color:"E4E4DE", width:1}});
const stat = (s, x, y, w, valor, etiqueta, color) => {
  tarjeta(s, x, y, w, 1.55);
  s.addText(valor, {x:x+0.2, y:y+0.16, w:w-0.4, h:0.72, fontSize:40, bold:true, color:color||VERDE, fontFace:TIT, isTextBox:true});
  s.addText(etiqueta, {x:x+0.2, y:y+0.92, w:w-0.4, h:0.55, fontSize:12.5, color:GRIS, fontFace:CUERPO, isTextBox:true});
};
const tabla = (s, filas, opciones) => s.addTable(filas, Object.assign({
  x:0.6, w:12.1, fontFace:CUERPO, fontSize:13.5, color:TINTA, border:{type:"solid", color:"E4E4DE", pt:1},
  rowH:0.4, valign:"middle", autoPage:false}, opciones));
const encabezado = (t) => ({text:t, options:{bold:true, color:BLANCO, fill:{color:VERDE}, fontSize:13}});

// ---------------------------------------------------------------- 1. Portada
let s = p.addSlide(); s.background = {color:VERDE};
s.addText("Sistema de scoring y política de crédito", {x:0.9, y:2.25, w:11.5, h:1.0, fontSize:42, bold:true, color:BLANCO, fontFace:TIT, isTextBox:true});
s.addText("Caso 15 · Caja Rural 360 · Microcrédito rural amortizable sin garantía", {x:0.9, y:3.3, w:11.5, h:0.5, fontSize:19, color:MUSGO, fontFace:CUERPO, isTextBox:true});
s.addShape(p.ShapeType.roundRect, {x:0.9, y:4.3, w:6.2, h:1.15, fill:{color:"24502A"}, rectRadius:0.12, line:{color:"3C7340", width:1}});
s.addText("Recomendación: aprobar con PD calibrada ≤ 18%", {x:1.1, y:4.45, w:5.8, h:0.35, fontSize:15, bold:true, color:BLANCO, fontFace:CUERPO, isTextBox:true});
s.addText("64.6% de aprobación con 9.3% de default esperado", {x:1.1, y:4.82, w:5.8, h:0.35, fontSize:13.5, color:MUSGO, fontFace:CUERPO, isTextBox:true});
s.addText("Equipo de Credit Risk Analytics · Credit Risk & Scoring Analytics 2026", {x:0.9, y:6.4, w:11.5, h:0.4, fontSize:13, color:MUSGO, fontFace:CUERPO, isTextBox:true});
s.addNotes("Abrir con la recomendación y el resultado. El detalle viene después.");

// ---------------------------------------------------------------- 2. El encargo y el conflicto
s = p.addSlide();
titulo(s, "El encargo, y un conflicto que hay que nombrar");
tarjeta(s, 0.6, 1.7, 5.9, 2.2, "EEF3EA");
s.addText("Lo que pide el negocio", {x:0.85, y:1.9, w:5.4, h:0.35, fontSize:17, bold:true, color:VERDE, fontFace:TIT, isTextBox:true});
s.addText("Crecer fuera de agencias sin excluir a quien no tiene trazabilidad bancaria.", {x:0.85, y:2.3, w:5.4, h:1.3, fontSize:15, color:TINTA, fontFace:CUERPO, isTextBox:true});
tarjeta(s, 6.8, 1.7, 5.9, 2.2, "EEF3EA");
s.addText("Lo que fija el apetito de riesgo", {x:7.05, y:1.9, w:5.4, h:0.35, fontSize:17, bold:true, color:VERDE, fontFace:TIT, isTextBox:true});
s.addText([{text:"Aprobación ≥ 70%", options:{bullet:true, breakLine:true}},
           {text:"Default 12m ≤ 11%", options:{bullet:true, breakLine:true}},
           {text:"Pérdida esperada ≤ 3% del monto", options:{bullet:true}}],
          {x:7.05, y:2.3, w:5.4, h:1.4, fontSize:15, color:TINTA, fontFace:CUERPO, paraSpaceAfter:6, isTextBox:true});
tarjeta(s, 0.6, 4.25, 12.1, 2.05, "FBEFEC");
s.addText("No existe un punto de corte que cumpla las dos cosas", {x:0.9, y:4.45, w:11.5, h:0.45, fontSize:22, bold:true, color:TIERRA, fontFace:TIT, isTextBox:true});
s.addText("Con el nivel de riesgo de 2024-2025, la política propuesta llega a 67.2% de aprobación con 10.7% de default. Aplica la regla de precedencia que el propio apetito define: prevalece el límite de riesgo, y el conflicto se escala al Comité con los números, no se disimula moviendo el corte.",
          {x:0.9, y:5.0, w:11.5, h:1.1, fontSize:15, color:TINTA, fontFace:CUERPO, isTextBox:true});
pie(s, "Fuente: reports/09_decision_engine.md §3 y §7 · decision_curva_tradeoff.csv");
s.addNotes("Este es el mensaje que diferencia el trabajo: el conflicto se mide y se escala.");

// ---------------------------------------------------------------- 3. Qué encontramos
s = p.addSlide();
titulo(s, "Qué encontramos en los datos", "Tres hallazgos que cambiaron el diseño del sistema");
stat(s, 0.6, 1.75, 3.9, "+5.4 pp", "Subió el default entre 2021 y 2024\n(8.6% → 14.0%)");
stat(s, 4.7, 1.75, 3.9, "0.005", "Índice de estabilidad del score:\nla población NO cambió", MUSGO);
stat(s, 8.8, 1.75, 3.9, "61-63%", "La severidad no se movió:\nla pérdida es por frecuencia", MUSGO);
s.addImage({path: path+"fig13_nivel_y_tendencia.png", x:0.6, y:3.6, w:12.1, h:2.6});
s.addText("Consecuencia: la calibración deja de ser un paso de cierre y pasa a ser un control permanente. Sin recalibrar, el sistema subestima el riesgo cerca de 30%.",
          {x:0.6, y:6.32, w:12.1, h:0.5, fontSize:14, bold:true, color:VERDE, fontFace:CUERPO, isTextBox:true});
s.addNotes("Si preguntan por qué no reentrenar: el problema es de nivel, no de ordenamiento.");

// ---------------------------------------------------------------- 4. El modelo
s = p.addSlide();
titulo(s, "El modelo: gana el más simple", "Seis candidatos, mismas reglas, misma partición temporal");
tabla(s, [
  [encabezado(""), encabezado("Scorecard (champion)"), encabezado("Boosting")],
  ["Gini fuera de muestra", {text:"0.348", options:{bold:true, color:VERDE}}, "0.304 a 0.320"],
  ["Brecha entre ajuste y realidad", {text:"9 puntos", options:{bold:true, color:VERDE}}, "hasta 45 puntos"],
  ["Tiempo por 1,000 solicitudes", {text:"menos de 1 ms", options:{bold:true, color:VERDE}}, "20 a 40 ms"],
  ["Explicación al cliente", {text:"exacta, por puntos", options:{bold:true, color:VERDE}}, "aproximada"],
], {y:1.75, colW:[4.3, 4.0, 3.8], rowH:0.46});
stat(s, 0.6, 4.35, 3.9, "0.424", "Gini en la cosecha 2025,\nque nunca se usó para construirlo");
tarjeta(s, 4.7, 4.35, 8.0, 1.55);
s.addText("Qué mira el modelo", {x:4.95, y:4.5, w:7.5, h:0.32, fontSize:16, bold:true, color:VERDE, fontFace:TIT, isTextBox:true});
s.addText("Score de buró (64% del puntaje) · Capacidad de pago post-crédito (20%) · Ahorro sobre el monto pedido (16%). Fuera del modelo por diseño: región, edad, distancia, dependientes e ingreso en efectivo.",
          {x:4.95, y:4.88, w:7.5, h:0.95, fontSize:13.5, color:TINTA, fontFace:CUERPO, isTextBox:true});
pie(s, "Fuente: modelos_comparacion.csv · validacion_metricas.csv");
s.addNotes("La regla de selección se fijó antes de ver resultados: el más simple que no sea significativamente peor.");

// ---------------------------------------------------------------- 5. Fairness
s = p.addSlide();
titulo(s, "Equidad: lo que medimos y lo que hay que gestionar");
tarjeta(s, 0.6, 1.7, 5.9, 2.0, "EEF3EA");
s.addText("El score no es un proxy", {x:0.85, y:1.88, w:5.4, h:0.35, fontSize:17, bold:true, color:VERDE, fontFace:TIT, isTextBox:true});
s.addText("Con los insumos del modelo no se puede reconstruir la región (acierto igual al azar) ni la informalidad, la distancia, la edad o los dependientes (R² ≈ 0).",
          {x:0.85, y:2.28, w:5.4, h:1.25, fontSize:14.5, color:TINTA, fontFace:CUERPO, isTextBox:true});
tarjeta(s, 6.8, 1.7, 5.9, 2.0, "FBEFEC");
s.addText("El punto a gestionar", {x:7.05, y:1.88, w:5.4, h:0.35, fontSize:17, bold:true, color:TIERRA, fontFace:TIT, isTextBox:true});
s.addText("El quintil de mayor ingreso en efectivo recibe aprobación automática con AIR de 0.74, bajo el umbral de 0.80. Se repite en 2025: no es ruido.",
          {x:7.05, y:2.28, w:5.4, h:1.25, fontSize:14.5, color:TINTA, fontFace:CUERPO, isTextBox:true});
s.addImage({path: path+"fig26_fairness_air.png", x:0.6, y:3.9, w:12.1, h:2.35});
s.addText("No se rechaza: se verifica el ingreso. Contando la revisión, el indicador sube a 0.93.",
          {x:0.6, y:6.32, w:12.1, h:0.5, fontSize:14, bold:true, color:VERDE, fontFace:CUERPO, isTextBox:true});
s.addNotes("La palanca no es cambiar el modelo: es hacer barata y rápida la verificación de ingreso.");

// ---------------------------------------------------------------- 6. La política
s = p.addSlide();
titulo(s, "La política de decisión", "El orden importa: la falta de información nunca se rechaza en automático");
const pasos = [["1","Falta información","Sin buró o sin ingreso → revisión"],
               ["2","Riesgo fuera del apetito","PD calibrada ≥ 20% → rechazo"],
               ["3","Verificación","Ticket > S/ 20,000 o efectivo alto → revisión"],
               ["4","La cuota no cabe","Contraoferta automática de monto y se recalcula la PD"],
               ["5","Zona gris 18%-20%","Revisión · el resto, aprobación automática"]];
pasos.forEach((paso, i) => {
  const y = 1.85 + i*0.85;
  s.addShape(p.ShapeType.ellipse, {x:0.65, y:y, w:0.55, h:0.55, fill:{color:VERDE}});
  s.addText(paso[0], {x:0.65, y:y, w:0.55, h:0.55, fontSize:17, bold:true, color:BLANCO, align:"center", valign:"middle", fontFace:TIT, margin:0, isTextBox:true});
  s.addText(paso[1], {x:1.42, y:y+0.02, w:3.3, h:0.32, fontSize:15, bold:true, color:TINTA, fontFace:CUERPO, isTextBox:true});
  s.addText(paso[2], {x:4.7, y:y+0.03, w:3.6, h:0.5, fontSize:13.5, color:GRIS, fontFace:CUERPO, isTextBox:true});
});
stat(s, 8.7, 1.85, 4.0, "53.3%", "Aprobación automática\n(12% con contraoferta de monto)");
stat(s, 8.7, 3.55, 4.0, "23.2%", "Revisión manual\npor reglas verificables", MUSGO);
stat(s, 8.7, 5.25, 4.0, "23.5%", "Rechazo\npor riesgo fuera del apetito", TIERRA);
pie(s, "Fuente: reports/09_decision_engine.md · decision_detalle_2024.csv");
s.addNotes("Exceder el DTI no manda a analista: dispara contraoferta. Eso libera capacidad para lo que sí requiere criterio.");

// ---------------------------------------------------------------- 7. Impacto
s = p.addSlide();
titulo(s, "Impacto: quién entra y quién sale");
tabla(s, [
  [encabezado("Grupo"), encabezado("Participación"), encabezado("Default observado")],
  ["Se mantienen aprobados", "46.9%", "9.8%"],
  [{text:"Salen (aprobados antes, ahora no)", options:{bold:true}}, {text:"35.9%", options:{bold:true}}, {text:"19.4%", options:{bold:true, color:TIERRA}}],
  [{text:"Entran (rechazados antes, ahora califican)", options:{bold:true}}, {text:"6.3%", options:{bold:true}}, "—"],
], {y:1.8, colW:[5.5, 3.3, 3.3], rowH:0.48});
s.addChart(p.ChartType.bar, [
  {name:"Política histórica", labels:["Aprobación", "Default"], values:[81.6, 13.4]},
  {name:"Política propuesta", labels:["Aprobación", "Default"], values:[64.6, 9.3]},
], {x:0.6, y:4.0, w:7.2, h:2.6, barDir:"col", chartColors:[GRIS, VERDE], showTitle:true,
    title:"Cosecha 2025: histórica vs. propuesta (%)", titleFontSize:14, titleColor:TINTA, titleFontFace:CUERPO,
    showValue:true, dataLabelPosition:"outEnd", dataLabelFontSize:12, dataLabelColor:TINTA, dataLabelFormatCode:"0.0",
    catAxisLabelColor:GRIS, valAxisLabelColor:GRIS, valAxisMaxVal:100, valGridLine:{color:"EDEDE8", size:1},
    catGridLine:{style:"none"}, showLegend:true, legendPos:"b", legendFontSize:11});
tarjeta(s, 8.1, 4.0, 4.6, 2.6, "EEF3EA");
s.addText("El recorte no es al azar", {x:8.35, y:4.2, w:4.1, h:0.35, fontSize:17, bold:true, color:VERDE, fontFace:TIT, isTextBox:true});
s.addText("Las solicitudes que salen tenían el doble de default que las que se mantienen. La política ataca justo la parte de la cartera que explicaba la pérdida, y deja entrar a un 6.3% que antes se rechazaba.",
          {x:8.35, y:4.62, w:4.1, h:1.8, fontSize:14, color:TINTA, fontFace:CUERPO, isTextBox:true});
s.addNotes("Swap-out 19.4% contra 9.8% de los que se mantienen: esa es la evidencia de que el corte es el correcto.");

// ---------------------------------------------------------------- 8. El costo
s = p.addSlide();
titulo(s, "El costo, dicho de frente", "Prestar mejor implica prestar menos: conviene separar los dos efectos");
tabla(s, [
  [encabezado("Cosecha 2025"), encabezado("Monto colocado"), encabezado("Pérdida esperada"), encabezado("Resultado")],
  ["Política histórica", "S/ 9.6 M", "S/ 0.36 M", {text:"S/ 1.69 M", options:{bold:true}}],
  ["Propuesta, cobrando la tasa histórica", "S/ 6.2 M", "S/ 0.18 M", {text:"S/ 1.16 M", options:{bold:true}}],
  ["Propuesta con pricing por riesgo", "S/ 6.2 M", "S/ 0.18 M", {text:"S/ 0.43 M", options:{bold:true}}],
], {y:1.8, colW:[4.9, 2.5, 2.5, 2.2], rowH:0.46});
tarjeta(s, 0.6, 4.0, 5.9, 1.5, "EEF3EA");
s.addText("Efecto selección: −S/ 0.53 M", {x:0.85, y:4.16, w:5.4, h:0.35, fontSize:16, bold:true, color:VERDE, fontFace:TIT, isTextBox:true});
s.addText("Decisión de riesgo. La pérdida por sol prestado baja de 3.75% a 2.99%.", {x:0.85, y:4.56, w:5.4, h:0.8, fontSize:14, color:TINTA, fontFace:CUERPO, isTextBox:true});
tarjeta(s, 6.8, 4.0, 5.9, 1.5, "FBEFEC");
s.addText("Efecto precio: −S/ 0.73 M", {x:7.05, y:4.16, w:5.4, h:0.35, fontSize:16, bold:true, color:TIERRA, fontFace:TIT, isTextBox:true});
s.addText("Decisión comercial del Comité. El modelo fija el piso de la tasa, no el precio.", {x:7.05, y:4.56, w:5.4, h:0.8, fontSize:14, color:TINTA, fontFace:CUERPO, isTextBox:true});
tarjeta(s, 0.6, 5.7, 12.1, 1.1, "EEF3EA");
s.addText("Stress: en el escenario severo la aprobación cae sola de 64.7% a 36.5% y la política absorbe 1.5 puntos de pérdida. El corte en PD calibrada es un estabilizador automático.",
          {x:0.9, y:5.9, w:11.5, h:0.75, fontSize:14.5, color:TINTA, fontFace:CUERPO, isTextBox:true});
s.addNotes("Parte del resultado histórico no era margen: era riesgo no provisionado. En 2024 la política histórica estaba fuera del apetito.");

// ---------------------------------------------------------------- 9. Gobierno
s = p.addSlide();
titulo(s, "Gobierno, monitoreo y puesta en producción");
const bloques = [["Tier 1", "Materialidad alta: decide sobre el 100% de las solicitudes. Validación anual y monitoreo trimestral."],
                 ["10 hallazgos", "Validación independiente: 2 de severidad alta a remediar antes del despliegue. Conclusión: apto con condiciones."],
                 ["13 indicadores", "Monitoreo separado en datos, modelo y negocio. Cada alerta tiene acción y responsable."],
                 ["API en línea", "Interfaz web, artefactos con hash y la misma respuesta que el desarrollo en 200 solicitudes."]];
bloques.forEach((b, i) => {
  const x = 0.6 + (i % 2) * 6.2, y = 1.8 + Math.floor(i / 2) * 2.3;
  tarjeta(s, x, y, 5.9, 2.0);
  s.addText(b[0], {x:x+0.25, y:y+0.2, w:5.4, h:0.5, fontSize:24, bold:true, color:VERDE, fontFace:TIT, isTextBox:true});
  s.addText(b[1], {x:x+0.25, y:y+0.78, w:5.4, h:1.1, fontSize:14, color:TINTA, fontFace:CUERPO, isTextBox:true});
});
s.addText("Reproducibilidad: python run_all.py reejecuta todo el proyecto · 110 pruebas automáticas en verde",
          {x:0.6, y:6.5, w:12.1, h:0.4, fontSize:14, bold:true, color:VERDE, fontFace:CUERPO, isTextBox:true});
s.addNotes("El marco de gobierno está implementado, no solo descrito: registro con hash, promoción y rollback.");

// ---------------------------------------------------------------- 10. Qué pedimos
s = p.addSlide(); s.background = {color:VERDE};
s.addText("Qué pedimos al Comité", {x:0.8, y:0.7, w:11.7, h:0.8, fontSize:36, bold:true, color:BLANCO, fontFace:TIT, isTextBox:true});
const pedidos = [["1", "Aprobar la política y sus umbrales", "PD 18% / 20% · DTI 45% / 60%"],
                 ["2", "Definir el margen objetivo del pricing", "El modelo fija el piso; el Comité fija el precio"],
                 ["3", "Resolver el conflicto de crecimiento", "Aceptar 67% de aprobación o ampliar verificación"],
                 ["4", "Aprobar el marco de gobierno", "Con las dos remediaciones previas al despliegue"]];
pedidos.forEach((item, i) => {
  const y = 1.85 + i*1.1;
  s.addShape(p.ShapeType.ellipse, {x:0.85, y:y, w:0.6, h:0.6, fill:{color:MUSGO}});
  s.addText(item[0], {x:0.85, y:y, w:0.6, h:0.6, fontSize:20, bold:true, color:VERDE, align:"center", valign:"middle", fontFace:TIT, margin:0, isTextBox:true});
  s.addText(item[1], {x:1.7, y:y-0.02, w:6.6, h:0.4, fontSize:19, bold:true, color:BLANCO, fontFace:CUERPO, isTextBox:true});
  s.addText(item[2], {x:1.7, y:y+0.36, w:10.6, h:0.35, fontSize:14, color:MUSGO, fontFace:CUERPO, isTextBox:true});
});
s.addText("Prestar mejor implica prestar menos. Lo que se gana es una cartera que resiste el escenario adverso sin decisiones de pánico.",
          {x:0.85, y:6.45, w:11.6, h:0.5, fontSize:15, italic:true, color:MUSGO, fontFace:CUERPO, isTextBox:true});
s.addNotes("Cerrar pidiendo las cuatro decisiones de forma explícita.");

p.writeFile({fileName: RUTA.join(__dirname, "..", "reports", "Presentacion_Caso15_CajaRural360.pptx")}).then(() => console.log("deck generado"));
