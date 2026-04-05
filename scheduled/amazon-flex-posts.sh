#!/bin/bash
# Amazon Flex cluster — 3 posts scheduled for first half of April
# Runs at 19:00 on 2026-03-24
# Topics:
#   1. Cómo conseguir bloques de alta paga en Amazon Flex → publish 2026-04-03 09:00
#   2. Sistema de valoraciones Amazon Flex (Fantastic/Great/Fair/Poor) → publish 2026-04-08 09:00
#   3. Amazon Flex vs Amazon Logistics: diferencias y qué conviene más → publish 2026-04-13 09:00

set -e
LOG=/tmp/amazon-flex-posts-$(date +%Y%m%d_%H%M).log
exec > >(tee -a "$LOG") 2>&1

PYTHON=/usr/bin/python3
NATURALIZER=/home/devops/projects/inforeparto/naturalizer/naturalizer.py
INDEXER=/home/devops/projects/inforeparto/gsc-indexing/index_urls.py
WP="wp --path=/var/www/html --allow-root"
BOT_TOKEN=$(grep TELEGRAM_BOT_TOKEN /home/devops/.env.projects 2>/dev/null | cut -d= -f2)
CHAT_ID=1312711201

notify() {
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d "chat_id=${CHAT_ID}" -d "text=$1" > /dev/null 2>&1 || true
}

create_post() {
    local CONTENT_FILE=$1
    local TITLE=$2
    local SLUG=$3
    local DATE=$4
    local FOCUS=$5
    local META_TITLE=$6
    local META_DESC=$7
    local CATEGORY=$8

    echo "Creating: $TITLE"

    # Create draft with author assigned
    POST_ID=$($WP post create \
        --post_title="$TITLE" \
        --post_content="$(cat $CONTENT_FILE)" \
        --post_status=future \
        --post_date="$DATE" \
        --post_type=post \
        --post_name="$SLUG" \
        --post_author=1 \
        --porcelain)

    echo "Post ID: $POST_ID"

    # Assign category
    $WP post term set $POST_ID category "$CATEGORY" 2>/dev/null || true

    # SEO meta
    $WP post meta set $POST_ID rank_math_title "$META_TITLE"
    $WP post meta set $POST_ID rank_math_description "$META_DESC"
    $WP post meta set $POST_ID rank_math_focus_keyword "$FOCUS"

    # Naturalize
    $PYTHON $NATURALIZER --post-id $POST_ID --backup

    # Index
    $PYTHON $INDEXER --post-id $POST_ID

    echo "Done: $POST_ID scheduled for $DATE"
    echo "$POST_ID"
}

# ── POST 1: Bloques alta paga ──
cat > /tmp/af-bloques-paga.html << 'HTMLEOF'
<p>Amazon Flex no paga todos los bloques igual. Un bloque de 3 horas en zona Prime Now puede rendir 45-60 €; el mismo bloque en reparto estándar, 30-38 €. La diferencia está en el tipo de entrega, la zona y la hora. Saber cuáles coger y cuáles ignorar marca la diferencia entre 12 €/h y 20 €/h en el mismo día.</p>

<p>Esta guía te explica cómo funciona la asignación de tarifas en Amazon Flex España y qué criterios usar para maximizar tus ingresos por hora.</p>

<h2>Cómo calcula Amazon Flex el precio de cada bloque</h2>

<p>Amazon Flex usa un sistema de tarifa base por bloque (no por entrega). En España, los rangos habituales son:</p>

<ul>
  <li><strong>Reparto Prime (2h):</strong> 18-28 € — pocas entregas, zonas densas, más propinas</li>
  <li><strong>Reparto estándar (3h):</strong> 28-40 € — más volumen, zonas más dispersas</li>
  <li><strong>Amazon Fresh (3-4h):</strong> 35-50 € — entregas programadas, clientes más exigentes</li>
  <li><strong>Amazon Locker (2h):</strong> 20-30 € — fácil pero bajo €/h</li>
</ul>

