---
name: wp-publish
description: Skill para publicar, actualizar y gestionar posts en WordPress de inforeparto.com. Usar siempre que haya que interactuar con la base de datos de WordPress o con wp-cli.
---

# WordPress Publisher - inforeparto.com

## Configuración

- Base de datos: MariaDB, `wordpress_db`
- WP path: `/var/www/html`
- WP-CLI: `wp --path=/var/www/html --allow-root`
- Tabla posts: `wp_posts`
- Tabla meta: `wp_postmeta`
- Usuario MySQL: root (local)

## Crear un post borrador

```bash
wp post create \
  --post_title="Título del post" \
  --post_content="$(cat /tmp/post-content.html)" \
  --post_status=draft \
  --post_type=post \
  --post_name="slug-del-post" \
  --path=/var/www/html --allow-root
```

Captura el ID devuelto para asignar meta, categorías e imagen.

## Asignar categoría y tags

```bash
# Listar categorías existentes
wp term list category --fields=term_id,name --path=/var/www/html --allow-root

# Asignar categoría (usa el ID o nombre)
wp post term set POST_ID category "Fiscalidad y Legalidad" --path=/var/www/html --allow-root

# Asignar tags
wp post term set POST_ID post_tag "tag1" "tag2" "tag3" --path=/var/www/html --allow-root
```

## Meta SEO (Rank Math)

Inforeparto usa Rank Math SEO. Los meta fields son:

```bash
# Meta title
wp post meta set POST_ID rank_math_title "Meta title aquí" --path=/var/www/html --allow-root

# Meta description
wp post meta set POST_ID rank_math_description "Meta description aquí" --path=/var/www/html --allow-root

# Focus keyword
wp post meta set POST_ID rank_math_focus_keyword "keyword principal" --path=/var/www/html --allow-root
```

## Publicar con fecha específica

```bash
# Publicar inmediatamente
wp post update POST_ID --post_status=publish --path=/var/www/html --allow-root

# Programar publicación futura
wp post update POST_ID \
  --post_status=future \
  --post_date="2026-04-01 09:00:00" \
  --path=/var/www/html --allow-root
```

## Buscar posts existentes

```bash
# Por título o contenido (para enlaces internos)
wp post list --post_type=post --post_status=publish \
  --fields=ID,post_title,post_name \
  --path=/var/www/html --allow-root | grep -i "keyword"

# Posts recientes
wp post list --post_type=post --post_status=publish \
  --posts_per_page=20 --orderby=date --order=DESC \
  --fields=ID,post_title,post_date \
  --path=/var/www/html --allow-root
```

## Enlaces internos

Siempre buscar posts relacionados antes de publicar:

```bash
wp db query "SELECT ID, post_title, post_name FROM wp_posts 
  WHERE post_status='publish' AND post_type='post' 
  AND (post_title LIKE '%keyword%' OR post_content LIKE '%keyword%') 
  LIMIT 10" --path=/var/www/html --allow-root
```

Formato de enlace interno: `<a href="https://inforeparto.com/slug-del-post/">texto ancla</a>`

## Actualizar post existente

```bash
# Primero backup
wp db export /var/backups/wp_posts_pre_edit_$(date +%Y%m%d).sql \
  --tables=wp_posts --path=/var/www/html --allow-root

# Actualizar contenido desde archivo
wp post update POST_ID /tmp/nuevo-contenido.html \
  --path=/var/www/html --allow-root
```

## Indexación en Google tras publicar

Después de publicar o programar un post, enviar URL a Google Indexing API:

```bash
python3 /home/devops/projects/inforeparto/gsc-indexing/index_urls.py --post-id POST_ID
```

Para indexar los últimos N posts:

```bash
python3 /home/devops/projects/inforeparto/gsc-indexing/index_urls.py --all-recent 10
```

Credenciales: `/home/devops/.credentials/gsc-serviceaccount.json`

## Reglas

- SIEMPRE hacer backup antes de UPDATE masivos
- SIEMPRE guardar como draft primero, nunca publicar directamente
- SIEMPRE verificar que la categoría existe antes de asignarla
- SIEMPRE asignar el post al autor (user ID 1, "Redacción Inforeparto") al crear o actualizar. Posts sin autor son penalizados por AdSense (E-E-A-T). Verificar con: `wp post get POST_ID --field=post_author`
- El contenido HTML debe ser limpio: <p>, <h2>, <h3>, <table>, <ul>, <a>
- No usar clases CSS inventadas ni bloques Gutenberg complejos
- No usar shortcodes que no estén registrados en el tema

## Asignar autor al crear posts

```bash
wp post create \
  --post_title="Título" \
  --post_content="$(cat /tmp/contenido.html)" \
  --post_status=draft \
  --post_author=1 \
  --path=/var/www/html --allow-root
```

Verificar que ningún post queda huérfano:

```bash
wp db query "SELECT ID, post_title FROM wp_posts WHERE post_status='publish' AND post_type='post' AND post_author=0" --path=/var/www/html --allow-root
```
