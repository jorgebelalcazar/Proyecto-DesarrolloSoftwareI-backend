"""
Pruebas de la regla "todo miembro del comité tiene al menos una especialidad".

La regla está en validar_especialidades_comite (usuarios/serializers.py) y
se aplica en los tres caminos que pueden dejar a un miembro del comité sin
especialidades:
  - HU-02: crear una cuenta con el rol COMITE    (POST  /api/usuarios/crear/).
  - HU-10: editar el perfil propio               (PATCH /api/usuarios/mi-perfil/).
  - HU-11: editar la cuenta de otro usuario      (PATCH /api/usuarios/{id}/).

La prueba de la HU-02 (crear un comité sin especialidades -> 400) la escribió
Santiago en test_crear_usuario.py; aquí se cubren la HU-10 y la HU-11.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import LineaTematica

from .models import Rol, Usuario
from .serializers import MENSAJE_COMITE_SIN_ESPECIALIDAD, MENSAJE_ESPECIALIDADES_SOLO_COMITE


def crear_usuario(correo, nombres, *roles):
    """Crea un usuario de prueba con los roles indicados."""
    usuario = Usuario.objects.create_user(
        correo, "ClaveSegura123",
        nombres=nombres, apellidos="Prueba",
        afiliacion="Universidad del Valle", pais="Colombia",
    )
    for rol in roles:
        usuario.asignar_rol(rol)
    return usuario


class EspecialidadComiteTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        """
        Datos comunes, creados UNA vez para todas las pruebas de la clase.

        Las líneas temáticas ya existen: las carga la migración de datos.
        """
        cls.inteligentes = LineaTematica.objects.get(nombre="Sistemas Inteligentes")
        cls.software = LineaTematica.objects.get(nombre="Sistemas de Software")

        cls.admin = crear_usuario("admin@ejemplo.com", "Ana", Rol.Nombre.ADMIN)
        cls.autor = crear_usuario("autor@ejemplo.com", "Andrés", Rol.Nombre.AUTOR)
        cls.comite = crear_usuario("comite@ejemplo.com", "Carolina", Rol.Nombre.COMITE)
        cls.comite.especialidades.set([cls.inteligentes])

    def editar_cuenta(self, usuario, datos):
        """Atajo HU-11: el Administrador edita la cuenta de "usuario"."""
        self.client.force_authenticate(user=self.admin)
        return self.client.patch(
            reverse("usuarios:gestion", args=[usuario.pk]), datos, format="json"
        )

    def editar_mi_perfil(self, usuario, datos):
        """Atajo HU-10: "usuario" edita su propio perfil."""
        self.client.force_authenticate(user=usuario)
        return self.client.patch(reverse("usuarios:mi-perfil"), datos, format="json")

    def assert_rechazada(self, respuesta, mensaje):
        """Verifica un 400 con el mensaje indicado en "especialidades"."""
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(respuesta.data["especialidades"], [mensaje])

    # ------------------------------------------- HU-11: editar la cuenta
    def test_autor_no_pasa_al_comite_sin_especialidades(self):
        respuesta = self.editar_cuenta(self.autor, {"roles": ["AUTOR", "COMITE"]})

        self.assert_rechazada(respuesta, MENSAJE_COMITE_SIN_ESPECIALIDAD)
        self.assertFalse(self.autor.tiene_rol(Rol.Nombre.COMITE))

    def test_autor_pasa_al_comite_con_una_especialidad(self):
        respuesta = self.editar_cuenta(
            self.autor, {"roles": ["AUTOR", "COMITE"], "especialidades": [self.software.id]}
        )

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertTrue(self.autor.tiene_rol(Rol.Nombre.COMITE))

    def test_no_se_vacian_las_especialidades_de_un_miembro_del_comite(self):
        respuesta = self.editar_cuenta(self.comite, {"especialidades": []})

        self.assert_rechazada(respuesta, MENSAJE_COMITE_SIN_ESPECIALIDAD)
        self.assertEqual(list(self.comite.especialidades.all()), [self.inteligentes])

    def test_cambiar_roles_conservando_comite_mantiene_sus_especialidades(self):
        """Si no se envían especialidades, cuentan las que ya tiene."""
        respuesta = self.editar_cuenta(self.comite, {"roles": ["COMITE", "AUTOR"]})

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(list(self.comite.especialidades.all()), [self.inteligentes])

    def test_quien_deja_el_comite_no_necesita_especialidades(self):
        respuesta = self.editar_cuenta(self.comite, {"roles": ["AUTOR"]})

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertFalse(self.comite.especialidades.exists())

    def test_cambio_sin_roles_ni_especialidades_no_se_bloquea(self):
        """
        Un miembro del comité creado antes de esta regla, sin especialidades,
        puede recibir otros cambios: la regla solo se revisa al tocar roles
        o especialidades.
        """
        antiguo = crear_usuario("antiguo@ejemplo.com", "Pedro", Rol.Nombre.COMITE)

        respuesta = self.editar_cuenta(antiguo, {"telefono": "3001234567"})

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    # --------------------------------------------- HU-10: editar el perfil
    def test_miembro_del_comite_no_vacia_sus_especialidades(self):
        respuesta = self.editar_mi_perfil(self.comite, {"especialidades": []})

        self.assert_rechazada(respuesta, MENSAJE_COMITE_SIN_ESPECIALIDAD)
        self.assertEqual(list(self.comite.especialidades.all()), [self.inteligentes])

    def test_miembro_del_comite_si_reemplaza_sus_especialidades(self):
        respuesta = self.editar_mi_perfil(self.comite, {"especialidades": [self.software.id]})

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(list(self.comite.especialidades.all()), [self.software])

    def test_autor_sigue_sin_poder_tener_especialidades(self):
        respuesta = self.editar_mi_perfil(self.autor, {"especialidades": [self.software.id]})

        self.assert_rechazada(respuesta, MENSAJE_ESPECIALIDADES_SOLO_COMITE)