<p>Las tarifas suben automáticamente cuando hay poca oferta de drivers (festivos, mal tiempo, picos de navidad). Amazon llama a esto "surge pricing" aunque no lo publicita explícitamente.</p>

<h2>Qué tipos de bloque dan más €/hora</h2>

<h3>Prime Now y Same-Day</h3>
<p>Los bloques de 2 horas en zonas Prime tienen la mejor ratio €/hora. Las entregas son pocas (6-12 paquetes), los clientes están acostumbrados a propinas y las rutas son compactas. El problema: hay pocos y desaparecen en segundos de la app.</p>

<h3>Fresh y programadas</h3>
<p>Las entregas de Amazon Fresh llevan franja horaria comprometida, lo que obliga a ser puntual. A cambio, las tarifas son más altas y hay menos competencia porque muchos drivers las evitan por la presión de los horarios.</p>

<h3>Bloques de madrugada</h3>
<p>Los bloques que empiezan entre las 5:00 y las 8:00 suelen tener tarifa un 10-20% superior. Hay menos conductores disponibles a esa hora. Si tienes vehículo propio (no necesitas trasporte público), son los más rentables del día.</p>

<h2>Cuándo aparecen los mejores bloques</h2>

<p>Amazon Flex libera bloques en oleadas: habitualmente a las 18:00-19:00 del día anterior para el día siguiente, y en oleadas durante la mañana del mismo día. Pero los bloques de alta tarifa aparecen cuando hay escasez de drivers, que ocurre:</p>

<ul>
  <li>Días de lluvia intensa</li>
  <li>Festivos nacionales y locales</li>
  <li>Picos de ventas (Black Friday, días previos a Navidad)</li>
  <li>Franjas horarias nocturnas o muy tempranas</li>
</ul>

<p>La app no notifica automáticamente estas subidas de tarifa. Tienes que abrir la app en esos momentos o usar las alertas del sistema operativo para los momentos de pico.</p>

<h2>Cómo no perder un bloque al cogerlo</h2>

<p>El fallo más frecuente: ves un bloque bueno, tardas 3 segundos en decidir y ya no está. Amazon Flex es un sistema de captura rápida. Lo que funciona:</p>

<ul>
  <li>Ten la app siempre en la pantalla de bloques disponibles durante las oleadas</li>
  <li>No filtres por zona antes de coger — filtra después (si no te conviene, cancela dentro del margen permitido)</li>
  <li>Activa las notificaciones de la app y mantén el teléfono con la pantalla encendida durante las oleadas</li>
</ul>

<p>Para técnicas legítimas más avanzadas de captura de bloques sin bots, consulta nuestra <a href="https://inforeparto.com/capturar-bloques-amazon-flex-trucos-sin-bots/">guía completa de captura de bloques en Amazon Flex</a>.</p>

<h2>Calcula tu €/hora real antes de aceptar un bloque</h2>

<p>La tarifa del bloque no es tu ingreso real. Descuenta:</p>
<ul>
  <li>Gasolina o electricidad: 0,08-0,15 €/km según vehículo</li>
  <li>Amortización vehículo: 0,05-0,10 €/km</li>
  <li>Cuota autónomo (si eres autónomo de tarifa plana, ~80 €/mes ÷ horas trabajadas)</li>
</ul>

<p>Un bloque de 35 € en 3 horas con 60 km de ruta = ~35 - 7,5 € de gasolina - 4,5 € amortización = 23 € netos. A 3h, son ~7,7 €/h reales. Un bloque Prime de 28 € en 2h con 20 km = 28 - 2,5 - 1,5 = 24 € netos en 2h = 12 €/h reales. El bloque Prime en este caso es mejor a pesar de pagar menos en bruto.</p>

<h2>Conclusión</h2>

<p>El €/hora real depende del tipo de bloque, la zona, la distancia y el momento del día. Los bloques de alta tarifa existen, pero hay que estar en el sitio correcto de la app en el momento correcto. Con criterio, Amazon Flex puede rendir 13-18 €/h netos consistentemente. Sin criterio, puede quedarse en 7-9 €/h.</p>
HTMLEOF

