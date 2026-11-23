"""
Pruebas de la gestión de la cuenta de otro usuario (HU-11).

Endpoint: GET y PATCH /api/usuarios/{id}/

Cubren:
  - Acceso: 401 sin token, 403 para el Autor, 404 si el usuario no existe,
    405 para PUT.
  - Consulta (GET) y edición (PATCH) de datos, roles y especialidades.
  - Lista permitida: activo, clave, is_superuser... se rechazan con 400.
  - Jerarquía: el Comité no asigna ADMIN, no cambia correos y no modifica
    cuentas de Administradores.
  - HU-11.2: siempre queda un Administrador activo, en la API y en el modelo.
"""

from django.db import transaction
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import LineaTematica

from .models import MENSAJE_ULTIMO_ADMIN, Rol, SinAdministradorActivo, Usuario, UsuarioRol


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


def roles_de(usuario):
    """Códigos de los roles de un usuario, leídos de la base de datos."""
    return set(usuario.roles.values_list("nombre", flat=True))


class GestionUsuarioTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        """
        Datos comunes, creados UNA vez para todas las pruebas de la clase.

        Las líneas temáticas ya existen: las carga la migración de datos.
        """
        cls.inteligentes = LineaTematica.objects.get(nombre="Sistemas Inteligentes")
        cls.software = LineaTematica.objects.get(nombre="Sistemas de Software")

        cls.admin = crear_usuario("admin@ejemplo.com", "Ana", Rol.Nombre.ADMIN)
        cls.comite = crear_usuario("comite@ejemplo.com", "Carolina", Rol.Nombre.COMITE)
        cls.autor = crear_usuario("autor@ejemplo.com", "Andrés", Rol.Nombre.AUTOR)

    def url(self, usuario):
        """Dirección de la cuenta: /api/usuarios/{id}/."""
        return reverse("usuarios:gestion", args=[usuario.pk])

    def editar_como(self, quien, usuario, datos, rol_activo=None):
        """Atajo: PATCH a la cuenta de "usuario", autenticado como "quien"."""
        self.client.force_authenticate(user=quien)
        encabezados = {"HTTP_X_ROL_ACTIVO": rol_activo} if rol_activo else {}
        return self.client.patch(self.url(usuario), datos, format="json", **encabezados)

    # ------------------------------------------------------------- Acceso
    def test_sin_token_devuelve_401(self):
        respuesta = self.client.patch(self.url(self.autor), {"nombres": "X"}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_autor_no_puede_consultar_ni_editar(self):
        self.client.force_authenticate(user=self.autor)

        consulta = self.client.get(self.url(self.comite))
        edicion = self.client.patch(self.url(self.comite), {"nombres": "X"}, format="json")

        self.assertEqual(consulta.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(edicion.status_code, status.HTTP_403_FORBIDDEN)

    def test_usuario_con_varios_roles_trabajando_como_autor_recibe_403(self):
        """Cuenta el rol ACTIVO, no todos los roles que tiene (HU-04)."""
        self.comite.asignar_rol(Rol.Nombre.AUTOR)

        respuesta = self.editar_como(self.comite, self.autor, {"nombres": "X"}, rol_activo="AUTOR")

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_usuario_inexistente_devuelve_404(self):
        self.client.force_authenticate(user=self.admin)
        respuesta = self.client.patch(
            reverse("usuarios:gestion", args=[99999]), {"nombres": "X"}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)

    def test_put_no_esta_permitido(self):
        self.client.force_authenticate(user=self.admin)
        respuesta = self.client.put(self.url(self.autor), {"nombres": "X"}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # ---------------------------------------------------------- Consulta
    def test_gestor_consulta_la_cuenta_completa_sin_la_clave(self):
        Usuario.objects.filter(pk=self.comite.pk).update(telefono="3001234567")
        self.comite.especialidades.set([self.inteligentes])

        self.client.force_authenticate(user=self.admin)
        respuesta = self.client.get(self.url(self.comite))

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["telefono"], "3001234567")
        self.assertEqual(respuesta.data["roles"], ["COMITE"])
        self.assertEqual(
            respuesta.data["especialidades"],
            [{"id": self.inteligentes.id, "nombre": "Sistemas Inteligentes"}],
        )
        self.assertNotIn("password", respuesta.data)
        self.assertNotIn("clave", respuesta.data)

    # ----------------------------------------------------------- Edición
    def test_admin_edita_datos_roles_y_especialidades(self):
        respuesta = self.editar_como(self.admin, self.autor, {
            "nombres": "Andrés Felipe",
            "roles": ["AUTOR", "COMITE"],
            "especialidades": [self.inteligentes.id, self.software.id],
        })

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.autor.refresh_from_db()
        self.assertEqual(self.autor.nombres, "Andrés Felipe")
        self.assertEqual(roles_de(self.autor), {"AUTOR", "COMITE"})
        self.assertEqual(
            {e["id"] for e in respuesta.data["especialidades"]},
            {self.inteligentes.id, self.software.id},
        )

    def test_comite_edita_a_un_autor_y_lo_suma_al_comite(self):
        respuesta = self.editar_como(self.comite, self.autor, {
            "afiliacion": "Universidad Nacional",
            "roles": ["AUTOR", "COMITE"],
            "especialidades": [self.software.id],
        })

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(roles_de(self.autor), {"AUTOR", "COMITE"})

    def test_patch_solo_cambia_lo_que_se_envia(self):
        self.editar_como(self.admin, self.comite, {"telefono": "3109876543"})

        self.comite.refresh_from_db()
        self.assertEqual(self.comite.telefono, "3109876543")
        self.assertEqual(self.comite.nombres, "Carolina")
        self.assertEqual(roles_de(self.comite), {"COMITE"})

    # ---------------------------------------------------- Lista permitida
    def test_campos_no_editables_devuelven_400_y_no_cambian_nada(self):
        casos = {
            "activo": False,                       # lo hace la HU-12
            "fecha_desactivacion": "2026-01-01T00:00:00Z",
            "password": "OtraClave123",
            "is_superuser": True,
            "acepta_tratamiento_datos": True,      # lo autoriza cada persona
        }
        for campo, valor in casos.items():
            with self.subTest(campo=campo):
                respuesta = self.editar_como(self.admin, self.autor, {campo: valor, "nombres": "X"})

                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(campo, respuesta.data)

        # Verificar: ningún envío guardó nada, ni siquiera el nombre.
        self.autor.refresh_from_db()
        self.assertTrue(self.autor.activo)
        self.assertFalse(self.autor.is_superuser)
        self.assertEqual(self.autor.nombres, "Andrés")
        self.assertTrue(self.autor.check_password("ClaveSegura123"))

    # ------------------------------------------------------------ Correo
    def test_admin_cambia_el_correo_y_se_guarda_en_minusculas(self):
        correo = "  Andres.Nuevo@Ejemplo.com "
        respuesta = self.editar_como(self.admin, self.autor, {"correo": correo})

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.autor.refresh_from_db()
        self.assertEqual(self.autor.correo, "andres.nuevo@ejemplo.com")

    def test_conservar_el_propio_correo_no_es_duplicado(self):
        respuesta = self.editar_como(self.admin, self.autor, {"correo": "AUTOR@ejemplo.com"})
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_correo_de_otra_cuenta_devuelve_400(self):
        respuesta = self.editar_como(self.admin, self.autor, {"correo": "Comite@Ejemplo.com"})

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("correo", respuesta.data)

    def test_comite_no_puede_cambiar_correos(self):
        """Quien cambia el correo puede pedir el PIN (HU-06) y quedarse con la cuenta."""
        respuesta = self.editar_como(self.comite, self.autor, {"correo": "mio@ejemplo.com"})

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("correo", respuesta.data)
        self.autor.refresh_from_db()
        self.assertEqual(self.autor.correo, "autor@ejemplo.com")

    # --------------------------------------------- Jerarquía de los roles
    def test_comite_no_puede_asignar_el_rol_admin(self):
        respuesta = self.editar_como(self.comite, self.autor, {"roles": ["AUTOR", "ADMIN"]})

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("roles", respuesta.data)
        self.assertEqual(roles_de(self.autor), {"AUTOR"})

    def test_comite_no_puede_modificar_la_cuenta_de_un_admin(self):
        respuesta = self.editar_como(self.comite, self.admin, {"nombres": "Otro"})

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.nombres, "Ana")

    def test_comite_si_puede_consultar_la_cuenta_de_un_admin(self):
        self.client.force_authenticate(user=self.comite)
        respuesta = self.client.get(self.url(self.admin))
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    # --------------------------------------- Roles y especialidades
    def test_lista_de_roles_vacia_devuelve_400(self):
        respuesta = self.editar_como(self.admin, self.autor, {"roles": []})

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(roles_de(self.autor), {"AUTOR"})

    def test_rol_o_especialidad_inexistente_devuelve_400(self):
        casos = {"roles": ["SUPERADMIN"], "especialidades": [99999]}
        for campo, valor in casos.items():
            with self.subTest(campo=campo):
                respuesta = self.editar_como(self.admin, self.comite, {campo: valor})
                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(campo, respuesta.data)

    def test_especialidades_sin_rol_comite_devuelven_400(self):
        respuesta = self.editar_como(self.admin, self.autor, {"especialidades": [self.software.id]})

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("especialidades", respuesta.data)

    def test_quien_deja_el_comite_pierde_sus_especialidades(self):
        self.comite.especialidades.set([self.inteligentes])

        respuesta = self.editar_como(self.admin, self.comite, {"roles": ["AUTOR"]})

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["especialidades"], [])
        self.assertFalse(self.comite.especialidades.exists())

    # ------------------------------- HU-11.2: el último Administrador activo
    def test_no_se_puede_quitar_el_rol_al_ultimo_admin(self):
        respuesta = self.editar_como(self.admin, self.admin, {"roles": ["AUTOR"]})

        # Verificar: 400 con el mensaje en "roles" (antes era un error 500).
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(respuesta.data["roles"], [MENSAJE_ULTIMO_ADMIN])
        self.assertEqual(roles_de(self.admin), {"ADMIN"})

    def test_ultimo_admin_puede_agregarse_roles_conservando_admin(self):
        """Conservar ADMIN no borra esa fila, así que la regla no se dispara."""
        respuesta = self.editar_como(self.admin, self.admin, {"roles": ["ADMIN", "COMITE"]})

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(roles_de(self.admin), {"ADMIN", "COMITE"})

    def test_si_hay_otro_admin_activo_si_se_puede_quitar_el_rol(self):
        crear_usuario("admin2@ejemplo.com", "Beatriz", Rol.Nombre.ADMIN)

        respuesta = self.editar_como(self.admin, self.admin, {"roles": ["AUTOR"]})

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(roles_de(self.admin), {"AUTOR"})

    def test_un_admin_desactivado_no_cuenta_como_el_que_queda(self):
        otro = crear_usuario("admin2@ejemplo.com", "Beatriz", Rol.Nombre.ADMIN)
        Usuario.objects.filter(pk=otro.pk).update(activo=False)

        respuesta = self.editar_como(self.admin, self.admin, {"roles": ["AUTOR"]})

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)


