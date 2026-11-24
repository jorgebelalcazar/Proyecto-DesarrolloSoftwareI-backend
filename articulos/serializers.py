"""
Serializadores del dominio de artículos.

Contenido:
  - CrearArticuloSerializer: postular un artículo (HU-14).
"""

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from conferencias.models import Conferencia
from core.models import LineaTematica
from core.serializers import LineaTematicaSerializer

from .excepciones import PostulacionCerrada
from .models import Articulo, HistorialEstado

# Límites de la HU-14 (criterio 3).
MAX_CARACTERES_TITULO = 200
MAX_PALABRAS_RESUMEN = 300


# ===========================================================================
# HU-14: POSTULAR UN ARTÍCULO
# ===========================================================================
class CrearArticuloSerializer(serializers.ModelSerializer):
    """
    Datos para postular un artículo (HU-14).

    Entrada (JSON):
      - titulo:         máximo 200 caracteres.
      - resumen:        máximo 300 palabras.
      - palabras_clave: separadas por comas, por ejemplo "IA, redes, salud".
      - linea_tematica: id de una de las 5 líneas oficiales
                        (ver GET /api/lineas-tematicas/).

    Lo asigna el servidor, no el cliente: la conferencia (la edición vigente),
    el autor responsable (el usuario del token), el estado (POSTULADO) y la
    fecha de postulación. Si alguien los envía, se ignoran.

    Salida: el artículo creado, con la línea temática como {id, nombre}.
    """

    linea_tematica = serializers.PrimaryKeyRelatedField(
        queryset=LineaTematica.objects.all(),
        error_messages={
            "required": "Debe seleccionar una línea temática.",
            "null": "Debe seleccionar una línea temática.",
            "does_not_exist": "La línea temática seleccionada no existe.",
            "incorrect_type": "El identificador de la línea temática debe ser numérico.",
        },
    )

    class Meta:
        model = Articulo
        fields = [
            "id", "titulo", "resumen", "palabras_clave", "linea_tematica",
            "conferencia", "autor_responsable", "estado", "fecha_postulacion",
        ]
        read_only_fields = [
            "id", "conferencia", "autor_responsable", "estado", "fecha_postulacion",
        ]
        # La columna admite 300 caracteres (modelo relacional), pero la HU-14
        # limita el título a 200: este límite es el que se valida en la API.
        extra_kwargs = {"titulo": {"max_length": MAX_CARACTERES_TITULO}}

    def validate_titulo(self, valor):
        """Título sin espacios sobrantes; no puede quedar vacío."""
        limpio = valor.strip()
        if not limpio:
            raise serializers.ValidationError("El título del artículo es obligatorio.")
        return limpio

    def validate_resumen(self, valor):
        """Resumen obligatorio de máximo 300 palabras."""
        limpio = valor.strip()
        if not limpio:
            raise serializers.ValidationError("El resumen del artículo es obligatorio.")

        # split() separa por cualquier espacio, salto de línea o tabulación.
        cantidad = len(limpio.split())
        if cantidad > MAX_PALABRAS_RESUMEN:
            raise serializers.ValidationError(
                f"El resumen no puede superar las {MAX_PALABRAS_RESUMEN} palabras "
                f"(tiene {cantidad})."
            )
        return limpio

    def validate_palabras_clave(self, valor):
        """
        Al menos una palabra clave. Se normaliza el formato:
        " IA ,redes,, salud " -> "IA, redes, salud".
        """
        etiquetas = [etiqueta.strip() for etiqueta in valor.split(",") if etiqueta.strip()]
        if not etiquetas:
            raise serializers.ValidationError("Debe ingresar al menos una palabra clave.")
        return ", ".join(etiquetas)

    def validate(self, datos):
        """
        Verifica que la postulación esté abierta (HU-14, criterio 1).

        La fecha límite es la de la edición vigente de la conferencia (HU-13).
        Si está abierta, deja esa edición en los datos para guardarla con el
        artículo.
        """
        conferencia = Conferencia.objects.vigente()

        # Caso 1: nadie ha configurado una edición que no haya terminado.
        if conferencia is None:
            raise PostulacionCerrada(
                "No hay una edición de la conferencia abierta para postulaciones."
            )

        # Caso 2: la edición existe, pero su plazo de postulación ya venció.
        if not conferencia.postulacion_abierta():
            # localtime(): la fecha se muestra en hora de Colombia.
            limite = timezone.localtime(conferencia.limite_postulacion)
            raise PostulacionCerrada(
                f"El plazo de postulación de {conferencia.nombre} venció el "
                f"{limite:%d/%m/%Y} a las {limite:%H:%M}."
            )

        datos["conferencia"] = conferencia
        return datos

    def create(self, datos):
        """
        Crea el artículo en estado POSTULADO y su primera fila en el historial.

        Usa una transacción: o se crean el artículo Y su historial, o nada.
        Así nunca queda un artículo sin la trazabilidad de su postulación.
        """
        # autor_responsable llega desde la vista: serializer.save(autor_responsable=...).
        with transaction.atomic():
            articulo = Articulo.objects.create(**datos)
            HistorialEstado.objects.create(
                articulo=articulo,
                usuario=articulo.autor_responsable,
                estado_anterior="",
                estado_nuevo=Articulo.Estado.POSTULADO,
                observacion="Postulación inicial del artículo.",
            )
        return articulo

    def to_representation(self, instance):
        """
        Devuelve la línea temática como {"id": 1, "nombre": "..."}, el mismo
        formato del directorio (HU-08) y de GET /api/lineas-tematicas/.
        """
        datos = super().to_representation(instance)
        datos["linea_tematica"] = LineaTematicaSerializer(instance.linea_tematica).data
        return datos
