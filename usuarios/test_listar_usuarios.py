"""
Pruebas del directorio de usuarios (HU-08).

Cubren:
  - HU-08.1: el endpoint paginado y su acceso desde todos los roles.
  - HU-08.2: la optimización de consultas (el número de consultas no crece
    con la cantidad de usuarios).
  - La privacidad: qué usuarios y qué campos ve cada rol activo.
"""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import LineaTematica

from .models import Especialidad, Rol, Usuario

# Campos que ve cualquier usuario autenticado.
CAMPOS_PUBLICOS = {"id", "nombres", "apellidos", "afiliacion", "pais", "roles", "especialidades"}

# Campos adicionales que solo ven el Administrador y el Comité.
CAMPOS_GESTION = {"correo", "activo", "fecha_registro", "fecha_desactivacion"}


def crear_usuario(correo, *roles, apellidos="Usuario", activo=True):
    """Crea un usuario de prueba con los roles indicados."""
    usuario = Usuario.objects.create_user(
        correo, "ClaveSegura123",
        nombres="Prueba", apellidos=apellidos,
        afiliacion="Universidad del Valle", pais="Colombia",
        activo=activo,
    )
    for rol in roles:
        usuario.asignar_rol(rol)
    return usuario


class ListarUsuariosTests(APITestCase):
    def setUp(self):
        """Preparación común: un usuario por rol y uno desactivado."""
        self.url = reverse("usuarios:listar")
        self.admin = crear_usuario("admin@ejemplo.com", Rol.Nombre.ADMIN, apellidos="Admin")
        self.comite = crear_usuario("comite@ejemplo.com", Rol.Nombre.COMITE, apellidos="Comite")
        self.autor = crear_usuario("autor@ejemplo.com", Rol.Nombre.AUTOR, apellidos="Autor")
        self.inactivo = crear_usuario(
            "inactivo@ejemplo.com", Rol.Nombre.AUTOR, apellidos="Inactivo", activo=False
        )

    def listar_como(self, usuario, rol_activo=None, **parametros):
        """Atajo: consulta el directorio autenticado como "usuario"."""
        self.client.force_authenticate(user=usuario)
        encabezados = {"HTTP_X_ROL_ACTIVO": rol_activo} if rol_activo else {}
        return self.client.get(self.url, parametros, **encabezados)

    @staticmethod
    def ids(respuesta):
        """Ids de los usuarios de la página, para comparar fácilmente."""
        return {fila["id"] for fila in respuesta.data["results"]}

    # ------------------------------------------------------- Acceso (08.1)
    def test_sin_autenticacion_recibe_401(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_todos_los_roles_pueden_consultar(self):
        for usuario in (self.admin, self.comite, self.autor):
            with self.subTest(usuario=usuario.correo):
                respuesta = self.listar_como(usuario)
                self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_rol_activo_ajeno_recibe_403(self):
        """El validador global de la HU-04 sigue activo en este endpoint."""
        respuesta = self.listar_como(self.autor, rol_activo="ADMIN")
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    # --------------------------------------------------------- Paginación
    def test_respuesta_paginada(self):
        respuesta = self.listar_como(self.admin)

        # Verificar: la respuesta trae los metadatos de la paginación.
        self.assertEqual(set(respuesta.data.keys()), {"count", "next", "previous", "results"})
        self.assertEqual(respuesta.data["count"], 4)

    def test_page_size_divide_los_resultados(self):
        # Ejecutar: pedir páginas de 3 usuarios.
        primera = self.listar_como(self.admin, page_size=3)
        segunda = self.listar_como(self.admin, page_size=3, page=2)

        # Verificar: 3 en la primera, 1 en la segunda, sin repetidos.
        self.assertEqual(len(primera.data["results"]), 3)
        self.assertEqual(len(segunda.data["results"]), 1)
        self.assertIsNotNone(primera.data["next"])
        self.assertIsNone(segunda.data["next"])
        self.assertFalse(self.ids(primera) & self.ids(segunda))

    # ------------------------------------------------------- Privacidad
    def test_admin_y_comite_ven_campos_de_gestion_y_desactivados(self):
        for usuario in (self.admin, self.comite):
            with self.subTest(usuario=usuario.correo):
                respuesta = self.listar_como(usuario)

                # Verificar: campos públicos más los de gestión.
                fila = respuesta.data["results"][0]
                self.assertEqual(set(fila.keys()), CAMPOS_PUBLICOS | CAMPOS_GESTION)

                # Verificar: el usuario desactivado aparece.
                self.assertIn(self.inactivo.id, self.ids(respuesta))

    def test_autor_ve_solo_campos_publicos_y_usuarios_activos(self):
        respuesta = self.listar_como(self.autor)

        # Verificar: solo los campos públicos; nunca el correo ni la clave.
        fila = respuesta.data["results"][0]
        self.assertEqual(set(fila.keys()), CAMPOS_PUBLICOS)

        # Verificar: el usuario desactivado no aparece.
        self.assertNotIn(self.inactivo.id, self.ids(respuesta))
        self.assertEqual(respuesta.data["count"], 3)

    def test_multirrol_ve_segun_su_rol_activo(self):
        """Un usuario Autor y Comité ve el directorio según el rol con el que trabaja."""
        multirrol = crear_usuario("multirrol@ejemplo.com", Rol.Nombre.AUTOR, Rol.Nombre.COMITE)

        como_comite = self.listar_como(multirrol, rol_activo="COMITE")
        como_autor = self.listar_como(multirrol, rol_activo="AUTOR")
        sin_encabezado = self.listar_como(multirrol)

        self.assertIn("correo", como_comite.data["results"][0])
        self.assertNotIn("correo", como_autor.data["results"][0])
        # Sin encabezado no se sabe su rol: recibe la vista de menor privilegio.
        self.assertNotIn("correo", sin_encabezado.data["results"][0])

    def test_roles_y_especialidades_en_el_formato_del_catalogo(self):
        # Preparar: el miembro del comité se especializa en una línea.
        linea = LineaTematica.objects.get(nombre="Sistemas Inteligentes")
        Especialidad.objects.create(usuario=self.comite, linea_tematica=linea)

        # Ejecutar
        respuesta = self.listar_como(self.admin)
        fila = next(f for f in respuesta.data["results"] if f["id"] == self.comite.id)

        # Verificar: roles por código y especialidades con id y nombre.
        self.assertEqual(fila["roles"], ["COMITE"])
        self.assertEqual(fila["especialidades"], [{"id": linea.id, "nombre": linea.nombre}])

    # ------------------------------------------- Optimización (HU-08.2)
    def test_las_consultas_no_crecen_con_la_cantidad_de_usuarios(self):
        """
        Con prefetch_related, la página cuesta lo mismo con 4 o con 10 usuarios.
        Sin él, habría 2 consultas extra por cada usuario (roles y especialidades).
        """
        # Medir con los 4 usuarios del setUp.
        with CaptureQueriesContext(connection) as pocas:
            self.listar_como(self.admin)

        # Agregar 6 usuarios más, cada uno con rol, y medir de nuevo.
        for numero in range(6):
            crear_usuario(f"extra{numero}@ejemplo.com", Rol.Nombre.AUTOR)
        with CaptureQueriesContext(connection) as muchas:
            self.listar_como(self.admin)

        # Verificar: el número de consultas es el mismo.
        self.assertEqual(len(pocas.captured_queries), len(muchas.captured_queries))