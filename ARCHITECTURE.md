# ARCHITECTURE.md — inforeparto.com Content Pipeline

## 1. Los 4 procesos y sus dependencias

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         INFOREPARTO PIPELINE                              │
│                                                                            │
│  Lunes 04:00            Diario 03:00          Diario 05:00   Diario 10:00│
│  ┌─────────────┐        ┌─────────────┐       ┌───────────┐  ┌─────────┐ │
│  │    GSC      │        │   Daily     │       │  Auto-    │  │  GSC    │ │
│  │  Topic      │──────▶│   Refresh   │       │ publisher │  │Indexing │ │
│  │ Discovery   │        │             │       │           │  │         │ │
│  └──────┬──────┘        └──────┬──────┘       └─────┬─────┘  └────┬────┘ │
│         │                      │                     │             │      │
│         ▼                      ▼                     ▼             ▼      │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                      RECURSOS COMPARTIDOS                            │  │
│  │   MariaDB (ir_topic_queue, ir_naturalization_log, ir_experiences)   │  │
│  │   naturalizer.py (motor v4, 8 capas)                                │  │
│  │   post_embeddings.json (caché Ollama)                               │  │
│  │   WordPress (WP-CLI + REST API)                                     │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

### Dependencias entre procesos

| Proceso | Depende de | Produce |
|---------|-----------|---------|
| `gsc-topic-discovery` | GSC API, Ollama (dedup semántico), `ir_topic_queue` | Filas en `ir_topic_queue` |
| `autopublisher` | `ir_topic_queue`, todas las APIs, `naturalizer.py`, WP | Post en WP + fila en `ir_naturalization_log` |
| `daily-refresh` | WP (posts existentes), GSC API, `naturalizer.py` | Post actualizado en WP + métricas en `ir_naturalization_log` |
| `index_urls.py` | WP (slugs de posts publicados), Google Indexing API | Notificaciones de indexación enviadas a Google |

---

## 2. Flujo de datos completo

```
GSC API ──────────────────────────────────────────────────────────┐
  │                                                                │
  │ (queries, posiciones, impresiones)                            │ (métricas CTR, posición)
  ▼                                                                ▼
gsc-topic-discovery.py                               daily-refresh.py
  │                                                        │
  │ [dedup semántico via Ollama]                          │ [posts ≥100 días, sin buen rendimiento]
  │                                                        │
  ▼                                                        │
ir_topic_queue                                             │
  │ (keyword, priority, source, status)                   │
  │                                                        │
  ▼                                                        ▼
autopublisher.py ──────────────────────────────▶ naturalizer.py
  │                                                 (8 capas)
  │ RESEARCH PHASE:                                  │
  │  ├─ Serper → análisis competitivo (Capa 6)      │ Capa 1: eliminar patrones IA
  │  ├─ Serper+Jina → fuentes verificadas (Capa 5b) │ Capa 2: inyectar voz
  │  ├─ ir_experiences → testimonios (Capa 4)       │ Capa 3: varianza sintáctica
  │  ├─ Ollama → links internos semánticos          │ Capa 3b: apertura gancho
  │  └─ affiliate_catalog.json → afiliados          │ Capa 5b: inyectar fuentes
  │                                                  │ Capa 6b: autor + JSON-LD
  │ GENERATION:                                      │ Capa 7: NaturalScore
  │  Claude Sonnet 4.6 + brief → HTML               │ Capa 8: integridad
  │                                                  │
  │◀────────────────────────────────────────────────┘
  │  (contenido naturalizado, score, issues)
  │
  ├─ [score ≥ 70] ──▶ WordPress (WP-CLI post create --future)
  │                      └─ Pexels → imágenes inline + featured
  │                      └─ ir_naturalization_log (INSERT)
  │                      └─ ir_topic_queue (status = 'done')
  │                      └─ Telegram (notificación éxito)
  │
  └─ [score < 70] ──▶ WordPress (WP-CLI draft)
                       └─ Telegram (notificación alerta)

WordPress (posts publicados)
  │
  └─▶ index_urls.py ──▶ Google Indexing API (URL_UPDATED)
       [10:00 diario]    [solicita rastreo inmediato]

post_embeddings.json (actualizado por daily-refresh)
  │
  └─▶ autopublisher (links internos + dedup temático)
  └─▶ gsc-topic-discovery (dedup semántico de la cola)
```

