"""
Vistas (endpoints) del dominio de artículos.

  POST /api/articulos/                      -> postular un artículo (HU-14).
  GET  /api/articulos/                      -> catálogo con filtros (HU-18).
  GET y PUT /api/articulos/{id}/coautores/  -> coautores del artículo (HU-15).
  GET /api/articulos/mis-articulos/         -> artículos del autor (HU-17).
"""

from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from core.paginacion import PaginacionEstandar
from usuarios.models import Rol
from usuarios.permisos import RequiereRolActivo

from .excepciones import ArticuloNoEditable
from .filters import ArticuloCatalogoFilter, ArticuloFilter
from .models import Articulo
from .permisos import EsAutorResponsable
from .serializers import (
    ArticuloCatalogoSerializer,
    ArticuloResumenSerializer,
    CoautoresArticuloSerializer,
    CoautorSerializer,
    CrearArticuloSerializer,
    guardar_coautores,
)


class ArticulosView(generics.ListCreateAPIView):
    """
    GET y POST /api/articulos/   (HU-18 y HU-14)

    La misma ruta atiende dos operaciones, cada una para un rol distinto:

    POST: postular un artículo (HU-14), solo con rol activo AUTOR.
      Lo crea en estado POSTULADO, a nombre del usuario del token y en la
      edición vigente de la conferencia, con sus coautores (HU-15) y la
      primera fila del historial de estados.

    GET: catálogo de TODOS los artículos (HU-18), solo con rol activo ADMIN
      o COMITE, paginado y con filtros combinables (HU-18.2):
        - ?linea_tematica=1
        - ?estado=POSTULADO
        - ?autor=5               id del autor responsable
        - ?search=redes          texto parcial en título, resumen o palabras clave
        - ?page=2&page_size=20

    Respuestas:
      - 200 OK:           GET; página de artículos (count, next, previous, results).
      - 201 Created:      POST; el artículo creado, con sus coautores.
      - 400 Bad Request:  POST con un campo inválido o la postulación cerrada;
                          GET con un filtro de valor inexistente.
      - 401 Unauthorized: no se envió un token válido.
      - 403 Forbidden:    el rol activo no corresponde a la operación.
    """

    pagination_class = PaginacionEstandar

    # Rol activo por operación; lo revisa RequiereRolActivo.
    permission_classes = [RequiereRolActivo]

    # Filtros exactos (HU-18.2) y búsqueda parcial por texto, sin importar mayúsculas.
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = ArticuloCatalogoFilter
    search_fields = ["titulo", "resumen", "palabras_clave"]

    @property
    def roles_permitidos(self):
        """
        Roles que pueden usar el método de esta petición.

        RequiereRolActivo lee este atributo de la vista. Como depende del
        método, es una propiedad: postular es del Autor; el catálogo, de
        quienes gestionan la conferencia.
        """
        if self.request.method == "POST":
            return [Rol.Nombre.AUTOR]
        return [Rol.Nombre.ADMIN, Rol.Nombre.COMITE]

    def get_serializer_class(self):
        """Datos completos para postular; filas resumidas para el catálogo."""
        if self.request.method == "POST":
            return CrearArticuloSerializer
        return ArticuloCatalogoSerializer

    def get_queryset(self):
        """
        Todos los artículos, del más reciente al más antiguo.

        select_related (HU-18.1, criterio 3: respuesta en <= 1.5 s) trae la
        línea temática y el autor responsable en la MISMA consulta, con dos
        JOIN. Sin esto, cada fila haría dos consultas más (problema N+1).
        """
        return Articulo.objects.select_related("linea_tematica", "autor_responsable").order_by(
            "-fecha_postulacion", "-id"
        )

    def perform_create(self, serializer):
        """El autor responsable es siempre el usuario del token, nunca uno enviado."""
        serializer.save(autor_responsable=self.request.user)


