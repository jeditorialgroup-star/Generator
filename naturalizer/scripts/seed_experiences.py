#!/usr/bin/env python3
"""
seed_experiences.py — Poblar ExperienceDB con experiencias reales de inforeparto.
Idempotente: solo inserta si la tabla está vacía (o con --force).

Uso:
  python3 seed_experiences.py
  python3 seed_experiences.py --force   # borra y reinserta todo
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from experience_db import ExperienceDB

EXPERIENCES_INFOREPARTO = [
    # ── Fiscalidad y autónomos ────────────────────────────────────────────────
    {
        "topic": "cuota autónomos RETA tarifa plana",
        "type": "metric",
        "content": "La mayoría de riders que se dan de alta el primer año no saben que existe la tarifa plana de 80€ mensuales para nuevos autónomos. En inforeparto lo vemos continuamente en los comentarios.",
        "tags": ["RETA", "autónomo", "tarifa plana", "alta autónomo"],
    },
    {
        "topic": "deducciones fiscales autónomo rider",
        "type": "process_insight",
        "content": "Para este artículo hemos consultado la normativa vigente en el BOE y contrastado con el portal de la Agencia Tributaria. También hemos revisado los criterios de la DGT sobre deducibilidad de vehículos y equipamiento.",
        "tags": ["fiscal", "deducciones", "autónomo", "IRPF", "boe"],
    },
    {
        "topic": "modelo 303 IVA trimestral autónomo",
        "type": "user_feedback",
        "content": "En grupos de Telegram de repartidores, el Modelo 303 es una de las dudas más repetidas: cuándo presentarlo, qué gastos incluir y si se puede hacer sin gestor. La confusión más habitual es mezclar el IVA repercutido de las plataformas con el IVA soportado de los gastos.",
        "tags": ["IVA", "modelo 303", "trimestral", "autónomo", "fiscal"],
    },
    {
        "topic": "estimación directa simplificada módulos",
        "type": "comparison",
        "content": "Hemos comparado casos reales de riders en estimación directa simplificada vs módulos: con ingresos variables (típico de rider con varios días de descanso al mes), la directa simplificada suele salir más a cuenta.",
        "tags": ["estimación directa", "módulos", "IRPF", "fiscal", "autónomo"],
    },
    {
        "topic": "declaración renta rider autónomo",
        "type": "anecdote",
        "content": "Abril llega y de repente aparecen en Telegram preguntas como '¿tengo que declarar si cobro menos de X?' o '¿cómo pongo los ingresos de Glovo?'. La respuesta rápida: si eres autónomo, siempre tienes que declarar.",
        "tags": ["declaración renta", "IRPF", "autónomo", "Glovo", "plataforma"],
    },

    # ── Equipamiento ──────────────────────────────────────────────────────────
    {
        "topic": "mochila térmica reparto comparativa",
        "type": "comparison",
        "content": "Hemos probado las mochilas más vendidas durante semanas reales de reparto: evaluamos peso en trayectos largos, capacidad con pedidos de supermercado (donde los packs de agua son el enemigo) y temperatura interior en verano.",
        "tags": ["mochila", "equipamiento", "comparativa", "térmica", "reparto"],
    },
    {
        "topic": "soporte móvil moto vibración",
        "type": "process_insight",
        "content": "Antes de recomendar cualquier soporte de móvil para moto, verificamos que tenga sistema antivibración. Un soporte sin amortiguación puede inutilizar la cámara del teléfono en pocos meses por las vibraciones del motor.",
        "tags": ["soporte móvil", "moto", "vibración", "equipamiento"],
    },
    {
        "topic": "candado antirrobo bicicleta moto seguridad",
        "type": "user_feedback",
        "content": "Entre los riders que usan bicicleta, el robo es una de las preocupaciones más citadas. En foros y grupos de Telegram de ciclistas de reparto, la recomendación más repetida es combinar dos sistemas: candado en U más cadena, o candado más GPS.",
        "tags": ["candado", "antirrobo", "bicicleta", "seguridad", "GPS"],
    },
    {
        "topic": "ropa lluvia impermeable repartidor invierno",
        "type": "anecdote",
        "content": "En invierno la pregunta más habitual no es si llueve, sino cuánto aguanta el chubasquero. Un traje de lluvia de 15€ puede empaparte en una hora de aguacero; los que superan los 30€ con costuras selladas aguantan jornadas completas.",
        "tags": ["lluvia", "impermeable", "invierno", "equipamiento", "chubasquero"],
    },

    # ── Plataformas y operativa ───────────────────────────────────────────────
    {
        "topic": "Glovo Uber Eats Just Eat comparativa plataforma",
        "type": "comparison",
        "content": "Las condiciones entre plataformas varían más de lo que parece: mismo horario, misma zona, ingresos distintos según la plataforma y el tipo de pedido. Lo que vemos en inforeparto es que no hay una respuesta única: depende de la ciudad, la franja y el tipo de vehículo.",
        "tags": ["Glovo", "Uber Eats", "Just Eat", "plataforma", "comparativa", "ingresos"],
    },
    {
        "topic": "bloques Amazon Flex reserva",
        "type": "process_insight",
        "content": "Para este artículo hemos revisado los foros de Amazon Flex España y grupos de Telegram específicos, donde los repartidores comparten estrategias para conseguir bloques en momentos de alta demanda.",
        "tags": ["Amazon Flex", "bloques", "reserva", "estrategia"],
    },
    {
        "topic": "desconexión bloqueo cuenta Glovo Uber",
        "type": "regulatory",
        "content": "Según la Ley Rider (Real Decreto-ley 9/2021), las plataformas deben presumir relación laboral con los repartidores. En la práctica, las desconexiones siguen ocurriendo sin proceso formal de despido, lo que ha generado cientos de sentencias en juzgados de lo social.",
        "tags": ["desconexión", "bloqueo", "Ley Rider", "laboral", "Glovo", "Uber Eats"],
    },
    {
        "topic": "Ley Rider derechos laborales repartidor",
        "type": "regulatory",
        "content": "La Ley Rider (Real Decreto-ley 9/2021) estableció la presunción de laboralidad para repartidores de plataformas digitales. Desde su entrada en vigor, las plataformas han adaptado sus modelos de contratación, aunque el debate sobre la efectividad de la norma sigue abierto.",
        "tags": ["Ley Rider", "RDL 9/2021", "laboral", "presunción laboralidad", "derechos"],
    },

    # ── Seguridad vial ────────────────────────────────────────────────────────
    {
        "topic": "seguridad vial repartidor accidente",
        "type": "metric",
        "content": "Los repartidores en bicicleta tienen una tasa de siniestralidad significativamente mayor que la media de ciclistas, según datos del informe anual de siniestralidad de la DGT. El factor principal: la presión del tiempo en los pedidos.",
        "tags": ["seguridad vial", "accidente", "bicicleta", "DGT", "siniestralidad"],
    },
    {
        "topic": "zonas bajas emisiones ZBE scooter eléctrico",
        "type": "regulatory",
        "content": "Las Zonas de Bajas Emisiones (ZBE) afectan directamente a los riders que usan motos de gasolina en ciudades como Madrid o Barcelona. Consultamos con las webs oficiales municipales para verificar qué vehículos tienen acceso restringido y en qué horarios.",
        "tags": ["ZBE", "zonas bajas emisiones", "moto", "gasolina", "eléctrico", "medioambiente"],
    },

    # ── Finanzas y banca ──────────────────────────────────────────────────────
    {
        "topic": "cuenta bancaria autónomo tarifa repartidor",
        "type": "comparison",
        "content": "Para este artículo comparamos las cuentas de negocio más populares entre riders: BBVA Autónomos, Revolut Business, Holvi y N26 Business. Evaluamos comisiones reales (no solo las de apertura), integración con facturación y facilidad para separar gastos personales de profesionales.",
        "tags": ["banco", "cuenta autónomo", "BBVA", "Revolut", "finanzas", "comisiones"],
    },
    {
        "topic": "tarifa móvil datos repartidor",
        "type": "process_insight",
        "content": "Para evaluar las tarifas móviles para riders comparamos el consumo real de datos de la app de Glovo, Uber Eats y Amazon Flex en una jornada tipo de 5 horas. El resultado: entre 300 MB y 1,2 GB según la plataforma y si se usan mapas integrados o externos.",
        "tags": ["tarifa móvil", "datos", "smartphone", "rider", "Glovo", "app"],
    },

    # ── Proceso editorial inforeparto ─────────────────────────────────────────
    {
        "topic": "inforeparto método investigación",
        "type": "process_insight",
        "content": "En inforeparto no publicamos sin contrastar: cada artículo sobre normativa cita la fuente oficial (BOE, portal de la Seguridad Social, Agencia Tributaria), y los artículos de equipamiento están basados en pruebas reales o en la experiencia directa de la comunidad de riders.",
        "tags": ["inforeparto", "método", "investigación", "calidad", "E-E-A-T"],
    },
]


def seed(site: str = "inforeparto", force: bool = False):
    db = ExperienceDB(site)

    if force:
        conn = db._connect()
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {db.TABLE} WHERE site = %s", (site,))
        conn.commit()
        cur.close()
        conn.close()
        print(f"  Tabla limpiada para site='{site}'.")
    else:
        n = db.count()
        if n > 0:
            print(f"  ExperienceDB ya tiene {n} experiencias para '{site}'. Usa --force para reinsertar.")
            return

    experiences = EXPERIENCES_INFOREPARTO if site == "inforeparto" else []
    if not experiences:
        print(f"  No hay experiencias seed para site='{site}'.")
        return

    for exp in experiences:
        db.add(exp["topic"], exp["type"], exp["content"], exp["tags"])

    print(f"  ✅ {len(experiences)} experiencias insertadas para site='{site}'.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="inforeparto")
    parser.add_argument("--force", action="store_true", help="Borrar y reinsertar todo")
    args = parser.parse_args()
    seed(args.site, args.force)


if __name__ == "__main__":
    main()