ID1=$(create_post /tmp/af-bloques-paga.html \
    "Cómo Conseguir Bloques de Alta Paga en Amazon Flex España 2026" \
    "bloques-alta-paga-amazon-flex" \
    "2026-04-03 09:00:00" \
    "bloques amazon flex" \
    "Bloques de Alta Paga Amazon Flex 2026 | Guía para Ganar Más" \
    "Aprende cuándo y cómo conseguir los bloques mejor pagados en Amazon Flex España. Comparativa por tipo de entrega, horas y estrategias legales." \
    "Plataformas")

notify "✅ Post 1/3 Amazon Flex creado (ID $ID1) — programado 03/04 09:00 | Bloques alta paga"

# ── POST 2: Sistema de valoraciones ──
cat > /tmp/af-valoraciones.html << 'HTMLEOF'
<p>Tu puntuación en Amazon Flex determina si sigues teniendo acceso a bloques o acabas desactivado. El sistema tiene cuatro niveles: Fantastic, Great, Fair y Poor. Si caes a Poor de forma sostenida, Amazon desactiva tu cuenta sin aviso previo. Esto pasa más de lo que parece — y muchos drivers no saben exactamente qué mide el sistema hasta que ya es tarde.</p>

<p>Esta guía explica qué factores entran en tu puntuación, cómo sube y baja, y qué hacer si tu nivel ha caído.</p>

<h2>Los cuatro niveles del sistema de puntuación</h2>

<ul>
  <li><strong>Fantastic (≥95%):</strong> Acceso prioritario a bloques, menos restricciones de cancelación</li>
  <li><strong>Great (90-94%):</strong> Funcionamiento normal, sin ventajas ni penalizaciones visibles</li>
  <li><strong>Fair (80-89%):</strong> Aviso de Amazon, posible reducción de bloques disponibles</li>
  <li><strong>Poor (&lt;80%):</strong> Riesgo real de desactivación. Amazon envía aviso antes de cerrar la cuenta</li>
</ul>

<h2>Qué métricas afectan tu puntuación</h2>

<h3>Tasa de entrega exitosa</h3>
<p>Es el factor más importante. Cada paquete no entregado (devuelto al almacén sin intento válido) penaliza directamente. "Sin intento válido" incluye no llamar al timbre, no dejar aviso y no intentar contacto. Amazon monitoriza esto con GPS y horario de entrega.</p>

<h3>Bloques abandonados</h3>
<p>Cancelar un bloque con menos de 45 minutos de antelación cuenta como abandono. Tres abandonos en un período corto pueden bajar tu nivel de Fantastic a Great o de Great a Fair de golpe. Cancelaciones con más de 45 minutos de antelación no penalizan.</p>

<h3>Tasa de paquetes dañados</h3>
<p>Paquetes reportados como dañados en la entrega cuentan contra ti aunque no seas responsable del estado original. Fotografía siempre los paquetes que lleguen ya dañados al almacén antes de cargarlos.</p>

<h3>Tiempo en entrega</h3>
<p>Amazon espera que las entregas se completen dentro de la ventana del bloque. Si sistemáticamente terminas tarde o llevas muchos paquetes de vuelta, baja tu puntuación.</p>

<h2>Qué no afecta tu puntuación (aunque lo parezca)</h2>

<ul>
  <li>Las quejas de clientes por tiempo de espera si entregaste dentro del bloque</li>
  <li>El orden en que haces las entregas (la app sugiere ruta pero no obliga)</li>
  <li>Usar el navegador del móvil en lugar del de la app de Flex</li>
</ul>

<h2>Cómo subir tu puntuación si ha bajado</h2>

<p>El sistema usa una media móvil de los últimos bloques, no histórico total. Esto significa que una racha de buenos bloques puede subir tu nivel en 2-3 semanas. Lo que funciona:</p>

<ul>
  <li>No aceptes bloques que no puedas completar — mejor cancelar con antelación que abandonar</li>
  <li>Intenta siempre contacto real con el cliente antes de devolver (foto + nota)</li>
  <li>Si hay incidencia técnica (app caída, GPS fallando), documéntalo en la app en el momento</li>
  <li>Evita zonas o tipos de entrega que te generan devoluciones frecuentes</li>
