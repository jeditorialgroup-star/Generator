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

## Procesos quincenales

| Cuando | Script | Descripción | Dependencias |
|--------|--------|-------------|--------------|
| Días 1 y 15, 02:00 | `scripts/affiliate_catalog_updater.py` | Amplía catálogo de afiliados via Serper + Jina | Serper API, Jina API |

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
    → Lee posts con status publish
    → Actualiza GSC metrics, imágenes, internal links
    → Genera post_embeddings.json (usado por gsc-topic-discovery)

seo_health_check.py (11:00)
    → Verifica estado de posts publicados
    → Alerta Telegram solo si hay problemas

affiliate_catalog_updater.py (días 1+15)
    → Lee/amplía affiliate_catalog.json
    → genera affiliate_catalog_new.json para revisión manual
    → autopublisher.py usa affiliate_catalog.json en research phase

affiliate_report.py (domingos)
    → Lee ir_affiliate_clicks (click.php)
    → Resumen semanal por Telegram
```

---

## Variables de entorno requeridas

Ver `.env.example` para la lista completa. Cargadas automáticamente via `python-dotenv` desde `~/.env.projects`.

## Notas

- `autopublisher.py` incluye gate de rendimiento: no corre si ya corrió hoy (salvo `--force`)
- `daily-refresh.py` incluye performance gate: excluye posts con `avg_position ≤ 20 AND clicks ≥ 15`
- `gsc-topic-discovery.py` añade columna `search_intent` a `ir_topic_queue` automáticamente si no existe
- IndexNow key: `2f5ab127cde204cb00580fbf5f32a504` — archivo de verificación en `/var/www/inforeparto/2f5ab127cde204cb00580fbf5f32a504.txt`
