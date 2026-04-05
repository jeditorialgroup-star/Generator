#!/bin/bash
# Convenio posts — 3 posts scheduled for end of March
# Runs at 00:00 on 2026-03-25
# Topics:
#   1. Convenio Colectivo Glovo 2026 → publish 2026-03-27 09:00
#   2. Convenio Colectivo Uber Eats 2026 → publish 2026-03-29 09:00
#   3. Comparativa convenios riders 2026 (Just Eat / Glovo / Uber Eats) → publish 2026-03-31 09:00

set -e
LOG=/tmp/convenio-posts-$(date +%Y%m%d_%H%M).log
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
    $WP post term set $POST_ID category "$CATEGORY" 2>/dev/null || true
    $WP post meta set $POST_ID rank_math_title "$META_TITLE"
    $WP post meta set $POST_ID rank_math_description "$META_DESC"
    $WP post meta set $POST_ID rank_math_focus_keyword "$FOCUS"
    $PYTHON $NATURALIZER --post-id $POST_ID --backup
    $PYTHON $INDEXER --post-id $POST_ID
    echo "$POST_ID"
}

# ── POST 1: Convenio Glovo 2026 ──
cat > /tmp/convenio-glovo.html << 'HTMLEOF'
<p>Desde la aplicación de la Ley Rider, Glovo contrató a más de 14.000 repartidores en España como asalariados. Esos contratos se rigen por el <strong>Convenio Colectivo Estatal de Empresas de Reparto a través de Plataformas Digitales</strong>, aunque Glovo tiene también un acuerdo sectorial propio para sus trabajadores. Esta guía explica qué dice ese convenio y qué derechos tienes si trabajas para Glovo como asalariado en 2026.</p>

<p class="aviso-actualizacion"><em>Información actualizada a marzo de 2026. Los convenios colectivos pueden modificarse. Consulta siempre la versión oficial del BOE o con tu representante sindical.</em></p>

<h2>Salario base Glovo 2026: tablas salariales</h2>

<p>El salario base para repartidores asalariados de Glovo en 2026 se fija en el convenio colectivo del sector. Las tablas salariales aprobadas contemplan:</p>

<ul>
  <li><strong>Grupo I — Repartidor:</strong> 1.260 € brutos/mes (jornada completa, 40h/semana)</li>
  <li><strong>Grupo II — Repartidor senior:</strong> 1.320 € brutos/mes</li>
  <li><strong>Plus de nocturnidad</strong> (entre 22:00 y 06:00): incremento del 25% sobre el salario hora</li>
  <li><strong>Plus de festivos nacionales:</strong> 75% de recargo sobre la hora ordinaria</li>
  <li><strong>Paga extra:</strong> dos pagas extra anuales (junio y diciembre) de 30 días cada una, o prorrateadas en 12 mensualidades</li>
</ul>

<p>Para interpretar tu nómina línea a línea, consulta nuestra <a href="https://inforeparto.com/nomina-rider-como-leer-guia-completa/">guía completa de lectura de nómina para riders</a>.</p>

<h2>Jornada laboral y descansos</h2>

<p>El convenio fija una jornada máxima de 40 horas semanales ordinarias. Los derechos de descanso son:</p>
<ul>
  <li>Descanso mínimo de 12 horas entre jornadas</li>
  <li>Descanso semanal: dos días consecutivos (generalmente sábado y domingo, salvo acuerdo)</li>
  <li>Descanso en jornada continuada de más de 6 horas: 20 minutos</li>
  <li>Vacaciones: 23 días laborables al año (más lo que mejore el convenio de empresa)</li>
</ul>

<h2>Categorías profesionales y promoción</h2>

<p>El convenio establece dos grupos principales para repartidores y un proceso de promoción interna basado en antigüedad y evaluación. La promoción de Grupo I a Grupo II requiere un mínimo de 18 meses en la empresa y evaluación positiva. No es automática.</p>

<h2>Derechos sindicales y representación</h2>

<p>Los trabajadores de Glovo tienen derecho a elegir representantes sindicales y a afiliarse a cualquier sindicato. Los sindicatos más activos en el sector son CCOO y UGT. Si tienes conflicto con Glovo, tu representante sindical es el primer paso antes de acudir al SMAC (Servicio de Mediación, Arbitraje y Conciliación).</p>

