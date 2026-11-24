"""
Pruebas de la postulación de artículos (HU-14).

Endpoint: POST /api/articulos/

Cubren el caso de prueba CP-10 de la subtarea de QA HU-14.5:
  - postulación correcta dentro del plazo -> 201;
  - postulación con el plazo vencido -> 400.
Y además: edición vigente de la conferencia (HU-13), historial de estados,
campos que asigna el servidor, límites del título, del resumen y de las
palabras clave, línea temática obligatoria, rol activo y transacción.
"""

from datetime import timedelta
from unittest.mock import patch

from django.db import DatabaseError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from conferencias.models import Conferencia
from core.models import LineaTematica
from usuarios.models import Rol, Usuario

from .models import Articulo, HistorialEstado


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


def crear_conferencia(dias_para_cerrar_postulacion=30, nombre="Nexo 2027"):
    """
    Crea una edición vigente cuyo plazo de postulación cierra en los días
    indicados. Con un número negativo, el plazo ya venció.
    """
    ahora = timezone.now()
    hoy = timezone.localdate()
    cierre = dias_para_cerrar_postulacion
    return Conferencia.objects.create(
        nombre=nombre,
        limite_postulacion=ahora + timedelta(days=cierre),
        limite_revision=ahora + timedelta(days=cierre + 15),
        limite_correccion=ahora + timedelta(days=cierre + 30),
        limite_version_final=ahora + timedelta(days=cierre + 45),
        fecha_inicio_evento=hoy + timedelta(days=cierre + 60),
        fecha_fin_evento=hoy + timedelta(days=cierre + 62),
    )


class CrearArticuloTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        """
        Datos comunes, creados UNA vez para todas las pruebas de la clase.

        Las líneas temáticas ya existen: las carga la migración de datos.
        """
        cls.linea = LineaTematica.objects.get(nombre="Sistemas Inteligentes")
        cls.autor = crear_usuario("autor@ejemplo.com", Rol.Nombre.AUTOR)

    def setUp(self):
        self.url = reverse("articulos:lista")

    def datos_validos(self, **cambios):
        """Datos de un artículo correcto; "cambios" reemplaza los campos indicados."""
        datos = {
            "titulo": "Detección temprana de anomalías con redes neuronales",
            "resumen": "Este trabajo propone una arquitectura ligera de monitoreo.",
            "palabras_clave": "inteligencia artificial, redes neuronales",
            "linea_tematica": self.linea.id,
        }
        datos.update(cambios)
        return datos

    def postular(self, usuario=None, rol_activo=None, **cambios):
        """Atajo: POST /api/articulos/ como "usuario" (por defecto, el autor)."""
        self.client.force_authenticate(user=usuario or self.autor)
        encabezados = {"HTTP_X_ROL_ACTIVO": rol_activo} if rol_activo else {}
        return self.client.post(
            self.url, self.datos_validos(**cambios), format="json", **encabezados
        )

    # --------------------------------------- CP-10: postulación en plazo
    def test_postulacion_en_plazo_crea_el_articulo_y_su_historial(self):
        conferencia = crear_conferencia()

        respuesta = self.postular()

        # Verificar: 201 con los datos que asigna el servidor.
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.data["estado"], Articulo.Estado.POSTULADO)
        self.assertEqual(respuesta.data["autor_responsable"], self.autor.id)
        self.assertEqual(respuesta.data["conferencia"], conferencia.id)
        self.assertEqual(
            respuesta.data["linea_tematica"],
            {"id": self.linea.id, "nombre": "Sistemas Inteligentes"},
        )

        # Verificar: la primera fila del historial (HU-14.2).
        historial = HistorialEstado.objects.get(articulo_id=respuesta.data["id"])
        self.assertEqual(historial.estado_anterior, "")
        self.assertEqual(historial.estado_nuevo, Articulo.Estado.POSTULADO)
        self.assertEqual(historial.usuario, self.autor)

    def test_los_campos_del_servidor_no_se_pueden_enviar(self):
        """Estado, autor y conferencia los asigna el servidor, aunque lleguen en el JSON."""
        crear_conferencia()
        otro = crear_usuario("otro@ejemplo.com", Rol.Nombre.AUTOR)

        respuesta = self.postular(estado="APROBADO", autor_responsable=otro.id, conferencia=999)

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        articulo = Articulo.objects.get(pk=respuesta.data["id"])
        self.assertEqual(articulo.estado, Articulo.Estado.POSTULADO)
        self.assertEqual(articulo.autor_responsable, self.autor)

    # --------------------------------------- CP-10: plazo vencido
    def test_postulacion_con_el_plazo_vencido_devuelve_400(self):
        crear_conferencia(dias_para_cerrar_postulacion=-1)

        respuesta = self.postular()

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("venció", str(respuesta.data["detail"]))
        self.assertFalse(Articulo.objects.exists())

    def test_sin_edicion_vigente_devuelve_400(self):
        respuesta = self.postular()

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("No hay una edición", str(respuesta.data["detail"]))

    # ------------------------------------------- Validación de campos
    def test_titulo_de_200_caracteres_si_y_de_201_no(self):
        crear_conferencia()

        self.assertEqual(self.postular(titulo="A" * 200).status_code, status.HTTP_201_CREATED)

        respuesta = self.postular(titulo="A" * 201)
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("titulo", respuesta.data)

    def test_resumen_de_300_palabras_si_y_de_301_no(self):
        crear_conferencia()

        self.assertEqual(
            self.postular(resumen="palabra " * 300).status_code, status.HTTP_201_CREATED
        )

        respuesta = self.postular(resumen="palabra " * 301)
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("resumen", respuesta.data)

    def test_campos_de_texto_vacios_devuelven_400(self):
        crear_conferencia()
        for campo, valor in {"titulo": "   ", "resumen": "   ", "palabras_clave": " , ,"}.items():
            with self.subTest(campo=campo):
                respuesta = self.postular(**{campo: valor})
                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(campo, respuesta.data)

    def test_las_palabras_clave_se_normalizan(self):
        crear_conferencia()

        respuesta = self.postular(palabras_clave=" IA ,redes,, salud ")

        self.assertEqual(respuesta.data["palabras_clave"], "IA, redes, salud")

    def test_linea_tematica_faltante_o_inexistente_devuelve_400(self):
        crear_conferencia()
        for valor in (None, 99999):
            with self.subTest(linea_tematica=valor):
                respuesta = self.postular(linea_tematica=valor)
                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("linea_tematica", respuesta.data)

    # ------------------------------------------------------------- Acceso
    def test_sin_token_devuelve_401(self):
        respuesta = self.client.post(self.url, self.datos_validos(), format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rol_activo_distinto_de_autor_devuelve_403(self):
        crear_conferencia()
        comite = crear_usuario("comite@ejemplo.com", Rol.Nombre.COMITE)

        respuesta = self.postular(usuario=comite)

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_usuario_con_varios_roles_postula_trabajando_como_autor(self):
        crear_conferencia()
        multirrol = crear_usuario("multi@ejemplo.com", Rol.Nombre.AUTOR, Rol.Nombre.COMITE)

        como_autor = self.postular(usuario=multirrol, rol_activo="AUTOR")
        como_comite = self.postular(usuario=multirrol, rol_activo="COMITE")

        self.assertEqual(como_autor.status_code, status.HTTP_201_CREATED)
        self.assertEqual(como_comite.status_code, status.HTTP_403_FORBIDDEN)

    # -------------------------------------------------------- Transacción
    def test_si_falla_el_historial_no_queda_el_articulo(self):
        """O se guardan el artículo y su historial, o ninguno de los dos."""
        crear_conferencia()
        self.client.force_authenticate(user=self.autor)

        with patch.object(HistorialEstado.objects, "create", side_effect=DatabaseError):
            with self.assertRaises(DatabaseError):
                self.client.post(self.url, self.datos_validos(), format="json")

        self.assertFalse(Articulo.objects.exists())