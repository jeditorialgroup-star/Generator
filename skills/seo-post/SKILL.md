---
name: seo-post
description: Skill de optimización SEO para posts de inforeparto.com. Usar al crear o revisar cualquier post para asegurar que cumple buenas prácticas SEO.
---

# SEO Optimizer - inforeparto.com

## Checklist SEO obligatoria

Antes de guardar cualquier post, verificar todos estos puntos:

### Keyword principal
- [ ] Aparece en el título (H1/post_title)
- [ ] Aparece en el primer párrafo (primeras 100 palabras)
- [ ] Aparece en al menos un H2
- [ ] Aparece 3-5 veces en total (densidad ~1-1.5%)
- [ ] Aparece en el slug
- [ ] Aparece en el meta title
- [ ] Aparece en el meta description
- [ ] Aparece en el alt text de al menos una imagen

### Estructura
- [ ] Meta title: máximo 60 caracteres (incluir keyword al inicio)
- [ ] Meta description: 140-160 caracteres (incluir keyword, call to action)
- [ ] Slug: corto, con keyword, separado por guiones
- [ ] Un solo H1 (el título del post)
- [ ] H2 para secciones principales (3-6 por post)
- [ ] H3 solo como subsecciones dentro de H2
- [ ] Párrafos cortos (2-4 frases)
- [ ] Al menos una lista (<ul> o <ol>) en el post
- [ ] Al menos una tabla si hay datos comparativos

### Enlaces
- [ ] 2-4 enlaces internos a otros posts de inforeparto
- [ ] 1-3 enlaces externos a fuentes autoritativas (BOE, sindicatos, medios)
- [ ] Enlaces externos con target="_blank" rel="noopener"
- [ ] Anchor text descriptivo (no "haz clic aquí")

### Contenido
- [ ] Extensión mínima: 1.200 palabras (ideal 1.500-2.000)
- [ ] Introducción que enganche (problema o pregunta del lector)
- [ ] Contenido que responde la intención de búsqueda
- [ ] Datos concretos y verificables (no genéricos)
- [ ] Conclusión con call to action o resumen práctico

### Imágenes
- [ ] Featured image con alt text + keyword
- [ ] 1-2 imágenes inline con alt text descriptivo
- [ ] Atributo loading="lazy" en imágenes inline

## Meta fields Rank Math

```bash
# Configurar SEO del post
wp post meta set POST_ID rank_math_title "KEYWORD | inforeparto" --path=/var/www/html --allow-root
wp post meta set POST_ID rank_math_description "Descripción con keyword y CTA" --path=/var/www/html --allow-root
wp post meta set POST_ID rank_math_focus_keyword "keyword principal" --path=/var/www/html --allow-root
```

## Patrones de meta title para inforeparto

| Tipo de post | Patrón |
|---|---|
| Guía/tutorial | Keyword principal + pipe + complemento |
| Comparativa | Keyword 2026 + pipe + vs o ranking |
| Informativo | Keyword + pipe + dato clave |
| Listado | N mejores + keyword + año |

Ejemplos:
- `Tablas salariales riders 2026 | Convenios Glovo, Just Eat, Uber Eats`
- `Mejores mochilas térmicas para repartidores 2026 | Top 7`
- `Cómo leer tu nómina de rider | Línea a línea`

## Keywords de inforeparto (nicho)

Clusters principales:
- **Salarios**: tablas salariales riders, sueldo repartidor, nómina rider, cuánto gana rider
- **Legal**: Ley Rider, convenio colectivo riders, derechos repartidores, alta autónomo rider
- **Plataformas**: Glovo opiniones, Just Eat repartidor, Uber Eats España
- **Equipamiento**: mochila térmica repartidor, móvil para riders, accesorios reparto
- **Ganancias**: cuánto se gana en Glovo, trucos repartidor, mejores horas reparto

## Enlazado interno

Buscar siempre posts relacionados antes de publicar:

```bash
# Buscar por keywords del cluster
wp db query "SELECT ID, post_title, post_name FROM wp_posts 
  WHERE post_status='publish' AND post_type='post' 
  AND (post_title LIKE '%rider%' OR post_title LIKE '%repartidor%' 
  OR post_title LIKE '%salario%' OR post_title LIKE '%convenio%') 
  LIMIT 20" --path=/var/www/html --allow-root
```

Insertar 2-4 enlaces internos de forma natural en el texto.

## Reglas

- NUNCA keyword stuffing (más de 2% de densidad es spam)
- NUNCA H2 o H3 que sean solo la keyword exacta
- Los títulos H2 deben sonar naturales, no robóticos
- Meta description debe incluir un beneficio para el lector
- Slug máximo 5 palabras separadas por guiones
