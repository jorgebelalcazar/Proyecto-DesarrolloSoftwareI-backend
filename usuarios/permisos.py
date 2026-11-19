"""
Permisos del dominio de usuarios (HU-02).

Un permiso de DRF responde una sola pregunta antes de ejecutar una vista:
"¿esta petición puede continuar?". Si la respuesta es no, DRF devuelve:
  - 401 Unauthorized: si no hay un usuario autenticado;
  - 403 Forbidden:    si hay usuario, pero no tiene permiso.

Rol activo (contrato con la HU-04 de Jefferson):
Un usuario puede tener varios roles y, al iniciar sesión, elige con cuál
trabajar . El front-end envía ese rol en
el encabezado HTTP "X-Rol-Activo" de cada petición. Los permisos revisan
el rol ACTIVO, no todos los roles que tiene el usuario.
"""

from rest_framework.permissions import BasePermission

from .models import Rol

# Nombre del encabezado HTTP que indica el rol activo.
ENCABEZADO_ROL_ACTIVO = "X-Rol-Activo"


def obtener_rol_activo(request):
    """
    Devuelve el rol con el que está trabajando el usuario en esta petición.

    Es el ÚNICO lugar del proyecto que decide cuál es el rol activo.
    Si la HU-04 cambia el mecanismo, solo se ajusta esta función.

    Reglas:
      1. Sin usuario autenticado, no hay rol activo.
      2. Si llega el encabezado X-Rol-Activo, se usa ese rol, pero SOLO si el
         usuario realmente lo tiene. Así nadie puede darse un rol con solo
         escribirlo en el encabezado.
      3. Si no llega el encabezado y el usuario tiene un solo rol, se usa ese.
      4. Si no llega el encabezado y el usuario tiene varios roles, no se puede
         saber cuál eligió: no hay rol activo y la petición se niega.

    Devuelve "ADMIN", "COMITE", "AUTOR" o None.
    """
    usuario = request.user

    # Regla 1: is_authenticated es False para un visitante sin sesión.
    if not usuario or not usuario.is_authenticated:
        return None

    # Regla 2: request.headers no distingue mayúsculas en el NOMBRE del encabezado;
    # con strip() y upper() tampoco importan los espacios ni las mayúsculas del VALOR.
    solicitado = request.headers.get(ENCABEZADO_ROL_ACTIVO)
    if solicitado:
        solicitado = solicitado.strip().upper()
        return solicitado if usuario.tiene_rol(solicitado) else None

    # Reglas 3 y 4: sin encabezado, solo se puede deducir si hay un único rol.
    roles = list(usuario.roles.values_list("nombre", flat=True))
    return roles[0] if len(roles) == 1 else None


class IsAdminOrComitePermission(BasePermission):
    """
    Permite la petición solo si el rol activo es ADMIN o COMITE (HU-02.1).

    El nombre en inglés sigue la convención de DRF (IsAuthenticated,
    IsAdminUser) y coincide con el de la subtarea en Jira.
    """

    # Mensaje que DRF devuelve en la respuesta 403.
    message = "Esta acción solo está permitida para el Administrador o el Comité científico."

    def has_permission(self, request, view):
        """DRF la ejecuta antes de la vista: True deja pasar la petición, False la niega."""
        return obtener_rol_activo(request) in (Rol.Nombre.ADMIN, Rol.Nombre.COMITE)