class ReglaUltimoAdminModeloTests(APITestCase):
    """
    HU-11.2 en el modelo: la regla se cumple aunque el cambio no venga de la
    API, por ejemplo desde el panel de administración o la consola de Django.
    """

    @classmethod
    def setUpTestData(cls):
        cls.admin = crear_usuario("admin@ejemplo.com", "Ana", Rol.Nombre.ADMIN, Rol.Nombre.AUTOR)

    def assert_sigue_siendo_admin(self):
        self.assertEqual(roles_de(self.admin), {"ADMIN", "AUTOR"})

    def test_borrar_la_fila_del_rol_es_rechazado(self):
        """Así borra el panel de administración una fila de "usuario_rol"."""
        fila = UsuarioRol.objects.get(usuario=self.admin, rol__nombre=Rol.Nombre.ADMIN)

        with self.assertRaises(SinAdministradorActivo):
            fila.delete()
        self.assert_sigue_siendo_admin()

    def test_borrar_en_lote_es_rechazado(self):
        with self.assertRaises(SinAdministradorActivo):
            UsuarioRol.objects.filter(usuario=self.admin).delete()
        self.assert_sigue_siendo_admin()

    def test_quitar_el_rol_con_remove_es_rechazado(self):
        # remove() no abre su propio punto de recuperación: el error invalida
        # la transacción en curso. Por eso se envuelve en una, como lo hace
        # el serializador en update().
        with self.assertRaises(SinAdministradorActivo), transaction.atomic():
            self.admin.roles.remove(Rol.objects.get(nombre=Rol.Nombre.ADMIN))
        self.assert_sigue_siendo_admin()

    def test_borrar_otros_roles_si_esta_permitido(self):
        UsuarioRol.objects.filter(usuario=self.admin, rol__nombre=Rol.Nombre.AUTOR).delete()
        self.assertEqual(roles_de(self.admin), {"ADMIN"})