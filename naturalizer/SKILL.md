---
name: naturalizer
description: "Transforma contenido generado por IA en texto indistinguible de escritura humana auténtica, optimizado para E-E-A-T (especialmente Experience). Usa este skill siempre que necesites naturalizar, humanizar o pulir contenido antes de publicarlo en cualquier sitio web (blog posts, artículos SEO, páginas de servicio, fichas de producto, reviews). Actívalo cuando el usuario mencione 'naturalizar', 'humanizar', 'que no parezca IA', 'hacer más natural', 'pulir para publicar', 'preparar para WordPress', 'añadir E-E-A-T', 'añadir fuentes', o cualquier variante. También úsalo como paso final en pipelines de contenido automatizado. El skill es AGNÓSTICO de sitio: funciona con cualquier web cargando su perfil de voz desde contextos/{site}/voz.md. NO es un simple parafraseo: aplica un sistema de capas (mash) que combina transformaciones técnicas, inyección de experiencia real, fuentes con enlaces, schema de autor y adaptación competitiva. Incluso si el usuario solo pide 'revisar el tono' o 'mejorar el estilo', considera usar este skill."
---

# Naturalizer v4 — Sistema de Naturalización por Capas (Mash) + E-E-A-T

## Filosofía

Este skill NO busca "esconder" que se usó IA. Busca transformar un borrador IA en contenido que un profesional con experiencia real habría escrito, porque le añade lo que la IA no puede fabricar: experiencia de primera mano, datos propios, fuentes verificables, voz personal y contexto local.

Google no penaliza contenido IA. Penaliza contenido genérico, vacío y publicado a escala sin valor. El core update de marzo 2026 ha dejado claro que la **Experience** (primera E de E-E-A-T) es ahora el diferenciador primario: contenido con experiencia real de primera mano supera a contenido exhaustivo pero impersonal.

**Principios rectores**:
1. Cada capa debe AÑADIR valor, no solo DISFRAZAR texto
2. Las 3-4 primeras frases son las más críticas: ahí se concentra el análisis de detectores Y la decisión del lector de seguir leyendo
3. Las fuentes con enlaces no son decoración: son señales de E-E-A-T que Google pondera
4. El skill es **agnóstico de sitio**: funciona con cualquier web. Los sitios preconfigurados (psicoprotego, inforeparto) son ejemplos; nuevos sitios se añaden creando su `contextos/{site}/voz.md`

## Nota de Integración para Claude Code

**IMPORTANTE**: Este skill SUSTITUYE cualquier paso de naturalización, humanización o pulido de estilo que exista en otros skills del pipeline. Si ya existe un paso de "revisión de tono" o "humanización" en BLOG-POST.md u otro orquestador, debe eliminarse o redirigirse a este skill para evitar que dos sistemas modifiquen el texto de forma contradictoria. El naturalizador es el ÚNICO responsable de la transformación final del texto antes de publicación.

Al integrarse en un pipeline existente:
1. Buscar en todos los SKILL.md del pipeline si hay pasos de "naturalización", "humanización", "revisión de tono" o "pulido de estilo"
2. Si los hay, sustituirlos por una llamada a este naturalizador
3. Si no los hay, insertar este skill como penúltimo paso (antes de publicación vía WP-CLI)
4. NO ejecutar nunca dos naturalizadores en cadena

---

## Contexto de Infraestructura

- **Servidor**: VPS Contabo (4 vCPU, 8GB RAM, 75GB NVMe, datacenter Alemania)
- **Stack**: Apache + MariaDB + WordPress (WP-CLI) + Python
- **Sitios actuales**: psicoprotego.es e inforeparto.com (el skill soporta N sitios)
- **Orquestación**: Claude Code como builder principal, bot Telegram para gestión remota
- **BD**: MariaDB (ya en uso para WordPress). PostgreSQL disponible si se justifica
- **APIs de búsqueda**: Serper API o Jina Reader (NO BeautifulSoup para scraping de SERPs)
- **SEO**: Rank Math en WordPress, Amazon PA-API pendiente para inforeparto

---

## Arquitectura: 11 Capas en 3 Fases

