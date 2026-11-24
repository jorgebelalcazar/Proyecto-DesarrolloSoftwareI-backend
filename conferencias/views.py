"""
Vistas (endpoints) de la conferencia (HU-13) y de su rúbrica (HU-22.2).

  GET  /api/conferencias/           -> lista de ediciones (todos los roles).
  POST /api/conferencias/           -> crea una edición (Admin o Comité).
  GET  /api/conferencias/vigente/   -> la edición vigente (todos los roles).
  GET  /api/conferencias/{id}/      -> una edición (todos los roles).
  PUT/PATCH /api/conferencias/{id}/ -> modifica sus fechas (Admin o Comité).
  GET y PUT /api/conferencias/{id}/criterios/ -> rúbrica de evaluación (HU-22.2).

No hay DELETE: los artículos de cada edición dependen de ella.
"""

from django.db.models import Sum
from rest_framework import generics
from rest_framework.exceptions import NotFound
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response

from usuarios.permisos import IsAdminOrComitePermission

from .excepciones import RubricaNoEditable
from .models import Conferencia
from .serializers import ConferenciaSerializer, CriterioEvaluacionSerializer, RubricaSerializer


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


class RubricaConferenciaView(generics.GenericAPIView):
    """
    GET y PUT /api/conferencias/{id}/criterios/   (HU-22.2)

    Consulta o reemplaza la rúbrica de evaluación de una edición.
    Con PUT se envía la lista COMPLETA de criterios, en el orden en que se
    deben mostrar (el mismo patrón de los coautores de la HU-15).

    Entrada del PUT (JSON):
        {"criterios": [
            {"nombre": "Originalidad", "descripcion": "...", "puntaje_maximo": 20},
            ...
        ]}

    Requiere:
      - Token JWT en el encabezado Authorization.
      - Rol activo ADMIN o COMITE: es la herramienta de trabajo del comité.

    Respuestas:
      - 200 OK:           {"conferencia": id, "puntaje_total": 100, "criterios": [...]}.
      - 400 Bad Request:  un criterio inválido o un nombre repetido (error en
                          la fila), una rúbrica vacía, o la postulación de la
                          edición ya cerró ("detail").
      - 401 Unauthorized: no se envió un token válido.
      - 403 Forbidden:    el rol activo no es ADMIN ni COMITE.
      - 404 Not Found:    no existe una edición con ese id.
    """

    queryset = Conferencia.objects.all()
    serializer_class = RubricaSerializer
    permission_classes = [IsAdminOrComitePermission]
    http_method_names = ["get", "put", "head", "options"]

    def respuesta(self, conferencia):
        """La rúbrica en su orden, con la suma de los puntajes máximos."""
        criterios = conferencia.criterios.all()
        return Response({
            "conferencia": conferencia.id,
            "puntaje_total": criterios.aggregate(total=Sum("puntaje_maximo"))["total"] or 0,
            "criterios": CriterioEvaluacionSerializer(criterios, many=True).data,
        })

    def get(self, request, pk):
        return self.respuesta(self.get_object())

    def put(self, request, pk):
        # Paso 1: buscar la edición y revisar el rol activo (404 o 403).
        conferencia = self.get_object()

        # Paso 2: la rúbrica se define antes de la revisión (400). Si cambiara
        # durante la revisión, unos artículos se evaluarían con criterios
        # distintos a los de otros.
        if not conferencia.postulacion_abierta():
            raise RubricaNoEditable(
                "La rúbrica ya no se puede modificar: la postulación de "
                f"{conferencia.nombre} cerró y empezó la revisión."
            )

        # Paso 3: validar la lista completa (400 con el error en cada fila).
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Paso 4: reemplazar la rúbrica en una transacción.
        serializer.guardar(conferencia)

        return self.respuesta(conferencia)