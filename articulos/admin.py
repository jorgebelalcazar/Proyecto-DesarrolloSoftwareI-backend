"""Registro del dominio de artículos en el panel de administración."""

from django.contrib import admin

from .models import Articulo, AutorArticulo, HistorialEstado, VersionArticulo


@admin.register(VersionArticulo)
class VersionArticuloAdmin(admin.ModelAdmin):
    """Muestra versiones sin exponer enlaces públicos al documento."""

    list_display = ("articulo", "numero_version", "cargado_por", "fecha_carga")
    list_filter = ("numero_version", "fecha_carga")
    readonly_fields = (
        "articulo", "numero_version", "ruta_archivo", "cargado_por", "fecha_carga"
    )

    def has_add_permission(self, request):
        """Las versiones solo se crean mediante el endpoint validado."""
        return False

    def has_change_permission(self, request, obj=None):
        """Evita alterar el historial de archivos desde el panel."""
        return False


class HistorialEstadoInline(admin.TabularInline):
    """Muestra el historial dentro del artículo en modo de consulta."""

    model = HistorialEstado
    extra = 0
    can_delete = False
    readonly_fields = ("estado_anterior", "estado_nuevo", "usuario", "observacion", "fecha")

    def has_add_permission(self, request, obj=None):
        """El historial lo escribe el sistema, no se agrega a mano."""
        return False


class AutorArticuloInline(admin.TabularInline):
    """Muestra coautores dentro del artículo, en orden de firma."""

    model = AutorArticulo
    extra = 0


@admin.register(Articulo)
class ArticuloAdmin(admin.ModelAdmin):
    """Permite consultar artículos, firmantes e historial desde Django Admin."""

    list_display = (
        "id", "titulo", "conferencia", "linea_tematica",
        "autor_responsable", "estado", "fecha_postulacion",
    )
    list_filter = ("conferencia", "estado", "linea_tematica")
    search_fields = ("titulo", "palabras_clave", "autor_responsable__correo")
    inlines = (AutorArticuloInline, HistorialEstadoInline)
