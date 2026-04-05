---
name: legal-review
description: Skill de revisión legal de posts de inforeparto.com. Usar ANTES de publicar cualquier post. Detecta afirmaciones peligrosas, valora necesidad de disclaimers y puede recomendar no publicar.
---

# Legal Review - inforeparto.com

## Cuándo ejecutar

SIEMPRE antes de publicar. En el workflow de blog-post va entre el paso 6 (guardar borrador) y el paso 7 (naturalización). Si el legal review no pasa, NO se naturaliza ni se publica.

## Proceso de revisión

Leer el post completo y evaluar cada sección contra estas categorías:

### 1. ALERTAS ROJAS (parar publicación)

Si se detecta cualquiera de estas, NO publicar y avisar al usuario:

- **Asesoramiento fiscal concreto**: "debes declarar X en la casilla Y", "te puedes deducir Z euros". Inforeparto NO es una asesoría fiscal
- **Asesoramiento legal concreto**: "demanda a tu empresa por X", "tienes derecho a indemnización de X euros por tu caso"
- **Datos médicos o de salud**: consejos médicos específicos (postura, lesiones) sin fuente profesional
- **Difamación**: acusaciones concretas contra empresas sin fuente verificable (ej: "Glovo estafa a sus riders")
- **Datos personales**: nombres de repartidores reales, managers, inspectores sin consentimiento
- **Información que facilite fraude**: cómo cobrar en B, cómo no declarar ingresos, cómo falsear horas

### 2. ALERTAS NARANJAS (requieren disclaimer)

Añadir el disclaimer correspondiente si se detecta:

**Contenido fiscal/tributario general:**
```html
<div class="disclaimer disclaimer-fiscal">
<p><strong>Aviso:</strong> Esta información es orientativa 
y no sustituye el asesoramiento de un profesional fiscal. 
Cada situación personal es diferente. Consulta con un 
asesor o gestor para tu caso concreto.</p>
</div>
```

**Contenido legal/laboral general:**
```html
<div class="disclaimer disclaimer-legal">
<p><strong>Aviso:</strong> Este artículo tiene carácter 
informativo y no constituye asesoramiento legal. Para 
cuestiones específicas sobre tu situación laboral, 
consulta con un abogado laboralista o acude a tu 
sindicato.</p>
</div>
```

**Contenido sobre ganancias/ingresos:**
```html
<div class="disclaimer disclaimer-ganancias">
<p><strong>Aviso:</strong> Las cifras de ingresos son 
estimaciones basadas en datos públicos y experiencias 
de repartidores. Los ingresos reales varían según 
ciudad, plataforma, horario, vehículo y otros factores.</p>
</div>
```

**Contenido con datos de convenio/salarios:**
```html
<div class="disclaimer disclaimer-convenio">
<p><strong>Aviso:</strong> Las tablas salariales mostradas 
corresponden al convenio indicado en el texto. El convenio 
aplicable a tu caso depende de tu empresa y comunidad 
autónoma. Verifica con tu empresa o sindicato cuál es 
el tuyo.</p>
</div>
```

**Contenido con enlaces de afiliado:**
Ya cubierto por el aviso de `amazon-affiliate` skill.

### 3. ALERTAS AMARILLAS (revisar redacción)

No requieren disclaimer pero sí reformulación:

- **Afirmaciones absolutas sin fuente**: "todos los riders cobran X" → "según el convenio de mensajería, el salario base es X"
- **Generalización de una plataforma a todas**: "Glovo paga X" no implica que todas paguen X
- **Datos sin fecha**: "el SMI es de X euros" → "el SMI en 2026 es de X euros"
- **Confusión autónomo/asalariado**: desde la Ley Rider, los repartidores de plataforma son asalariados. NO dar información sobre ser autónomo como rider de plataforma como si fuera la situación actual
- **Consejos de multiapping**: aclarar que es legal tener varias apps pero puede haber restricciones contractuales
- **Promesas de ingresos**: nunca "ganarás X€", siempre "se puede ganar entre X y Y según..."

### 4. VERIFICACIÓN DE FUENTES

Para cada dato numérico o legal del post, verificar:

- [ ] ¿Tiene fuente identificable? (BOE, convenio, sindicato, medio)
- [ ] ¿La fuente es de los últimos 12 meses?
- [ ] ¿Se cita la fuente en el texto?
- [ ] Si es un convenio: ¿se especifica cuál y su ámbito?
- [ ] Si es una ley: ¿se cita correctamente? (nombre, número, fecha)

Leyes clave del sector:
- Ley Rider: Real Decreto-ley 9/2021, de 11 de mayo
- Estatuto de los Trabajadores: Real Decreto Legislativo 2/2015
- SMI 2026: buscar el Real Decreto vigente

### 5. FORMATO DEL INFORME

Después de la revisión, generar un informe para el usuario:

```
REVISIÓN LEGAL - Post: "Título del post"

🔴 ALERTAS ROJAS: X
[Detalle de cada una con la frase problemática y por qué]

🟠 DISCLAIMERS NECESARIOS: X
[Qué disclaimers hay que añadir y dónde]

🟡 REVISIONES DE REDACCIÓN: X
[Frases a reformular y sugerencia]

✅ FUENTES VERIFICADAS: X/Y
[Lista de datos y si tienen fuente o no]

VEREDICTO:
- ✅ PUBLICABLE (con/sin disclaimers)
- ⚠️ PUBLICABLE TRAS CORRECCIONES
- 🛑 NO PUBLICAR (motivo)
```

## Ubicación de disclaimers en el post

- Disclaimer fiscal/legal: al final del post, antes de los comentarios
- Disclaimer de ganancias: al inicio de la sección de cifras
- Disclaimer de convenio: antes de la primera tabla salarial
- Se pueden combinar si el post toca varios temas

## Reglas

- NUNCA aprobar un post con alertas rojas
- Los disclaimers NO son opcionales si hay alertas naranjas
- Ante la duda, añadir disclaimer (es mejor sobrar que faltar)
- Si un dato no tiene fuente verificable, o se encuentra la fuente o se elimina el dato
- El legal review se ejecuta sobre el contenido ANTES de naturalizar (el naturalizador no debe alterar disclaimers)
