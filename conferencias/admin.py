"""
Registro de la conferencia en el panel de administración.

Las fechas se pueden revisar y corregir desde el panel; si quedan fuera de
orden, las restricciones de la base de datos (Meta.constraints) lo impiden.
"""

from django.contrib import admin

from .models import Conferencia, CriterioEvaluacion


class CriterioEvaluacionInline(admin.TabularInline):
    """
    Rúbrica de evaluación dentro de cada edición (HU-22.2).

    El Administrador también puede configurarla aquí. La base de datos
    rechaza nombres repetidos y puntajes fuera del rango de 1 a 100.
    """

    model = CriterioEvaluacion
    extra = 0
    fields = ("nombre", "descripcion", "puntaje_maximo")


@admin.register(Conferencia)
class ConferenciaAdmin(admin.ModelAdmin):
    # Columnas de la lista de ediciones.
    list_display = ("nombre", "fecha_inicio_evento", "fecha_fin_evento", "limite_postulacion")

    # Campos en los que busca el buscador.
    search_fields = ("nombre",)

    # Rúbrica de evaluación dentro de la edición.
    inlines = (CriterioEvaluacionInline,)