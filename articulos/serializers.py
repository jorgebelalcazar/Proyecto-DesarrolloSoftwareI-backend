"""
Serializadores del dominio de artículos científicos (HU-14).
"""

from django.db import transaction
from rest_framework import serializers

from core.models import LineaTematica
from core.serializers import LineaTematicaSerializer

from .models import Articulo, HistorialEstado, AutorArticulo
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

# ---------------------------------------------------------------------------
# COAUTORES / FIRMANTES DEL ARTÍCULO (HU-15.2)
# ---------------------------------------------------------------------------
def validar_lista_coautores(coautores):
    """
    Valida una lista de coautores/firmantes para un artículo:
    - Asigna orden_firma consecutivo (1, 2, 3...) si no viene explícito.
    - Impide correos electrónicos duplicados dentro del mismo artículo.
    - Impide posiciones orden_firma duplicadas en la misma lista.
    """
    correos_vistos = set()
    ordenes_vistos = set()

    for indice, firmante in enumerate(coautores, start=1):
        correo = firmante["correo"].strip().lower()
        firmante["correo"] = correo

        if correo in correos_vistos:
            raise serializers.ValidationError(
                f"El correo '{correo}' está duplicado dentro del mismo artículo."
            )
        correos_vistos.add(correo)

        orden = firmante.get("orden_firma") or indice
        if orden in ordenes_vistos:
            raise serializers.ValidationError(
                f"El orden de firma {orden} está repetido entre los coautores."
            )
        ordenes_vistos.add(orden)
        firmante["orden_firma"] = orden

    return coautores


def sincronizar_coautores_articulo(articulo, coautores_validados):
    """
    Reemplaza/actualiza transaccionalmente la lista de coautores de un artículo
    garantizando que el orden de firma y los correos queden sin conflictos.
    """
    with transaction.atomic():
        articulo.coautores.all().delete()
        instancias = [
            AutorArticulo(
                articulo=articulo,
                nombre_completo=firmante["nombre_completo"],
                afiliacion=firmante["afiliacion"],
                correo=firmante["correo"],
                orden_firma=firmante["orden_firma"],
            )
            for firmante in coautores_validados
        ]
        AutorArticulo.objects.bulk_create(instancias)

    return list(articulo.coautores.all())


class AutorArticuloSerializer(serializers.ModelSerializer):
    """
    Serializador de un coautor/firmante de artículo (HU-15.2).

    Valida nombre completo, afiliación institucional, formato de correo electrónico
    y orden de firma sin requerir que exista cuenta en Usuario.
    """

    orden_firma = serializers.IntegerField(min_value=1, required=False)

    class Meta:
        model = AutorArticulo
        fields = [
            "id",
            "nombre_completo",
            "afiliacion",
            "correo",
            "orden_firma",
        ]
        read_only_fields = ["id"]

    def validate_nombre_completo(self, valor):
        """Verifica que el nombre completo no sea solo espacios."""
        limpio = valor.strip()
        if not limpio:
            raise serializers.ValidationError("El nombre completo es obligatorio.")
        return limpio

    def validate_afiliacion(self, valor):
        """Verifica que la afiliación institucional no sea solo espacios."""
        limpio = valor.strip()
        if not limpio:
            raise serializers.ValidationError(
                "La afiliación institucional es obligatoria."
            )
        return limpio

    def validate_correo(self, valor):
        """Normaliza el correo electrónico en minúsculas tras validar su formato."""
        return valor.strip().lower()


class GestionCoautoresArticuloSerializer(serializers.Serializer):
    """
    Serializador anidado para agregar, ordenar y editar los coautores/firmantes
    de un artículo de forma transaccional (HU-15.2).
    """

    coautores = AutorArticuloSerializer(many=True, allow_empty=False)

    def validate_coautores(self, coautores):
        """Valida unicidad de correos y orden de firma dentro del artículo."""
        return validar_lista_coautores(coautores)

    def validate(self, attrs):
        """Verifica que el artículo esté editable y dentro del plazo vigente."""
        articulo = self.context["articulo"]
        if articulo.estado == Articulo.Estado.DESHABILITADO:
            raise serializers.ValidationError(
                {
                    "estado": [
                        "No se pueden modificar los coautores de un artículo deshabilitado."
                    ]
                }
            )
        validar_plazo_postulacion_abierto()
        return attrs

    def save(self, **kwargs):
        """Guarda de forma atómica los coautores validados en AUTOR_ARTICULO."""
        articulo = self.context["articulo"]
        coautores_actualizados = sincronizar_coautores_articulo(
            articulo, self.validated_data["coautores"]
        )
        return {"articulo_id": articulo.id, "coautores": coautores_actualizados}

    def to_representation(self, instance):
        """Devuelve el identificador del artículo y su lista ordenada de firmantes."""
        return {
            "articulo_id": instance["articulo_id"],
            "coautores": AutorArticuloSerializer(
                instance["coautores"], many=True
            ).data,
        }