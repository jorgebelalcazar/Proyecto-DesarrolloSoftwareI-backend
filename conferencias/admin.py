"""
Registro de la conferencia en el panel de administración.

Las fechas se pueden revisar y corregir desde el panel; si quedan fuera de
orden, las restricciones de la base de datos (Meta.constraints) lo impiden.
"""

from django.contrib import admin

from .models import Conferencia


@admin.register(Conferencia)
class ConferenciaAdmin(admin.ModelAdmin):
    # Columnas de la lista de ediciones.
    list_display = (
        "nombre", "fecha_inicio_postulacion", "limite_postulacion",
        "fecha_inicio_evento", "fecha_fin_evento",
    )

    # Campos en los que busca el buscador.
    search_fields = ("nombre",)
