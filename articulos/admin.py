"""
Registro del dominio de artículos en el panel de administración.
"""

from django.contrib import admin

from .models import Articulo, AutorArticulo, HistorialEstado


class HistorialEstadoInline(admin.TabularInline):
    """Muestra el historial dentro de cada artículo, solo para consultar."""

    model = HistorialEstado
    extra = 0
    can_delete = False
    readonly_fields = ("estado_anterior", "estado_nuevo", "usuario", "observacion", "fecha")

    def has_add_permission(self, request, obj=None):
        """El historial lo escribe el sistema, no se agrega a mano."""
        return False


class AutorArticuloInline(admin.TabularInline):
    """Muestra los coautores dentro de cada artículo, en orden de firma."""

    model = AutorArticulo
    extra = 0


@admin.register(Articulo)
class ArticuloAdmin(admin.ModelAdmin):
    # Columnas de la lista de artículos.
    list_display = (
        "id", "titulo", "conferencia", "linea_tematica",
        "autor_responsable", "estado", "fecha_postulacion",
    )

    # Filtros del panel derecho.
    list_filter = ("conferencia", "estado", "linea_tematica")

    # Campos en los que busca el buscador.
    search_fields = ("titulo", "palabras_clave", "autor_responsable__correo")

    # Coautores e historial de estados dentro del artículo.
    inlines = (AutorArticuloInline, HistorialEstadoInline)