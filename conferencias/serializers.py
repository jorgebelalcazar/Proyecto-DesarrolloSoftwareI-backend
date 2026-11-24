"""
Serializadores de la conferencia (HU-13) y de su rúbrica (HU-22.2).

  - ConferenciaSerializer traduce la tabla "conferencia" a JSON y valida que
    los plazos de las etapas vayan en orden cronológico estricto.
  - CriterioEvaluacionSerializer y RubricaSerializer validan la rúbrica de
    evaluación de una edición.

Zona horaria: las fechas con hora se responden en la hora de Colombia, por
ejemplo "2026-03-15T23:59:00-05:00" (TIME_ZONE = "America/Bogota" en
settings.py). Si el front-end envía una fecha con hora sin zona horaria,
Django la interpreta también como hora de Colombia.
"""

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import Conferencia, CriterioEvaluacion

# Orden de los plazos: cada uno debe ser posterior al anterior.
# Cada tupla es (campo, campo anterior, mensaje si no es posterior).
ORDEN_DE_LOS_PLAZOS = [
    ("limite_revision", "limite_postulacion",
     "Debe ser posterior al límite de postulación."),
    ("limite_correccion", "limite_revision",
     "Debe ser posterior al límite de revisión."),
    ("limite_version_final", "limite_correccion",
     "Debe ser posterior al límite de corrección."),
]


class ConferenciaSerializer(serializers.ModelSerializer):
    """
    Datos de una edición de la conferencia (HU-13).

    Entrada (JSON), todos obligatorios al crear (POST) o reemplazar (PUT):
      - nombre: por ejemplo "Nexo 2027".
      - fecha_inicio_evento y fecha_fin_evento: días, "2027-05-20".
      - limite_postulacion, limite_revision, limite_correccion y
        limite_version_final: fecha y hora, "2027-03-15T23:59:00-05:00".

    Con PATCH se envían solo los campos que cambian, y el orden se valida
    junto con los valores que ya tiene la conferencia.
    """

    class Meta:
        model = Conferencia
        fields = [
            "id", "nombre", "fecha_inicio_evento", "fecha_fin_evento",
            "limite_postulacion", "limite_revision", "limite_correccion",
            "limite_version_final",
        ]
        read_only_fields = ["id"]

    def valor(self, datos, campo):
        """
        Valor que tendrá el campo después de guardar: el que llegó en la
        petición o, si no llegó (PATCH), el que ya tiene la conferencia.
        """
        if campo in datos:
            return datos[campo]
        return getattr(self.instance, campo, None)

    def validate(self, datos):
        """
        Valida el orden cronológico estricto de las etapas (HU-13.2).

        Cada error se reporta en el campo que quedó fuera de orden, para que
        el front-end lo muestre debajo del selector correspondiente.
        """
        errores = {}

        # Paso 1: cada plazo debe ser posterior al anterior.
        for campo, anterior, mensaje in ORDEN_DE_LOS_PLAZOS:
            if self.valor(datos, campo) <= self.valor(datos, anterior):
                errores[campo] = [mensaje]

        # Paso 2: la versión final se entrega antes del día en que empieza el evento.
        # localtime() pasa la fecha con hora a la hora de Colombia antes de
        # tomar el día; si no, una entrega a las 22:00 del 19 de mayo en
        # Colombia (03:00 del 20 en UTC) parecería del día 20.
        version_final = self.valor(datos, "limite_version_final")
        inicio_evento = self.valor(datos, "fecha_inicio_evento")
        if timezone.localtime(version_final).date() >= inicio_evento:
            errores.setdefault("fecha_inicio_evento", []).append(
                "El evento debe empezar después del límite de versión final."
            )

        # Paso 3: el evento no puede terminar antes de empezar.
        if self.valor(datos, "fecha_fin_evento") < inicio_evento:
            errores["fecha_fin_evento"] = [
                "Debe ser igual o posterior a la fecha de inicio del evento."
            ]

        if errores:
            raise serializers.ValidationError(errores)
        return datos


# ===========================================================================
# HU-22.2: RÚBRICA DE EVALUACIÓN
# ===========================================================================
class CriterioEvaluacionSerializer(serializers.ModelSerializer):
    """
    Un criterio de la rúbrica (HU-22.2).

    Entrada (JSON): {"nombre": "...", "descripcion": "...", "puntaje_maximo": 20}
      - nombre: obligatorio, máximo 100 caracteres.
      - descripcion: opcional; explica qué evalúa el criterio.
      - puntaje_maximo: número entero de 1 a 100.
    """

    puntaje_maximo = serializers.IntegerField(
        min_value=1,
        max_value=100,
        error_messages={
            "min_value": "El puntaje máximo debe ser al menos 1.",
            "max_value": "El puntaje máximo no puede superar 100.",
        },
    )

    class Meta:
        model = CriterioEvaluacion
        fields = ["id", "nombre", "descripcion", "puntaje_maximo"]
        read_only_fields = ["id"]
        extra_kwargs = {"descripcion": {"required": False}}


def validar_criterios(criterios):
    """
    Valida la rúbrica completa (HU-22.2).

    Reglas:
      - Tiene al menos un criterio.
      - Un nombre no se repite, sin importar mayúsculas. El error se marca
        en la fila repetida, igual que los coautores de la HU-15:
            {"criterios": [{}, {"nombre": ["Este criterio ya está..."]}]}
    """
    if not criterios:
        raise serializers.ValidationError("La rúbrica debe tener al menos un criterio.")

    errores = []
    nombres_vistos = set()
    for criterio in criterios:
        nombre = criterio["nombre"].lower()
        if nombre in nombres_vistos:
            errores.append({"nombre": ["Este criterio ya está en la rúbrica."]})
        else:
            errores.append({})
            nombres_vistos.add(nombre)

    if any(errores):
        raise serializers.ValidationError(errores)
    return criterios


class RubricaSerializer(serializers.Serializer):
    """
    Rúbrica completa de una edición, para reemplazarla (HU-22.2).

    Entrada (JSON): {"criterios": [{...}, {...}]}
    Se envía la lista COMPLETA en el orden en que se debe mostrar: así se
    agregan, editan, quitan y reordenan los criterios en una sola petición.
    """

    criterios = CriterioEvaluacionSerializer(many=True)

    def validate_criterios(self, criterios):
        return validar_criterios(criterios)

    def guardar(self, conferencia):
        """
        Reemplaza la rúbrica de la edición por la lista recibida.

        Usa una transacción: si algo falla, la edición conserva su rúbrica
        anterior completa, nunca queda a medias.
        """
        with transaction.atomic():
            conferencia.criterios.all().delete()
            CriterioEvaluacion.objects.bulk_create(
                CriterioEvaluacion(conferencia=conferencia, **criterio)
                for criterio in self.validated_data["criterios"]
            )