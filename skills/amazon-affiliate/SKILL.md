---
name: amazon-affiliate
description: Skill para gestionar enlaces de afiliado de Amazon en posts de inforeparto.com. Usar cuando un post necesite enlaces a productos de Amazon.
---

# Amazon Afiliados - inforeparto.com

## Formato de enlace oficial

Según la documentación de Amazon Afiliados España:

```
https://www.amazon.es/dp/ASIN/ref=nosim?tag=inforeparto-21
```

- **ASIN**: código de 10 caracteres alfanuméricos del producto
- **tag**: `inforeparto-21` (SIEMPRE este, no cambiar)
- **ref=nosim**: va en la ruta, antes del `?`

## Cómo encontrar ASINs

NO hacer scraping de Amazon. Buscar vía web search:

```
buscar en Google: site:amazon.es "producto buscado"
```

El ASIN aparece en la URL de Amazon: `amazon.es/dp/B09V3KXJPB/`

También aparece en la página del producto en "Detalles del producto".

## Insertar enlace en el post

```html
Si necesitas una mochila térmica resistente, la 
<a href="https://www.amazon.es/dp/B09V3KXJPB/ref=nosim?tag=inforeparto-21" 
   target="_blank" rel="nofollow noopener">Nombre del Producto</a> 
es una de las más usadas entre repartidores.
```

Atributos obligatorios:
- `target="_blank"` (abre en nueva pestaña)
- `rel="nofollow noopener"` (nofollow para afiliados)

## Aviso de afiliación

OBLIGATORIO en cada post que contenga enlaces de afiliado.
Insertar después del primer o segundo párrafo:

```html
<p class="aviso-afiliados"><em>Este artículo contiene 
enlaces de afiliado de Amazon. Si compras a través de 
ellos, inforeparto recibe una pequeña comisión sin 
coste adicional para ti. Esto nos ayuda a mantener 
el sitio.</em></p>
```

## Cuadros comparativos

Cuando un post incluya una tabla comparativa de productos, SIEMPRE añadir enlace de afiliado en la primera columna (nombre del producto):

```html
<table>
  <thead>
    <tr>
      <th>Casco</th>
      <th>Homologación</th>
      ...
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><a href="https://www.amazon.es/dp/ASIN/ref=nosim?tag=inforeparto-21" target="_blank" rel="nofollow noopener">Nombre Producto</a></td>
      <td>EN 1078</td>
      ...
    </tr>
  </tbody>
</table>
```

- El enlace va en el `<td>` del nombre, no en el `<th>` del encabezado
- Mismos atributos obligatorios: `target="_blank" rel="nofollow noopener"`
- Si el producto ya tiene enlace en el cuerpo del post, igualmente añadirlo en la tabla — son puntos de conversión independientes
- Los enlaces de tabla NO cuentan para el límite de 5-8 por post (son navegación estructural)

## Reglas de la política de Amazon

- NO incluir precios de productos (no tenemos PA API)
- NO incluir imágenes de Amazon
- Si se menciona precio: "consulta el precio actual en Amazon"
- NO hacer scraping de Amazon directamente
- Los enlaces deben integrarse de forma natural en el texto
- No poner bloques de 10 enlaces seguidos
- Máximo razonable: 5-8 enlaces por post

## Verificar enlaces existentes

```bash
wp db query "SELECT ID, post_title FROM wp_posts 
  WHERE post_status='publish' AND post_type='post' 
  AND post_content LIKE '%amazon.es%' 
  AND post_content NOT LIKE '%aviso-afiliados%'" \
  --path=/var/www/html --allow-root
```

Esto encuentra posts con enlaces de Amazon pero sin aviso de afiliación.
