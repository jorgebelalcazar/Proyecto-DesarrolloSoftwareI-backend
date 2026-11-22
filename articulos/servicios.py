"""
Servicios y reglas de dominio del módulo de artículos.

Centraliza la consulta de la fecha límite de postulación y la validación
de ventana temporal para crear o modificar artículos (HU-14.2 y HU-20).
"""

from datetime import datetime

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers


def obtener_fecha_limite_postulacion():
    """
    Devuelve la fecha y hora límite vigente para postular artículos (aware datetime),
    o None si no hay una fecha límite configurada.

    Lee la configuración definida en settings.FECHA_LIMITE_POSTULACION en formato
    ISO 8601 y garantiza que tenga zona horaria activa.
    """
    valor = getattr(settings, "FECHA_LIMITE_POSTULACION", "")
    if not valor:
        return None

    if isinstance(valor, datetime):
        fecha = valor
    else:
        fecha = parse_datetime(str(valor).strip())

    if fecha is None:
        return None

    if timezone.is_naive(fecha):
        fecha = timezone.make_aware(fecha, timezone.get_current_timezone())

    return fecha


def validar_plazo_postulacion_abierto():
    """
    Verifica que la fecha y hora actual sea menor o igual a la fecha límite
    de postulación (fecha_actual <= fecha_limite_postulacion).

    Si el plazo ya venció, lanza ValidationError para responder HTTP 400.
    """
    fecha_limite = obtener_fecha_limite_postulacion()
    if fecha_limite is not None and timezone.now() > fecha_limite:
        raise serializers.ValidationError(
            {
                "fecha_limite": [
                    "La fecha límite para postular artículos ha vencido."
                ]
            }
        )