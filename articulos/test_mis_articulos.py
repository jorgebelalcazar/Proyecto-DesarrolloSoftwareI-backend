"""
Pruebas del listado "Mis artículos" (HU-17).

Endpoint: GET /api/articulos/mis-articulos/

Cubren el caso de prueba CP-13 de la subtarea de QA HU-17.3:
  - dos autores: ninguno ve las postulaciones del otro.
Y además: formato de cada fila, orden, filtros por estado y línea temática
(solos, combinados y con valores inválidos), paginación, rol activo y número
de consultas constante (criterio de rendimiento).
"""

from datetime import timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from conferencias.models import Conferencia
from core.models import LineaTematica
from usuarios.models import Rol, Usuario

from .models import Articulo


def crear_usuario(correo, *roles):
    """Crea un usuario de prueba con los roles indicados."""
    usuario = Usuario.objects.create_user(
        correo, "ClaveSegura123",
        nombres="Ana", apellidos="Prueba",
        afiliacion="Universidad del Valle", pais="Colombia",
    )
    for rol in roles:
        usuario.asignar_rol(rol)
    return usuario


class MisArticulosTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        """
        Datos comunes, creados UNA vez para todas las pruebas de la clase.

        Las líneas temáticas ya existen: las carga la migración de datos.
        """
        ahora = timezone.now()
        hoy = timezone.localdate()
        cls.conferencia = Conferencia.objects.create(
            nombre="Nexo 2027",
            limite_postulacion=ahora + timedelta(days=30),
            limite_revision=ahora + timedelta(days=45),
            limite_correccion=ahora + timedelta(days=60),
            limite_version_final=ahora + timedelta(days=75),
            fecha_inicio_evento=hoy + timedelta(days=90),
            fecha_fin_evento=hoy + timedelta(days=92),
        )
        cls.inteligentes = LineaTematica.objects.get(nombre="Sistemas Inteligentes")
        cls.software = LineaTematica.objects.get(nombre="Sistemas de Software")

        cls.ana = crear_usuario("ana@ejemplo.com", Rol.Nombre.AUTOR)
        cls.luis = crear_usuario("luis@ejemplo.com", Rol.Nombre.AUTOR)

        # Ana: 3 artículos. Luis: 1 artículo.
        cls.ana_ia = cls.crear_articulo(cls.ana, "IA en el agro", cls.inteligentes)
        cls.ana_sw = cls.crear_articulo(cls.ana, "Pruebas de software", cls.software)
        cls.ana_revision = cls.crear_articulo(
            cls.ana, "Redes neuronales", cls.inteligentes, Articulo.Estado.EN_REVISION
        )
        cls.luis_ia = cls.crear_articulo(cls.luis, "Visión artificial", cls.inteligentes)

    @classmethod
    def crear_articulo(cls, autor, titulo, linea, estado=Articulo.Estado.POSTULADO):
        """Crea un artículo directamente en la base de datos."""
        return Articulo.objects.create(
            conferencia=cls.conferencia,
            linea_tematica=linea,
            autor_responsable=autor,
            titulo=titulo,
            resumen="Resumen.",
            palabras_clave="prueba",
            estado=estado,
        )

    def setUp(self):
        self.url = reverse("articulos:mis-articulos")

    def listar_como(self, usuario, rol_activo=None, **filtros):
        """Atajo: GET /api/articulos/mis-articulos/ como "usuario", con filtros opcionales."""
        self.client.force_authenticate(user=usuario)
        encabezados = {"HTTP_X_ROL_ACTIVO": rol_activo} if rol_activo else {}
        return self.client.get(self.url, filtros, **encabezados)

    @staticmethod
    def ids(respuesta):
        """Ids de los artículos de la respuesta, para comparar fácilmente."""
        return {fila["id"] for fila in respuesta.data["results"]}

    # ------------------------------------- CP-13: aislamiento entre autores
    def test_cada_autor_ve_solo_sus_articulos(self):
        de_ana = self.listar_como(self.ana)
        de_luis = self.listar_como(self.luis)

        self.assertEqual(de_ana.status_code, status.HTTP_200_OK)
        self.assertEqual(self.ids(de_ana), {self.ana_ia.id, self.ana_sw.id, self.ana_revision.id})
        self.assertEqual(self.ids(de_luis), {self.luis_ia.id})

    def test_los_filtros_no_permiten_ver_articulos_ajenos(self):
        """Ni filtrando por la línea de Luis, Ana ve el artículo de Luis."""
        respuesta = self.listar_como(self.ana, linea_tematica=self.inteligentes.id)
        self.assertNotIn(self.luis_ia.id, self.ids(respuesta))

    def test_autor_sin_articulos_recibe_una_lista_vacia(self):
        nuevo = crear_usuario("nuevo@ejemplo.com", Rol.Nombre.AUTOR)

        respuesta = self.listar_como(nuevo)

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["count"], 0)

    # ------------------------------------------------- Formato de las filas
    def test_cada_fila_trae_los_datos_de_la_tabla(self):
        respuesta = self.listar_como(self.luis)
        fila = respuesta.data["results"][0]

        self.assertEqual(fila["titulo"], "Visión artificial")
        self.assertEqual(
            fila["linea_tematica"], {"id": self.inteligentes.id, "nombre": "Sistemas Inteligentes"}
        )
        self.assertEqual(fila["estado"], "POSTULADO")
        self.assertEqual(fila["estado_nombre"], "Postulado")
        # Liviana: el resumen y los coautores van en el detalle (HU-19).
        self.assertNotIn("resumen", fila)
        self.assertNotIn("coautores", fila)

    def test_del_mas_reciente_al_mas_antiguo(self):
        respuesta = self.listar_como(self.ana)

        ids = [fila["id"] for fila in respuesta.data["results"]]
        self.assertEqual(ids, [self.ana_revision.id, self.ana_sw.id, self.ana_ia.id])

    # ------------------------------------------------ Filtros (criterio 3)
    def test_filtro_por_estado(self):
        respuesta = self.listar_como(self.ana, estado="EN_REVISION")
        self.assertEqual(self.ids(respuesta), {self.ana_revision.id})

    def test_filtro_por_linea_tematica(self):
        respuesta = self.listar_como(self.ana, linea_tematica=self.software.id)
        self.assertEqual(self.ids(respuesta), {self.ana_sw.id})

    def test_filtros_combinados(self):
        respuesta = self.listar_como(
            self.ana, estado="POSTULADO", linea_tematica=self.inteligentes.id
        )
        self.assertEqual(self.ids(respuesta), {self.ana_ia.id})

    def test_valor_de_filtro_inexistente_devuelve_400(self):
        for filtro, valor in {"estado": "INVENTADO", "linea_tematica": 99999}.items():
            with self.subTest(filtro=filtro):
                respuesta = self.listar_como(self.ana, **{filtro: valor})

                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(filtro, respuesta.data)

    def test_paginacion(self):
        respuesta = self.listar_como(self.ana, page_size=2)

        self.assertEqual(respuesta.data["count"], 3)
        self.assertEqual(len(respuesta.data["results"]), 2)
        self.assertIsNotNone(respuesta.data["next"])

    # ------------------------------------------------------------- Acceso
    def test_sin_token_devuelve_401(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rol_activo_distinto_de_autor_devuelve_403(self):
        comite = crear_usuario("comite@ejemplo.com", Rol.Nombre.COMITE)
        respuesta = self.listar_como(comite)
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_miembro_del_comite_que_tambien_es_autor_ve_los_suyos_como_autor(self):
        multirrol = crear_usuario("multi@ejemplo.com", Rol.Nombre.AUTOR, Rol.Nombre.COMITE)
        propio = self.crear_articulo(multirrol, "Propio", self.software)

        como_autor = self.listar_como(multirrol, rol_activo="AUTOR")
        como_comite = self.listar_como(multirrol, rol_activo="COMITE")

        self.assertEqual(self.ids(como_autor), {propio.id})
        self.assertEqual(como_comite.status_code, status.HTTP_403_FORBIDDEN)

    # --------------------------------------- Rendimiento (criterio 2)
    def test_el_numero_de_consultas_no_crece_con_los_articulos(self):
        """
        Sin select_related, cada artículo agregaría una consulta para leer su
        línea temática (problema N+1). Con 3 o con 10 artículos, deben ser las mismas.
        """
        with CaptureQueriesContext(connection) as pocas:
            self.listar_como(self.ana)

        for numero in range(7):
            self.crear_articulo(self.ana, f"Extra {numero}", self.software)
        with CaptureQueriesContext(connection) as muchas:
            self.listar_como(self.ana)

        self.assertEqual(len(pocas.captured_queries), len(muchas.captured_queries))