"""
Vistas compartidas del sistema.

  GET /api/salud/            -> prueba de integración (Sprint 0).
  GET /api/lineas-tematicas/ -> catálogo de líneas temáticas (HU-02.8).
"""

from django.db import connection
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import CriterioEvaluacion, LineaTematica
from .paginacion import PaginacionEstandar
from .serializers import CriterioEvaluacionSerializer, LineaTematicaSerializer
from usuarios.models import Rol
from usuarios.permisos import RequiereRolActivo


@api_view(["GET"])
@permission_classes([AllowAny])
def salud(request):
    """
    GET /api/salud/

    Confirma que la API responde y que la base de datos está conectada.

    Es público (AllowAny): desde la HU-03 todos los endpoints exigen
    autenticación por defecto, pero este debe poder consultarse sin
    iniciar sesión, porque lo usa la prueba de integración del front-end.
    """
    # Le pide su versión a PostgreSQL: si responde, la conexión funciona.
    with connection.cursor() as cursor:
        cursor.execute("SELECT version();")
        version_bd = cursor.fetchone()[0]

    return Response({
        "estado": "ok",
        "mensaje": "API de la conferencia funcionando",
        "base_de_datos": version_bd,
    })


class LineaTematicaListView(generics.ListAPIView):
    """
    GET /api/lineas-tematicas/   (HU-02.8)

    Devuelve el catálogo paginado con el formato compartido de la API.

    Lo usan los selectores del front-end:
      - especialidades de los miembros del comité (HU-02.5);
      - filtro por especialidad del directorio de usuarios (HU-09.3);
      - en el futuro, la línea temática de cada artículo (Épica 2).

    Seguridad: exige un rol activo ADMIN, COMITE o AUTOR. Es de solo lectura;
    las líneas se cargan con la migración de datos.
    """

    # Consulta que devuelve la vista. El orden alfabético lo define el
    # Meta.ordering del modelo LineaTematica.
    queryset = LineaTematica.objects.all()
    serializer_class = LineaTematicaSerializer
    permission_classes = [RequiereRolActivo]
    roles_permitidos = [Rol.Nombre.ADMIN, Rol.Nombre.COMITE, Rol.Nombre.AUTOR]
    pagination_class = PaginacionEstandar


class CriterioEvaluacionListView(generics.ListAPIView):
    """GET /api/criterios-evaluacion/ devuelve la rúbrica activa al comité."""

    serializer_class = CriterioEvaluacionSerializer
    permission_classes = [RequiereRolActivo]
    roles_permitidos = [Rol.Nombre.ADMIN, Rol.Nombre.COMITE]
    pagination_class = PaginacionEstandar

    def get_queryset(self):
        """Solo incluye criterios habilitados, en el orden definido por el comité."""
        return CriterioEvaluacion.objects.filter(activo=True)
