"""
Permisos basados en el rol activo (HU-02 y HU-04).

Un permiso de DRF responde una sola pregunta antes de ejecutar una vista:
"¿esta petición puede continuar?". Si la respuesta es no, DRF devuelve:
  - 401 Unauthorized: si no hay un usuario autenticado;
  - 403 Forbidden:    si hay usuario, pero no tiene permiso.

Rol activo (respuesta de la profesora G03-R2):
Un usuario puede tener varios roles y, al iniciar sesión, elige con cuál
trabajar. El front-end envía ese rol en el encabezado HTTP "X-Rol-Activo"
de cada petición. Los permisos revisan el rol ACTIVO, no todos los roles
que tiene el usuario.

Contenido:
  - obtener_rol_activo:          ÚNICA función que decide el rol activo.
  - ValidarRolActivo:            validador global del encabezado (HU-04.2).
  - RequiereRolActivo:           permiso por vista con "roles_permitidos" (HU-04.2).
  - IsAdminOrComitePermission:   permiso para crear usuarios (HU-02.1).
"""

from django.core.exceptions import ImproperlyConfigured
from rest_framework.permissions import BasePermission

from .models import Rol

# Nombre del encabezado HTTP que indica el rol activo.
# Debe coincidir con CORS_ALLOW_HEADERS en settings.py; si no, el navegador
# bloquea el encabezado antes de que llegue a Django.
ENCABEZADO_ROL_ACTIVO = "X-Rol-Activo"


def leer_encabezado_rol(request):
    """
    Devuelve el rol escrito en el encabezado X-Rol-Activo, normalizado.

    Quita los espacios y lo pasa a mayúsculas: " comite " -> "COMITE".
    Si el encabezado no llega o está vacío, devuelve None.
    request.headers no distingue mayúsculas en el NOMBRE del encabezado.
    """
    valor = (request.headers.get(ENCABEZADO_ROL_ACTIVO) or "").strip().upper()
    return valor or None


def obtener_rol_activo(request):
    """
    Devuelve el rol con el que está trabajando el usuario en esta petición.

    Es el ÚNICO lugar del proyecto que decide cuál es el rol activo:
    todos los permisos y las vistas que necesiten el rol deben usarla.

    Reglas:
      1. Sin usuario autenticado, no hay rol activo.
      2. Si llega el encabezado X-Rol-Activo, se usa ese rol, pero SOLO si el
         usuario realmente lo tiene. El encabezado elige entre los roles
         propios; no otorga roles nuevos.
      3. Si no llega el encabezado y el usuario tiene un solo rol, se usa ese.
      4. Si no llega el encabezado y el usuario tiene varios roles, no se puede
         saber cuál eligió: no hay rol activo.

    Devuelve "ADMIN", "COMITE", "AUTOR" o None.
    """
    usuario = request.user

    # Regla 1: is_authenticated es False para un visitante sin sesión.
    if not usuario or not usuario.is_authenticated:
        return None

    # Regla 2: el rol del encabezado solo vale si el usuario lo tiene.
    solicitado = leer_encabezado_rol(request)
    if solicitado:
        return solicitado if usuario.tiene_rol(solicitado) else None

    # Reglas 3 y 4: sin encabezado, solo se puede deducir si hay un único rol.
    roles = list(usuario.roles.values_list("nombre", flat=True))
    return roles[0] if len(roles) == 1 else None


class ValidarRolActivo(BasePermission):
    """
    Validador global del encabezado X-Rol-Activo (HU-04.2).

    Está registrado en REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"], así que
    revisa todas las vistas que usan los permisos por defecto:
      - Si el encabezado NO llega: deja pasar. Así se puede consultar
        /api/auth/sesion/ al recargar la página, antes de elegir rol.
      - Si el encabezado SÍ llega: el usuario debe tener ese rol; si no, 403.

    Las vistas que definen sus propios permission_classes no heredan este
    validador. Por eso RequiereRolActivo hace la misma verificación a través
    de obtener_rol_activo: un rol que no se tiene nunca se acepta.
    """

    message = "No tiene asignado el rol indicado en el encabezado X-Rol-Activo."

    def has_permission(self, request, view):
        # Paso 1: sin encabezado no hay nada que validar.
        if not leer_encabezado_rol(request):
            return True

        # Paso 2: sin usuario autenticado, no aplica; IsAuthenticated decide.
        if not request.user or not request.user.is_authenticated:
            return True

        # Paso 3: con encabezado, obtener_rol_activo devuelve None si el
        # usuario no tiene ese rol.
        return obtener_rol_activo(request) is not None


class RequiereRolActivo(BasePermission):
    """
    Permite la petición solo si el rol activo está entre los permitidos (HU-04.2).

    Uso en las vistas de las próximas historias de usuario:

        class CrearArticuloView(generics.CreateAPIView):
            permission_classes = [RequiereRolActivo]
            roles_permitidos = [Rol.Nombre.AUTOR]

    Si la vista no define roles_permitidos, se lanza un error de
    configuración en lugar de dejar pasar la petición: un permiso mal
    configurado nunca debe abrir el endpoint a todos (fallar cerrado).
    """

    message = "El rol activo no tiene permiso para realizar esta operación."

    # Las subclases pueden fijar sus roles aquí, en lugar de hacerlo en la vista.
    roles_permitidos = ()

    def obtener_roles_permitidos(self, view):
        """Busca los roles permitidos primero en la vista y después en el permiso."""
        roles = getattr(view, "roles_permitidos", None) or self.roles_permitidos
        if not roles:
            raise ImproperlyConfigured(
                f"{type(view).__name__} usa {type(self).__name__} pero no define "
                "roles_permitidos."
            )
        return {str(rol).upper() for rol in roles}

    def has_permission(self, request, view):
        """DRF la ejecuta antes de la vista: True deja pasar la petición, False la niega."""
        return obtener_rol_activo(request) in self.obtener_roles_permitidos(view)


class IsAdminOrComitePermission(RequiereRolActivo):
    """
    Permite la petición solo si el rol activo es ADMIN o COMITE (HU-02.1).

    Es un RequiereRolActivo con los roles ya fijados. El nombre en inglés
    sigue la convención de DRF y coincide con el de la subtarea en Jira.
    """

    message = "Esta acción solo está permitida para el Administrador o el Comité científico."
    roles_permitidos = (Rol.Nombre.ADMIN, Rol.Nombre.COMITE)

    def obtener_roles_permitidos(self, view):
        """Ignora los roles de la vista: este permiso siempre exige ADMIN o COMITE."""
        return set(self.roles_permitidos)