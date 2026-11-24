"""
Vistas (endpoints) del dominio de artículos.

  POST /api/articulos/   -> postular un artículo (HU-14).
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

from .almacenamiento import eliminar_pdf_articulo, subir_pdf_articulo
from .models import Articulo, VersionArticulo
from .serializers import CrearArticuloSerializer
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