</ul>

<h2>Qué hacer si Amazon desactiva tu cuenta</h2>

<p>Si recibes el email de desactivación, tienes derecho a apelar. El proceso:</p>
<ol>
  <li>Responde al email de desactivación dentro de los 14 días indicados</li>
  <li>Aporta contexto (incidencias documentadas, problemas técnicos, circunstancias excepcionales)</li>
  <li>Amazon revisa y responde habitualmente en 7-14 días laborables</li>
</ol>

<p>Las apelaciones tienen éxito principalmente cuando hay incidencias documentadas o errores del sistema. No funcionan si la desactivación se debe a patrón sostenido de baja entrega.</p>

<p>Para más información sobre cómo funcionan los almacenes y códigos de Amazon Flex en España, consulta nuestra guía sobre <a href="https://inforeparto.com/codigos-almacenes-amazon-flex-espana-dbc2-dmx1/">códigos de almacén Amazon Flex DBC2, DMX1 y más</a>.</p>
HTMLEOF

ID2=$(create_post /tmp/af-valoraciones.html \
    "Sistema de Valoraciones Amazon Flex: Fantastic, Great, Fair y Poor — Cómo Funciona en 2026" \
    "valoraciones-amazon-flex-fantastic-great-fair-poor" \
    "2026-04-08 09:00:00" \
    "valoraciones amazon flex" \
    "Valoraciones Amazon Flex 2026: Fantastic, Great, Fair y Poor Explicadas" \
    "Entiende cómo funciona el sistema de puntuación de Amazon Flex en España. Qué métricas te afectan, cómo subir de nivel y qué hacer si te desactivan." \
    "Plataformas")

notify "✅ Post 2/3 Amazon Flex creado (ID $ID2) — programado 08/04 09:00 | Sistema valoraciones"

# ── POST 3: Flex vs Logistics ──
cat > /tmp/af-vs-logistics.html << 'HTMLEOF'
<p>Amazon tiene dos modelos de reparto con conductores en España: <strong>Amazon Flex</strong> (autónomos que trabajan por bloques) y <strong>Amazon Logistics</strong> (conductores contratados por empresas de reparto subcontratadas). No son lo mismo, no pagan igual y no tienen los mismos requisitos. Esto es lo que diferencia uno del otro y cuál conviene más según tu situación.</p>

<h2>Amazon Flex: autónomo por bloques</h2>

<p>Amazon Flex es un contrato directo entre tú (autónomo) y Amazon. Tú aportas el vehículo, gestionas tus horarios y cobras por bloque completado. No tienes jefe directo, no tienes horario fijo y no tienes garantía de ingresos.</p>

<p><strong>Ventajas:</strong></p>
<ul>
  <li>Flexibilidad total de horario</li>
  <li>Tarifa por bloque (no por hora) — puedes acabar antes si eres eficiente</li>
  <li>Sin turno mínimo obligatorio</li>
  <li>Puedes compatibilizarlo con otras plataformas</li>
</ul>

<p><strong>Inconvenientes:</strong></p>
<ul>
  <li>Necesitas vehículo propio (coche, furgoneta) y seguro de autónomo</li>
  <li>Sin bloque = sin ingreso ese día</li>
  <li>La competencia por bloques es alta en ciudades grandes</li>
  <li>Alta carga administrativa (facturación, IRPF, IVA)</li>
</ul>

<h2>Amazon Logistics: conductor asalariado</h2>

<p>Amazon Logistics trabaja con empresas de transporte (DSP, Delivery Service Partners) que contratan conductores con contrato laboral. Amazon marca las rutas y los estándares; la empresa subcontratada gestiona la relación laboral.</p>

<p><strong>Ventajas:</strong></p>
<ul>
  <li>Contrato con salario base garantizado (habitualmente convenio de transporte)</li>
  <li>Nómina mensual, alta en Seguridad Social, vacaciones pagadas</li>
  <li>No necesitas vehículo propio (la empresa lo aporta)</li>
  <li>Sin gestiones fiscales propias</li>
