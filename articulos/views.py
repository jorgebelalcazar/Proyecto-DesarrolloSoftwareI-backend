"""
Vistas (endpoints) del dominio de artículos.

  POST /api/articulos/                      -> postular un artículo (HU-14).
  GET  /api/articulos/                      -> catálogo con filtros (HU-18).
  GET y PUT /api/articulos/{id}/coautores/  -> coautores del artículo (HU-15).
  GET /api/articulos/mis-articulos/         -> artículos del autor (HU-17).
  POST /api/articulos/{id}/versiones/       -> subir el PDF inicial (HU-16).
  GET /api/articulos/{id}/                  -> ficha completa del artículo (HU-19).
  PUT y PATCH /api/articulos/{id}/          -> modificar el artículo propio (HU-20).
  PATCH /api/articulos/{id}/deshabilitar/   -> retirar el artículo (HU-21, Comité).
"""

import logging

from django.db import IntegrityError, transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.filters import SearchFilter
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from core.paginacion import PaginacionEstandar
from usuarios.models import Rol
from usuarios.permisos import RequiereRolActivo

from .almacenamiento import eliminar_pdf_articulo, subir_pdf_articulo
from .excepciones import (
    AlmacenamientoNoDisponible,
    ArticuloNoEditable,
    DeshabilitacionNoPermitida,
    VersionInicialExistente,
)
from .filters import ArticuloCatalogoFilter, ArticuloFilter
from .models import Articulo, ArticuloYaDeshabilitado, VersionArticulo
from .permisos import EsAutorResponsable, PuedeVerArticulo
from .serializers import (
    ArticuloCatalogoSerializer,
    ArticuloDetalleSerializer,
    ArticuloResumenSerializer,
    CoautoresArticuloSerializer,
    CoautorSerializer,
    CrearArticuloSerializer,
    DeshabilitacionSerializer,
    DeshabilitarArticuloSerializer,
    EditarArticuloSerializer,
    SubirVersionInicialSerializer,
    VersionArticuloSerializer,
    guardar_coautores,
)

logger = logging.getLogger(__name__)


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


class SubirVersionInicialView(generics.GenericAPIView):
    """
    POST /api/articulos/{id}/versiones/   (HU-16)

    Sube el PDF inicial del artículo a Supabase Storage y lo registra en
    VERSION_ARTICULO como la versión 1, de tipo INICIAL.

    Entrada (multipart/form-data): un campo "archivo" con el PDF.

    Requiere:
      - Token JWT en el encabezado Authorization.
      - Rol activo AUTOR.
      - Ser el autor responsable del artículo.

    Respuestas:
      - 201 Created:      la versión registrada (sin la ruta privada del bucket).
      - 400 Bad Request:  el archivo no es un PDF válido o pesa más de 10 MB
                          (error en "archivo"); o el artículo ya tiene su PDF
                          inicial, está deshabilitado o su plazo venció ("detail").
      - 401 Unauthorized: no se envió un token válido.
      - 403 Forbidden:    el rol activo no es AUTOR, o el artículo es de otro autor.
      - 404 Not Found:    no existe un artículo con ese id.
      - 503 Service Unavailable: Supabase Storage no respondió.
    """

    # select_related trae la conferencia en la misma consulta: se usa para
    # revisar el plazo de postulación.
    queryset = Articulo.objects.select_related("conferencia")
    serializer_class = SubirVersionInicialSerializer

    # Los mismos permisos de los coautores (HU-15): rol activo AUTOR y, con el
    # artículo ya encontrado, que sea su autor responsable.
    permission_classes = [RequiereRolActivo, EsAutorResponsable]
    roles_permitidos = [Rol.Nombre.AUTOR]

    # Solo se reciben formularios con archivos (multipart/form-data).
    parser_classes = [MultiPartParser]

    def post(self, request, pk):
        # Paso 1: buscar el artículo y revisar los permisos (404 o 403).
        articulo = self.get_object()

        # Paso 2: el artículo debe seguir siendo editable (400).
        motivo = articulo.motivo_no_editable()
        if motivo:
            raise ArticuloNoEditable(motivo)

        # Paso 3: solo hay un PDF inicial por artículo (400). Se revisa ANTES
        # de subir, para no gastar espacio en Supabase con un archivo que no
        # se va a registrar.
        if articulo.versiones.filter(tipo=VersionArticulo.Tipo.INICIAL).exists():
            raise VersionInicialExistente()

        # Paso 4: validar el archivo: .pdf, <= 10 MB y firma %PDF (400).
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        archivo = serializer.validated_data["archivo"]

        # Paso 5: subir el PDF al bucket privado (503 si Supabase falla).
        try:
            ruta = subir_pdf_articulo(articulo.id, archivo)
        except Exception as error:
            logger.exception("No se pudo subir el PDF del artículo %s.", articulo.id)
            raise AlmacenamientoNoDisponible() from error

        # Paso 6: registrar la versión 1. Si falla, se borra el PDF recién
        # subido, para que no quede un archivo sin registro en el bucket.
        try:
            with transaction.atomic():
                version = VersionArticulo.objects.create(
                    articulo=articulo,
                    tipo=VersionArticulo.Tipo.INICIAL,
                    numero=1,
                    ruta_pdf=ruta,
                )
        except Exception as error:
            borrar_pdf_huerfano(ruta)
            # Dos subidas al mismo tiempo: ambas pasaron el paso 3, pero la
            # restricción uk_version_articulo_numero solo deja guardar una.
            if isinstance(error, IntegrityError):
                raise VersionInicialExistente() from error
            raise

        return Response(VersionArticuloSerializer(version).data, status=status.HTTP_201_CREATED)


