"""
Vistas (endpoints) del dominio de artículos.

  POST /api/articulos/                      -> postular un artículo (HU-14).
  GET y PUT /api/articulos/{id}/coautores/  -> gestionar firmantes (HU-15).
  POST /api/articulos/{id}/versiones/       -> subir PDF inicial (HU-16).
"""

import logging

from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from usuarios.models import Rol
from usuarios.permisos import RequiereRolActivo

from .excepciones import ArticuloNoEditable
from .almacenamiento import eliminar_pdf_articulo, subir_pdf_articulo
from .models import Articulo, VersionArticulo
from .permisos import EsAutorResponsable
from .serializers import (
    CoautoresArticuloSerializer,
    CoautorSerializer,
    CrearArticuloSerializer,
    guardar_coautores,
)
from .validadores_archivo import validar_pdf

logger = logging.getLogger(__name__)


class CrearArticuloView(generics.CreateAPIView):
    """
    POST /api/articulos/   (HU-14)

    Postula un artículo: lo crea en estado POSTULADO, a nombre del usuario
    del token y en la edición vigente de la conferencia, y registra la
    postulación en el historial de estados.

    Requiere:
      - Token JWT en el encabezado Authorization.
      - Rol activo AUTOR (encabezado X-Rol-Activo, o AUTOR como único rol).

    Puede incluir sus coautores (HU-15): se guardan en la misma transacción.

    Respuestas:
      - 201 Created:      el artículo creado, con sus coautores.
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


class SubirVersionInicialView(APIView):
    """
    POST /api/articulos/{id}/versiones/ (HU-16)

    Valida el PDF inicial, lo guarda en Supabase Storage y registra su ruta
    privada en VERSION_ARTICULO como versión 1.

    Requiere token JWT y rol activo AUTOR; solo permite subir al autor responsable.

    Respuestas: 201 al guardar, 400 por archivo inválido o versión duplicada,
    401 sin token, 403 con otro rol, 404 si el artículo no pertenece al usuario
    y 503 si Supabase no está disponible.
    """

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [RequiereRolActivo]
    roles_permitidos = [Rol.Nombre.AUTOR]

    def post(self, request, articulo_id):
        """Guarda el PDF y registra la versión inicial del artículo."""
        # Paso 1: comprobar que el artículo pertenece al autor autenticado.
        articulo = get_object_or_404(
            Articulo, pk=articulo_id, autor_responsable=request.user
        )
        # Paso 2: exigir el archivo y validar formato, firma y tamaño.
        archivo = request.FILES.get("archivo")
        if archivo is None:
            return Response(
                {"archivo": ["Debe adjuntar un archivo PDF."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Paso 3: impedir que se reemplace una versión inicial existente.
        validar_pdf(archivo)
        if VersionArticulo.objects.filter(articulo=articulo, numero_version=1).exists():
            return Response(
                {"version": ["El artículo ya tiene un PDF inicial cargado."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Paso 4: subir el archivo privado y traducir fallos del proveedor.
        try:
            ruta = subir_pdf_articulo(articulo.id, archivo)
        except ImproperlyConfigured as error:
            return Response(
                {"detail": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception:
            logger.exception("No fue posible subir el PDF del artículo %s", articulo.id)
            return Response(
                {"detail": "El almacenamiento de archivos no está disponible."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Paso 5: registrar la versión; compensar la subida si falla la BD.
        try:
            with transaction.atomic():
                version = VersionArticulo.objects.create(
                    articulo=articulo,
                    numero_version=1,
                    ruta_archivo=ruta,
                    cargado_por=request.user,
                )
        except IntegrityError:
            self._eliminar_archivo_si_es_posible(ruta)
            return Response(
                {"version": ["El artículo ya tiene un PDF inicial cargado."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            self._eliminar_archivo_si_es_posible(ruta)
            logger.exception("No fue posible registrar la versión del artículo %s", articulo.id)
            return Response(
                {"detail": "No fue posible registrar la versión del archivo."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Paso 6: devolver los datos públicos de la versión creada.
        return Response(
            {
                "id": version.id,
                "articulo": articulo.id,
                "numero_version": version.numero_version,
                "fecha_carga": version.fecha_carga,
            },
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _eliminar_archivo_si_es_posible(ruta):
        """Evita dejar un objeto huérfano si falla el registro en PostgreSQL."""
        try:
            eliminar_pdf_articulo(ruta)
        except Exception:
            logger.exception("No fue posible limpiar el PDF huérfano %s", ruta)


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
