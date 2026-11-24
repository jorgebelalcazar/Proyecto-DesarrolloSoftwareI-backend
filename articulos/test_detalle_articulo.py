"""
Pruebas del detalle técnico del artículo y URL firmada del PDF (HU-19).

Endpoint: GET /api/articulos/{id}/

Cubren:
- metadatos completos, palabras clave y orden de firmantes (autor + coautores);
- generación de URL firmada temporal desde VersionArticulo sin exponer ruta_pdf;
- tolerancia a fallos de Supabase Storage al firmar el enlace;
- control de acceso por rol activo (AUTOR responsable, coautor, COMITE, ADMIN,
  terceros y peticiones sin autenticar);
- llamada de crear_url_firmada_pdf al bucket privado de Supabase.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from conferencias.models import Conferencia
from core.models import LineaTematica
from usuarios.models import Rol, Usuario

from .almacenamiento import crear_url_firmada_pdf
from .excepciones import AlmacenamientoNoDisponible
from .models import Articulo, AutorArticulo, VersionArticulo

URL_FIRMADA_FALSA = (
    "https://proyecto.supabase.co/storage/v1/object/sign/articulos/1/doc.pdf?token=abc123"
)


def crear_usuario(correo, *roles, nombres="Ana", apellidos="Prueba"):
    """Crea un usuario de prueba con los roles indicados."""
    usuario = Usuario.objects.create_user(
        correo,
        "ClaveSegura123",
        nombres=nombres,
        apellidos=apellidos,
        afiliacion="Universidad del Valle",
        pais="Colombia",
    )
    for rol in roles:
        usuario.asignar_rol(rol)
    return usuario


def crear_conferencia(dias_para_cerrar=30):
    """Crea una edición vigente de la conferencia."""
    ahora = timezone.now()
    hoy = timezone.localdate()
    return Conferencia.objects.create(
        nombre="Nexo 2027",
        limite_postulacion=ahora + timedelta(days=dias_para_cerrar),
        limite_revision=ahora + timedelta(days=45),
        limite_correccion=ahora + timedelta(days=60),
        limite_version_final=ahora + timedelta(days=75),
        fecha_inicio_evento=hoy + timedelta(days=90),
        fecha_fin_evento=hoy + timedelta(days=92),
    )


@patch("articulos.serializers.crear_url_firmada_pdf", return_value=URL_FIRMADA_FALSA)
class DetalleArticuloTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.autor = crear_usuario(
            "autor@ejemplo.com", Rol.Nombre.AUTOR, nombres="Carlos", apellidos="Pérez"
        )
        cls.coautor_usuario = crear_usuario(
            "coautor@ejemplo.com", Rol.Nombre.AUTOR, nombres="Laura", apellidos="Gómez"
        )
        cls.otro_autor = crear_usuario("otro@ejemplo.com", Rol.Nombre.AUTOR)
        cls.comite = crear_usuario("comite@ejemplo.com", Rol.Nombre.COMITE)
        cls.admin = crear_usuario("admin@ejemplo.com", Rol.Nombre.ADMIN)

        cls.conferencia = crear_conferencia()
        cls.linea = LineaTematica.objects.get(nombre="Sistemas Inteligentes")

        cls.articulo = Articulo.objects.create(
            conferencia=cls.conferencia,
            linea_tematica=cls.linea,
            autor_responsable=cls.autor,
            titulo="Arquitecturas distribuidas en tiempo real",
            resumen="Resumen técnico del artículo.",
            palabras_clave="sistemas distribuidos, latencia, consenso",
        )

        AutorArticulo.objects.create(
            articulo=cls.articulo,
            nombre_completo="Laura Gómez",
            afiliacion="Universidad Nacional",
            correo="coautor@ejemplo.com",
            orden=1,
        )
        AutorArticulo.objects.create(
            articulo=cls.articulo,
            nombre_completo="Diego Ruiz",
            afiliacion="ICESI",
            correo="diego@externo.com",
            orden=2,
        )

    def setUp(self):
        self.url = f"/api/articulos/{self.articulo.id}/"
        self.client.force_authenticate(user=self.autor)

    def consultar(self, rol="AUTOR", url=None):
        """Atajo: GET al detalle con el encabezado X-Rol-Activo."""
        headers = {"HTTP_X_ROL_ACTIVO": rol} if rol else {}
        return self.client.get(url or self.url, **headers)

    # ------------------------------------------- Estructura y metadatos
    def test_autor_responsable_obtiene_ficha_tecnica_completa(self, firmar_url):
        VersionArticulo.objects.create(
            articulo=self.articulo,
            tipo=VersionArticulo.Tipo.INICIAL,
            numero=1,
            ruta_pdf="articulos/1/inicial.pdf",
        )

        respuesta = self.consultar(rol="AUTOR")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(respuesta.data),
            {
                "id",
                "titulo",
                "estado",
                "linea_tematica",
                "fecha_postulacion",
                "resumen",
                "palabras_clave",
                "firmantes",
                "tiene_pdf",
                "pdf_url",
                "pdf_expira_en",
            },
        )
        self.assertEqual(respuesta.data["titulo"], self.articulo.titulo)
        self.assertEqual(respuesta.data["linea_tematica"]["nombre"], "Sistemas Inteligentes")
        self.assertEqual(
            respuesta.data["palabras_clave"],
            ["sistemas distribuidos", "latencia", "consenso"],
        )
        self.assertTrue(respuesta.data["tiene_pdf"])
        self.assertEqual(respuesta.data["pdf_url"], URL_FIRMADA_FALSA)
        self.assertEqual(respuesta.data["pdf_expira_en"], 900)
        self.assertNotIn("ruta_pdf", str(respuesta.data))
        firmar_url.assert_called_once_with("articulos/1/inicial.pdf", expira_en=900)

    def test_firmantes_conservan_orden_principal_y_coautores(self, firmar_url):
        respuesta = self.consultar(rol="AUTOR")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        firmantes = respuesta.data["firmantes"]
        self.assertEqual(len(firmantes), 3)

        self.assertEqual(firmantes[0]["orden"], 1)
        self.assertTrue(firmantes[0]["es_principal"])
        self.assertEqual(firmantes[0]["correo"], "autor@ejemplo.com")

        self.assertEqual(firmantes[1]["orden"], 2)
        self.assertFalse(firmantes[1]["es_principal"])
        self.assertEqual(firmantes[1]["correo"], "coautor@ejemplo.com")

        self.assertEqual(firmantes[2]["orden"], 3)
        self.assertEqual(firmantes[2]["correo"], "diego@externo.com")

    # ------------------------------------------- Manejo del PDF y Supabase
    def test_articulo_sin_pdf_devuelve_pdf_url_none_sin_llamar_supabase(self, firmar_url):
        respuesta = self.consultar(rol="AUTOR")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertFalse(respuesta.data["tiene_pdf"])
        self.assertIsNone(respuesta.data["pdf_url"])
        self.assertIsNone(respuesta.data["pdf_expira_en"])
        firmar_url.assert_not_called()

    def test_firma_la_ultima_version_registrada(self, firmar_url):
        VersionArticulo.objects.create(
            articulo=self.articulo,
            tipo=VersionArticulo.Tipo.INICIAL,
            numero=1,
            ruta_pdf="articulos/1/v1.pdf",
        )
        VersionArticulo.objects.create(
            articulo=self.articulo,
            tipo=VersionArticulo.Tipo.CORRECCION,
            numero=2,
            ruta_pdf="articulos/1/v2.pdf",
        )

        respuesta = self.consultar(rol="AUTOR")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        firmar_url.assert_called_once_with("articulos/1/v2.pdf", expira_en=900)

    def test_si_supabase_falla_al_firmar_devuelve_200_con_pdf_url_none(self, firmar_url):
        VersionArticulo.objects.create(
            articulo=self.articulo,
            tipo=VersionArticulo.Tipo.INICIAL,
            numero=1,
            ruta_pdf="articulos/1/inicial.pdf",
        )
        firmar_url.side_effect = AlmacenamientoNoDisponible("Supabase fuera de línea")

        respuesta = self.consultar(rol="AUTOR")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertTrue(respuesta.data["tiene_pdf"])
        self.assertIsNone(respuesta.data["pdf_url"])

    # ------------------------------------------- Permisos y privacidad
    def test_coautor_con_cuenta_puede_consultar_el_detalle(self, firmar_url):
        self.client.force_authenticate(user=self.coautor_usuario)
        respuesta = self.consultar(rol="AUTOR")
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_comite_y_admin_pueden_consultar_cualquier_articulo(self, firmar_url):
        for usuario, rol in [(self.comite, "COMITE"), (self.admin, "ADMIN")]:
            with self.subTest(rol=rol):
                self.client.force_authenticate(user=usuario)
                respuesta = self.consultar(rol=rol)
                self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_otro_autor_ajeno_al_articulo_recibe_404(self, firmar_url):
        self.client.force_authenticate(user=self.otro_autor)
        respuesta = self.consultar(rol="AUTOR")
        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)

    def test_rol_no_permitido_devuelve_403(self, firmar_url):
        self.client.force_authenticate(user=self.otro_autor)
        for rol_invalido in ("REVISOR", "COMITE"):
            with self.subTest(rol=rol_invalido):
                respuesta = self.consultar(rol=rol_invalido)
                self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_sin_token_devuelve_401(self, firmar_url):
        self.client.force_authenticate(user=None)
        respuesta = self.consultar(rol="AUTOR")
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_articulo_inexistente_devuelve_404(self, firmar_url):
        respuesta = self.consultar(rol="AUTOR", url="/api/articulos/99999/")
        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)


class UrlFirmadaSupabaseTests(APITestCase):
    """Servicio crear_url_firmada_pdf en almacenamiento.py, sin red."""

    @override_settings(
        SUPABASE_URL="https://proyecto.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="llave-de-prueba",
        SUPABASE_STORAGE_BUCKET="articulos",
    )
    @patch("supabase.create_client")
    def test_genera_url_firmada_temporal_en_bucket_privado(self, create_client):
        bucket = MagicMock()
        bucket.create_signed_url.return_value = {"signedURL": URL_FIRMADA_FALSA}
        create_client.return_value.storage.from_.return_value = bucket

        url = crear_url_firmada_pdf("articulos/7/manuscrito.pdf", expira_en=600)

        create_client.assert_called_once_with(
            "https://proyecto.supabase.co", "llave-de-prueba"
        )
        create_client.return_value.storage.from_.assert_called_once_with("articulos")
        bucket.create_signed_url.assert_called_once_with("articulos/7/manuscrito.pdf", 600)
        self.assertEqual(url, URL_FIRMADA_FALSA)