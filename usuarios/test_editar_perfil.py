"""
Pruebas de la consulta y edición del perfil propio (HU-10).

Cubren:
  - HU-10.1: consultar y editar los datos propios, incluidas las especialidades.
  - HU-10.2: bloqueo de la auto-escalación (roles, estado, correo, clave...).
  - Reglas: especialidades solo para el comité; PUT no permitido; 401 sin token.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import LineaTematica

from .models import Especialidad, Rol, Usuario


def crear_usuario(correo, *roles):
    """Crea un usuario de prueba con los roles indicados."""
    usuario = Usuario.objects.create_user(
        correo, "ClaveSegura123",
        nombres="Ana", apellidos="Pérez",
        afiliacion="Universidad del Valle", pais="Colombia",
    )
    for rol in roles:
        usuario.asignar_rol(rol)
    return usuario


class MiPerfilTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        """Un autor y un miembro del comité; las líneas las carga la migración."""
        cls.inteligentes = LineaTematica.objects.get(nombre="Sistemas Inteligentes")
        cls.software = LineaTematica.objects.get(nombre="Sistemas de Software")

        cls.autor = crear_usuario("autor@ejemplo.com", Rol.Nombre.AUTOR)
        cls.comite = crear_usuario("comite@ejemplo.com", Rol.Nombre.COMITE)
        Especialidad.objects.create(usuario=cls.comite, linea_tematica=cls.inteligentes)

    def setUp(self):
        self.url = reverse("usuarios:mi-perfil")

    def editar_como(self, usuario, datos):
        """Atajo: envía un PATCH al perfil autenticado como "usuario"."""
        self.client.force_authenticate(user=usuario)
        return self.client.patch(self.url, datos, format="json")

    # ---------------------------------------------------- Consulta (10.1)
    def test_consultar_mi_perfil(self):
        self.client.force_authenticate(user=self.comite)
        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["correo"], "comite@ejemplo.com")
        self.assertEqual(respuesta.data["roles"], ["COMITE"])
        self.assertEqual(
            respuesta.data["especialidades"],
            [{"id": self.inteligentes.id, "nombre": self.inteligentes.nombre}],
        )

    def test_sin_autenticacion_recibe_401(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    # ------------------------------------------------------ Edición (10.1)
    def test_editar_datos_personales(self):
        # Ejecutar: cambiar solo tres campos (edición parcial).
        respuesta = self.editar_como(self.autor, {
            "nombres": "Ana María",
            "afiliacion": "Universidad Nacional",
            "telefono": "3001234567",
        })

        # Verificar: 200, los cambios guardados y los demás datos intactos.
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.autor.refresh_from_db()
        self.assertEqual(self.autor.nombres, "Ana María")
        self.assertEqual(self.autor.afiliacion, "Universidad Nacional")
        self.assertEqual(self.autor.telefono, "3001234567")
        self.assertEqual(self.autor.apellidos, "Pérez")

    def test_comite_reemplaza_sus_especialidades(self):
        respuesta = self.editar_como(self.comite, {"especialidades": [self.software.id]})

        # Verificar: la respuesta y la base de datos tienen solo la nueva línea.
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(
            respuesta.data["especialidades"],
            [{"id": self.software.id, "nombre": self.software.nombre}],
        )
        self.assertEqual(list(self.comite.especialidades.all()), [self.software])

    def test_campo_obligatorio_en_blanco_devuelve_400(self):
        respuesta = self.editar_como(self.autor, {"nombres": ""})

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nombres", respuesta.data)

    def test_put_no_esta_permitido(self):
        self.client.force_authenticate(user=self.autor)
        respuesta = self.client.put(self.url, {"nombres": "Ana"}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # ----------------------------------------- Auto-escalación (HU-10.2)
    def test_bloquea_cambiar_roles_estado_y_correo(self):
        # Ejecutar: un autor intenta volverse administrador y cambiar su correo.
        respuesta = self.editar_como(self.autor, {
            "nombres": "Intruso",
            "roles": ["ADMIN"],
            "activo": False,
            "correo": "otro@ejemplo.com",
        })

        # Verificar: 400 con un error por cada campo prohibido.
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        for campo in ("roles", "activo", "correo"):
            self.assertIn(campo, respuesta.data)

        # Verificar: no se guardó NADA, ni siquiera el campo permitido.
        self.autor.refresh_from_db()
        self.assertEqual(self.autor.nombres, "Ana")
        self.assertTrue(self.autor.activo)
        self.assertEqual(self.autor.correo, "autor@ejemplo.com")
        self.assertEqual(list(self.autor.roles.values_list("nombre", flat=True)), ["AUTOR"])

    def test_bloquea_campos_que_no_estan_en_la_lista_permitida(self):
        """Lista permitida: también se rechazan campos que nadie previó, como la clave."""
        respuesta = self.editar_como(self.autor, {"password": "OtraClave123", "is_superuser": True})

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", respuesta.data)
        self.assertIn("is_superuser", respuesta.data)
        self.autor.refresh_from_db()
        self.assertTrue(self.autor.check_password("ClaveSegura123"))
        self.assertFalse(self.autor.is_superuser)

    def test_autor_no_puede_asignarse_especialidades(self):
        """Misma regla de la HU-02: las especialidades son solo del comité."""
        respuesta = self.editar_como(self.autor, {"especialidades": [self.inteligentes.id]})

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("especialidades", respuesta.data)
        self.assertFalse(self.autor.especialidades.exists())