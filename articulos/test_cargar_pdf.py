"""
Pruebas de la carga y reemplazo del PDF inicial del artículo (HU-16 y HU-23).

Endpoint: POST /api/articulos/{id}/versiones/

Cubren el caso de prueba CP-12 de la subtarea de QA HU-16.5:
  - un PDF válido de 2 MB se acepta;
  - un PDF de 12 MB y un archivo .docx se rechazan en el servidor.
Y además: firma %PDF, límite exacto de 10 MB, permisos, plazo, versión
versiones iniciales incrementales, fallos de Supabase, limpieza de archivos huérfanos y las
reglas de la tabla version_articulo en la base de datos.

Las pruebas NO se conectan con Supabase: la subida se reemplaza con
unittest.mock.patch. Así no dependen de internet ni llenan el bucket real.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from conferencias.models import Conferencia
from core.models import LineaTematica
from usuarios.models import Rol, Usuario

from .almacenamiento import subir_pdf_articulo
from .models import Articulo, VersionArticulo

RUTA_FALSA = "articulos/1/archivo-de-prueba.pdf"
UN_MB = 1024 * 1024


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


def crear_conferencia(dias_para_cerrar=30):
    """Edición de la conferencia; con días negativos, la postulación ya cerró."""
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


def pdf(nombre="manuscrito.pdf", tamano=1024, contenido=None, content_type="application/pdf"):
    """
    Archivo de prueba. Por defecto, un PDF de "tamano" bytes que empieza
    con la firma %PDF-.
    """
    if contenido is None:
        contenido = b"%PDF-" + b"x" * (tamano - 5)
    return SimpleUploadedFile(nombre, contenido, content_type=content_type)


# El nombre que se reemplaza es el que usa la vista: "articulos.views.<función>".
@patch("articulos.views.eliminar_pdf_articulo")
@patch("articulos.views.subir_pdf_articulo", return_value=RUTA_FALSA)
class SubirVersionInicialTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        """Datos comunes, creados UNA vez para todas las pruebas de la clase."""
        cls.autor = crear_usuario("autor@ejemplo.com", Rol.Nombre.AUTOR)
        cls.otro_autor = crear_usuario("otro@ejemplo.com", Rol.Nombre.AUTOR)
        cls.comite = crear_usuario("comite@ejemplo.com", Rol.Nombre.COMITE)
        cls.conferencia = crear_conferencia()
        cls.linea = LineaTematica.objects.get(nombre="Sistemas Inteligentes")
        cls.articulo = Articulo.objects.create(
            conferencia=cls.conferencia, linea_tematica=cls.linea,
            autor_responsable=cls.autor, titulo="Redes neuronales en el agro",
            resumen="Monitoreo de cultivos.", palabras_clave="IA, agro",
        )

    def setUp(self):
        self.url = reverse("articulos:versiones", args=[self.articulo.id])
        self.client.force_authenticate(user=self.autor)

    def subir(self, archivo=None, url=None):
        """Atajo: POST multipart con el archivo indicado (o sin archivo)."""
        datos = {"archivo": archivo} if archivo is not None else {}
        return self.client.post(url or self.url, datos, format="multipart")

    # ------------------------------------------- Caso exitoso (criterio 2)
    def test_pdf_valido_queda_registrado_como_version_1_inicial(self, subir, eliminar):
        respuesta = self.subir(pdf())

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        version = VersionArticulo.objects.get(articulo=self.articulo)
        self.assertEqual(version.tipo, VersionArticulo.Tipo.INICIAL)
        self.assertEqual(version.numero, 1)
        self.assertEqual(version.ruta_pdf, RUTA_FALSA)
        subir.assert_called_once()
        self.assertEqual(subir.call_args.args[0], self.articulo.id)

    def test_la_respuesta_no_expone_la_ruta_privada(self, subir, eliminar):
        respuesta = self.subir(pdf())

        self.assertEqual(
            set(respuesta.data),
            {"id", "articulo", "tipo", "tipo_nombre", "numero", "fecha_subida"},
        )
        self.assertEqual(respuesta.data["tipo_nombre"], "Inicial")

    # ----------------------------- CP-12 y validación del servidor (criterios 1 y 3)
    def test_cp12_pdf_de_2_mb_se_acepta(self, subir, eliminar):
        respuesta = self.subir(pdf(tamano=2 * UN_MB))
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    def test_pdf_de_exactamente_10_mb_se_acepta(self, subir, eliminar):
        respuesta = self.subir(pdf(tamano=10 * UN_MB))
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    def test_archivos_invalidos_se_rechazan_sin_subir_nada(self, subir, eliminar):
        casos = {
            "CP-12: PDF de 12 MB": pdf(tamano=12 * UN_MB),
            "un byte más de 10 MB": pdf(tamano=10 * UN_MB + 1),
            "CP-12: archivo .docx": pdf(nombre="manuscrito.docx"),
            "MIME incorrecto": pdf(content_type="application/octet-stream"),
            "PDF sin firma %PDF": pdf(contenido=b"PK\x03\x04 un docx renombrado"),
            "archivo vacío": pdf(contenido=b""),
        }
        for caso, archivo in casos.items():
            with self.subTest(caso=caso):
                respuesta = self.subir(archivo)

                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("archivo", respuesta.data)

        subir.assert_not_called()
        self.assertFalse(VersionArticulo.objects.exists())

    def test_sin_archivo_devuelve_400(self, subir, eliminar):
        respuesta = self.subir()

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(respuesta.data["archivo"], ["Debe adjuntar el PDF del artículo."])

    # ------------------------------------------------------------ Permisos
    def test_otro_autor_recibe_403(self, subir, eliminar):
        self.client.force_authenticate(user=self.otro_autor)

        respuesta = self.subir(pdf())

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)
        subir.assert_not_called()

    def test_comite_recibe_403(self, subir, eliminar):
        self.client.force_authenticate(user=self.comite)
        respuesta = self.subir(pdf())
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_sin_token_devuelve_401(self, subir, eliminar):
        self.client.force_authenticate(user=None)
        respuesta = self.subir(pdf())
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_articulo_inexistente_devuelve_404(self, subir, eliminar):
        url = reverse("articulos:versiones", args=[99999])
        respuesta = self.subir(pdf(), url=url)
        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)

    # ------------------------------------------- Reglas del artículo
    def test_reemplazo_registra_nueva_version_y_conserva_la_anterior(self, subir, eliminar):
        VersionArticulo.objects.create(
            articulo=self.articulo, tipo=VersionArticulo.Tipo.INICIAL,
            numero=1, ruta_pdf="articulos/1/anterior.pdf",
        )
        subir.return_value = "articulos/1/reemplazo.pdf"

        respuesta = self.subir(pdf())

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.data["tipo"], VersionArticulo.Tipo.INICIAL)
        self.assertEqual(respuesta.data["numero"], 2)
        versiones = list(self.articulo.versiones.order_by("numero"))
        self.assertEqual(len(versiones), 2)
        self.assertEqual(versiones[0].ruta_pdf, "articulos/1/anterior.pdf")
        self.assertEqual(versiones[1].ruta_pdf, "articulos/1/reemplazo.pdf")
        subir.assert_called_once()

    def test_con_el_plazo_vencido_devuelve_400(self, subir, eliminar):
        self.articulo.conferencia = crear_conferencia(dias_para_cerrar=-1)
        self.articulo.save()

        respuesta = self.subir(pdf())

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("venció", respuesta.data["detail"])
        subir.assert_not_called()

    def test_en_el_instante_limite_se_permite_el_reemplazo(self, subir, eliminar):
        limite = self.articulo.conferencia.limite_postulacion

        with patch("articulos.models.timezone.now", return_value=limite):
            respuesta = self.subir(pdf())

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    def test_articulo_deshabilitado_devuelve_400(self, subir, eliminar):
        
        self.articulo.deshabilitar(self.comite, "Fuera del alcance temático del evento.")

        respuesta = self.subir(pdf())

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("deshabilitado", respuesta.data["detail"])
        subir.assert_not_called()

    # ----------------------------------------------- Fallos de Supabase
    def test_si_supabase_falla_devuelve_503_y_no_registra(self, subir, eliminar):
        subir.side_effect = OSError("sin conexión")

        with self.assertLogs("articulos.views", level="ERROR"):
            respuesta = self.subir(pdf())

        self.assertEqual(respuesta.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertNotIn("conexión", respuesta.data["detail"])
        self.assertFalse(VersionArticulo.objects.exists())

    def test_si_falla_el_registro_se_borra_el_pdf_subido(self, subir, eliminar):
        with patch.object(VersionArticulo.objects, "create", side_effect=RuntimeError("BD caída")):
            with self.assertRaises(RuntimeError), self.assertLogs("django.request"):
                self.subir(pdf())

        eliminar.assert_called_once_with(RUTA_FALSA)


class ConexionSupabaseTests(APITestCase):
    """Servicio de almacenamiento.py (HU-16.1), sin conectarse a Supabase."""

    @override_settings(
        SUPABASE_URL="https://proyecto.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="llave-de-prueba",
        SUPABASE_STORAGE_BUCKET="articulos",
    )
    @patch("supabase.create_client")
    def test_sube_al_bucket_privado_con_un_nombre_aleatorio(self, create_client):
        bucket = MagicMock()
        create_client.return_value.storage.from_.return_value = bucket

        ruta = subir_pdf_articulo(7, pdf(nombre="../../otro.pdf"))

        create_client.assert_called_once_with("https://proyecto.supabase.co", "llave-de-prueba")
        create_client.return_value.storage.from_.assert_called_once_with("articulos")
        self.assertRegex(ruta, r"^articulos/7/[0-9a-f-]{36}\.pdf$")
        argumentos = bucket.upload.call_args.kwargs
        self.assertEqual(argumentos["path"], ruta)
        self.assertTrue(argumentos["file"].startswith(b"%PDF-"))
        self.assertEqual(argumentos["file_options"]["content-type"], "application/pdf")

    @override_settings(SUPABASE_URL="", SUPABASE_SERVICE_ROLE_KEY="")
    def test_sin_credenciales_la_api_responde_503(self):
        """Si falta el .env, el autor recibe 503 y no un error 500."""
        autor = crear_usuario("autor@ejemplo.com", Rol.Nombre.AUTOR)
        articulo = Articulo.objects.create(
            conferencia=crear_conferencia(),
            linea_tematica=LineaTematica.objects.get(nombre="Sistemas Inteligentes"),
            autor_responsable=autor, titulo="Título", resumen="Resumen.", palabras_clave="IA",
        )
        self.client.force_authenticate(user=autor)

        with self.assertLogs("articulos.views", level="ERROR"):
            respuesta = self.client.post(
                reverse("articulos:versiones", args=[articulo.id]),
                {"archivo": pdf()}, format="multipart",
            )

        self.assertEqual(respuesta.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)


class ReglasVersionArticuloTests(TestCase):
    """Restricciones de la tabla version_articulo en la base de datos."""

    @classmethod
    def setUpTestData(cls):
        autor = crear_usuario("autor@ejemplo.com", Rol.Nombre.AUTOR)
        cls.articulo = Articulo.objects.create(
            conferencia=crear_conferencia(),
            linea_tematica=LineaTematica.objects.get(nombre="Sistemas Inteligentes"),
            autor_responsable=autor, titulo="Título", resumen="Resumen.", palabras_clave="IA",
        )

    def crear(self, tipo, numero):
        return VersionArticulo.objects.create(
            articulo=self.articulo, tipo=tipo, numero=numero, ruta_pdf=f"articulos/x/{numero}.pdf"
        )

    def test_rechaza_numeros_invalidos_y_repetidos(self):
        Tipo = VersionArticulo.Tipo
        self.crear(Tipo.INICIAL, 1)
        casos = {
            "número repetido": (Tipo.CORRECCION, 1),
            "número cero": (Tipo.CORRECCION, 0),
        }
        for caso, (tipo, numero) in casos.items():
            with self.subTest(caso=caso):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.crear(tipo, numero)

    def test_acepta_reemplazos_iniciales_incrementales(self):
        self.crear(VersionArticulo.Tipo.INICIAL, 1)
        segunda = self.crear(VersionArticulo.Tipo.INICIAL, 2)
        self.assertEqual(segunda.tipo, VersionArticulo.Tipo.INICIAL)
        self.assertEqual(self.articulo.versiones.count(), 2)

    def test_acepta_la_correccion_despues_de_la_inicial(self):
        self.crear(VersionArticulo.Tipo.INICIAL, 1)
        self.crear(VersionArticulo.Tipo.CORRECCION, 2)
        self.assertEqual(self.articulo.versiones.count(), 2)
