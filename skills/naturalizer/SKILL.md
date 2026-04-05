---
name: naturalizer
description: Skill para humanizar textos de inforeparto.com. Usar como último paso antes de publicar cualquier post. Elimina estilo IA y da tono de repartidor veterano.
---

# Naturalizer - inforeparto.com

## Agente

Script: `~/projects/inforeparto/naturalizer/naturalizer.py`

## Uso

```bash
# Primero dry-run para revisar
python3 ~/projects/inforeparto/naturalizer/naturalizer.py \
  --post-id POST_ID --dry-run --verbose

# Con backup y guardar
python3 ~/projects/inforeparto/naturalizer/naturalizer.py \
  --post-id POST_ID --backup

# Varios posts
python3 ~/projects/inforeparto/naturalizer/naturalizer.py \
  --post-id 123 456 789 --backup

# Los modificados hoy
python3 ~/projects/inforeparto/naturalizer/naturalizer.py \
  --modified-today --backup
```

## Qué hace

1. Lee el post de la base de datos
2. Envía el contenido a Claude API (sonnet) con prompt de humanización
3. Verifica que enlaces de Amazon y avisos de afiliados no se han alterado
4. Guarda el resultado

## Criterios de humanización

- Elimina palabras IA: "además", "en este sentido", "es importante destacar", "cabe mencionar", "sin duda", "asimismo", "no obstante", "resulta imprescindible"
- Usa jerga de repartidores: curro, pedido, ruta, mochila, app, zona, franja, pico, propina
- Varía longitud de frases, rompe estructuras paralelas
- Tono de repartidor veterano, tutea siempre
- Máximo 3-4 negritas por post
- H2/H3 naturales, no SEO robóticos

## Contenido protegido (NUNCA se modifica)

- Bloques con clase `aviso-afiliados`
- Enlaces de Amazon (`amazon.es/dp/`)
- Datos legales, leyes, cifras con fuente
- Shortcodes de WordPress
- Tablas HTML con datos

## Reglas

- SIEMPRE usar --dry-run primero
- SIEMPRE usar --backup en producción
- SIEMPRE revisar el resultado antes de dar por bueno
- Si el verificador detecta que un enlace de Amazon cambió, el post NO se guarda
- Ejecutar DESPUÉS de que el contenido esté aprobado (datos verificados, SEO OK)
- Es el ÚLTIMO paso antes de publicar
