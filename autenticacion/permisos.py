"""
Validadores de rol activo (HU-04).

Interceptan la cabecera HTTP 'X-Active-Role' enviada por React en cada petición
autenticada para:
1. Verificar que el rol enviado pertenezca realmente al usuario en USUARIO_ROL
   (evitando que alguien falsifique la cabecera desde el navegador o Postman).
2. Exponer 'request.rol_activo' a las vistas.
3. Validar que el rol con el que está operando tenga permiso en el endpoint.
"""

from rest_framework.permissions import BasePermission

NOMBRE_CABECERA_ROL = "X-Active-Role"


class ValidarRolActivo(BasePermission):
    """
    Validador global de la cabecera 'X-Active-Role'.

    Se registra en REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] para que
    intercepte todas las peticiones autenticadas:
    - Si la cabecera NO viene: deja 'request.rol_activo = None' (permite
      consultar /api/auth/sesion/ al recargar la página antes de elegir rol).
    - Si la cabecera SÍ viene: comprueba que el usuario tenga ese rol asignado
      en la base de datos. Si no lo tiene, bloquea con 403 Forbidden.
    """

    message = "No tiene permisos para operar con el rol indicado en X-Active-Role."

    def has_permission(self, request, view):
        # Paso 1: si es un endpoint público sin usuario autenticado, no aplica.
        if not request.user or not request.user.is_authenticated:
            request.rol_activo = None
            return True

        # Paso 2: leer la cabecera X-Active-Role (insensible a mayúsculas/minúsculas).
        rol_crudo = request.headers.get(NOMBRE_CABECERA_ROL)
        if not rol_crudo or not rol_crudo.strip():
            request.rol_activo = None
            return True

        rol_normalizado = rol_crudo.strip().upper()

        # Paso 3: verificar en la base de datos que el usuario posea ese rol.
        tiene_rol = request.user.roles.filter(nombre=rol_normalizado).exists()
        if not tiene_rol:
            self.message = (
                f"El usuario no tiene asignado el rol '{rol_normalizado}' "
                f"enviado en {NOMBRE_CABECERA_ROL}."
            )
            return False

        # Paso 4: adjuntar el rol validado al request para que las vistas lo usen.
        request.rol_activo = rol_normalizado
        return True


class RequiereRolActivo(BasePermission):
    """
    Validador por vista según el rol operando.

    Uso en cualquier vista de las próximas historias de usuario:
        class CrearArticuloView(APIView):
            permission_classes = [IsAuthenticated, ValidarRolActivo, RequiereRolActivo]
            roles_permitidos = [Rol.Nombre.AUTOR]
    """

    message = "El rol activo no tiene permiso para realizar esta operación."

    def has_permission(self, request, view):
        # Paso 1: obtener la lista de roles autorizados definida en la vista.
        roles_permitidos = getattr(view, "roles_permitidos", None)
        if not roles_permitidos:
            return True

        # Paso 2: exigir que el cliente haya enviado la cabecera X-Active-Role.
        rol_activo = getattr(request, "rol_activo", None)
        if not rol_activo:
            self.message = (
                f"Debe enviar la cabecera '{NOMBRE_CABECERA_ROL}' con un rol activo "
                "para acceder a este recurso."
            )
            return False

        # Paso 3: comprobar que el rol operando esté dentro de los permitidos.
        roles_normalizados = {str(rol).strip().upper() for rol in roles_permitidos}
        if rol_activo not in roles_normalizados:
            self.message = (
                f"El rol activo '{rol_activo}' no tiene permiso para esta acción."
            )
            return False

        return True