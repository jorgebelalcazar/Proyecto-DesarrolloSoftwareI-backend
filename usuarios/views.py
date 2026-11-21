"""
Vistas (endpoints) de la API del dominio de usuarios.

Una vista recibe la petición HTTP, usa un serializador para validar los datos
y devuelve la respuesta en JSON con el código de estado correspondiente.
"""

from rest_framework import generics
from rest_framework.permissions import AllowAny

from core.paginacion import PaginacionEstandar

from .models import Rol, Usuario
from .permisos import IsAdminOrComitePermission, obtener_rol_activo
from .serializers import (
    CrearUsuarioSerializer,
    RegistroAutorSerializer,
    UsuarioDirectorioGestionSerializer,
    UsuarioDirectorioSerializer,
)

# Roles que gestionan cuentas y por eso ven el directorio completo (HU-08).
ROLES_GESTION = (Rol.Nombre.ADMIN, Rol.Nombre.COMITE)


class RegistroAutorView(generics.CreateAPIView):
    """
    POST /api/usuarios/registro-autor/   (HU-01)

    Permite que una persona nueva cree su propia cuenta con el rol Autor
    (respuesta de la profesora G03-R1).

    Respuestas:
      - 201 Created:     cuenta creada; devuelve los datos sin la clave.
      - 400 Bad Request: datos inválidos; devuelve los errores por campo.
    """

    serializer_class = RegistroAutorSerializer

    # Algunas herramientas de DRF, como la API navegable, consultan el queryset.
    queryset = Usuario.objects.all()

    # Endpoint público: quien se registra todavía no tiene cuenta.
    permission_classes = [AllowAny]

    # No se autentica a nadie en esta ruta; una sesión abierta no interfiere.
    authentication_classes = []


class CrearUsuarioView(generics.CreateAPIView):
    """
    POST /api/usuarios/crear/   (HU-02)

    Permite que el Administrador o un miembro del Comité creen una cuenta
    con uno o varios roles y, para el comité, sus especialidades.

    Requiere:
      - Token JWT en el encabezado Authorization.
      - Rol activo ADMIN o COMITE (encabezado X-Rol-Activo).

    Respuestas:
      - 201 Created:      cuenta creada; devuelve los datos sin la clave.
      - 400 Bad Request:  datos inválidos (por ejemplo, el comité intenta crear un administrador).
      - 401 Unauthorized: no se envió un token válido.
      - 403 Forbidden:    el rol activo no es ADMIN ni COMITE.
    """

    serializer_class = CrearUsuarioSerializer
    queryset = Usuario.objects.all()

    # Se usa la autenticación por defecto (JWT y sesión), pero con un permiso
    # más estricto que el global: además de estar autenticado, el rol activo
    # debe ser ADMIN o COMITE.
    permission_classes = [IsAdminOrComitePermission]


class ListarUsuariosView(generics.ListAPIView):
    """
    GET /api/usuarios/   (HU-08)

    Directorio paginado de los usuarios registrados en la conferencia.
    Lo pueden consultar todos los roles (enunciado del proyecto), pero cada
    uno ve solo lo que necesita (principio de mínimo privilegio):
      - ADMIN o COMITE: todos los usuarios, incluso los desactivados, con los
        datos públicos más el correo, el estado de la cuenta y sus fechas.
      - AUTOR (o sin rol activo): solo los usuarios activos, con los datos
        públicos.

    Requiere:
      - Token JWT en el encabezado Authorization.
      - Para un usuario con varios roles, el encabezado X-Rol-Activo; sin él
        recibe la vista de Autor, que es la de menor privilegio.

    Respuestas:
      - 200 OK:           página de usuarios (count, next, previous, results).
      - 401 Unauthorized: no se envió un token válido.
      - 403 Forbidden:    X-Rol-Activo indica un rol que el usuario no tiene.

    Permisos: no se declara permission_classes, a propósito. Así se usan los
    de settings.py: IsAuthenticated y el validador global del rol activo
    (HU-04). Si se declarara [IsAuthenticated], ese validador se perdería.
    """

    pagination_class = PaginacionEstandar

    def es_gestor(self):
        """Indica si el rol activo de la petición es ADMIN o COMITE."""
        return obtener_rol_activo(self.request) in ROLES_GESTION

    def get_queryset(self):
        """
        Consulta de usuarios según el rol activo.

        prefetch_related (HU-08.2) carga los roles y las especialidades de
        TODA la página en dos consultas adicionales, en lugar de dos consultas
        por cada usuario. Con 10 usuarios por página son 2 consultas, no 20.

        El orden incluye "id" al final para que la paginación sea estable:
        dos usuarios con el mismo nombre siempre quedan en el mismo orden y
        ninguno se repite ni se pierde entre páginas.
        """
        consulta = Usuario.objects.prefetch_related("roles", "especialidades").order_by(
            "apellidos", "nombres", "id"
        )

        # Los usuarios desactivados (HU-12) solo los ven quienes gestionan cuentas.
        if not self.es_gestor():
            consulta = consulta.filter(activo=True)

        return consulta

    def get_serializer_class(self):
        """Elige el serializador según el rol activo: más campos para quien gestiona."""
        if self.es_gestor():
            return UsuarioDirectorioGestionSerializer
        return UsuarioDirectorioSerializer