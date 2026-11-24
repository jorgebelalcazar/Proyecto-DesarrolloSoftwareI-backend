"""Pruebas para la carga del PDF inicial en Supabase (HU-16)."""

from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from conferencias.models import Conferencia
from core.models import LineaTematica
from usuarios.models import Rol, Usuario

from .models import Articulo, VersionArticulo


class CargarPdfTests(APITestCase):
    """Verifica validación, permisos, almacenamiento y registro de la versión."""

    @classmethod
    def setUpTestData(cls):
        cls.autor = Usuario.objects.create_user(
            "autor-pdf@ejemplo.com",
            "ClaveSegura123",
            nombres="Ana",
            apellidos="Prueba",
            afiliacion="Universidad del Valle",
            pais="Colombia",
        )
        cls.autor.asignar_rol(Rol.Nombre.AUTOR)
        cls.otro_autor = Usuario.objects.create_user(
            "otro-pdf@ejemplo.com",
            "ClaveSegura123",
            nombres="Luis",
            apellidos="Prueba",
            afiliacion="Universidad del Valle",
            pais="Colombia",
        )
        cls.otro_autor.asignar_rol(Rol.Nombre.AUTOR)
        cls.comite = Usuario.objects.create_user(
            "comite-pdf@ejemplo.com",
            "ClaveSegura123",
            nombres="Sara",
            apellidos="Prueba",
            afiliacion="Universidad del Valle",
            pais="Colombia",
        )
        cls.comite.asignar_rol(Rol.Nombre.COMITE)
        cls.linea = LineaTematica.objects.get(nombre="Sistemas Inteligentes")
        ahora = timezone.now()
        cls.conferencia = Conferencia.objects.create(
            nombre="Nexo 2027",
            limite_postulacion=ahora + timedelta(days=10),
            limite_revision=ahora + timedelta(days=20),
            limite_correccion=ahora + timedelta(days=30),
            limite_version_final=ahora + timedelta(days=40),
            fecha_inicio_evento=timezone.localdate() + timedelta(days=50),
            fecha_fin_evento=timezone.localdate() + timedelta(days=52),
        )

    def setUp(self):
        self.articulo = Articulo.objects.create(
            conferencia=self.conferencia,
            linea_tematica=self.linea,
            autor_responsable=self.autor,
            titulo="Artículo de prueba",
            resumen="Resumen de prueba.",
            palabras_clave="prueba",
        )
        self.url = reverse("articulos:subir-version-inicial", args=[self.articulo.id])
        self.client.force_authenticate(user=self.autor)

    @staticmethod
    def pdf(nombre="manuscrito.pdf", contenido=b"%PDF-1.7 contenido"):
        """Crea un archivo temporal con los bytes indicados."""
        return SimpleUploadedFile(nombre, contenido, content_type="application/pdf")

    @patch("articulos.views.subir_pdf_articulo", return_value="articulos/1/inicial.pdf")
    def test_pdf_valido_se_registra_como_version_uno(self, subir):
        # Preparar: adjuntar un PDF pequeño y válido.
        respuesta = self.client.post(self.url, {"archivo": self.pdf()}, format="multipart")

        # Verificar: se registra la primera versión y se conserva la ruta privada.
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        version = VersionArticulo.objects.get(articulo=self.articulo)
        self.assertEqual(version.numero_version, 1)
        self.assertEqual(version.ruta_archivo, "articulos/1/inicial.pdf")
        self.assertEqual(version.cargado_por, self.autor)
        subir.assert_called_once()

    @patch("articulos.views.subir_pdf_articulo", return_value="articulos/1/inicial.pdf")
    def test_pdf_de_dos_mib_se_acepta_para_el_caso_cp12(self, subir):
        """El tamaño esperado en CP-12 sigue siendo válido en el servidor."""
        # Preparar: construir un PDF válido de 2 MiB, como en la prueba manual.
        archivo = self.pdf(contenido=b"%PDF-" + b"x" * (2 * 1024 * 1024 - 5))

        # Ejecutar: enviar el archivo como multipart.
        respuesta = self.client.post(self.url, {"archivo": archivo}, format="multipart")

        # Verificar: el servidor acepta el archivo y registra la versión inicial.
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertTrue(VersionArticulo.objects.filter(articulo=self.articulo, numero_version=1).exists())
        subir.assert_called_once()

    @patch("articulos.views.subir_pdf_articulo")
    def test_rechaza_extension_distinta_de_pdf(self, subir):
        respuesta = self.client.post(
            self.url, {"archivo": self.pdf("manuscrito.docx")}, format="multipart"
        )

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("archivo", respuesta.data)
        subir.assert_not_called()

    @patch("articulos.views.subir_pdf_articulo")
    def test_rechaza_archivo_mayor_a_10_mib(self, subir):
        archivo = self.pdf(contenido=b"%PDF-" + b"x" * (10 * 1024 * 1024))

        respuesta = self.client.post(self.url, {"archivo": archivo}, format="multipart")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        subir.assert_not_called()

    @patch("articulos.views.subir_pdf_articulo")
    def test_rechaza_pdf_de_doce_mib_para_el_caso_cp12(self, subir):
        """El tamaño de 12 MiB de CP-12 se rechaza antes de contactar Supabase."""
        # Preparar: construir un PDF válido que supera el máximo permitido.
        archivo = self.pdf(contenido=b"%PDF-" + b"x" * (12 * 1024 * 1024 - 5))

        # Ejecutar: enviar el archivo al endpoint.
        respuesta = self.client.post(self.url, {"archivo": archivo}, format="multipart")

        # Verificar: el servidor responde 400 y no intenta subirlo.
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("archivo", respuesta.data)
        subir.assert_not_called()

    @patch("articulos.views.subir_pdf_articulo", return_value="articulos/1/inicial.pdf")
    def test_alias_subir_pdf_usa_el_mismo_contrato(self, subir):
        """La ruta publicada por el front-end crea la misma versión inicial."""
        # Preparar: usar el alias que consume articleService.js.
        url = reverse("articulos:subir-pdf", args=[self.articulo.id])

        # Ejecutar: enviar un PDF válido al alias.
        respuesta = self.client.post(url, {"archivo": self.pdf()}, format="multipart")

        # Verificar: se conserva la misma respuesta y registro de versión.
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(VersionArticulo.objects.get(articulo=self.articulo).numero_version, 1)
        subir.assert_called_once()

    @patch("articulos.views.subir_pdf_articulo")
    def test_rechaza_archivo_sin_firma_pdf(self, subir):
        respuesta = self.client.post(
            self.url, {"archivo": self.pdf(contenido=b"texto plano")}, format="multipart"
        )

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        subir.assert_not_called()

    @patch("articulos.views.subir_pdf_articulo")
    def test_exige_adjuntar_un_archivo(self, subir):
        respuesta = self.client.post(self.url, {}, format="multipart")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        subir.assert_not_called()

    @patch("articulos.views.subir_pdf_articulo")
    def test_otro_autor_no_puede_subir_archivo_al_articulo(self, subir):
        self.client.force_authenticate(user=self.otro_autor)

        respuesta = self.client.post(self.url, {"archivo": self.pdf()}, format="multipart")

        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)
        subir.assert_not_called()

    @patch("articulos.views.subir_pdf_articulo")
    def test_comite_no_puede_subir_el_pdf(self, subir):
        self.client.force_authenticate(user=self.comite)

        respuesta = self.client.post(self.url, {"archivo": self.pdf()}, format="multipart")

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)
        subir.assert_not_called()

    @patch("articulos.views.subir_pdf_articulo")
    def test_sin_token_responde_401(self, subir):
        self.client.force_authenticate(user=None)

        respuesta = self.client.post(self.url, {"archivo": self.pdf()}, format="multipart")

        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)
        subir.assert_not_called()

    @patch("articulos.views.subir_pdf_articulo")
    def test_no_permite_cargar_dos_veces_la_version_inicial(self, subir):
        VersionArticulo.objects.create(
            articulo=self.articulo,
            numero_version=1,
            ruta_archivo="articulos/1/anterior.pdf",
            cargado_por=self.autor,
        )

        respuesta = self.client.post(self.url, {"archivo": self.pdf()}, format="multipart")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        subir.assert_not_called()

    @patch("articulos.views.subir_pdf_articulo", side_effect=OSError("sin conexión"))
    def test_si_supabase_no_responde_devuelve_503(self, subir):
        respuesta = self.client.post(self.url, {"archivo": self.pdf()}, format="multipart")

        self.assertEqual(respuesta.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(VersionArticulo.objects.filter(articulo=self.articulo).exists())

    @patch("articulos.views.eliminar_pdf_articulo")
    @patch("articulos.views.subir_pdf_articulo", return_value="articulos/1/inicial.pdf")
    @patch("articulos.models.VersionArticulo.objects.create", side_effect=RuntimeError)
    def test_limpia_el_archivo_si_falla_el_registro(
        self, crear_version, subir, eliminar
    ):
        respuesta = self.client.post(self.url, {"archivo": self.pdf()}, format="multipart")

        self.assertEqual(respuesta.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        eliminar.assert_called_once_with("articulos/1/inicial.pdf")