---

## 3. Tablas MariaDB

### `ir_topic_queue` — Cola de temas pendientes

```sql
CREATE TABLE ir_topic_queue (
  id               INT AUTO_INCREMENT PRIMARY KEY,
  site             VARCHAR(50) NOT NULL DEFAULT 'inforeparto',
  keyword          VARCHAR(255) NOT NULL,
  source           ENUM('gsc_gap','manual','serper_paa','embedding_gap') DEFAULT 'manual',
  priority         FLOAT NOT NULL DEFAULT 0.5,        -- 0-1, mayor = más urgente
  status           ENUM('pending','in_progress','done','skipped') DEFAULT 'pending',
  gsc_impressions  INT DEFAULT NULL,                  -- impresiones en GSC
  gsc_avg_position FLOAT DEFAULT NULL,                -- posición media en GSC
  created_at       DATETIME DEFAULT NOW(),
  processed_at     DATETIME DEFAULT NULL,
  wp_post_id       INT DEFAULT NULL,                  -- ID del post generado
  notes            TEXT DEFAULT NULL,                 -- motivo de error/skip
  UNIQUE KEY uk_site_keyword (site, keyword)
);
```

**Ciclo de vida de un topic:**
```
pending → in_progress → done       (publicado correctamente)
                      → pending    (error recuperable: API falla, score bajo)
                      → skipped    (tema prohibido, bloqueado por Ley Rider)
```

### `ir_naturalization_log` — Log de posts procesados

```sql
CREATE TABLE ir_naturalization_log (
  id                 INT AUTO_INCREMENT PRIMARY KEY,
  site               VARCHAR(50),
  topic              VARCHAR(200),
  wp_post_id         INT,
  score_before       FLOAT,                    -- NaturalScore antes (solo daily-refresh)
  score_after        FLOAT,                    -- NaturalScore tras naturalización
  experiences_used   JSON,                     -- testimonios inyectados
  sources_added      JSON,                     -- fuentes verificadas inyectadas
  pageviews_30d      INT,                      -- visitas últimos 30 días (GSC)
  avg_time_on_page   FLOAT,                    -- tiempo medio (GSC)
  avg_position       FLOAT,                    -- posición media Google (GSC)
  ctr                FLOAT,                    -- CTR en Google (GSC)
  created_at         TIMESTAMP DEFAULT NOW(),
  metrics_updated_at TIMESTAMP,               -- última actualización de métricas GSC
  INDEX idx_site_post (site, wp_post_id),
  INDEX idx_created (created_at DESC)
);
```

**Performance gate en daily-refresh:**
Posts con `avg_position ≤ 20 AND pageviews_30d ≥ 15` se excluyen del refresh (ya van bien).

### `ir_experiences` — Experiencias reales de repartidores (Capa 4)

Gestionada por `experience_db.py` y `scripts/seed_experiences.py`.

Campos principales: `site`, `type` (metric/anecdote/regulatory/comparison/user_feedback/process_insight), `content`, `topics` (JSON array de keywords relevantes), `used_count`, `created_at`.

### Meta WP especial

| Meta key | Valor | Propósito |
|----------|-------|-----------|
| `_ir_autopublished` | `1` | Marca posts de la serie del autopublisher para el cálculo del calendario de publicación |
| `_thumbnail_id` | ID attachment | Imagen destacada del post |

---

## 4. APIs externas

### Anthropic Claude

| Modelo | Uso | Coste aprox. |
|--------|-----|-------------|
| `claude-sonnet-4-6` | Generación post + naturalización (Capas 1-3b) | ~$0.003/1K tokens out |
| `claude-haiku-4-5-20251001` | Tareas rápidas: queries Pexels, integridad (Capa 8), competitive brief | ~$0.00025/1K tokens out |

Coste estimado por post completo: **~0.15-0.25 €**

Rate limits: 1M tokens/min (Sonnet), sin límite práctico para este volumen.

### Google Search Console API