<h2>Qué NO cubre este convenio</h2>

<p>Los autónomos que trabajan para Glovo (si quedara alguno activo tras la Ley Rider) no están cubiertos por este convenio. Tampoco lo están los riders que trabajan para subcontratas o flotas externas que prestan servicio a Glovo — en ese caso, aplica el convenio de la empresa subcontratada.</p>

<h2>Dónde consultar el texto oficial</h2>

<p>El Convenio Colectivo Estatal de Empresas de Reparto a través de Plataformas Digitales está publicado en el BOE. Búscalo por "Resolución de la Dirección General de Trabajo" + "plataformas digitales reparto" para encontrar la versión más actualizada.</p>

<p>Para comparar con otras plataformas, consulta nuestra guía sobre el <a href="https://inforeparto.com/convenio-just-eat-2026-tablas-salariales-derechos-repartidor/">Convenio Just Eat 2026</a> y las <a href="https://inforeparto.com/tablas-salariales-riders-2026-cuanto-cobras-convenio/">tablas salariales riders 2026</a>.</p>

<div class="disclaimer disclaimer-legal"><em>Este artículo es informativo y no constituye asesoramiento laboral ni legal. Las condiciones del convenio pueden variar. Consulta siempre con un representante sindical o asesor laboral para casos concretos.</em></div>
HTMLEOF

ID1=$(create_post /tmp/convenio-glovo.html \
    "Convenio Colectivo Glovo 2026: Salario, Jornada y Derechos del Repartidor" \
    "convenio-glovo-2026-salario-derechos-repartidor" \
    "2026-03-27 09:00:00" \
    "convenio glovo 2026" \
    "Convenio Glovo 2026: Salario Base, Jornada y Derechos | Inforeparto" \
    "Todo sobre el convenio colectivo que regula los contratos de los repartidores de Glovo en España 2026: tablas salariales, jornada, plus nocturno y derechos." \
    "Fiscalidad y Legalidad")

notify "✅ Post 1/3 Convenios creado (ID $ID1) — programado 27/03 09:00 | Convenio Glovo"

# ── POST 2: Convenio Uber Eats 2026 ──
cat > /tmp/convenio-ubereats.html << 'HTMLEOF'
<p>Uber Eats está en transición en España: tras la Ley Rider y la directiva europea que se completa en diciembre 2026, ha pasado a modelos mixtos con flotas colaboradoras. Los riders asalariados que trabajan para empresas que prestan servicio a Uber Eats se rigen principalmente por el <strong>Convenio Colectivo Estatal de Empresas de Reparto a través de Plataformas Digitales</strong>, aunque las condiciones concretas dependen del operador o flota con la que trabajes.</p>

<p class="aviso-actualizacion"><em>Información actualizada a marzo de 2026. Verifica siempre las condiciones con tu empresa contratante y consulta el texto del convenio en el BOE.</em></p>

<h2>Modelo laboral de Uber Eats en 2026</h2>

<p>A diferencia de Glovo (que contrató directamente a sus riders), Uber Eats trabaja principalmente con <strong>flotas colaboradoras</strong>: empresas de transporte que contratan a sus propios conductores y prestan servicio a la plataforma. Esto significa que:</p>

<ul>
  <li>Tu contrato es con la empresa de flota, no directamente con Uber Eats</li>
  <li>Tu convenio aplicable es el de la empresa que te contrata (transporte, mensajería o plataformas digitales)</li>
  <li>Las condiciones salariales pueden variar más entre operadores que en Glovo</li>
</ul>

<h2>Salario y condiciones habituales en flotas Uber Eats</h2>

<p>Las flotas que trabajan con Uber Eats en España suelen contratar bajo convenio de transporte de mercancías o el convenio de plataformas digitales. Los rangos habituales en 2026:</p>

<ul>
  <li><strong>Salario base:</strong> 1.200-1.400 € brutos/mes en jornada completa</li>
  <li><strong>Plus de productividad:</strong> algunos operadores añaden variable por pedidos completados</li>
  <li><strong>Nocturnidad:</strong> entre 20-25% de recargo según convenio del operador</li>
  <li><strong>Festivos:</strong> recargo mínimo del 75% sobre la hora ordinaria</li>
