"""
Serializadores de los catálogos compartidos entre módulos.
"""

from rest_framework import serializers

from .models import CriterioEvaluacion, LineaTematica


class LineaTematicaSerializer(serializers.ModelSerializer):
    """
    Una línea temática en formato JSON: {"id": 1, "nombre": "Sistemas Inteligentes"}.

    El front-end muestra el nombre en los selectores y envía el id al
    guardar; por ejemplo, en las especialidades de la HU-02.
    """

    class Meta:
        model = LineaTematica
        fields = ["id", "nombre"]


class CriterioEvaluacionSerializer(serializers.ModelSerializer):
    """Datos públicos del criterio que requiere el front-end."""

    class Meta:
        model = CriterioEvaluacion
        fields = ["id", "nombre", "descripcion", "peso", "orden"]
