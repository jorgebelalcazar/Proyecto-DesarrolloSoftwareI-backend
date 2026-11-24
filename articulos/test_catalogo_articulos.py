"""
Pruebas del catálogo de artículos para el Comité y el Administrador (HU-18).

Endpoint: GET /api/articulos/

Cubren el caso de prueba CP-14 de la subtarea de QA HU-18.5:
  - combinación simultánea de 2 y 3 filtros en el catálogo.
Y además: acceso por rol (la misma ruta postula con rol AUTOR), cada filtro
por separado, búsqueda parcial por texto, valores inválidos, formato de cada
fila, orden, paginación y número de consultas constante (criterio de rendimiento).
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


class CatalogoArticulosTests(APITestCase):
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

        cls.admin = crear_usuario("admin@ejemplo.com", "Ana", Rol.Nombre.ADMIN)
        cls.comite = crear_usuario("comite@ejemplo.com", "Carolina", Rol.Nombre.COMITE)
        cls.ana = crear_usuario("ana@ejemplo.com", "Ana", Rol.Nombre.AUTOR)
        cls.luis = crear_usuario("luis@ejemplo.com", "Luis", Rol.Nombre.AUTOR)

        # Cuatro artículos de dos autores, en dos líneas y dos estados.
        cls.ana_ia = cls.crear_articulo(
            cls.ana, "Redes neuronales en el agro", cls.inteligentes,
            resumen="Monitoreo de cultivos con sensores.", palabras_clave="IA, agro",
        )
        cls.ana_sw = cls.crear_articulo(
            cls.ana, "Pruebas automatizadas", cls.software,
            resumen="Calidad del software con integración continua.",
            palabras_clave="pruebas, calidad",
        )
        cls.luis_ia = cls.crear_articulo(
            cls.luis, "Visión artificial", cls.inteligentes,
            resumen="Detección de objetos con redes convolucionales.",
            palabras_clave="visión, imágenes",
        )
        cls.luis_revision = cls.crear_articulo(
            cls.luis, "Aprendizaje por refuerzo", cls.inteligentes,
            resumen="Agentes que aprenden jugando.", palabras_clave="agentes",
            estado=Articulo.Estado.EN_REVISION,
        )

    @classmethod
    def crear_articulo(cls, autor, titulo, linea, resumen, palabras_clave,
                       estado=Articulo.Estado.POSTULADO):
        """Crea un artículo directamente en la base de datos."""
        return Articulo.objects.create(
            conferencia=cls.conferencia, linea_tematica=linea, autor_responsable=autor,
            titulo=titulo, resumen=resumen, palabras_clave=palabras_clave, estado=estado,
        )

    def setUp(self):
        self.url = reverse("articulos:lista")

    def listar_como(self, usuario, rol_activo=None, **filtros):
        """Atajo: GET /api/articulos/ como "usuario", con filtros opcionales."""
        self.client.force_authenticate(user=usuario)
        encabezados = {"HTTP_X_ROL_ACTIVO": rol_activo} if rol_activo else {}
        return self.client.get(self.url, filtros, **encabezados)

    @staticmethod
    def ids(respuesta):
        """Ids de los artículos de la respuesta, para comparar fácilmente."""
        return {fila["id"] for fila in respuesta.data["results"]}

    # -------------------------------------------- Acceso (criterio 2)
    def test_comite_y_admin_ven_los_articulos_de_todos_los_autores(self):
        todos = {self.ana_ia.id, self.ana_sw.id, self.luis_ia.id, self.luis_revision.id}
        for usuario in (self.comite, self.admin):
            with self.subTest(usuario=usuario.correo):
                respuesta = self.listar_como(usuario)

                self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
                self.assertEqual(self.ids(respuesta), todos)

    def test_autor_no_ve_el_catalogo(self):
        """El Autor tiene su propio listado (HU-17); el catálogo es de gestión."""
        respuesta = self.listar_como(self.ana)
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_sin_token_devuelve_401(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cuenta_el_rol_activo_no_todos_los_roles(self):
        multirrol = crear_usuario("multi@ejemplo.com", "Marta", Rol.Nombre.AUTOR, Rol.Nombre.COMITE)

        como_comite = self.listar_como(multirrol, rol_activo="COMITE")
        como_autor = self.listar_como(multirrol, rol_activo="AUTOR")

        self.assertEqual(como_comite.status_code, status.HTTP_200_OK)
        self.assertEqual(como_autor.status_code, status.HTTP_403_FORBIDDEN)

    # ----------------------------------------- Filtros uno por uno (HU-18.2)
    def test_filtro_por_linea_tematica(self):
        respuesta = self.listar_como(self.comite, linea_tematica=self.software.id)
        self.assertEqual(self.ids(respuesta), {self.ana_sw.id})

    def test_filtro_por_estado(self):
        respuesta = self.listar_como(self.comite, estado="EN_REVISION")
        self.assertEqual(self.ids(respuesta), {self.luis_revision.id})

    def test_filtro_por_autor(self):
        respuesta = self.listar_como(self.comite, autor=self.ana.id)
        self.assertEqual(self.ids(respuesta), {self.ana_ia.id, self.ana_sw.id})

    def test_busqueda_parcial_sin_importar_mayusculas(self):
        casos = {
            "NEURONALES": {self.ana_ia.id},                # en el título
            "convolucionales": {self.luis_ia.id},          # en el resumen
            "calidad": {self.ana_sw.id},                   # en resumen y palabras clave
            "agentes": {self.luis_revision.id},            # en las palabras clave
        }
        for texto, esperados in casos.items():
            with self.subTest(search=texto):
                respuesta = self.listar_como(self.comite, search=texto)
                self.assertEqual(self.ids(respuesta), esperados)

    # -------------------------------- CP-14: 2 y 3 filtros combinados
    def test_dos_filtros_combinados_linea_y_estado(self):
        respuesta = self.listar_como(
            self.comite, linea_tematica=self.inteligentes.id, estado="POSTULADO"
        )
        self.assertEqual(self.ids(respuesta), {self.ana_ia.id, self.luis_ia.id})

    def test_tres_filtros_combinados_linea_estado_y_autor(self):
        respuesta = self.listar_como(
            self.comite, linea_tematica=self.inteligentes.id, estado="POSTULADO", autor=self.luis.id
        )
        self.assertEqual(self.ids(respuesta), {self.luis_ia.id})

    def test_filtros_y_busqueda_combinados(self):
        respuesta = self.listar_como(
            self.comite, linea_tematica=self.inteligentes.id, search="redes"
        )
        self.assertEqual(self.ids(respuesta), {self.ana_ia.id, self.luis_ia.id})

    def test_valor_de_filtro_inexistente_devuelve_400(self):
        casos = {"linea_tematica": 99999, "estado": "INVENTADO", "autor": 99999}
        for filtro, valor in casos.items():
            with self.subTest(filtro=filtro):
                respuesta = self.listar_como(self.comite, **{filtro: valor})

                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(filtro, respuesta.data)

    # ---------------------------------------- Formato, orden y paginación
    def test_cada_fila_trae_el_autor_responsable(self):
        respuesta = self.listar_como(self.comite, autor=self.luis.id, estado="EN_REVISION")
        fila = respuesta.data["results"][0]

        self.assertEqual(fila["titulo"], "Aprendizaje por refuerzo")
        self.assertEqual(fila["estado_nombre"], "En revisión")
        self.assertEqual(fila["autor_responsable"], {
            "id": self.luis.id, "nombres": "Luis", "apellidos": "Prueba",
            "correo": "luis@ejemplo.com",
        })
        self.assertNotIn("resumen", fila)

    def test_del_mas_reciente_al_mas_antiguo_y_paginado(self):
        respuesta = self.listar_como(self.comite, page_size=2)

        self.assertEqual(respuesta.data["count"], 4)
        ids = [fila["id"] for fila in respuesta.data["results"]]
        self.assertEqual(ids, [self.luis_revision.id, self.luis_ia.id])

    # ------------------------------------------ Rendimiento (criterio 3)
    def test_el_numero_de_consultas_no_crece_con_los_articulos(self):
        """
        Sin select_related, cada fila agregaría dos consultas: su línea
        temática y su autor (problema N+1). Con 4 o con 12 artículos, deben
        ser las mismas.
        """
        with CaptureQueriesContext(connection) as pocas:
            self.listar_como(self.comite)

        otro = crear_usuario("otro@ejemplo.com", "Pedro", Rol.Nombre.AUTOR)
        for numero in range(8):
            self.crear_articulo(otro, f"Extra {numero}", self.software, "Resumen.", "extra")
        with CaptureQueriesContext(connection) as muchas:
            self.listar_como(self.comite)

        self.assertEqual(len(pocas.captured_queries), len(muchas.captured_queries))