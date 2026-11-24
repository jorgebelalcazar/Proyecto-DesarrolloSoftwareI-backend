"""
Registro del dominio de artículos en el panel de administración.
"""

from django.contrib import admin

from .models import VersionArticulo


@admin.register(VersionArticulo)
class VersionArticuloAdmin(admin.ModelAdmin):
    """Muestra las versiones sin exponer enlaces públicos al documento."""

    list_display = ("articulo", "numero_version", "cargado_por", "fecha_carga")
    list_filter = ("numero_version", "fecha_carga")
    readonly_fields = ("articulo", "numero_version", "ruta_archivo", "cargado_por", "fecha_carga")

    def has_add_permission(self, request):
        """Las versiones solo se crean mediante el endpoint validado."""
        return False

    def has_change_permission(self, request, obj=None):
        """Evita alterar el historial de archivos desde el panel."""
        return False

from .models import Articulo, HistorialEstado


class HistorialEstadoInline(admin.TabularInline):
    """Muestra el historial dentro de cada artículo, solo para consultar."""

    model = HistorialEstado
    extra = 0
    can_delete = False
    readonly_fields = ("estado_anterior", "estado_nuevo", "usuario", "observacion", "fecha")

    def has_add_permission(self, request, obj=None):
        """El historial lo escribe el sistema, no se agrega a mano."""
        return False


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

    # Historial de estados dentro del artículo.
    inlines = (HistorialEstadoInline,)
