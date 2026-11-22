"""
Pruebas automáticas para la edición administrativa de usuarios (HU-11).

Cubre los criterios de aceptación del endpoint PUT/PATCH /api/usuarios/{id}/:
- Acceso restringido exclusivamente a rol activo ADMIN o COMITE (401 y 403).
- Actualización de datos básicos, estado de cuenta, roles y especialidades (200).
- Validación en servidor para no dejar al sistema sin un ADMIN activo (400).
- Restricción para que COMITE no asigne ni revoque el rol ADMIN (400).
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import LineaTematica

from .models import Rol, Usuario


class EditarUsuarioAdminTests(APITestCase):
    """Pruebas del endpoint PUT/PATCH /api/usuarios/{id}/ (HU-11)."""

    @classmethod
    def setUpTestData(cls):
        """Prepara roles, líneas temáticas y usuarios base para las pruebas."""
        cls.rol_admin = Rol.objects.get_or_create(nombre=Rol.Nombre.ADMIN)[0]
        cls.rol_comite = Rol.objects.get_or_create(nombre=Rol.Nombre.COMITE)[0]
        cls.rol_autor = Rol.objects.get_or_create(nombre=Rol.Nombre.AUTOR)[0]

        cls.linea_ia = LineaTematica.objects.get_or_create(
            nombre="Inteligencia Artificial"
        )[0]
        cls.linea_bd = LineaTematica.objects.get_or_create(
            nombre="Bases de Datos"
        )[0]

        cls.admin = Usuario.objects.create_user(
            correo="admin@conferencia.edu.co",
            password="Password123",
            nombres="Carlos",
            apellidos="Administrador",
            afiliacion="Universidad del Valle",
            pais="Colombia",
        )
        cls.admin.asignar_rol(Rol.Nombre.ADMIN)

        cls.comite = Usuario.objects.create_user(
            correo="comite@conferencia.edu.co",
            password="Password123",
            nombres="Carolina",
            apellidos="Comité",
            afiliacion="Universidad del Valle",
            pais="Colombia",
        )
        cls.comite.asignar_rol(Rol.Nombre.COMITE)

        cls.autor = Usuario.objects.create_user(
            correo="autor@conferencia.edu.co",
            password="Password123",
            nombres="Andrés",
            apellidos="Autor",
            afiliacion="Universidad Nacional",
            pais="Colombia",
        )
        cls.autor.asignar_rol(Rol.Nombre.AUTOR)

    def _url_detalle(self, usuario_id):
        """Construye la URL /api/usuarios/{id}/."""
        return reverse("usuarios:editar-usuario", kwargs={"pk": usuario_id})

    def test_sin_autenticacion_recibe_401(self):
        """Una petición sin token JWT debe recibir 401 Unauthorized."""
        # Preparar
        url = self._url_detalle(self.autor.id)

        # Ejecutar
        respuesta = self.client.patch(url, {"nombres": "Nuevo"}, format="json")

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_autor_recibe_403(self):
        """Un usuario con rol activo AUTOR no puede editar a otros usuarios."""
        # Preparar
        self.client.force_authenticate(user=self.autor)
        self.client.credentials(HTTP_X_ROL_ACTIVO=Rol.Nombre.AUTOR)
        url = self._url_detalle(self.comite.id)

        # Ejecutar
        respuesta = self.client.patch(url, {"nombres": "Intruso"}, format="json")

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_edita_datos_roles_y_especialidades_con_patch(self):
        """Un ADMIN puede actualizar datos básicos, estado, roles y especialidades."""
        # Preparar
        self.client.force_authenticate(user=self.admin)
        self.client.credentials(HTTP_X_ROL_ACTIVO=Rol.Nombre.ADMIN)
        url = self._url_detalle(self.autor.id)
        payload = {
            "nombres": "Andrés Felipe",
            "afiliacion": "Universidad del Cauca",
            "roles": [Rol.Nombre.AUTOR, Rol.Nombre.COMITE],
            "especialidades": [self.linea_ia.id, self.linea_bd.id],
        }

        # Ejecutar
        respuesta = self.client.patch(url, payload, format="json")

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["nombres"], "Andrés Felipe")
        self.assertEqual(
            set(respuesta.data["roles"]),
            {Rol.Nombre.AUTOR, Rol.Nombre.COMITE},
        )
        ids_especialidades = {e["id"] for e in respuesta.data["especialidades"]}
        self.assertEqual(ids_especialidades, {self.linea_ia.id, self.linea_bd.id})

    def test_admin_actualizacion_completa_con_put(self):
        """Un ADMIN puede realizar una actualización completa mediante PUT."""
        # Preparar
        self.client.force_authenticate(user=self.admin)
        self.client.credentials(HTTP_X_ROL_ACTIVO=Rol.Nombre.ADMIN)
        url = self._url_detalle(self.autor.id)
        payload = {
            "correo": "autor.actualizado@conferencia.edu.co",
            "nombres": "Andrés",
            "apellidos": "Gómez",
            "tipo_documento": "CC",
            "numero_documento": "12345678",
            "afiliacion": "Univalle",
            "pais": "Colombia",
            "telefono": "3001234567",
            "activo": True,
            "roles": [Rol.Nombre.AUTOR],
            "especialidades": [],
        }

        # Ejecutar
        respuesta = self.client.put(url, payload, format="json")

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["correo"], "autor.actualizado@conferencia.edu.co")
        self.assertEqual(respuesta.data["apellidos"], "Gómez")

    def test_no_permite_quitar_rol_al_ultimo_admin_activo(self):
        """Debe fallar con 400 si se intenta quitar ADMIN al único administrador activo."""
        # Preparar
        self.client.force_authenticate(user=self.admin)
        self.client.credentials(HTTP_X_ROL_ACTIVO=Rol.Nombre.ADMIN)
        url = self._url_detalle(self.admin.id)

        # Ejecutar
        respuesta = self.client.patch(
            url, {"roles": [Rol.Nombre.COMITE]}, format="json"
        )

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("roles", respuesta.data)

    def test_no_permite_desactivar_al_ultimo_admin_activo(self):
        """Debe fallar con 400 si se intenta desactivar al único administrador activo."""
        # Preparar
        self.client.force_authenticate(user=self.admin)
        self.client.credentials(HTTP_X_ROL_ACTIVO=Rol.Nombre.ADMIN)
        url = self._url_detalle(self.admin.id)

        # Ejecutar
        respuesta = self.client.patch(url, {"activo": False}, format="json")

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("roles", respuesta.data)

    def test_permite_quitar_rol_admin_si_hay_otro_admin_activo(self):
        """Si existe otro administrador activo, sí permite quitar el rol ADMIN a uno."""
        # Preparar
        segundo_admin = Usuario.objects.create_user(
            correo="admin2@conferencia.edu.co",
            password="Password123",
            nombres="Laura",
            apellidos="Segunda",
            afiliacion="Univalle",
            pais="Colombia",
        )
        segundo_admin.asignar_rol(Rol.Nombre.ADMIN)

        self.client.force_authenticate(user=self.admin)
        self.client.credentials(HTTP_X_ROL_ACTIVO=Rol.Nombre.ADMIN)
        url = self._url_detalle(segundo_admin.id)

        # Ejecutar
        respuesta = self.client.patch(
            url, {"roles": [Rol.Nombre.AUTOR]}, format="json"
        )

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["roles"], [Rol.Nombre.AUTOR])

    def test_comite_no_puede_asignar_rol_admin(self):
        """Un miembro del comité no puede otorgar el rol ADMIN a otro usuario."""
        # Preparar
        self.client.force_authenticate(user=self.comite)
        self.client.credentials(HTTP_X_ROL_ACTIVO=Rol.Nombre.COMITE)
        url = self._url_detalle(self.autor.id)

        # Ejecutar
        respuesta = self.client.patch(
            url, {"roles": [Rol.Nombre.ADMIN]}, format="json"
        )

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("roles", respuesta.data)

    def test_especialidades_sin_rol_comite_devuelve_400(self):
        """No se pueden guardar especialidades si el usuario no tiene el rol COMITE."""
        # Preparar
        self.client.force_authenticate(user=self.admin)
        self.client.credentials(HTTP_X_ROL_ACTIVO=Rol.Nombre.ADMIN)
        url = self._url_detalle(self.autor.id)

        # Ejecutar
        respuesta = self.client.patch(
            url,
            {"roles": [Rol.Nombre.AUTOR], "especialidades": [self.linea_ia.id]},
            format="json",
        )

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("especialidades", respuesta.data)

    def test_correo_duplicado_devuelve_400(self):
        """No permite asignar un correo que ya pertenece a otro usuario."""
        # Preparar
        self.client.force_authenticate(user=self.admin)
        self.client.credentials(HTTP_X_ROL_ACTIVO=Rol.Nombre.ADMIN)
        url = self._url_detalle(self.autor.id)

        # Ejecutar
        respuesta = self.client.patch(
            url, {"correo": self.comite.correo}, format="json"
        )

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("correo", respuesta.data)