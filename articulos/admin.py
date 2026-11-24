"""
Registro del dominio de artículos en el panel de administración.
"""

from django.contrib import admin

from .models import Articulo, AutorArticulo, HistorialEstado, VersionArticulo


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


class VersionArticuloInline(admin.TabularInline):
    """
    Muestra las versiones del PDF dentro de cada artículo, solo para consultar (HU-16).

    No se agregan, cambian ni borran desde el panel: una versión solo se crea
    con el endpoint, que valida el PDF y lo sube a Supabase. Si se editara la
    ruta aquí, dejaría de apuntar al archivo real del bucket.
    """

    model = VersionArticulo
    extra = 0
    can_delete = False
    readonly_fields = ("tipo", "numero", "ruta_pdf", "fecha_subida")

    def has_add_permission(self, request, obj=None):
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
    
    # El estado y la deshabilitación solo cambian con los endpoints, que
    # dejan el historial (HU-21). Desde el panel no se puede rehabilitar.
    readonly_fields = (
        "estado", "habilitado", "motivo_deshabilitacion", "fecha_deshabilitacion",
    )

    # Coautores, versiones del PDF e historial de estados dentro del artículo.
    inlines = (AutorArticuloInline, VersionArticuloInline, HistorialEstadoInline)