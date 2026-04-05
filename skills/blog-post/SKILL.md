---
name: blog-post
description: Skill orquestador para crear posts completos en inforeparto.com. Usar cuando el usuario pida crear un post sobre cualquier tema. Encadena investigación, redacción, SEO, imágenes, enlaces de afiliado y naturalización.
---

# Blog Post Creator - inforeparto.com

Skill orquestador. Lee las skills específicas según lo que necesite cada paso.

## Contexto del sitio

- **inforeparto.com**: blog sobre reparto a domicilio en España (Glovo, Uber Eats, Just Eat)
- **Audiencia**: repartidores actuales y personas que quieren empezar
- **Tono**: repartidor veterano que ayuda a los nuevos, cercano, con jerga del sector
- **WordPress en**: /var/www/html (base de datos: wordpress_db)
- **Skills en**: ~/projects/inforeparto/skills/

## Workflow de creación de un post

Cuando el usuario pida crear un post, seguir este orden:

### Paso 1: Investigación
- Usar web search para encontrar datos REALES y actualizados
- NUNCA inventar cifras, leyes, o datos
- Anotar las fuentes (URL, nombre del medio, fecha)
- Si un dato no se puede verificar, marcarlo como "pendiente de confirmación"

### Paso 2: Redacción
- Leer la skill `seo-post` (~/projects/inforeparto/skills/seo-post/SKILL.md)
- Escribir el contenido en HTML limpio
- Extensión: 1.500-2.000 palabras
- Incluir tabla HTML si hay datos comparativos
- Buscar posts relacionados para enlaces internos
- Citar fuentes de forma natural en el texto

### Paso 3: SEO
- Aplicar el checklist de `seo-post`
- Definir: meta title, meta description, slug, focus keyword
- Verificar densidad de keyword (~1-1.5%)

### Paso 4: Imágenes
- Leer la skill `image-fetch` (~/projects/inforeparto/skills/image-fetch/SKILL.md)
- Buscar y subir: 1 featured image + 1-2 inline
- Asignar alt text con keyword

### Paso 5: Enlaces de afiliado (solo si procede)
- Leer la skill `amazon-affiliate` (~/projects/inforeparto/skills/amazon-affiliate/SKILL.md)
- Solo añadir si el post menciona productos comprables
- Posts informativos puros (legal, salarios) NO llevan afiliados
- Si lleva afiliados: añadir aviso de afiliación

### Paso 6: Guardar borrador
- Leer la skill `wp-publish` (~/projects/inforeparto/skills/wp-publish/SKILL.md)
- Guardar como draft (NUNCA publicar directamente)
- Asignar categoría, tags, meta SEO, featured image
- MOSTRAR AL USUARIO el borrador para revisión

### Paso 7: Revisión legal (OBLIGATORIO)
- Leer la skill `legal-review` (~/projects/inforeparto/skills/legal-review/SKILL.md)
- Ejecutar revisión completa del borrador
- Mostrar informe al usuario con veredicto
- Si hay ALERTAS ROJAS: parar. No continuar hasta resolver
- Si hay DISCLAIMERS: añadirlos antes de continuar
- Si hay REVISIONES: corregir redacción
- Esperar aprobación del usuario

### Paso 8: Naturalización (tras aprobación legal)
- Leer la skill `naturalizer` (~/projects/inforeparto/skills/naturalizer/SKILL.md)
- Ejecutar en dry-run primero
- Si OK, ejecutar con backup
- Mostrar resultado al usuario

### Paso 9: Publicación (solo con fecha del usuario)
- El usuario indica la fecha de publicación
- Programar con wp-cli
- Confirmar al usuario

## Modelos por tarea

Leer la skill `model-router` (~/projects/inforeparto/skills/model-router/SKILL.md)
para asignar el modelo correcto a cada paso. Resumen rápido:

| Paso | Modelo |
|---|---|
| Investigación | sesión Claude Code |
| Redacción | sonnet |
| SEO check | haiku |
| Imágenes | haiku |
| Afiliados | haiku |
| Legal review | opus |
| Naturalización | sonnet |
| Publicar | haiku |

## Ejemplo de interacción mínima

El usuario dice:
> "Crea un post sobre las mejores mochilas térmicas para repartidores"

Claude Code:
1. Busca en Google mochilas térmicas para riders
2. Busca ASINs en los resultados
3. Redacta el post con SEO optimizado
4. Busca imágenes en Unsplash/Pexels
5. Añade enlaces de afiliado + aviso
6. Guarda como borrador
7. Muestra al usuario para revisión
8. Tras aprobación: naturaliza
9. Tras aprobación: programa publicación

## Categorías de inforeparto

| Categoría | Cuándo usarla |
|---|---|
| Ganancias | Cuánto se gana, trucos, estrategias |
| Fiscalidad y Legalidad | Leyes, convenios, impuestos, nóminas |
| Plataformas | Reviews de Glovo, Just Eat, Uber Eats |
| Equipamiento | Mochilas, móviles, accesorios, ropa |
| Guías | Cómo empezar, tutoriales paso a paso |

## Reglas generales

- SIEMPRE investigar antes de escribir
- NUNCA publicar sin aprobación del usuario
- NUNCA inventar datos ni cifras
- Los posts informativos (legal/salarios) NO llevan afiliados
- Los posts de equipamiento/productos SÍ llevan afiliados
- Naturalizar SIEMPRE como último paso
- Cada skill se lee bajo demanda, no se carga todo de golpe
