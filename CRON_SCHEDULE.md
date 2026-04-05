# CRON_SCHEDULE — inforeparto.com

Todos los crons corren como usuario `devops`. Logs en `scripts/logs/` o `/var/log/projects/`.

---

## Procesos diarios

| Hora  | Script | Descripción | Dependencias |
|-------|--------|-------------|--------------|
| 03:00 | `scripts/daily-refresh.py` | Refresca posts existentes: GSC data, imágenes, embeddings, afiliados | MariaDB, Anthropic API (Batch), Pexels, Ollama |
| 04:00 | `naturalizer/scripts/update_metrics.py` | Actualiza métricas de naturalización en ir_naturalization_log | MariaDB |
| 05:00 | `scripts/autopublisher.py` | Genera y programa un nuevo post SEO | MariaDB, Anthropic API, Serper, Jina, Pexels, Ollama |
| 10:00 | `gsc-indexing/index_urls.py` | Notifica Google Indexing API + IndexNow para posts publicados | GSC Service Account, IndexNow key |
| 11:00 | `scripts/seo_health_check.py` | Verifica sitemap, 404s, canonicals, meta descriptions | MariaDB, HTTP |

## Procesos semanales

| Cuando | Script | Descripción | Dependencias |
|--------|--------|-------------|--------------|
| Lunes 04:00 | `scripts/gsc-topic-discovery.py` | Detecta gaps GSC + clasificación de intención → ir_topic_queue | MariaDB, GSC API, Ollama |
| Domingo 08:30 | `scripts/affiliate_report.py` | Reporte de clics en afiliados (top ASINs + top posts) | MariaDB, Telegram |
| Domingo 20:00 | `scripts/performance_report.py` | Informe semanal: top CTR, oportunidades, schema stats, score evolution | MariaDB, Telegram |

## Procesos quincenales

| Cuando | Script | Descripción | Dependencias |
|--------|--------|-------------|--------------|
| Días 1 y 15, 02:00 | `scripts/affiliate_catalog_updater.py` | Amplía catálogo de afiliados via Serper + Jina | Serper API, Jina API |
| Días 1 y 15, 03:30 | `scripts/experience_enricher.py` | Scraping de testimonios reales de repartidores → ir_experience_bank | Serper, Jina, Anthropic (Haiku), Ollama |

## Procesos del sistema

| Hora | Script | Descripción |
|------|--------|-------------|
| 02:00 | `infra/backup-scripts/backup-db.sh` | Backup diario de MariaDB y PostgreSQL |

---

## Flujo de dependencias

```
gsc-topic-discovery.py (lunes)
    → ir_topic_queue
        → autopublisher.py (05:00 diario)
            → WordPress (post status: future)
                → [cron WordPress] transición future→publish
                    → ir-auto-index.php (mu-plugin)
                        → index_urls.py --post-id
                            → Google Indexing API
                            → IndexNow (Bing/Yandex)

daily-refresh.py (03:00)
    → update_all_post_performance_metrics()
        → GSC page metrics (7d + 30d) para TODOS los posts
        → affiliate_clicks_30d desde ir_affiliate_clicks
        → post_performance (feedback loop)
    → get_posts_to_refresh() por opportunity_score
        → Lee posts con ≥100 imp, ≥60 días sin refresh
    → Actualiza imágenes, internal links, afiliados
    → Genera post_embeddings.json (usado por gsc-topic-discovery)

seo_health_check.py (11:00)
    → Verifica estado de posts publicados
    → Alerta Telegram solo si hay problemas

affiliate_catalog_updater.py (días 1+15)
    → Lee/amplía affiliate_catalog.json
    → genera affiliate_catalog_new.json para revisión manual
    → autopublisher.py usa affiliate_catalog.json en research phase

experience_enricher.py (días 1+15)
    → Serper search → Jina scrape → Haiku extraction
    → Cosine dedup via Ollama (threshold 0.85)
    → Inserta en ir_experience_bank
    → naturalizer usa ir_experience_bank en Capa 4

affiliate_report.py (domingos)
    → Lee ir_affiliate_clicks (click.php)
    → Resumen semanal por Telegram

performance_report.py (domingos 20:00)
    → Lee post_performance
    → Top clicks afiliado, top CTR, oportunidades CTR<2%
    → Estadísticas por schema type, evolución natural_score
    → Resumen semanal por Telegram
```

---

## Variables de entorno requeridas

Ver `.env.example` para la lista completa. Cargadas automáticamente via `python-dotenv` desde `~/.env.projects`.

## Notas

- `autopublisher.py` incluye gate de rendimiento: no corre si ya corrió hoy (salvo `--force`)
- `daily-refresh.py` selecciona posts por `opportunity_score` (impressions×0.4 + position×0.4 + CTR_penalty×0.2); solo posts con ≥100 impresiones_30d (o sin datos GSC) y ≥60 días de antigüedad
- `gsc-topic-discovery.py` añade columna `search_intent` a `ir_topic_queue` automáticamente si no existe
- IndexNow key: `2f5ab127cde204cb00580fbf5f32a504` — archivo de verificación en `/var/www/inforeparto/2f5ab127cde204cb00580fbf5f32a504.txt`
