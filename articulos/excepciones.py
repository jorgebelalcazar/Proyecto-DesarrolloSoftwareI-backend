"""
Errores propios del dominio de artículos.

En DRF, una excepción que hereda de APIException se convierte automáticamente
en una respuesta HTTP con su código de estado y su mensaje: {"detail": "..."}.
"""

from rest_framework import status
from rest_framework.exceptions import APIException


class PostulacionCerrada(APIException):
    """
    No se pueden postular artículos en este momento. Responde 400 (HU-14.2).

    Casos: no hay una edición vigente de la conferencia, o ya pasó su
    límite de postulación (HU-13). La vista indica el mensaje de cada caso.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "La postulación de artículos está cerrada."
    default_code = "postulacion_cerrada"


class ArticuloNoEditable(APIException):
    """
    El autor ya no puede modificar el artículo. Responde 400 (HU-15 y HU-20).

    Casos: el artículo está DESHABILITADO, o ya pasó el límite de
    postulación de su edición. El mensaje lo da Articulo.motivo_no_editable().
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "El artículo ya no se puede modificar."
    default_code = "articulo_no_editable"


class VersionInicialExistente(APIException):
    """
    El artículo ya tiene su PDF inicial. Responde 400 (HU-16).

    La versión inicial es una sola, la número 1. Las versiones siguientes
    (corrección y final) se suben en sus propias historias de usuario.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "El artículo ya tiene su PDF inicial cargado."
    default_code = "version_inicial_existente"


class AlmacenamientoNoDisponible(APIException):
    """
    No se pudo guardar el archivo en Supabase Storage. Responde 503 (HU-16).

    503 Service Unavailable indica que el error no es del usuario sino de un
    servicio externo: el front-end puede pedirle que lo intente más tarde.
    El detalle técnico queda en el log del servidor, no en la respuesta.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "El almacenamiento de archivos no está disponible. Intente más tarde."
    default_code = "almacenamiento_no_disponible"


class DeshabilitacionNoPermitida(APIException):
    """
    El artículo ya estaba deshabilitado. Responde 400 (HU-21).

    La deshabilitación es permanente: no se repite ni se revierte.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "El artículo ya está deshabilitado."
    default_code = "deshabilitacion_no_permitida"