```
ENTRADA: Borrador IA crudo + site + topic
    │
    ▼
╔═══════════════════════════════════════════════════╗
║  FASE 1 — MASH TÉCNICO (Forma)                   ║
║                                                   ║
║  Capa 1: Rompe-patrones IA                       ║
║  Capa 2: Inyector de voz personal                 ║
║  Capa 3: Variabilidad sintáctica                  ║
║  Capa 3b: Gancho de apertura (primeras 3-4 frases)║
╚═══════════════════════════════════════════════════╝
    │
    ▼
╔═══════════════════════════════════════════════════╗
║  FASE 2 — MASH DE SUSTANCIA (Fondo + E-E-A-T)    ║
║                                                   ║
║  Capa 4: Inyector de experiencia real              ║
║  Capa 5: Enriquecedor contextual                  ║
║  Capa 5b: Inyector de fuentes con enlaces          ║
║  Capa 6: Adaptación competitiva                   ║
║  Capa 6b: Schema de autor y señales E-E-A-T       ║
╚═══════════════════════════════════════════════════╝
    │
    ▼
╔═══════════════════════════════════════════════════╗
║  FASE 3 — VERIFICACIÓN Y APRENDIZAJE             ║
║                                                   ║
║  Capa 7: NaturalScore (métricas internas)         ║
║  Capa 8: Integridad semántica                     ║
║  Capa 9: Feedback loop post-publicación           ║
╚═══════════════════════════════════════════════════╝
    │
    ▼
SALIDA: Contenido natural + E-E-A-T + fuentes + schema + metadata
```

---

## FASE 1 — MASH TÉCNICO

### Capa 1: Rompe-patrones IA

Detectar y eliminar (cargar desde `config/patterns_es.yaml`):

- Muletillas IA: "cabe destacar", "es importante señalar", "en definitiva", "sin duda alguna", "es fundamental", "en este sentido", "resulta crucial", "conviene recordar", "huelga decir", "no es de extrañar"
- Intensificadores vacíos: "verdaderamente", "realmente", "sumamente", "tremendamente", "ciertamente", "significativamente"
- Transiciones robóticas: "en primer lugar... en segundo lugar... en tercer lugar", "a continuación", "como se mencionó anteriormente", "por otro lado"
- Arranques vacíos: "Es importante tener en cuenta que", "Cabe mencionar que", "Vale la pena señalar que"
- Triadas exactas → variar a 2, 4 o 1 desarrollado
- Párrafos de longitud uniforme → romper simetría
- Listas con viñetas donde cabe prosa → narrativizar
- Em dashes en exceso (>2 por 500 palabras)
- Intros resumen ("En este artículo veremos...") → eliminar
- Conclusiones que repiten intro → reescribir con perspectiva nueva

### Capa 2: Inyector de Voz Personal

Cargar perfil desde `contextos/{site}/voz.md`. Ver sección **Perfiles de Voz** para detalle.

Para sitios nuevos, el script `generate_voice.py`:
1. Solicita 3-5 muestras de texto ya publicado
2. Busca en foros/comunidades del sector (vía Serper: "foro [sector] expresiones", "[sector] jerga", "comunidad [sector] España")
3. Extrae patrones de tono, registro, jerga, humor
4. Genera `voz.md` para validación humana

### Capa 3: Variabilidad Sintáctica

- Longitud de frase variable: 5 a 30+ palabras
- Arranques variados: no repetir estructura en párrafos consecutivos
- Digresiones controladas: 1-2 por artículo
- Preguntas retóricas: 2-3 por artículo largo
- Oralidad calibrada según perfil de voz
- NO errores gramaticales aleatorios (detectable por estilometría)

### Capa 3b: Gancho de Apertura (Primeras 3-4 frases) ⚡

Las primeras 3-4 frases reciben tratamiento especial: son el punto más analizado por detectores Y donde el lector decide si sigue.

**NUNCA empezar con:**
- Definición ("La ansiedad es un trastorno que...")
- Generalización ("En la sociedad actual...")
- Resumen de contenido ("En este artículo veremos...")
- Cualquier muletilla de Capa 1

**SIEMPRE empezar con:**
- Dato experiencial, escena concreta, pregunta provocadora o afirmación inesperada
- Al menos una señal de experiencia real en las 2 primeras frases
- Tensión/curiosidad que obligue a seguir
- Estructura sintáctica no predecible

**Patrones de apertura** (rotar entre artículos del mismo sitio):

