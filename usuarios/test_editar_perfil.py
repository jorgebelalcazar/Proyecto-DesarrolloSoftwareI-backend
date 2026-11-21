"""
Pruebas automáticas para la edición del propio perfil (HU-10).

Se ejecutan con:  python manage.py test usuarios.test_editar_perfil
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import LineaTematica
from usuarios.models import Rol, Usuario


class EditarPerfilTests(APITestCase):
    """Pruebas para GET/PATCH /api/usuarios/mi-perfil/ (HU-10.1 y HU-10.2)."""

    @classmethod
    def setUpTestData(cls):
        cls.rol_autor = Rol.objects.get_or_create(nombre=Rol.Nombre.AUTOR)[0]
        cls.rol_comite = Rol.objects.get_or_create(nombre=Rol.Nombre.COMITE)[0]
        cls.linea1 = LineaTematica.objects.get_or_create(nombre="Sistemas Inteligentes")[0]
        cls.linea2 = LineaTematica.objects.get_or_create(nombre="Ingeniería de Software")[0]

        cls.usuario = Usuario.objects.create_user(
            correo="autor@test.com",
            password="ClaveSegura123",
            nombres="Ana",
            apellidos="Pérez",
            afiliacion="Universidad del Valle",
            pais="Colombia",
        )
        cls.usuario.roles.add(cls.rol_autor)
        cls.usuario.especialidades.add(cls.linea1)

    def setUp(self):
        self.url = reverse("usuarios:mi-perfil")
        self.client.force_authenticate(user=self.usuario)
        self.client.credentials(HTTP_X_ROL_ACTIVO=Rol.Nombre.AUTOR)

    def test_consultar_mi_perfil(self):
        """GET devuelve los datos del usuario autenticado y sus especialidades."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["correo"], "autor@test.com")
        self.assertEqual(response.data["nombres"], "Ana")
        self.assertEqual(response.data["roles"], ["AUTOR"])
        self.assertEqual(
            response.data["especialidades"],
            [{"id": self.linea1.id, "nombre": self.linea1.nombre}],
        )

    def test_editar_datos_personales_y_especialidades(self):
        """PATCH actualiza campos permitidos y reemplaza especialidades en BD."""
        payload = {
            "nombres": "Ana María",
            "afiliacion": "Universidad Nacional",
            "telefono": "3001234567",
            "especialidades": [self.linea2.id],
        }
        response = self.client.patch(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.nombres, "Ana María")
        self.assertEqual(self.usuario.afiliacion, "Universidad Nacional")
        self.assertEqual(self.usuario.telefono, "3001234567")
        self.assertEqual(
            list(self.usuario.especialidades.values_list("id", flat=True)),
            [self.linea2.id],
        )

    def test_bloquea_auto_escalacion_de_roles_y_estado(self):
        """HU-10.2: Rechaza con 400 cualquier intento de cambiar roles, activo o correo."""
        payload = {
            "nombres": "Hacker",
            "roles": ["ADMIN"],
            "activo": False,
            "correo": "otro@test.com",
        }
        response = self.client.patch(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("roles", response.data)
        self.assertIn("activo", response.data)
        self.assertIn("correo", response.data)

        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.activo)
        self.assertEqual(self.usuario.correo, "autor@test.com")
        self.assertEqual(list(self.usuario.roles.values_list("nombre", flat=True)), ["AUTOR"])

    def test_requiere_autenticacion(self):
        """Un usuario anónimo recibe 401 Unauthorized."""
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)