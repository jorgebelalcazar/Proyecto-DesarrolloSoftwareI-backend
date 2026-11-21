"""
Vistas (endpoints) de la API del dominio de usuarios.

Una vista recibe la petición HTTP, usa un serializador para validar los datos
y devuelve la respuesta en JSON con el código de estado correspondiente.
"""

from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.pagination import PageNumberPagination

from .models import Usuario
from .permisos import IsAdminOrComitePermission
from .serializers import CrearUsuarioSerializer, RegistroAutorSerializer, UsuarioListadoSerializer


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


class UsuarioPagination(PageNumberPagination):
    """
    Paginación por número de página para el listado de usuarios (HU-08).

    Evita respuestas pesadas (heavy payload) devolviendo bloques manejables
    con metadatos: count, next, previous y results.
    """

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class ListarUsuariosView(generics.ListAPIView):
    """
    GET /api/usuarios/   (HU-08)

    Permite que cualquier usuario autenticado (Administrador, Comité o Autor)
    liste y consulte los usuarios registrados en la conferencia de forma paginada.

    Respuestas:
- 200 OK:           listado paginado de usuarios.
- 401 Unauthorized: no se envió un token válido.
    """

    serializer_class = UsuarioListadoSerializer
    queryset = Usuario.objects.prefetch_related("roles", "especialidades").all()
    permission_classes = [IsAuthenticated]
    pagination_class = UsuarioPagination