| Patrón | Ejemplo Psicoprotego | Ejemplo Inforeparto |
|--------|---------------------|---------------------|
| Escena concreta | "El martes pasado una madre me dijo: 'Pensaba que era cosa de la edad.'" | "Llevas media hora esperando un pedido. La app se congela. Y el cliente ya está llamando." |
| Dato propio | "De las últimas 40 consultas por ansiedad, solo 3 llegaron por iniciativa del chaval." | "El 70% de los riders que leen nuestra guía no sabían que podían deducirse la mochila." |
| Pregunta provocadora | "¿Y si lo que parece rebeldía fuera un grito de auxilio silencioso?" | "¿Sabías que podrías estar pagando de más en tu cuota desde el primer día?" |
| Contra-intuitiva | "Que un adolescente diga 'estoy bien' es una de las señales que más nos preocupan." | "Darte de alta como autónomo es fácil. Lo difícil es no perder dinero haciéndolo mal." |
| Humor/ironía | (no aplica) | "Con el precio de la gasolina, vamos a acabar repartiendo en patinete." |

**Verificación post**: Releer las 3 primeras frases aisladas. ¿Las podría haber escrito un chatbot cualquiera? Si sí, reescribir.

---

## FASE 2 — MASH DE SUSTANCIA (+ E-E-A-T)

### Capa 4: Inyector de Experiencia Real

**ExperienceDB** en MariaDB:

