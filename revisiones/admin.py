"""
Registro de las revisiones en el panel de administración.

Sirve para auditar las asignaciones y las evaluaciones. Las reglas de la
base de datos (jurado único por artículo, estado coherente) también se
aplican a lo que se guarde desde aquí.
"""

from django.contrib import admin

from .models import Calificacion, Revision


class CalificacionInline(admin.TabularInline):
    """Puntajes de la rúbrica dentro de cada revisión (HU-28)."""

    model = Calificacion
    extra = 0
    fields = ("criterio", "puntaje")


@admin.register(Revision)
class RevisionAdmin(admin.ModelAdmin):
    # Columnas de la lista de revisiones.
    list_display = ("articulo", "revisor", "estado", "decision", "fecha_asignacion", "fecha_entrega")

    # Filtros del panel lateral.
    list_filter = ("estado", "decision")

    # Busca por título del artículo o por correo del jurado.
    search_fields = ("articulo__titulo", "revisor__correo")

    # Evita cargar listas desplegables enormes de artículos y usuarios.
    raw_id_fields = ("articulo", "revisor", "asignado_por")

    inlines = (CalificacionInline,)