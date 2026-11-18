"""
Pruebas del validador de cabecera X-Active-Role (HU-04).
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate
from rest_framework.views import APIView

from usuarios.models import Rol, Usuario

from .permisos import RequiereRolActivo, ValidarRolActivo

# Obtener dinámicamente los roles reales definidos en Rol.Nombre
ROLES_DISPONIBLES = list(Rol.Nombre.values)
ROL_SECUNDARIO = next(r for r in ROLES_DISPONIBLES if r != Rol.Nombre.AUTOR)
ROL_NO_ASIGNADO = next(
    (r for r in ROLES_DISPONIBLES if r not in (Rol.Nombre.AUTOR, ROL_SECUNDARIO)),
    "ROL_NO_ASIGNADO",
)


class VistaSoloSegundoRolDummy(APIView):
    """Vista auxiliar para probar RequiereRolActivo aisladamente."""

    permission_classes = [IsAuthenticated, ValidarRolActivo, RequiereRolActivo]
    roles_permitidos = [ROL_SECUNDARIO]

    def get(self, request):
        return Response({"rol_operando": request.rol_activo})


class RolActivoHeaderTests(APITestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            "carlos@correo.com",
            "ClaveSegura123",
            nombres="Carlos",
            apellidos="Gómez",
            afiliacion="Universidad del Valle",
            pais="Colombia",
        )
        self.usuario.asignar_rol(Rol.Nombre.AUTOR)
        self.usuario.asignar_rol(ROL_SECUNDARIO)

        self.url_sesion = reverse("autenticacion:sesion")
        self.client.force_authenticate(user=self.usuario)

    def test_cabecera_rol_asignado_permite_acceso(self):
        respuesta = self.client.get(
            self.url_sesion, HTTP_X_ACTIVE_ROLE=ROL_SECUNDARIO
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_cabecera_rol_no_asignado_devuelve_403(self):
        """Bloquea si el usuario intenta operar con un rol que no posee."""
        respuesta = self.client.get(
            self.url_sesion, HTTP_X_ACTIVE_ROLE=ROL_NO_ASIGNADO
        )
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_vista_restringida_valida_rol_operando(self):
        """Aunque tenga ambos roles, bloquea si opera con el rol equivocado."""
        factory = APIRequestFactory()
        vista = VistaSoloSegundoRolDummy.as_view()

        # Caso 1: opera como AUTOR en una vista exclusiva de ROL_SECUNDARIO -> 403
        req_autor = factory.get("/dummy/", HTTP_X_ACTIVE_ROLE=Rol.Nombre.AUTOR)
        force_authenticate(req_autor, user=self.usuario)
        resp_autor = vista(req_autor)
        self.assertEqual(resp_autor.status_code, status.HTTP_403_FORBIDDEN)

        # Caso 2: cambia cabecera a ROL_SECUNDARIO -> 200
        req_secundario = factory.get("/dummy/", HTTP_X_ACTIVE_ROLE=ROL_SECUNDARIO)
        force_authenticate(req_secundario, user=self.usuario)
        resp_secundario = vista(req_secundario)
        self.assertEqual(resp_secundario.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_secundario.data["rol_operando"], ROL_SECUNDARIO)

    def test_vista_restringida_sin_cabecera_devuelve_403(self):
        factory = APIRequestFactory()
        vista = VistaSoloSegundoRolDummy.as_view()

        req_sin_header = factory.get("/dummy/")
        force_authenticate(req_sin_header, user=self.usuario)
        respuesta = vista(req_sin_header)
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)