---
name: qa-retrospective
description: Skill de mejora continua del propio workflow. Cuando se detecta un error, amenaza u oportunidad en un flujo de trabajo, se actualiza el skill correspondiente para que no vuelva a ocurrir. No es un scanner de contenido.
---

# QA Retrospective — Mejora del Workflow

## Principio

Cada error cometido, cada corrección manual aplicada o cada mejora detectada en un flujo de trabajo **debe generar un cambio en el skill correspondiente**. El objetivo es que los errores nunca ocurran dos veces.

## Cuándo activar

- Al detectar un error durante o después de ejecutar cualquier tarea
- Cuando el usuario corrige algo que se hizo mal
- Cuando una corrección manual resulta evidente y repetible
- Al terminar un flujo largo (post completo, cluster de posts, cambio de configuración)

## Proceso de aprendizaje

### Paso 1 — Identificar el error y su causa raíz

No basta con "hubo un error". Hay que saber:
- ¿Qué ocurrió exactamente?
- ¿En qué paso del flujo?
- ¿Por qué ocurrió? (faltaba una instrucción, mal orden, datos no validados, etc.)
- ¿Qué skill o script debería haber evitado esto?

### Paso 2 — Clasificar la corrección

#### 🟢 MENOR — Aplicar autónomamente + informar

El skill o script se puede actualizar de forma segura sin afectar funcionalidad existente.

Ejemplos:
- Añadir `--post_author=1` a un comando que lo olvidaba
- Añadir una comprobación a un script
- Actualizar una regla en un SKILL.md
- Registrar un error conocido en el historial

**Acción:** Actualizar el skill → informar al usuario: *"He corregido el skill X para que no vuelva a pasar esto."*

#### 🟡 MEDIO — Proponer + pedir confirmación

El cambio afecta comportamiento habitual o podría tener efectos secundarios.

Ejemplos:
- Cambiar el orden de pasos en un workflow
- Añadir una validación que podría rechazar inputs válidos
- Modificar un script de producción
- Cambiar la configuración por defecto de una herramienta

**Acción:** Describir el cambio propuesto → esperar confirmación → aplicar.

#### 🔴 MAYOR — Siempre pedir confirmación

Cambios que afectan al sitio en producción, al código crítico o a la seguridad.

Ejemplos:
- Cambiar lógica del naturalizador
- Modificar funciones.php del tema
- Cambiar estructura de URLs o slugs
- Tocar credenciales o configuración de APIs

## Historial de aprendizaje

| Fecha | Error detectado | Causa raíz | Corrección aplicada | Skill actualizado |
|---|---|---|---|---|
| 2026-03-24 | Posts creados sin autor (post_author=0) | `wp post create` sin `--post_author` | Añadida regla + ejemplo en wp-publish | ✅ wp-publish |
| 2026-03-24 | Ping de sitemap a Google devolvía 404 | API deprecada en 2023 | Migrado a Indexing API | ✅ wp-publish |
| 2026-03-24 | `{{EMAIL_CONTACTO}}` placeholder en producción | Template no personalizado antes de publicar | Revisión de placeholders en flujo de publicación | — |
| 2026-03-24 | Cuadro comparativo sin enlaces de afiliado | Skill amazon-affiliate no mencionaba tablas | Añadida sección "Cuadros comparativos" | ✅ amazon-affiliate |
| 2026-03-24 | scan.py corrompió posts al extraer contenido con `wp db query` | La extracción TSV rompe contenido con newlines embebidos; el fix en Python sobreescribió datos parciales | Eliminar scan.py de producción; fix real via MySQL REPLACE directo | ✅ qa-retrospective |
| 2026-03-24 | scan.py añadía disclaimer a posts que ya lo tenían | No verificaba presencia antes de añadir | No repetir este patrón; siempre verificar antes de insertar contenido | ✅ qa-retrospective |

## Regla para modificar posts masivamente

**NUNCA** usar `wp db query SELECT` + Python + `wp post update` para modificar contenido en masa.
- El TSV de `wp db query` escapa newlines, lo que rompe el parseo de contenido multi-línea
- El método correcto para fixes en DB es `wp db query UPDATE` directamente (MySQL REPLACE, etc.)
- Para cambios individuales: `wp post get POST_ID --field=post_content` > archivo > `wp post update`

## Qué NO hace este skill

- No es un scanner periódico de posts
- No modifica contenido de posts directamente
- No genera informes automáticos sin que se lo pidan