def borrar_pdf_huerfano(ruta):
    """
    Intenta borrar del bucket un PDF que no quedó registrado (HU-16).

    Si tampoco se puede borrar, solo se deja en el log: el error que importa
    es el original, y es el que se le responde al usuario.
    """
    try:
        eliminar_pdf_articulo(ruta)
    except Exception:
        logger.exception("No se pudo borrar el PDF huérfano %s.", ruta)


class ArticuloDetalleView(generics.RetrieveUpdateAPIView):
    """
    GET, PUT y PATCH /api/articulos/{id}/   (HU-19 y HU-20)

    GET (HU-19): ficha completa del artículo: metadatos, autor responsable,
      coautores en orden de firma y un enlace firmado de 15 minutos para
      abrir su PDF. Rol activo AUTOR (solo sus artículos), COMITE o ADMIN.

    PUT y PATCH (HU-20): modificar título, resumen, palabras clave, línea
      temática y coautores. Solo el autor responsable, con rol activo AUTOR,
      y solo si el artículo no está DESHABILITADO y el plazo de postulación
      de su edición sigue abierto.

    Respuestas:
      - 200 OK:           GET: la ficha; "pdf" es null si aún no tiene PDF, y
                          "pdf.url" es null si Supabase no respondió.
                          PUT/PATCH: el artículo modificado, con sus coautores.
      - 400 Bad Request:  PUT/PATCH con un campo inválido (error en el campo),
                          o el artículo ya no se puede modificar ("detail").
      - 401 Unauthorized: no se envió un token válido.
      - 403 Forbidden:    el rol activo no corresponde a la operación, o el
                          artículo es de otro autor.
      - 404 Not Found:    no existe un artículo con ese id.
    """

    # El artículo, su línea temática, su autor y su edición llegan en UNA
    # consulta (select_related, con JOIN). Los coautores y las versiones
    # suman una consulta cada uno, sin importar cuántos haya.
    queryset = Articulo.objects.select_related(
        "linea_tematica", "autor_responsable", "conferencia"
    )

    # Primero el rol activo (antes de buscar el artículo); luego, con el
    # artículo encontrado, si ese rol puede verlo. Con rol AUTOR,
    # PuedeVerArticulo solo deja pasar al autor responsable: por eso sirve
    # también para la modificación (HU-20, criterio 1).
    permission_classes = [RequiereRolActivo, PuedeVerArticulo]
    http_method_names = ["get", "put", "patch", "head", "options"]

    @property
    def roles_permitidos(self):
        """Consultar: Autor, Comité y Admin. Modificar: solo el Autor."""
        if self.request.method in ("PUT", "PATCH"):
            return [Rol.Nombre.AUTOR]
        return [Rol.Nombre.AUTOR, Rol.Nombre.COMITE, Rol.Nombre.ADMIN]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return EditarArticuloSerializer
        return ArticuloDetalleSerializer

    def update(self, request, *args, **kwargs):
        """
        Revisa el bloqueo ANTES de validar los datos (HU-20.2): si el
        artículo está deshabilitado o el plazo venció, no importa qué se
        envió, la respuesta es 400 con el motivo.
        """
        motivo = self.get_object().motivo_no_editable()
        if motivo:
            raise ArticuloNoEditable(motivo)
        return super().update(request, *args, **kwargs)


class DeshabilitarArticuloView(generics.GenericAPIView):
    """
    PATCH /api/articulos/{id}/deshabilitar/   (HU-21)

    Retira el artículo de la conferencia de forma permanente, con un motivo
    obligatorio que queda en el artículo y en el historial de estados.

    Entrada (JSON): {"motivo": "..."}   de 10 a 1000 caracteres.

    Requiere:
      - Token JWT en el encabezado Authorization.
      - Rol activo COMITE: es una acción exclusiva del comité científico
        (HU-21, criterio 1). Ni el Administrador ni el Autor pueden hacerlo.

    Respuestas:
      - 200 OK:           el nuevo estado: {id, estado, estado_nombre, habilitado,
                          motivo_deshabilitacion, fecha_deshabilitacion}.
      - 400 Bad Request:  falta el motivo o es muy corto (error en "motivo"),
                          o el artículo ya estaba deshabilitado ("detail").
      - 401 Unauthorized: no se envió un token válido.
      - 403 Forbidden:    el rol activo no es COMITE.
      - 404 Not Found:    no existe un artículo con ese id.

    No hay operación para rehabilitar: el cambio es irreversible (criterio 2).
    """

    queryset = Articulo.objects.all()
    serializer_class = DeshabilitarArticuloSerializer
    permission_classes = [RequiereRolActivo]
    roles_permitidos = [Rol.Nombre.COMITE]
    http_method_names = ["patch", "options"]

    def patch(self, request, pk):
        # Paso 1: buscar el artículo (404) después de revisar el rol (403).
        articulo = self.get_object()

        # Paso 2: validar el motivo (400 en "motivo").
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Paso 3: deshabilitar y registrar en el historial, en una transacción.
        try:
            articulo.deshabilitar(request.user, serializer.validated_data["motivo"])
        except ArticuloYaDeshabilitado as error:
            raise DeshabilitacionNoPermitida(str(error)) from error

        return Response(DeshabilitacionSerializer(articulo).data)