```sql
CREATE TABLE IF NOT EXISTS experience_bank (
    id INT AUTO_INCREMENT PRIMARY KEY,
    site VARCHAR(50) NOT NULL,
    topic VARCHAR(200),
    type ENUM('clinical_observation','metric','anecdote','regulatory','comparison','user_feedback','process_insight') NOT NULL,
    content TEXT NOT NULL,
    tags JSON,
    success_score FLOAT DEFAULT 0.5,
    times_used INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP NULL,
    INDEX idx_site_topic (site, topic),
    INDEX idx_success (success_score DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Tipo `process_insight`: "Estuvimos una semana comparando mochilas", "Consultamos con un asesor fiscal especializado". Refuerza Experience mostrando el trabajo detrás del contenido.

Inyección priorizada: (1) primeras 3-4 frases, (2) tras cada afirmación importante, (3) en el cierre.

Si no hay experiencia: `[EXPERIENCIA: qué insertar]`. **NUNCA fabricar.**

### Capa 5: Enriquecedor Contextual

- Temporalidad: fechas concretas, normativas con fecha de publicación
- Geografía: según perfil del sitio
- Normativa: citar norma concreta; verificar vía Jina/Serper
- Precios: verificar vía búsqueda
- Enlaces internos: 2-3 por artículo (consultar WP-CLI)
- Marcadores si falta dato: `[DATO: verificar X]`, `[NORMATIVA: verificar X]`

### Capa 5b: Inyector de Fuentes con Enlaces 🔗

**Reglas:**
1. Mínimo 3 fuentes externas para artículos >1500 palabras, 1-2 para cortos
2. Prioridad de fuentes (mayor a menor valor E-E-A-T):
   - Oficiales: BOE, ministerios, Seguridad Social, colegios profesionales
   - Datos: INE, CIS, informes sectoriales, papers académicos
   - Medios de referencia: El País, El Mundo, Xataka, medios del nicho
   - Sectoriales: asociaciones profesionales, referentes del sector
   - Evitar: blogs genéricos, agregadores, fuentes sin autoría

3. Integración natural en narrativa (NO notas al pie):
   ```
   MAL:  "La ansiedad ha aumentado un 30%. [Fuente: OMS]"
   BIEN: "Según el último informe de UNICEF sobre salud mental infanto-juvenil, 
         la prevalencia se ha duplicado — algo que vemos a diario en consulta."
   ```

4. Verificar cada URL con Jina Reader antes de incluir
5. Máximo 1 enlace por dominio externo
6. Si no se encuentra fuente: `[FUENTE: buscar referencia para X]`

Dominios preferentes por nicho (configurables en `settings.yaml`):
- Psicoprotego: who.int, cop.es, boe.es, comunidad.madrid
- Inforeparto: boe.es, seg-social.es, agenciatributaria.es, xataka.com

### Capa 6: Adaptación Competitiva

1. Serper API → top 5 SERP para el topic
2. Jina Reader → extraer contenido limpio
3. Analizar: estructura, tono, experiencia propia, ángulos no cubiertos
4. Generar recomendación de diferenciación
5. Cache en MariaDB (TTL 7 días)

### Capa 6b: Schema de Autor y Señales E-E-A-T 👤

Para cada artículo, generar/verificar:

1. **Byline** con autor real enlazado a página de autor
2. **Schema Person/Organization** en JSON-LD:
   ```json
   {
     "@context": "https://schema.org",
     "@type": "Person",
     "name": "[autor]",
     "url": "[página de autor]",
     "jobTitle": "[título]",
     "knowsAbout": ["[tema1]", "[tema2]"],
     "sameAs": ["[linkedin]", "[colegio profesional]"],
     "worksFor": { "@type": "Organization", "name": "[sitio]", "url": "[url]" }
   }
   ```

3. **Página de autor**: foto real, bio con credenciales verificables, enlaces externos, lista de artículos

**Estrategia de credenciales por tipo de sitio:**

| Tipo | Ejemplo | Estrategia |
|------|---------|-----------|
| Credenciales profesionales | Psicoprotego | Nº colegiado, certificaciones (EMDR II), años experiencia, publicaciones (Papeles del Psicólogo), enlace a colegio para verificar |
| Autoridad por transparencia | Inforeparto | Transparencia sobre método ("investigamos comparando X fuentes"), volumen de contenido especializado, citas de normativa oficial, jerga del sector, @type Organization con knowsAbout detallado |
| Experiencia demostrable | Reviews/comparativas | "Hemos probado X durante Y días", fotos propias, datos de uso real |

Para **Inforeparto** específicamente:
- Usar `@type: Organization` como autor (marca "Inforeparto")
- `knowsAbout`: legislación laboral riders, RETA, plataformas delivery, Ley Rider, fiscalidad autónomos
- Complementar con firma: "El equipo de Inforeparto"
- En cada artículo, incluir una frase de proceso: "Para este artículo hemos consultado la normativa vigente en [boe.es] y contrastado con [fuente]"
- Cuando sea posible: "Revisado por [nombre asesor fiscal/abogado]" como reviewer

**Checklist pre-publicación:**
- [ ] Página de autor existe con schema válido
- [ ] Byline enlaza a página de autor
- [ ] Schema Article incluye author
- [ ] Credenciales son verificables (no inventadas)

---

## FASE 3 — VERIFICACIÓN Y APRENDIZAJE

### Capa 7: NaturalScore

```python
class NaturalScorer:
    def burstiness(text) -> float        # CV longitud frases
    def lexical_diversity(text) -> float  # MATTR ventanas 100 palabras
    def pattern_detection(text) -> dict   # Patrones IA desde YAML
    def paragraph_variance(text) -> float # Varianza longitud párrafos
    def opening_score(text) -> float      # ¿Primeras 3 frases genéricas?
    def source_density(text) -> float     # Fuentes con enlace por 500 palabras
    
    def overall_score(text) -> float:
        # burstiness*0.20 + lexical*0.20 + (1-patterns)*0.25 
        # + paragraphs*0.10 + opening*0.15 + sources*0.10
```

Umbrales: ≥70 OK | 50-69 retry (max 2) | <50 revisión humana obligatoria.

### Capa 8: Integridad Semántica

Vía Claude API (sin modelos locales pesados):
- Puntos clave del original presentes
- No afirmaciones falsas introducidas
- Keywords SEO preservadas
- URLs y datos numéricos intactos
- Fuentes de Capa 5b coherentes con contenido

### Capa 9: Feedback Loop

```sql
CREATE TABLE IF NOT EXISTS naturalization_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    site VARCHAR(50), topic VARCHAR(200), wp_post_id INT,
    score_before FLOAT, score_after FLOAT, intensity VARCHAR(20),
    experiences_used JSON, sources_added JSON, competitor_data JSON,
    pageviews_30d INT, avg_time_on_page FLOAT, bounce_rate FLOAT,
    avg_position FLOAT, ctr FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metrics_updated_at TIMESTAMP NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Flujo: naturalizar → loguear → 30d después cron GSC+GA4 → actualizar success_score experiencias → cada 10 artículos recalibrar pesos → alertas Telegram si score medio < 70.

---

## Perfiles de Voz

Ver archivos completos en `contextos/{site}/voz.md`. Resumen de campos:

```yaml
---
site: nombre
url: https://...
tono: [profesional-cercano | directo-práctico | técnico-accesible]
registro: [formal | formal-medio | informal-medio | informal]
persona: [1a_plural | 2a_directa | 1a_singular]
tuteo: true/false
marcadores_experiencia: [...]
jerga_sector: [{expresion, significado, uso}]  # Investigada en foros
terminos_propios: [...]
terminos_prohibidos: [...]
humor_ironia: true/false
nivel_oralidad: [bajo | medio | alto]
patrones_humor: [{tipo, ejemplo}]  # Solo si humor_ironia: true
ejemplos_voz: [...]
autores: [{nombre, rol, schema_type, credenciales, knows_about, same_as}]
eeat_strategy: [credenciales_profesionales | autoridad_por_transparencia | experiencia_demostrable]
---
```

**Inforeparto** incluye jerga investigada del sector: "me cayó un pedido" (asignación), "batear" (rechazar pedidos), "zona caliente" (zona con muchos pedidos), "desconexión" (despido/bloqueo), "doble app" (trabajar para dos plataformas). También patrones de humor e ironía: ironía sobre costes, complicidad con el lector, realismo con humor, guiños de cierre.

**Psicoprotego** mantiene tono profesional-cercano con oralidad baja y sin humor/ironía. Puede usar marcadores discursivos suaves ("bueno", "a ver", "la verdad es que") pero NUNCA jerga coloquial ni humor.

### Banco de Expresiones Informales (Español de España)

📄 **Archivo completo**: `config/expresiones_es.yaml` — Cargado por Capa 2 y Capa 3.

Contiene ~100 expresiones organizadas en 10 categorías por función pragmática: saludos/aperturas, sorpresa/énfasis, incredulidad, conexión con lector, marcadores discursivos, opinión, cercanía/apoyo, cierres, comodines y expresiones idiomáticas españolas.

**Reglas de uso clave:**
- Máximo 4-6 expresiones informales por artículo de 1500 palabras
- No mezclar registros (coloquial neutro vs vulgar) en el mismo artículo
- Distribuir a lo largo del texto, no concentrar
- Las más efectivas para romper patrón IA: marcadores discursivos ("es que...", "o sea...", "total...") — la IA nunca los genera de forma natural
- Para Psicoprotego: solo usar los marcadores más suaves ("bueno", "a ver", "la verdad es que"), sin humor ni jerga coloquial

Plantilla para nuevos sitios en `contextos/_template/voz.md`.

---

## Estructura de Directorios

```
naturalizer/
├── SKILL.md
├── core.py                     # naturalize() principal
├── analyzer.py                 # NaturalScorer
├── experience_db.py            # ExperienceDB (MariaDB)
├── competitor.py               # CompetitorAnalyzer (Serper+Jina)
├── sources.py                  # SourceInjector (Serper+Jina)
├── author_schema.py            # Generador JSON-LD
├── feedback.py                 # FeedbackLoop + Telegram
├── prompts/
│   ├── capa1_rompe_patrones.md
│   ├── capa2_voz.md
│   ├── capa3_variabilidad.md
│   ├── capa3b_gancho_apertura.md
│   ├── capa4_experiencia.md
│   ├── capa5_contexto.md
│   ├── capa5b_fuentes.md
│   ├── capa6_competencia.md
│   ├── capa6b_author_schema.md
│   └── capa8_integridad.md
├── config/
│   ├── patterns_es.yaml
│   ├── expresiones_es.yaml      # Banco de expresiones informales por función
│   ├── weights.json
│   └── settings.yaml
├── contextos/
│   ├── psicoprotego/voz.md
│   ├── inforeparto/voz.md
│   └── _template/voz.md
├── scripts/
│   ├── seed_experiences.py
│   ├── update_metrics.py
│   ├── migrate_db.py
│   └── generate_voice.py
└── tests/
```

---

## Anti-patrones

1. NO errores gramaticales aleatorios
2. NO sinónimos forzados
3. NO experiencias ni fuentes falsas
4. NO prometer 100% indetectabilidad
5. NO sacrificar SEO por naturalidad
6. NO Celery/Redis — ejecución secuencial
7. NO BeautifulSoup — usar Serper+Jina
8. NO modelos pesados en RAM
9. NO competir con otros skills — ÚNICO responsable del pulido final
