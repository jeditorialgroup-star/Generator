---
site: nombre_del_sitio
url: https://ejemplo.com
tono: directo-práctico         # profesional-cercano | directo-práctico | técnico-accesible
registro: informal-medio       # formal | formal-medio | informal-medio | informal
persona: 2a_directa            # 1a_plural | 2a_directa | 1a_singular
tuteo: true                    # true | false
nivel_oralidad: medio          # bajo | medio | alto
humor_ironia: false            # true | false
---

# Perfil de Voz — [NOMBRE SITIO]

## Identidad editorial

[Descripción de quién escribe y para quién. Qué experiencia real tiene el autor. Tono general.]

Referencias de voz (completar con muestras reales):
- [URL o descripción de texto modelo 1]
- [URL o descripción de texto modelo 2]

## Tono y registro

- [Tratamiento: tuteo/usted]
- [Persona: 1a plural, 2a directa, etc.]
- [Nivel de formalidad]
- [Actitud hacia el lector]
- [¿Permite opiniones directas?]

## Vocabulario del sector (jerga activa)

| Expresión | Significado | Uso |
|-----------|-------------|-----|
| [expr] | [significado] | frecuente / contextual |

## Expresiones informales — prioridad de uso

Ver `config/expresiones_es.yaml`. Indicar nivel de oralidad y preferencias:
- Nivel oralidad BAJO: solo marcadores suaves ("bueno", "a ver", "la verdad es que")
- Nivel oralidad MEDIO: marcadores + conexión con lector
- Nivel oralidad ALTO: todo el banco, incluido humor

## Marcadores de experiencia

Usar 1-2 por artículo:
- "[Frase que señala experiencia real]"
- "[Frase que señala proceso de investigación]"

## Patrones de apertura — Capa 3b

| Tipo | Ejemplo específico del sitio |
|------|------------------------------|
| Escena concreta | [ejemplo] |
| Dato sorprendente | [ejemplo] |
| Pregunta provocadora | [ejemplo] |
| Contra-intuitiva | [ejemplo] |
| Humor/ironía | [ejemplo o "no aplica"] |

## Estructura de texto

[Instrucciones específicas de estructura para este sitio]

## Patrones de humor e ironía

[Solo si humor_ironia: true]

| Tipo | Ejemplo |
|------|---------|
| [tipo] | [ejemplo] |

## Términos prohibidos

- [término o expresión 1]
- [término o expresión 2]

## Autores y E-E-A-T

```yaml
autor:
  nombre: "[nombre]"
  rol: "[rol]"
  schema_type: "Person"    # Person | Organization
  eeat_strategy: "credenciales_profesionales"  # credenciales_profesionales | autoridad_por_transparencia | experiencia_demostrable
  knows_about:
    - "[área de conocimiento 1]"
  credenciales: "[descripción de credenciales verificables]"
```
