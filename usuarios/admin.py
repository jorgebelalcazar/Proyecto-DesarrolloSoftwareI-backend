"""
Registro del dominio de usuarios en el panel de administración.

Decisión de seguridad:
Los usuarios solo se crean por la API (HU-01 y HU-02) o con el comando
"createsuperuser", porque esos caminos guardan la clave como hash.
Por eso el panel NO permite crear usuarios ni editar su clave.
"""

from django.contrib import admin

from .models import CodigoRecuperacion, Especialidad, Rol, Usuario, UsuarioRol


# Un "inline" muestra una tabla relacionada dentro de la página de otro modelo.
# Así, al abrir un usuario, se ven y editan sus roles y especialidades.
class UsuarioRolInline(admin.TabularInline):
    model = UsuarioRol
    extra = 0  # No muestra filas vacías adicionales


class EspecialidadInline(admin.TabularInline):
    model = Especialidad
    extra = 0


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    # Columnas de la lista de usuarios.
    list_display = ("correo", "nombres", "apellidos", "afiliacion", "lista_roles", "activo")

    # Filtros del panel derecho.
    list_filter = ("activo", "roles")

    # Campos en los que busca el buscador.
    search_fields = ("correo", "nombres", "apellidos", "afiliacion")

    # Campos del formulario de detalle, en este orden.
    fields = (
        "correo", "nombres", "apellidos", "tipo_documento", "numero_documento",
        "afiliacion", "pais", "telefono", "acepta_tratamiento_datos", "activo",
        "is_superuser", "password", "last_login", "fecha_registro", "fecha_desactivacion",
    )

    # Campos visibles pero no editables.
    # La clave aparece como hash y no se puede modificar desde aquí.
    readonly_fields = ("password", "last_login", "fecha_registro", "fecha_desactivacion")

    # Tablas relacionadas que se muestran dentro del usuario.
    inlines = (UsuarioRolInline, EspecialidadInline)

    @admin.display(description="roles")
    def lista_roles(self, obj):
        """Columna calculada: muestra los roles separados por comas."""
        return ", ".join(rol.get_nombre_display() for rol in obj.roles.all())

    def has_add_permission(self, request):
        """Oculta el botón "Agregar": los usuarios se crean por la API."""
        return False


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ("nombre",)


@admin.register(CodigoRecuperacion)
class CodigoRecuperacionAdmin(admin.ModelAdmin):
    """Solo lectura: los códigos los genera y los valida el sistema."""

    list_display = ("usuario", "creado_en", "expira_en", "intentos", "usado")

    # Todos los campos son de solo lectura; el PIN solo se ve como hash.
    readonly_fields = ("usuario", "pin_hash", "creado_en", "expira_en", "intentos", "usado")

    def has_add_permission(self, request):
        """Los códigos no se crean a mano: los genera la HU-06."""
        return False