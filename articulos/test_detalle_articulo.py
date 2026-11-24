"""
Pruebas del detalle de un artículo y el enlace firmado de su PDF (HU-19).

Endpoint: GET /api/articulos/{id}/

Cubren el caso de prueba CP-15 de la subtarea de QA HU-19.3:
  - el Autor y el Comité abren la ficha del artículo;
  - el enlace del PDF es firmado y temporal.
Y además: metadatos completos, coautores en orden de firma, la versión más
reciente del PDF, la ruta privada nunca expuesta, falla de Supabase,
acceso por rol activo (incluido quien tiene un solo rol y no envía el
encabezado) y número de consultas constante.

Las pruebas NO se conectan con Supabase: la firma se reemplaza con
unittest.mock.patch.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.db import connection
from django.test.utils import CaptureQueriesContext, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from conferencias.models import Conferencia
from core.models import LineaTematica
from usuarios.models import Rol, Usuario

from .almacenamiento import crear_url_firmada_pdf
from .models import Articulo, AutorArticulo, VersionArticulo

URL_FIRMADA = "https://proyecto.supabase.co/storage/v1/object/sign/articulos/1/v.pdf?token=abc"


def crear_usuario(correo, *roles, nombres="Ana"):
    """Crea un usuario de prueba con los roles indicados."""
    usuario = Usuario.objects.create_user(
        correo, "ClaveSegura123",
        nombres=nombres, apellidos="Prueba",
        afiliacion="Universidad del Valle", pais="Colombia",
    )
    for rol in roles:
        usuario.asignar_rol(rol)
    return usuario


def crear_conferencia():
    """Edición de la conferencia con la postulación abierta."""
    ahora = timezone.now()
    hoy = timezone.localdate()
    return Conferencia.objects.create(
        nombre="Nexo 2027",
        limite_postulacion=ahora + timedelta(days=30),
        limite_revision=ahora + timedelta(days=45),
        limite_correccion=ahora + timedelta(days=60),
        limite_version_final=ahora + timedelta(days=75),
        fecha_inicio_evento=hoy + timedelta(days=90),
        fecha_fin_evento=hoy + timedelta(days=92),
    )


# El nombre que se reemplaza es el que usa el serializador.
@patch("articulos.serializers.crear_url_firmada_pdf", return_value=URL_FIRMADA)
class DetalleArticuloTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        """Datos comunes, creados UNA vez para todas las pruebas de la clase."""
        cls.autor = crear_usuario("autor@ejemplo.com", Rol.Nombre.AUTOR, nombres="Carlos")
        cls.otro_autor = crear_usuario("otro@ejemplo.com", Rol.Nombre.AUTOR)
        cls.comite = crear_usuario("comite@ejemplo.com", Rol.Nombre.COMITE)
        cls.admin = crear_usuario("admin@ejemplo.com", Rol.Nombre.ADMIN)

        cls.articulo = Articulo.objects.create(
            conferencia=crear_conferencia(),
            linea_tematica=LineaTematica.objects.get(nombre="Sistemas Inteligentes"),
            autor_responsable=cls.autor,
            titulo="Arquitecturas distribuidas en tiempo real",
            resumen="Resumen completo del artículo.",
            palabras_clave="sistemas distribuidos, latencia, consenso",
        )
        # Se crean en desorden a propósito: la respuesta debe ir por "orden".
        AutorArticulo.objects.create(
            articulo=cls.articulo, nombre_completo="Diego Ruiz",
            afiliacion="ICESI", correo="diego@externo.com", orden=2,
        )
        AutorArticulo.objects.create(
            articulo=cls.articulo, nombre_completo="Laura Gómez",
            afiliacion="Universidad Nacional", correo="laura@externo.com", orden=1,
        )

    def setUp(self):
        self.url = reverse("articulos:detalle", args=[self.articulo.id])
        self.client.force_authenticate(user=self.autor)

    def agregar_version(self, tipo, numero):
        """Registra una versión del PDF directamente en la base de datos."""
        return VersionArticulo.objects.create(
            articulo=self.articulo, tipo=tipo, numero=numero,
            ruta_pdf=f"articulos/{self.articulo.id}/v{numero}.pdf",
        )

    # ------------------------------------------- Metadatos (criterio 1)
    def test_la_ficha_trae_todos_los_metadatos(self, firmar):
        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(respuesta.data),
            {
                "id", "titulo", "linea_tematica", "estado", "estado_nombre",
                "conferencia", "fecha_postulacion", "autor_responsable",
                "resumen", "palabras_clave", "coautores", "pdf",
            },
        )
        self.assertEqual(respuesta.data["resumen"], "Resumen completo del artículo.")
        self.assertEqual(
            respuesta.data["palabras_clave"], "sistemas distribuidos, latencia, consenso"
        )
        self.assertEqual(respuesta.data["linea_tematica"]["nombre"], "Sistemas Inteligentes")
        self.assertEqual(respuesta.data["autor_responsable"]["correo"], "autor@ejemplo.com")

    def test_coautores_en_orden_de_firma(self, firmar):
        respuesta = self.client.get(self.url)

        self.assertEqual(
            [(c["orden"], c["nombre_completo"]) for c in respuesta.data["coautores"]],
            [(1, "Laura Gómez"), (2, "Diego Ruiz")],
        )

    # --------------------------------------------- PDF firmado (criterio 2)
    def test_sin_pdf_responde_null_sin_llamar_a_supabase(self, firmar):
        respuesta = self.client.get(self.url)

        self.assertIsNone(respuesta.data["pdf"])
        firmar.assert_not_called()

    def test_entrega_el_enlace_firmado_sin_la_ruta_privada(self, firmar):
        self.agregar_version(VersionArticulo.Tipo.INICIAL, 1)

        pdf = self.client.get(self.url).data["pdf"]

        self.assertEqual(pdf["url"], URL_FIRMADA)
        self.assertEqual(pdf["vence_en_segundos"], 900)
        self.assertEqual(pdf["tipo"], "INICIAL")
        self.assertEqual(pdf["numero"], 1)
        self.assertNotIn("ruta_pdf", pdf)
        firmar.assert_called_once_with(f"articulos/{self.articulo.id}/v1.pdf")

    def test_firma_la_version_mas_reciente(self, firmar):
        self.agregar_version(VersionArticulo.Tipo.INICIAL, 1)
        self.agregar_version(VersionArticulo.Tipo.CORRECCION, 2)

        pdf = self.client.get(self.url).data["pdf"]

        self.assertEqual(pdf["tipo"], "CORRECCION")
        firmar.assert_called_once_with(f"articulos/{self.articulo.id}/v2.pdf")

    def test_si_supabase_falla_la_ficha_llega_sin_enlace(self, firmar):
        self.agregar_version(VersionArticulo.Tipo.INICIAL, 1)
        firmar.side_effect = OSError("sin conexión")

        with self.assertLogs("articulos.serializers", level="ERROR"):
            respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["pdf"]["numero"], 1)
        self.assertIsNone(respuesta.data["pdf"]["url"])
        self.assertIsNone(respuesta.data["pdf"]["vence_en_segundos"])

    # --------------------------------------- Acceso por rol (criterio 3)
    def test_comite_y_admin_ven_cualquier_articulo(self, firmar):
        for usuario in (self.comite, self.admin):
            with self.subTest(usuario=usuario.correo):
                # Tienen un solo rol: no envían X-Rol-Activo, igual que en el front.
                self.client.force_authenticate(user=usuario)
                respuesta = self.client.get(self.url)
                self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_otro_autor_recibe_403(self, firmar):
        self.client.force_authenticate(user=self.otro_autor)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_cuenta_el_rol_activo_no_todos_los_roles(self, firmar):
        multirrol = crear_usuario("multi@ejemplo.com", Rol.Nombre.AUTOR, Rol.Nombre.COMITE)
        self.client.force_authenticate(user=multirrol)

        como_comite = self.client.get(self.url, HTTP_X_ROL_ACTIVO="COMITE")
        como_autor = self.client.get(self.url, HTTP_X_ROL_ACTIVO="AUTOR")

        self.assertEqual(como_comite.status_code, status.HTTP_200_OK)
        self.assertEqual(como_autor.status_code, status.HTTP_403_FORBIDDEN)

    def test_un_rol_que_no_tiene_devuelve_403(self, firmar):
        respuesta = self.client.get(self.url, HTTP_X_ROL_ACTIVO="ADMIN")
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_sin_token_devuelve_401(self, firmar):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_articulo_inexistente_devuelve_404(self, firmar):
        url = reverse("articulos:detalle", args=[99999])
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)

    # ------------------------------------------------------- Rendimiento
    def test_el_numero_de_consultas_no_crece_con_coautores_ni_versiones(self, firmar):
        with CaptureQueriesContext(connection) as pocas:
            self.client.get(self.url)

        for numero in range(3, 9):
            AutorArticulo.objects.create(
                articulo=self.articulo, nombre_completo=f"Firmante {numero}",
                afiliacion="Univalle", correo=f"f{numero}@externo.com", orden=numero,
            )
        self.agregar_version(VersionArticulo.Tipo.INICIAL, 1)
        self.agregar_version(VersionArticulo.Tipo.CORRECCION, 2)
        with CaptureQueriesContext(connection) as muchas:
            self.client.get(self.url)

        self.assertEqual(len(pocas.captured_queries), len(muchas.captured_queries))


class UrlFirmadaSupabaseTests(APITestCase):
    """Servicio crear_url_firmada_pdf de almacenamiento.py (HU-19.1), sin red."""

    @override_settings(
        SUPABASE_URL="https://proyecto.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="llave-de-prueba",
        SUPABASE_STORAGE_BUCKET="articulos",
    )
    @patch("supabase.create_client")
    def test_firma_en_el_bucket_privado_por_15_minutos(self, create_client):
        bucket = MagicMock()
        bucket.create_signed_url.return_value = {"signedURL": URL_FIRMADA, "signedUrl": URL_FIRMADA}
        create_client.return_value.storage.from_.return_value = bucket

        url = crear_url_firmada_pdf("articulos/7/manuscrito.pdf")

        create_client.return_value.storage.from_.assert_called_once_with("articulos")
        bucket.create_signed_url.assert_called_once_with("articulos/7/manuscrito.pdf", 900)
        self.assertEqual(url, URL_FIRMADA)