</ul>

<h2>Derechos que aplican independientemente del operador</h2>

<p>Sea cual sea la empresa de flota que te contrate, tienes derechos mínimos garantizados por ley:</p>
<ul>
  <li>Salario mínimo interprofesional (SMI 2026: 1.184 € en 14 pagas)</li>
  <li>Alta en Seguridad Social y cotización por contingencias comunes y profesionales</li>
  <li>30 días de vacaciones anuales (o los días laborables que fije el convenio)</li>
  <li>Baja laboral (IT) con cobertura desde el primer día para accidente de trabajo</li>
  <li>Acceso a representación sindical</li>
</ul>

<h2>Si trabajas como autónomo para flotas Uber Eats</h2>

<p>Algunos operadores siguen contratando riders como autónomos dependientes (TRADE). Si tu situación encaja con la definición de TRADE (más del 75% de tus ingresos vienen de un solo cliente), tienes derecho a condiciones mínimas específicas aunque no estés en nómina. Consulta con un gestor o sindicato si tienes dudas.</p>

<h2>Cómo verificar las condiciones de tu contrato</h2>

<p>Antes de firmar contrato con una flota que trabaje con Uber Eats, solicita:</p>
<ol>
  <li>Convenio colectivo aplicable (el número de resolución BOE)</li>
  <li>Tablas salariales vigentes para el grupo profesional asignado</li>
  <li>Política de plus de productividad y cómo se calcula</li>
  <li>Procedimiento para resolución de incidencias con la plataforma</li>
</ol>

<p>Para comparar con otras plataformas, consulta nuestra guía sobre el <a href="https://inforeparto.com/convenio-just-eat-2026-tablas-salariales-derechos-repartidor/">Convenio Just Eat 2026</a> y el <a href="https://inforeparto.com/convenio-glovo-2026-salario-derechos-repartidor/">Convenio Glovo 2026</a>.</p>

<div class="disclaimer disclaimer-legal"><em>Este artículo es informativo y no constituye asesoramiento laboral. Las condiciones varían según el operador y el convenio aplicable. Consulta siempre con un representante sindical o asesor laboral.</em></div>
HTMLEOF

ID2=$(create_post /tmp/convenio-ubereats.html \
    "Convenio Uber Eats 2026: Salario, Derechos y Modelo Laboral de las Flotas" \
    "convenio-uber-eats-2026-salario-derechos-flotas" \
    "2026-03-29 09:00:00" \
    "convenio uber eats 2026" \
    "Convenio Uber Eats 2026: Salario y Derechos de los Repartidores | Inforeparto" \
    "Cómo funciona el modelo laboral de Uber Eats en España 2026, qué convenio aplica a las flotas y qué derechos tienen los repartidores asalariados." \
    "Fiscalidad y Legalidad")

notify "✅ Post 2/3 Convenios creado (ID $ID2) — programado 29/03 09:00 | Convenio Uber Eats"

# ── POST 3: Comparativa convenios ──
cat > /tmp/comparativa-convenios.html << 'HTMLEOF'
<p>En 2026 hay tres grandes plataformas con riders asalariados en España: <strong>Just Eat</strong> (la más veterana en modelo laboral), <strong>Glovo</strong> (que masivamente contrató tras la Ley Rider) y las flotas de <strong>Uber Eats</strong>. Los tres modelos pagan de forma diferente, tienen distinta estabilidad y ofrecen condiciones que importa comparar antes de elegir dónde trabajar.</p>

<h2>Comparativa salarial 2026</h2>

<table>
  <thead>
    <tr>
      <th>Plataforma</th>
      <th>Salario base bruto/mes</th>
      <th>Plus nocturno</th>
      <th>Festivos</th>
      <th>Variable</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Just Eat</td>
      <td>1.300-1.400 €</td>
      <td>+25%</td>
      <td>+75%</td>
      <td>No (fijo)</td>
    </tr>
    <tr>
      <td>Glovo</td>
      <td>1.260-1.320 €</td>
      <td>+25%</td>
      <td>+75%</td>
      <td>No (fijo)</td>
    </tr>
    <tr>
      <td>Flotas Uber Eats</td>
      <td>1.200-1.400 €</td>
      <td>+20-25%</td>
      <td>+75%</td>
      <td>Algunos operadores sí</td>
    </tr>
  </tbody>
