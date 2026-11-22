"""
Vistas (endpoints) del dominio de artículos científicos (HU-14).
"""

from rest_framework import generics

from usuarios.models import Rol
from usuarios.permisos import RequiereRolActivo

from .models import Articulo
from .serializers import CrearArticuloSerializer


class CrearArticuloView(generics.CreateAPIView):
    """
    POST /api/articulos/   (HU-14.2)

    Crea y postula un nuevo artículo científico asociado al autor responsable
    autenticado, verificando que la fecha límite de postulación no haya vencido
    y registrando su estado inicial POSTULADO en el historial de estados.

    Requiere:
    - Token JWT en el encabezado Authorization.
    - Encabezado X-Rol-Activo: AUTOR (opcional si AUTOR es su único rol).

    Respuestas:
    - 201 Created:      artículo creado con su línea temática y estado POSTULADO.
    - 400 Bad Request:  datos inválidos o fecha límite de postulación vencida.
    - 401 Unauthorized: no se envió un token válido.
    - 403 Forbidden:    el rol activo no es AUTOR o no pertenece al usuario.
    """

    queryset = Articulo.objects.all()
    serializer_class = CrearArticuloSerializer
    permission_classes = [RequiereRolActivo]
    roles_permitidos = [Rol.Nombre.AUTOR]

    def perform_create(self, serializer):
        """Asocia el artículo al usuario autenticado como autor responsable."""
        serializer.save(autor_responsable=self.request.user)