"""
Vistas (endpoints) del dominio de artículos.

  POST /api/articulos/   -> postular un artículo (HU-14).
"""

from rest_framework import generics

from usuarios.models import Rol
from usuarios.permisos import RequiereRolActivo

from .models import Articulo
from .serializers import CrearArticuloSerializer


class CrearArticuloView(generics.CreateAPIView):
    """
    POST /api/articulos/   (HU-14)

    Postula un artículo: lo crea en estado POSTULADO, a nombre del usuario
    del token y en la edición vigente de la conferencia, y registra la
    postulación en el historial de estados.

    Requiere:
      - Token JWT en el encabezado Authorization.
      - Rol activo AUTOR (encabezado X-Rol-Activo, o AUTOR como único rol).

    Respuestas:
      - 201 Created:      el artículo creado.
      - 400 Bad Request:  un campo inválido (error en el campo), o la
                          postulación está cerrada (error en "detail").
      - 401 Unauthorized: no se envió un token válido.
      - 403 Forbidden:    el rol activo no es AUTOR.
    """

    queryset = Articulo.objects.all()
    serializer_class = CrearArticuloSerializer
    permission_classes = [RequiereRolActivo]
    roles_permitidos = [Rol.Nombre.AUTOR]

    def perform_create(self, serializer):
        """El autor responsable es siempre el usuario del token, nunca uno enviado."""
        serializer.save(autor_responsable=self.request.user)