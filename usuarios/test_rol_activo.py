"""
Pruebas del rol activo (HU-04.2).

Cubren las tres piezas de usuarios/permisos.py:
  - ValidarRolActivo:  validador global del encabezado X-Rol-Activo.
  - RequiereRolActivo: permiso por vista con "roles_permitidos".
  - obtener_rol_activo: la regla que usan ambos.

Para probar RequiereRolActivo sin depender de una historia futura se usan
vistas de prueba ("dummy") que se ejecutan con APIRequestFactory, sin rutas.
"""

from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate
from rest_framework.views import APIView

from .models import Rol, Usuario
from .permisos import RequiereRolActivo


class VistaSoloComite(APIView):
    """Vista de prueba: solo admite el rol activo COMITE."""

    permission_classes = [RequiereRolActivo]
    roles_permitidos = [Rol.Nombre.COMITE]

    def get(self, request):
        return Response({"ok": True})


class VistaSinRolesConfigurados(APIView):
    """Vista de prueba mal configurada: usa RequiereRolActivo sin roles_permitidos."""

    permission_classes = [RequiereRolActivo]

    def get(self, request):
        return Response({"ok": True})


def crear_usuario(correo, *roles):
    """Crea un usuario de prueba con los roles indicados."""
    usuario = Usuario.objects.create_user(
        correo, "ClaveSegura123",
        nombres="Prueba", apellidos="Usuario",
        afiliacion="Universidad del Valle", pais="Colombia",
    )
    for rol in roles:
        usuario.asignar_rol(rol)
    return usuario


class ValidarRolActivoTests(APITestCase):
    """El validador global, probado sobre /api/auth/sesion/ (usa los permisos por defecto)."""

    def setUp(self):
        # Usuario con dos roles: AUTOR y COMITE. No tiene ADMIN.
        self.usuario = crear_usuario("multirrol@ejemplo.com", Rol.Nombre.AUTOR, Rol.Nombre.COMITE)
        self.client.force_authenticate(user=self.usuario)
        self.url_sesion = reverse("autenticacion:sesion")

    def test_rol_que_el_usuario_tiene_permite_el_acceso(self):
        respuesta = self.client.get(self.url_sesion, HTTP_X_ROL_ACTIVO="COMITE")
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_rol_que_el_usuario_no_tiene_devuelve_403(self):
        """Seguridad: nadie se da un rol escribiéndolo en el encabezado."""
        respuesta = self.client.get(self.url_sesion, HTTP_X_ROL_ACTIVO="ADMIN")
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_sin_encabezado_se_puede_consultar_la_sesion(self):
        """Al recargar la página, el front-end consulta la sesión antes de elegir rol."""
        respuesta = self.client.get(self.url_sesion)
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_encabezado_sin_distinguir_mayusculas_ni_espacios(self):
        respuesta = self.client.get(self.url_sesion, HTTP_X_ROL_ACTIVO="  comite ")
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)


class RequiereRolActivoTests(APITestCase):
    """El permiso por vista, probado sobre las vistas de prueba."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.multirrol = crear_usuario("multirrol@ejemplo.com", Rol.Nombre.AUTOR, Rol.Nombre.COMITE)
        self.solo_comite = crear_usuario("comite@ejemplo.com", Rol.Nombre.COMITE)

    def ejecutar(self, vista, usuario, rol_activo=None):
        """Atajo: ejecuta la vista autenticado como "usuario" y con el rol indicado."""
        encabezados = {"HTTP_X_ROL_ACTIVO": rol_activo} if rol_activo else {}
        peticion = self.factory.get("/prueba/", **encabezados)
        force_authenticate(peticion, user=usuario)
        return vista.as_view()(peticion)

    def test_el_rol_activo_decide_el_acceso(self):
        """Con los mismos roles, el resultado cambia según el rol con el que trabaja."""
        # Trabajando como AUTOR: se niega.
        respuesta = self.ejecutar(VistaSoloComite, self.multirrol, rol_activo="AUTOR")
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

        # Trabajando como COMITE: se permite.
        respuesta = self.ejecutar(VistaSoloComite, self.multirrol, rol_activo="COMITE")
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_multirrol_sin_encabezado_devuelve_403(self):
        """Con varios roles y sin encabezado no se sabe con cuál trabaja."""
        respuesta = self.ejecutar(VistaSoloComite, self.multirrol)
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_un_solo_rol_no_necesita_encabezado(self):
        """Si el usuario tiene un solo rol, ese es su rol activo."""
        respuesta = self.ejecutar(VistaSoloComite, self.solo_comite)
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_vista_sin_roles_permitidos_falla_cerrado(self):
        """Un permiso mal configurado lanza un error en vez de abrir el endpoint."""
        with self.assertRaises(ImproperlyConfigured):
            self.ejecutar(VistaSinRolesConfigurados, self.solo_comite)