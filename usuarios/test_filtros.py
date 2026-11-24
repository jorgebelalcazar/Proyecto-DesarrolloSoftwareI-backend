"""
Pruebas de los filtros y la búsqueda del directorio de usuarios (HU-09).

Cubren:
  - HU-09.1: filtros por rol, especialidad y estado, solos y combinados.
  - HU-09.2: búsqueda libre por texto.
  - Validación: un filtro con un valor inexistente responde 400.
  - Privacidad: un Autor no puede buscar por correo ni ver desactivados.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import LineaTematica

from .models import Especialidad, Rol, Usuario


def crear_usuario(correo, nombres, *roles, afiliacion="Universidad del Valle", activo=True):
    """Crea un usuario de prueba con los roles indicados."""
    usuario = Usuario.objects.create_user(
        correo, "ClaveSegura123",
        nombres=nombres, apellidos="Prueba",
        afiliacion=afiliacion, pais="Colombia",
        activo=activo,
    )
    for rol in roles:
        usuario.asignar_rol(rol)
    return usuario


class FiltrosDirectorioTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        """
        Datos comunes, creados UNA vez para todas las pruebas de la clase.

        Las líneas temáticas ya existen: las carga la migración de datos.
        """
        cls.inteligentes = LineaTematica.objects.get(nombre="Sistemas Inteligentes")
        cls.software = LineaTematica.objects.get(nombre="Sistemas de Software")

        cls.admin = crear_usuario("admin@ejemplo.com", "Administradora", Rol.Nombre.ADMIN)
        cls.autor = crear_usuario("juan@ejemplo.com", "Juan", Rol.Nombre.AUTOR)
        cls.comite_ia = crear_usuario(
            "revisora.ia@ejemplo.com", "Laura", Rol.Nombre.COMITE, afiliacion="Universidad Nacional"
        )
        cls.comite_sw = crear_usuario("revisor.sw@ejemplo.com", "Pedro", Rol.Nombre.COMITE)
        cls.inactivo = crear_usuario("inactivo@ejemplo.com", "Inés", Rol.Nombre.AUTOR, activo=False)

        Especialidad.objects.create(usuario=cls.comite_ia, linea_tematica=cls.inteligentes)
        Especialidad.objects.create(usuario=cls.comite_sw, linea_tematica=cls.software)

    def setUp(self):
        self.url = reverse("usuarios:listar")

    def listar_como(self, usuario, **parametros):
        """Atajo: consulta el directorio como "usuario" con los parámetros indicados."""
        self.client.force_authenticate(user=usuario)
        return self.client.get(self.url, parametros)

    @staticmethod
    def ids(respuesta):
        """Ids de los usuarios de la respuesta, para comparar fácilmente."""
        return {fila["id"] for fila in respuesta.data["results"]}

    # ------------------------------------------------- Filtros (HU-09.1)
    def test_filtro_por_rol(self):
        respuesta = self.listar_como(self.admin, rol="COMITE")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(self.ids(respuesta), {self.comite_ia.id, self.comite_sw.id})

    def test_filtro_por_especialidad(self):
        respuesta = self.listar_como(self.admin, especialidad=self.inteligentes.id)
        self.assertEqual(self.ids(respuesta), {self.comite_ia.id})

    def test_filtro_por_estado(self):
        desactivados = self.listar_como(self.admin, estado="false")
        activos = self.listar_como(self.admin, estado="true")

        self.assertEqual(self.ids(desactivados), {self.inactivo.id})
        self.assertNotIn(self.inactivo.id, self.ids(activos))
        self.assertEqual(activos.data["count"], 4)

    def test_filtros_combinados(self):
        respuesta = self.listar_como(self.admin, rol="COMITE", especialidad=self.software.id)
        self.assertEqual(self.ids(respuesta), {self.comite_sw.id})

    def test_filtros_y_paginacion_combinados(self):
        respuesta = self.listar_como(self.admin, rol="COMITE", page_size=1)

        # Verificar: el total respeta el filtro y la página trae un solo usuario.
        self.assertEqual(respuesta.data["count"], 2)
        self.assertEqual(len(respuesta.data["results"]), 1)

    # ----------------------------------------------- Búsqueda (HU-09.2)
    def test_busqueda_por_nombre_sin_importar_mayusculas(self):
        respuesta = self.listar_como(self.admin, search="LAURA")
        self.assertEqual(self.ids(respuesta), {self.comite_ia.id})

    def test_busqueda_por_afiliacion(self):
        respuesta = self.listar_como(self.admin, search="nacional")
        self.assertEqual(self.ids(respuesta), {self.comite_ia.id})

    def test_gestor_puede_buscar_por_correo(self):
        respuesta = self.listar_como(self.admin, search="revisora.ia")
        self.assertEqual(self.ids(respuesta), {self.comite_ia.id})

    def test_busqueda_y_filtro_combinados(self):
        # "Prueba" es el apellido de todos; el filtro deja solo a los del comité.
        respuesta = self.listar_como(self.admin, search="prueba", rol="COMITE")
        self.assertEqual(self.ids(respuesta), {self.comite_ia.id, self.comite_sw.id})

    # --------------------------------------------------------- Validación
    def test_valor_de_filtro_inexistente_devuelve_400(self):
        casos = {"rol": "SUPERADMIN", "especialidad": 9999}
        for filtro, valor in casos.items():
            with self.subTest(filtro=filtro):
                respuesta = self.listar_como(self.admin, **{filtro: valor})
                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(filtro, respuesta.data)

    # --------------------------------------------------------- Privacidad
    def test_autor_no_puede_buscar_por_correo(self):
        """Si pudiera, descubriría a quién pertenece un correo que no se le muestra."""
        respuesta = self.listar_como(self.autor, search="revisora.ia")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["count"], 0)

    def test_autor_si_puede_buscar_por_nombre(self):
        respuesta = self.listar_como(self.autor, search="laura")
        self.assertEqual(self.ids(respuesta), {self.comite_ia.id})

    def test_autor_no_ve_desactivados_aunque_los_filtre(self):
        respuesta = self.listar_como(self.autor, estado="false")
        self.assertEqual(respuesta.data["count"], 0)