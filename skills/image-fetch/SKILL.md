---
name: image-fetch
description: Skill para buscar, descargar y subir imágenes a WordPress usando las APIs de Unsplash y Pexels. Usar cuando un post necesite imágenes destacadas o inline.
---

# Image Fetcher - inforeparto.com

## APIs disponibles

Las keys están en `~/.env.projects` (cargar con `source ~/.env.projects`):

- **Unsplash**: `$UNSPLASH_ACCESS_KEY`
- **Pexels**: `$PEXELS_API_KEY`

## Buscar imágenes

### Unsplash

```bash
curl -s "https://api.unsplash.com/search/photos?query=delivery+rider+city&per_page=5&orientation=landscape" \
  -H "Authorization: Client-ID $UNSPLASH_ACCESS_KEY" | python3 -c "
import json,sys
data=json.load(sys.stdin)
for r in data['results']:
    print(f\"ID: {r['id']} | {r['urls']['regular']} | {r['alt_description']}\")
"
```

### Pexels

```bash
curl -s "https://api.pexels.com/v1/search?query=delivery+rider&per_page=5&orientation=landscape" \
  -H "Authorization: $PEXELS_API_KEY" | python3 -c "
import json,sys
data=json.load(sys.stdin)
for p in data['photos']:
    print(f\"ID: {p['id']} | {p['src']['large']} | {p['alt']}\")
"
```

## Queries recomendadas por temática

| Tema del post | Query EN |
|---|---|
| Repartidores general | delivery rider bicycle city |
| Salarios/nóminas | person checking paycheck phone |
| Equipamiento | backpack thermal food delivery |
| Legal/derechos | worker rights protest sign |
| Apps/plataformas | smartphone delivery app screen |
| Bici/moto | motorcycle scooter urban delivery |
| Lluvia/mal tiempo | rain cycling city street |

Buscar siempre en inglés (mejores resultados).

## Descargar imagen

```bash
# Descargar a /tmp con nombre descriptivo
curl -sL "URL_DE_LA_IMAGEN" -o /tmp/img-slug-del-post.jpg
```

Preferir tamaños:
- Unsplash: usar `urls.regular` (1080px ancho) — NO `urls.full`
- Pexels: usar `src.large` (940px) — NO `src.original`

## Subir a WordPress media library

```bash
wp media import /tmp/img-slug-del-post.jpg \
  --title="Título descriptivo de la imagen" \
  --alt="Alt text con keyword SEO" \
  --caption="Foto: Unsplash" \
  --path=/var/www/html --allow-root
```

Captura el attachment ID del output (Success: Imported file ... as attachment ID XXX).

## Asignar como featured image

```bash
wp post meta set POST_ID _thumbnail_id ATTACHMENT_ID \
  --path=/var/www/html --allow-root
```

## Insertar imagen inline en el contenido

Obtener la URL de WordPress de la imagen subida:

```bash
wp post get ATTACHMENT_ID --field=guid \
  --path=/var/www/html --allow-root
```

Insertar en el HTML del post:

```html
<img src="URL_WORDPRESS" alt="Alt text SEO" width="800" loading="lazy" />
```

## Reglas

- NUNCA hotlinkear imágenes de Unsplash/Pexels (siempre descargar)
- SIEMPRE descargar tamaño regular/large, nunca original
- SIEMPRE añadir alt text descriptivo con keyword del post
- Formato JPEG para fotos, PNG solo si tiene transparencia
- Cada post necesita: 1 featured image + 1-2 inline
- Limpiar /tmp después: `rm /tmp/img-*.jpg`
- Si Unsplash no tiene resultados buenos, probar Pexels y viceversa
- Atribución no obligatoria (licencia libre) pero caption "Foto: Unsplash" es cortesía