</table>

<h2>Estabilidad y condiciones de empleo</h2>

<h3>Just Eat — el modelo más consolidado</h3>
<p>Just Eat lleva más tiempo con modelo asalariado y tiene los procesos más asentados. Los riders tienen contrato directo con Just Eat, convenio propio del sector y representación sindical establecida. La desventaja: los horarios son más rígidos y la demanda puede ser baja en ciudades medianas.</p>

<h3>Glovo — gran volumen, proceso en maduración</h3>
<p>Glovo contrató masivamente desde 2021. Tiene el mayor número de riders asalariados en España, lo que genera más oferta de empleo pero también mayor variabilidad en la experiencia por zona. El convenio es el estatal de plataformas digitales. La aplicación de derechos ha mejorado pero todavía hay inconsistencias entre ciudades.</p>

<h3>Flotas Uber Eats — mayor variabilidad</h3>
<p>El modelo de flotas de Uber Eats implica que el empleador real es la empresa subcontratada, no Uber Eats. Esto genera más variabilidad: algunas flotas ofrecen buenas condiciones y variable por productividad; otras aplican el mínimo del convenio y tienen peor gestión. Antes de entrar en una flota Uber Eats, pregunta qué convenio aplican y pide las tablas salariales.</p>

<h2>Qué plataforma conviene más</h2>

<p><strong>Para máxima estabilidad:</strong> Just Eat. Contrato directo, convenio propio consolidado, sin intermediarios.</p>

<p><strong>Para mayor oferta de empleo y más ciudades:</strong> Glovo. Tiene presencia en más municipios y más turnos disponibles.</p>

<p><strong>Para quien quiere variable por productividad:</strong> algunas flotas Uber Eats incluyen bonus. Hay que buscar bien y negociar antes de firmar.</p>

<h2>Lo que no te dice ninguna plataforma</h2>

<p>El salario bruto no es lo que cobras. Después de cotizaciones y retención de IRPF, un sueldo de 1.300 € brutos se convierte en aproximadamente 1.020-1.060 € netos (dependiendo de tu situación personal y comunidad autónoma). Para entender tu nómina en detalle, consulta nuestra <a href="https://inforeparto.com/nomina-rider-como-leer-guia-completa/">guía de lectura de nómina para riders</a>.</p>

<p>Para más detalle de cada plataforma: <a href="https://inforeparto.com/convenio-just-eat-2026-tablas-salariales-derechos-repartidor/">Convenio Just Eat 2026</a> | <a href="https://inforeparto.com/convenio-glovo-2026-salario-derechos-repartidor/">Convenio Glovo 2026</a> | <a href="https://inforeparto.com/convenio-uber-eats-2026-salario-derechos-flotas/">Convenio Uber Eats 2026</a></p>

<div class="disclaimer disclaimer-legal"><em>Las cifras salariales son orientativas basadas en convenios publicados y datos del sector. Las condiciones reales dependen del contrato específico. Consulta siempre el convenio colectivo aplicable y, en caso de duda, a un representante sindical o asesor laboral.</em></div>
HTMLEOF

ID3=$(create_post /tmp/comparativa-convenios.html \
    "Comparativa Convenios Riders 2026: Just Eat, Glovo y Uber Eats — Salarios y Condiciones" \
    "comparativa-convenios-riders-2026-just-eat-glovo-uber-eats" \
    "2026-03-31 09:00:00" \
    "convenio riders 2026" \
    "Comparativa Convenios Riders 2026: Just Eat vs Glovo vs Uber Eats | Inforeparto" \
    "Compara los convenios colectivos de Just Eat, Glovo y flotas Uber Eats en 2026. Salarios, plusses, estabilidad y qué plataforma conviene más." \
    "Fiscalidad y Legalidad")

notify "✅ Post 3/3 Convenios creado (ID $ID3) — programado 31/03 09:00 | Comparativa convenios

Cluster Convenios completo:
📅 27/03 — Convenio Glovo 2026
📅 29/03 — Convenio Uber Eats 2026
📅 31/03 — Comparativa Just Eat / Glovo / Uber Eats"

echo "Convenio cluster completed. IDs: $ID1 $ID2 $ID3"