class CoautoresArticuloView(generics.GenericAPIView):
    """
    GET y PUT /api/articulos/{id}/coautores/   (HU-15)

    Consulta o reemplaza la lista de coautores o firmantes de un artículo.
    Con PUT se envía la lista COMPLETA en el orden de firma deseado: así se
    agregan, editan, quitan y reordenan los firmantes en una sola petición.

    Entrada del PUT (JSON):
        {"coautores": [
            {"nombre_completo": "...", "afiliacion": "...", "correo": "..."},
            ...
        ]}

    Requiere:
      - Token JWT en el encabezado Authorization.
      - Rol activo AUTOR.
      - Ser el autor responsable del artículo (HU-15, criterio 2).

    Respuestas:
      - 200 OK:           {"articulo": id, "coautores": [...]} en orden de firma.
      - 400 Bad Request:  un coautor con datos inválidos o un correo repetido
                          (error en la fila), o el artículo ya no se puede
                          modificar: deshabilitado o plazo vencido ("detail").
      - 401 Unauthorized: no se envió un token válido.
      - 403 Forbidden:    el rol activo no es AUTOR, o el artículo es de otro autor.
      - 404 Not Found:    no existe un artículo con ese id.
    """

    # select_related trae la conferencia en la misma consulta: se usa para
    # revisar el plazo de postulación.
    queryset = Articulo.objects.select_related("conferencia")

    # Dos permisos, en orden: rol activo AUTOR (antes de buscar el artículo)
    # y, con el artículo ya encontrado, que sea su autor responsable.
    permission_classes = [RequiereRolActivo, EsAutorResponsable]
    roles_permitidos = [Rol.Nombre.AUTOR]

    http_method_names = ["get", "put", "head", "options"]

    def respuesta(self, articulo):
        """El artículo y sus coautores en orden de firma."""
        return Response({
            "articulo": articulo.id,
            "coautores": CoautorSerializer(articulo.coautores.all(), many=True).data,
        })

    def get(self, request, pk):
        return self.respuesta(self.get_object())

    def put(self, request, pk):
        # Paso 1: buscar el artículo y revisar los permisos (404 o 403).
        articulo = self.get_object()

        # Paso 2: el artículo debe seguir siendo editable (400).
        motivo = articulo.motivo_no_editable()
        if motivo:
            raise ArticuloNoEditable(motivo)

        # Paso 3: validar la lista recibida (400 con el error en cada fila).
        serializer = CoautoresArticuloSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Paso 4: reemplazar la lista en una transacción.
        with transaction.atomic():
            guardar_coautores(articulo, serializer.validated_data["coautores"])

        return self.respuesta(articulo)


class MisArticulosView(generics.ListAPIView):
    """
    GET /api/articulos/mis-articulos/   (HU-17)

    Lista paginada de los artículos que postuló el usuario del token, del más
    reciente al más antiguo, para hacer seguimiento a sus envíos.

    Privacidad (HU-17, criterio 1): la consulta SIEMPRE se filtra por
    autor_responsable = usuario del token. No hay ningún parámetro para pedir
    los artículos de otra persona.

    Filtros (HU-17, criterio 3), combinables entre sí y con la paginación:
      - ?estado=POSTULADO
      - ?linea_tematica=1
      - ?page=2&page_size=20

    Requiere:
      - Token JWT en el encabezado Authorization.
      - Rol activo AUTOR.

    Respuestas:
      - 200 OK:           página de artículos (count, next, previous, results).
      - 400 Bad Request:  un filtro con un valor que no existe.
      - 401 Unauthorized: no se envió un token válido.
      - 403 Forbidden:    el rol activo no es AUTOR.
    """

    serializer_class = ArticuloResumenSerializer
    pagination_class = PaginacionEstandar
    permission_classes = [RequiereRolActivo]
    roles_permitidos = [Rol.Nombre.AUTOR]

    # Filtros por estado y línea temática; un valor inválido responde 400.
    filter_backends = [DjangoFilterBackend]
    filterset_class = ArticuloFilter

    def get_queryset(self):
        """
        Artículos del usuario del token.

        select_related (HU-17, criterio 2: respuesta en <= 1.5 s) trae la
        línea temática en la MISMA consulta, con un JOIN. Sin esto, la tabla
        haría una consulta adicional por cada artículo para leer el nombre
        de su línea (el problema N+1).

        El orden incluye "id" para que la paginación sea estable: dos
        artículos postulados en el mismo instante no se repiten ni se
        pierden entre páginas.
        """
        return (
            Articulo.objects.filter(autor_responsable=self.request.user)
            .select_related("linea_tematica")
            .order_by("-fecha_postulacion", "-id")
        )