- **Uso:** Lectura de queries, posiciones, impresiones, CTR
- **Autenticación:** Service Account JSON (`/home/devops/.credentials/gsc-serviceaccount.json`)
- **Scopes:** `https://www.googleapis.com/auth/webmasters.readonly`
- **Límites:** 1.200 consultas/día, máx. 25.000 filas por consulta
- **Latencia datos:** 2-3 días de retraso en GSC (datos no son en tiempo real)

### Google Indexing API

- **Uso:** Notificar a Google que una URL ha sido actualizada (indexación prioritaria)
- **Autenticación:** Mismo service account que GSC
- **Scopes:** `https://www.googleapis.com/auth/indexing`
- **Límites:** 200 notificaciones/día (cuota estándar)
- **Nota:** Técnicamente diseñada para JobPosting/BroadcastEvent, pero funciona para cualquier URL

### Serper.dev

- **Uso:** Análisis competitivo (top 10 Google para el keyword), búsqueda de fuentes
- **Límites plan Free:** 2.500 consultas/mes. Pipeline usa ~3-4 consultas por post.
- **Coste a 7 posts/semana:** ~12 consultas/semana → ~50/mes (dentro del free tier)

### Jina.ai Reader

- **Uso:** Extraer texto de URLs (verificar que las fuentes tienen contenido relevante)
- **Endpoint:** `https://r.jina.ai/{url}`
- **Límites:** Rate limit en free tier. Con API key, más generoso.
- **Coste:** Free tier disponible; ~$0.002/1K tokens si se supera

### Pexels API

- **Uso:** Imágenes de stock (1 featured + 2 inline por post)
- **Límites:** 200 requests/hora, 20.000/mes — gratuito
- **Parámetros usados:** `locale=es-ES`, `orientation=landscape`

### Ollama (local, sin coste)

- **Modelo:** `nomic-embed-text` (embedding de 768 dimensiones)
- **Uso:** Deduplicación semántica de temas + búsqueda de links internos
- **RAM requerida:** ~500 MB
- **Latencia:** ~50-200ms por embedding

---

## 5. Configuración del motor de naturalización (settings.yaml)

```yaml
models:
  naturalizacion: "claude-sonnet-4-6"        # Calidad alta: Capas 1-3b
  integridad: "claude-haiku-4-5-20251001"    # Coste bajo: Capa 8

natural_score:
  thresholds:
    ok: 70       # ≥70: publicar directamente
    retry: 50    # 50-69: reintentar (hasta max_retries veces)
    human: 50    # <50: guardar como borrador + alerta Telegram
  max_retries: 2
  weights:
    burstiness: 0.20          # Variedad en longitud de frases
    lexical_diversity: 0.20   # Riqueza de vocabulario (MATTR)
    pattern_detection: 0.25   # Penalización por frases genéricas IA
    paragraph_variance: 0.10  # Variedad en longitud de párrafos
    opening_score: 0.15       # Calidad de la apertura (anti-genérico)
    source_density: 0.10      # Densidad de fuentes citadas
```

---

## 6. Reglas editoriales (editorial_rules.yaml)

### Temas prohibidos

| Patrón | Excepción | Motivo |
|--------|-----------|--------|
| autónomo, autónomos, RETA, cuota autónomo | Amazon Flex / Amazon Logistics | Ley Rider RDL 9/2021: riders de plataforma son asalariados |
| fraude, b negro, en negro, evasión, no declarar | — | Evasión fiscal o fraude laboral |
| alquiler de cuenta, alquilar cuenta | — | Práctica ilegal en plataformas |

### Red flags (frases que bloquean o alertan)

| Patrón | Motivo |
|--------|--------|
| "debes declarar" | Asesoramiento fiscal concreto |
| "te puedes deducir" | Usar "es posible deducir" en su lugar |
| "tienes derecho a indemnización de" | Asesoramiento legal con cifra |
| "demanda a " | Instrucción legal directa |

### Disclaimer universal

Se inyecta al final del post si el contenido contiene keywords de riesgo (IRPF, seguro, despido, sindicato, ganancias, convenio salarial, etc.). Un único bloque gris que cubre todas las casuísticas.