</ul>

<p><strong>Inconvenientes:</strong></p>
<ul>
  <li>Horario fijo, turnos de 8-10 horas</li>
  <li>Sin flexibilidad — faltar tiene consecuencias laborales</li>
  <li>Salario base típico: 1.200-1.500 € brutos (convenio transporte)</li>
  <li>Depende del DSP local — condiciones y gestión varían mucho</li>
</ul>

<h2>Comparativa directa</h2>

<table>
  <thead>
    <tr><th>Factor</th><th>Amazon Flex</th><th>Amazon Logistics</th></tr>
  </thead>
  <tbody>
    <tr><td>Relación laboral</td><td>Autónomo</td><td>Asalariado (empresa DSP)</td></tr>
    <tr><td>Vehículo</td><td>Tuyo</td><td>De la empresa</td></tr>
    <tr><td>Ingresos</td><td>Variable (8-18 €/h real)</td><td>Fijo (~1.200-1.500 € brutos)</td></tr>
    <tr><td>Flexibilidad</td><td>Alta</td><td>Baja</td></tr>
    <tr><td>Seguridad</td><td>Baja</td><td>Alta</td></tr>
    <tr><td>Gestión fiscal</td><td>Tú mismo</td><td>La empresa</td></tr>
    <tr><td>Compatibilidad con otras apps</td><td>Sí</td><td>Generalmente no</td></tr>
  </tbody>
</table>

<h2>Cuál conviene más según tu situación</h2>

<p><strong>Elige Amazon Flex si:</strong> ya eres autónomo con otras plataformas, tienes vehículo propio, valoras la flexibilidad por encima de la seguridad y puedes gestionar periodos sin ingresos.</p>

<p><strong>Elige Amazon Logistics si:</strong> buscas estabilidad y nómina garantizada, no tienes (ni quieres) vehículo propio, prefieres no gestionar la fiscalidad autónoma o quieres derechos laborales completos (baja, vacaciones, finiquito).</p>

<h2>Cómo acceder a cada uno</h2>

<p>Para <strong>Amazon Flex</strong>: descarga la app Amazon Flex, regístrate con CIF/NIF de autónomo, verifica documentación del vehículo y espera activación (puede tardar días o semanas según zona).</p>

<p>Para <strong>Amazon Logistics</strong>: busca ofertas de empleo de empresas DSP en tu ciudad (suelen publicar en InfoJobs o LinkedIn). No se accede directamente a través de Amazon sino a través del partner local.</p>

<p>Si ya repartes con Amazon Flex y quieres optimizar tu rendimiento, consulta nuestra guía sobre <a href="https://inforeparto.com/capturar-bloques-amazon-flex-trucos-sin-bots/">cómo capturar los mejores bloques sin bots</a> y los <a href="https://inforeparto.com/codigos-almacenes-amazon-flex-espana-dbc2-dmx1/">códigos de almacén Amazon Flex en España</a>.</p>
HTMLEOF

ID3=$(create_post /tmp/af-vs-logistics.html \
    "Amazon Flex vs Amazon Logistics: Diferencias, Ingresos y Cuál Conviene en 2026" \
    "amazon-flex-vs-amazon-logistics-diferencias" \
    "2026-04-13 09:00:00" \
    "amazon flex vs logistics" \
    "Amazon Flex vs Amazon Logistics 2026: Diferencias y Cuál Elegir" \
    "Comparativa completa entre Amazon Flex (autónomo) y Amazon Logistics (asalariado DSP) en España 2026. Ingresos, requisitos, ventajas e inconvenientes." \
    "Plataformas")

notify "✅ Post 3/3 Amazon Flex creado (ID $ID3) — programado 13/04 09:00 | Flex vs Logistics

Cluster Amazon Flex completo:
📅 03/04 — Bloques alta paga
📅 08/04 — Sistema valoraciones
📅 13/04 — Flex vs Logistics"

echo "Amazon Flex cluster completed. IDs: $ID1 $ID2 $ID3"
