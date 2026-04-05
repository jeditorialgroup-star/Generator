# CRON_SCHEDULE — Pipeline SEO (referencia definitiva)

Todos los crons corren como usuario `devops`. Logs en `scripts/logs/` o `/var/log/projects/`.

---

## Tabla maestra de cron jobs

| Hora  | Frecuencia  | Script                              | Descripción                                  |
|-------|-------------|--------------------------------------|----------------------------------------------|
| 02:00 | Quincenal   | `affiliate_catalog_updater.py`       | Actualiza catálogo de afiliados              |
| 02:00 | Diario      | `infra/backup-scripts/backup-db.sh`  | Backup MariaDB + PostgreSQL                  |
| 02:30 | Quincenal   | `experience_enricher.py`             | Enriquece ExperienceDB con testimonios reales|
| 03:00 | Diario      | `daily-refresh.py --site X`          | Refresca posts con bajo rendimiento (opportunity_score) |
| 04:00 | Lunes       | `gsc-topic-discovery.py --site X`    | Descubre nuevos temas desde GSC              |
| 05:00 | Diario      | `autopublisher.py --site X`          | Genera y programa post nuevo                 |
| 10:00 | Diario      | `gsc-indexing/index_urls.py --site X`| Notifica Google/Bing de URLs nuevas          |
| 11:00 | Diario      | `seo_health_check.py`                | Verifica salud SEO técnica                   |
| 08:30 | Domingos    | `affiliate_report.py`                | Reporte semanal de clicks de afiliado        |
| 20:00 | Domingos    | `performance_report.py`              | Reporte semanal de rendimiento completo      |
| —     | WP Hook     | `ir-auto-index.php` (mu-plugin)      | Indexa post al transicionar future→publish   |

> Nota: los quincenal corren los días 1 y 15 de cada mes.

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
