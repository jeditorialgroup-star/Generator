# inforeparto.com — Content Pipeline

Sistema de generación autónoma de contenido SEO para [inforeparto.com](https://inforeparto.com), blog de referencia para repartidores y riders en España.

## ¿Qué hace?

Genera, naturaliza y publica artículos SEO de forma completamente automática:

1. **Descubre temas** con potencial usando Google Search Console (gaps semánticos)
2. **Investiga** cada tema: competencia, fuentes verificadas, experiencias reales de repartidores
3. **Genera** el artículo con Claude Sonnet (HTML directo, voz editorial propia)
4. **Naturaliza** el texto en 8 capas para eliminar patrones de IA
5. **Publica** en WordPress programado 3 días adelante, con imágenes de Pexels
6. **Refresca** posts antiguos que han perdido posicionamiento

## Requisitos del sistema

- Python 3.11+
- MariaDB 10.6+ (con acceso a `wordpress_db`)
- WordPress con WP-CLI instalado en PATH
- [Ollama](https://ollama.ai) con modelo `nomic-embed-text` (para embeddings locales)
- Conexión a internet para APIs externas

### Verificar Ollama

```bash
ollama list | grep nomic-embed-text
# Si no está:
ollama pull nomic-embed-text
```

## APIs necesarias

| Variable de entorno | Servicio | Uso | Plan mínimo |
|---------------------|----------|-----|-------------|
| `ANTHROPIC_API_KEY` | [Anthropic](https://console.anthropic.com) | Generación + naturalización | Pay-per-use |
| `SERPER_API_KEY` | [Serper.dev](https://serper.dev) | Análisis competitivo + fuentes | Free: 2.500/mes |
| `JINA_API_KEY` | [Jina.ai](https://jina.ai) | Lectura y verificación de URLs | Free tier disponible |
| `PEXELS_API_KEY` | [Pexels](https://www.pexels.com/api/) | Imágenes para posts | Gratuito |
| `WP_INFOREPARTO_USER` | WordPress REST API | Publicar + subir imágenes | Usuario WP con app password |
| `WP_INFOREPARTO_APP_PASSWORD` | WordPress REST API | App password del usuario WP | — |
| `WP_INFOREPARTO_URL` | WordPress REST API | Base URL del API | — |

### APIs opcionales (mejoran la calidad pero no son bloqueantes)

| Variable | Servicio | Uso |
|----------|----------|-----|
| `OLLAMA_URL` | Ollama local | Embeddings (default: `http://localhost:11434`) |

## Variables de entorno

Todas las credenciales van en `~/.env.projects`. Ver [`.env.example`](.env.example) para la lista completa.

```bash
# Verificar que el entorno está configurado
source ~/.env.projects && env | grep -E "ANTHROPIC|SERPER|PEXELS|JINA|WP_INFO"
```

## Instalación

```bash
# 1. Clonar / acceder al directorio
cd /home/devops/projects/inforeparto

# 2. Instalar dependencias Python
pip install -r requirements.txt

# 3. Copiar y rellenar variables de entorno
cp .env.example ~/.env.projects
nano ~/.env.projects

# 4. Verificar conexión a BD
python3 -c "import mysql.connector; c = mysql.connector.connect(host='localhost', user='wp_user', password='...', database='wordpress_db'); print('BD OK')"

# 5. Verificar Ollama
curl http://localhost:11434/api/tags | python3 -c "import sys,json; print([m['name'] for m in json.load(sys.stdin)['models']])"
```

## Estructura de directorios

```
inforeparto/
├── README.md                    # Este archivo
├── AUDIT.md                     # Auditoría del código
├── ARCHITECTURE.md              # Arquitectura del sistema
├── requirements.txt             # Dependencias Python
├── .env.example                 # Plantilla de variables de entorno
│
├── scripts/                     # Procesos cron
│   ├── autopublisher.py         # Generación diaria de posts (05:00)
│   ├── daily-refresh.py         # Re-naturalización de posts viejos (03:00)
│   ├── gsc-topic-discovery.py   # Descubrimiento de temas vía GSC (lun 04:00)
│   ├── affiliate_catalog.json   # Catálogo de productos Amazon con ASINs
│   ├── post_embeddings.json     # Caché de embeddings (generado automáticamente)
│   └── logs/                    # Logs diarios (autopublisher-YYYY-MM-DD.log, etc.)
│
├── gsc-indexing/
│   └── index_urls.py            # Notificación de indexación a Google API (10:00)
│
└── naturalizer/                 # Motor de naturalización v4
    ├── naturalizer.py           # Motor principal: 8 capas + NaturalScorer
    ├── author_schema.py         # Capa 6b: byline de autor + JSON-LD schema
    ├── competitor.py            # Capa 6: análisis competitivo (Serper)
    ├── sources.py               # Capa 5b: inyector de fuentes (Jina)
    ├── experience_db.py         # Capa 4: experiencias reales de repartidores
    │
    ├── config/                  # Configuración global del motor
    │   ├── settings.yaml        # Modelos, thresholds, retries, pesos del score
    │   ├── patterns_es.yaml     # Patrones IA a eliminar, malas aperturas
    │   └── expresiones_es.yaml  # Expresiones naturales para inyectar
    │
    ├── contextos/inforeparto/   # Configuración específica del sitio
    │   ├── editorial_rules.yaml # Temas prohibidos, disclaimers, red flags
    │   └── voz.md               # Perfil de voz editorial
    │
    └── scripts/                 # Scripts de mantenimiento (manuales)
        ├── seed_experiences.py  # Carga inicial de experiencias en BD
        ├── migrate_db.py        # Migraciones de schema MariaDB
        └── update_metrics.py    # Actualiza métricas GSC manualmente
```

## Cómo ejecutar cada proceso

### Autopublisher (generación de contenido)

```bash
cd /home/devops/projects/inforeparto/scripts
source ~/.env.projects

# Producción (selecciona tema de la cola automáticamente)
python3 autopublisher.py

# Con tema manual
python3 autopublisher.py --topic "mejores mochilas para repartidor 2026"

# Dry-run (no publica, no consume cuota WP)
python3 autopublisher.py --dry-run

# Forzar aunque ya haya corrido hoy
python3 autopublisher.py --force

# Dry-run con tema manual
python3 autopublisher.py --topic "seguro moto repartidor" --dry-run
```

### GSC Topic Discovery (descubrimiento de temas)

```bash
cd /home/devops/projects/inforeparto/scripts
source ~/.env.projects

python3 gsc-topic-discovery.py
python3 gsc-topic-discovery.py --dry-run          # Ver qué insertaría sin insertar
python3 gsc-topic-discovery.py --days 60          # Rango GSC (default: 90 días)
python3 gsc-topic-discovery.py --min-impressions 50
```

### Daily Refresh (mejora de posts existentes)

```bash
cd /home/devops/projects/inforeparto/scripts
source ~/.env.projects

python3 daily-refresh.py
python3 daily-refresh.py --dry-run
python3 daily-refresh.py --post-id 590   # Refrescar un post específico
```

### GSC Indexing (notificar a Google)

```bash
cd /home/devops/projects/inforeparto/gsc-indexing
source ~/.env.projects

python3 index_urls.py                  # Indexar los últimos 10 posts publicados
python3 index_urls.py --post-id 590   # Indexar un post concreto
python3 index_urls.py --all-recent 20 # Indexar los últimos N posts
```

### Insertar tema manualmente en la cola

```bash
mysql -u wp_user -p wordpress_db -e "
INSERT INTO ir_topic_queue (site, keyword, source, priority)
VALUES ('inforeparto', 'tu tema aquí', 'manual', 0.8)
ON DUPLICATE KEY UPDATE priority=0.8, status='pending';
"
```

## Cron jobs configurados

```cron
# Daily Refresh — 03:00 diario
0 3 * * * cd /home/devops/projects/inforeparto/scripts && source /home/devops/.env.projects && python3 daily-refresh.py >> logs/daily-refresh-$(date +\%Y-\%m-\%d).log 2>&1

# GSC Topic Discovery — Lunes 04:00
0 4 * * 1 cd /home/devops/projects/inforeparto/scripts && source /home/devops/.env.projects && python3 gsc-topic-discovery.py >> logs/gsc-topic-discovery-$(date +\%Y-\%m-\%d).log 2>&1

# Autopublisher — 05:00 diario
0 5 * * * cd /home/devops/projects/inforeparto/scripts && source /home/devops/.env.projects && python3 autopublisher.py >> logs/autopublisher-$(date +\%Y-\%m-\%d).log 2>&1

# GSC Indexing — 10:00 diario
0 10 * * * python3 /home/devops/projects/inforeparto/gsc-indexing/index_urls.py >> /var/log/projects/gsc-indexing.log 2>&1
```

## Métricas de rendimiento esperadas

| Métrica | Valor |
|---------|-------|
| Tiempo medio de generación | ~3-4 min por post |
| NaturalScore objetivo | ≥ 70/100 |
| Posts por semana (cron) | 2-3 (cada 3 días) |
| Coste aproximado por post | ~0.15-0.25 € (API Anthropic) |

## Solución de problemas frecuentes

**El autopublisher no encuentra temas:**
```bash
# Ver la cola
mysql -u wp_user -p wordpress_db -e "SELECT keyword, status, priority FROM ir_topic_queue WHERE site='inforeparto' ORDER BY priority DESC LIMIT 10;"
# Si está vacía, insertar manualmente o esperar al lunes (gsc-topic-discovery)
```

**Las imágenes no se suben:**
Verificar que `WP_INFOREPARTO_USER` y `WP_INFOREPARTO_APP_PASSWORD` están en el entorno.

**NaturalScore siempre bajo:**
Revisar que Ollama está corriendo: `curl http://localhost:11434/api/tags`

**Posts con "autónomos" bloqueados:**
El pipeline hace 2 intentos. Si ambos fallan, el tema se resetea a 'pending'. Elegir un tema diferente o ajustar el brief.
