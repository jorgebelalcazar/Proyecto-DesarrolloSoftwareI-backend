"""
Vistas (endpoints) del dominio de artículos científicos (HU-14).
"""

from rest_framework import generics
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from usuarios.models import Rol
from usuarios.permisos import RequiereRolActivo

from .models import Articulo
from .permisos import EsAutorResponsableArticulo
from .serializers import CrearArticuloSerializer, AutorArticuloSerializer, GestionCoautoresArticuloSerializer


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


class GestionCoautoresArticuloView(APIView):
    """
    GET / PUT /api/articulos/<articulo_id>/coautores/   (HU-15.2)

    Consulta o actualiza transaccionalmente la lista ordenada de coautores
    y firmantes de un artículo propio, validando formato de correo electrónico
    e impidiendo correos duplicados dentro del mismo artículo.

    Requiere:
    - Token JWT en el encabezado Authorization.
    - Encabezado X-Rol-Activo: AUTOR (opcional si AUTOR es su único rol).
    - Ser el autor responsable del artículo.

    Respuestas:
    - 200 OK:           lista ordenada de coautores registrada o consultada.
    - 400 Bad Request:  formato de correo inválido, correos duplicados o plazo vencido.
    - 401 Unauthorized: no se envió un token válido.
    - 403 Forbidden:    rol activo distinto de AUTOR o artículo perteneciente a otro autor.
    - 404 Not Found:    el artículo indicado no existe.
    """

    permission_classes = [RequiereRolActivo, EsAutorResponsableArticulo]
    roles_permitidos = [Rol.Nombre.AUTOR]

    def obtener_articulo(self, request, articulo_id):
        """Obtiene el artículo y verifica que request.user sea su autor responsable."""
        articulo = get_object_or_404(Articulo, pk=articulo_id)
        self.check_object_permissions(request, articulo)
        return articulo

    def get(self, request, articulo_id):
        """Devuelve la lista ordenada de coautores del artículo."""
        articulo = self.obtener_articulo(request, articulo_id)
        serializador = AutorArticuloSerializer(articulo.coautores.all(), many=True)
        return Response(
            {"articulo_id": articulo.id, "coautores": serializador.data},
            status=status.HTTP_200_OK,
        )

    def put(self, request, articulo_id):
        """Crea, ordena o edita de forma atómica los coautores del artículo."""
        articulo = self.obtener_articulo(request, articulo_id)
        serializador = GestionCoautoresArticuloSerializer(
            data=request.data,
            context={"articulo": articulo},
        )
        serializador.is_valid(raise_exception=True)
        resultado = serializador.save()
        return Response(
            serializador.to_representation(resultado),
            status=status.HTTP_200_OK,
        )