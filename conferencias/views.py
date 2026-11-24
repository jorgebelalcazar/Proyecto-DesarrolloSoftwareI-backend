"""
Vistas (endpoints) de la conferencia (HU-13).

  GET  /api/conferencias/           -> lista de ediciones (todos los roles).
  POST /api/conferencias/           -> crea una edición (Admin o Comité).
  GET  /api/conferencias/vigente/   -> la edición vigente (todos los roles).
  GET  /api/conferencias/{id}/      -> una edición (todos los roles).
  PUT/PATCH /api/conferencias/{id}/ -> modifica sus fechas (Admin o Comité).

No hay DELETE: los artículos de cada edición dependen de ella.
"""

from rest_framework import generics
from rest_framework.exceptions import NotFound
from rest_framework.permissions import SAFE_METHODS

from usuarios.permisos import IsAdminOrComitePermission

from .models import Conferencia
from .serializers import ConferenciaSerializer


class LecturaTodosEscrituraGestores:
    """
    Permisos de las vistas de la conferencia (HU-13, criterio 1).

      - Consultar (GET): cualquier usuario autenticado. Los autores necesitan
        ver los plazos para saber hasta cuándo pueden postular.
      - Crear o modificar (POST, PUT, PATCH): solo con rol activo ADMIN o
        COMITE. Un Autor recibe 403.

    Para consultar se usan los permisos por defecto de settings.py
    (IsAuthenticated y el validador global del rol activo de la HU-04).
    """

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return super().get_permissions()
        return [IsAdminOrComitePermission()]


class ConferenciaListCreateView(LecturaTodosEscrituraGestores, generics.ListCreateAPIView):
    """
    GET y POST /api/conferencias/   (HU-13)

    Respuestas:
      - 200 OK:           GET; lista de ediciones, de la más reciente a la más antigua.
      - 201 Created:      POST; la edición creada.
      - 400 Bad Request:  un campo falta, tiene formato inválido o las fechas
                          no van en orden; el error va en el campo afectado.
      - 401 Unauthorized: no se envió un token válido.
      - 403 Forbidden:    POST con un rol activo distinto de ADMIN o COMITE.
    """

    serializer_class = ConferenciaSerializer
    queryset = Conferencia.objects.all()


class ConferenciaDetalleView(LecturaTodosEscrituraGestores, generics.RetrieveUpdateAPIView):
    """
    GET, PUT y PATCH /api/conferencias/{id}/   (HU-13)

    Respuestas:
      - 200 OK:           los datos de la edición (también después de modificarla).
      - 400 Bad Request:  las fechas no van en orden.
      - 401 Unauthorized: no se envió un token válido.
      - 403 Forbidden:    PUT o PATCH con un rol activo distinto de ADMIN o COMITE.
      - 404 Not Found:    no existe una edición con ese id.
      - 405 Method Not Allowed: DELETE.
    """

    serializer_class = ConferenciaSerializer
    queryset = Conferencia.objects.all()
    http_method_names = ["get", "put", "patch", "head", "options"]


class ConferenciaVigenteView(generics.RetrieveAPIView):
    """
    GET /api/conferencias/vigente/   (HU-13)

    Devuelve la edición vigente: la próxima que todavía no ha terminado.
    El front-end la usa para mostrar los plazos y saber si la postulación
    sigue abierta (HU-14 y HU-20), sin tener que conocer su id.

    Respuestas:
      - 200 OK:           los datos de la edición vigente.
      - 401 Unauthorized: no se envió un token válido.
      - 404 Not Found:    no hay ninguna edición configurada que no haya terminado.
    """

    serializer_class = ConferenciaSerializer

    def get_object(self):
        conferencia = Conferencia.objects.vigente()
        if conferencia is None:
            raise NotFound("No hay una edición de la conferencia vigente.")
        return conferencia