"""
Serializadores del dominio de artículos científicos (HU-14).
"""

from django.db import transaction
from rest_framework import serializers

from core.models import LineaTematica
from core.serializers import LineaTematicaSerializer

from .models import Articulo, HistorialEstado
from .servicios import validar_plazo_postulacion_abierto

MAX_PALABRAS_RESUMEN = 300


class CrearArticuloSerializer(serializers.ModelSerializer):
    """
    Serializador para crear y postular un artículo científico (HU-14.2).

    Valida:
    - Que el plazo de postulación esté vigente (fecha_actual <= fecha_limite_postulacion).
    - Título obligatorio de máximo 200 caracteres.
    - Resumen obligatorio de máximo 300 palabras.
    - Palabras clave obligatorias (lista separada por comas).
    - Selección obligatoria de una de las líneas temáticas oficiales.
    """

    linea_tematica = serializers.PrimaryKeyRelatedField(
        queryset=LineaTematica.objects.all(),
        error_messages={
            "required": "Debe seleccionar una línea temática oficial.",
            "null": "Debe seleccionar una línea temática oficial.",
            "does_not_exist": "La línea temática seleccionada no existe.",
            "incorrect_type": "El identificador de la línea temática debe ser numérico.",
        },
    )

    class Meta:
        model = Articulo
        fields = [
            "id",
            "titulo",
            "resumen",
            "palabras_clave",
            "linea_tematica",
            "autor_responsable",
            "estado",
            "fecha_postulacion",
        ]
        read_only_fields = [
            "id",
            "autor_responsable",
            "estado",
            "fecha_postulacion",
        ]

    def validate_titulo(self, valor):
        """Verifica que el título no quede vacío tras limpiar espacios."""
        limpio = valor.strip()
        if not limpio:
            raise serializers.ValidationError("El título del artículo es obligatorio.")
        return limpio

    def validate_resumen(self, valor):
        """Verifica que el resumen no esté vacío y no supere las 300 palabras."""
        limpio = valor.strip()
        if not limpio:
            raise serializers.ValidationError("El resumen del artículo es obligatorio.")

        cantidad_palabras = len(limpio.split())
        if cantidad_palabras > MAX_PALABRAS_RESUMEN:
            raise serializers.ValidationError(
                f"El resumen no puede superar las {MAX_PALABRAS_RESUMEN} palabras "
                f"(actualmente tiene {cantidad_palabras})."
            )
        return limpio

    def validate_palabras_clave(self, valor):
        """Valida que exista al menos una palabra clave válida y normaliza espacios."""
        etiquetas = [item.strip() for item in valor.split(",") if item.strip()]
        if not etiquetas:
            raise serializers.ValidationError(
                "Debe ingresar al menos una palabra clave."
            )
        normalizado = ", ".join(etiquetas)
        if len(normalizado) > 255:
            raise serializers.ValidationError(
                "Las palabras clave no pueden superar los 255 caracteres."
            )
        return normalizado

    def validate(self, attrs):
        """Valida que la postulación se realice antes de la fecha límite."""
        validar_plazo_postulacion_abierto()
        return attrs

    def create(self, validated_data):
        """
        Crea el artículo en estado POSTULADO asociado al autor responsable
        y registra su trazabilidad inicial en HISTORIAL_ESTADO dentro de una
        transacción atómica.
        """
        # Paso 1: obtener el autor responsable inyectado desde la vista (request.user).
        autor = validated_data["autor_responsable"]

        # Paso 2: crear el artículo y su registro inicial en historial_estado.
        with transaction.atomic():
            articulo = Articulo.objects.create(
                **validated_data,
                estado=Articulo.Estado.POSTULADO,
            )
            HistorialEstado.objects.create(
                articulo=articulo,
                estado_anterior="",
                estado_nuevo=Articulo.Estado.POSTULADO,
                usuario=autor,
                observacion="Postulación inicial del artículo.",
            )

        return articulo

    def to_representation(self, instance):
        """
        Devuelve la línea temática como {"id": 1, "nombre": "..."} según la
        convención de la API.
        """
        datos = super().to_representation(instance)
        datos["linea_tematica"] = LineaTematicaSerializer(
            instance.linea_tematica
        ).data
        return datos