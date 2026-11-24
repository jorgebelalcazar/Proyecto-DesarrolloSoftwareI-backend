"""
Pruebas de la deshabilitación de un artículo por el comité (HU-21).

Endpoint: PATCH /api/articulos/{id}/deshabilitar/

Cubren el caso de prueba CP-17 de la subtarea de QA HU-21.4:
  - el Comité deshabilita un artículo y queda el registro en el historial;
  - el cambio es irreversible y bloquea las modificaciones futuras.
Y además: acción exclusiva del Comité, motivo obligatorio de 10 caracteres,
sin borrado físico y reglas de la tabla en la base de datos.
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from conferencias.models import Conferencia
from core.models import LineaTematica
from usuarios.models import Rol, Usuario

from .models import Articulo, ArticuloYaDeshabilitado, HistorialEstado

MOTIVO = "El artículo no corresponde al alcance temático del evento."


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


class DeshabilitarArticuloTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        """Datos comunes, creados UNA vez para todas las pruebas de la clase."""
        cls.autor = crear_usuario("autor@ejemplo.com", Rol.Nombre.AUTOR)
        cls.comite = crear_usuario("comite@ejemplo.com", Rol.Nombre.COMITE)
        cls.admin = crear_usuario("admin@ejemplo.com", Rol.Nombre.ADMIN)
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

    def setUp(self):
        self.articulo = Articulo.objects.create(
            conferencia=self.conferencia,
            linea_tematica=LineaTematica.objects.get(nombre="Sistemas Inteligentes"),
            autor_responsable=self.autor, titulo="Artículo", resumen="Resumen.",
            palabras_clave="IA",
        )
        self.url = reverse("articulos:deshabilitar", args=[self.articulo.id])
        self.client.force_authenticate(user=self.comite)

    def deshabilitar(self, motivo=MOTIVO):
        return self.client.patch(self.url, {"motivo": motivo}, format="json")

    # --------------------------------- Deshabilitar (CP-17, criterios 2 y 3)
    def test_comite_deshabilita_el_articulo(self):
        respuesta = self.deshabilitar()

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["estado"], "DESHABILITADO")
        self.assertFalse(respuesta.data["habilitado"])
        self.assertEqual(respuesta.data["motivo_deshabilitacion"], MOTIVO)
        self.assertIsNotNone(respuesta.data["fecha_deshabilitacion"])

    def test_queda_registrado_en_el_historial(self):
        self.deshabilitar()

        fila = HistorialEstado.objects.get(articulo=self.articulo)
        self.assertEqual(fila.estado_anterior, "POSTULADO")
        self.assertEqual(fila.estado_nuevo, "DESHABILITADO")
        self.assertEqual(fila.usuario, self.comite)
        self.assertEqual(fila.observacion, MOTIVO)

    def test_no_hay_borrado_fisico(self):
        self.deshabilitar()
        self.assertTrue(Articulo.objects.filter(pk=self.articulo.pk).exists())

    def test_es_irreversible_no_se_repite(self):
        self.deshabilitar()

        respuesta = self.deshabilitar("Otro motivo cualquiera.")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(respuesta.data["detail"], "El artículo ya está deshabilitado.")
        self.assertEqual(HistorialEstado.objects.filter(articulo=self.articulo).count(), 1)

    def test_el_autor_ya_no_puede_modificarlo(self):
        self.deshabilitar()
        self.client.force_authenticate(user=self.autor)

        respuesta = self.client.patch(
            reverse("articulos:detalle", args=[self.articulo.id]),
            {"titulo": "Intento"}, format="json",
        )

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("deshabilitado", respuesta.data["detail"])

    # -------------------------------------------------- Motivo (HU-21.2)
    def test_motivo_obligatorio_de_al_menos_10_caracteres(self):
        for motivo in ("", "   ", "Corto", "x" * 9):
            with self.subTest(motivo=motivo):
                respuesta = self.deshabilitar(motivo)

                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("motivo", respuesta.data)

        self.articulo.refresh_from_db()
        self.assertTrue(self.articulo.habilitado)

    def test_motivo_de_10_caracteres_es_valido(self):
        self.assertEqual(self.deshabilitar("x" * 10).status_code, status.HTTP_200_OK)

    # ------------------------------------ Solo el Comité (criterio 1)
    def test_admin_y_autor_reciben_403(self):
        for usuario in (self.admin, self.autor):
            with self.subTest(usuario=usuario.correo):
                self.client.force_authenticate(user=usuario)
                self.assertEqual(self.deshabilitar().status_code, status.HTTP_403_FORBIDDEN)

        self.articulo.refresh_from_db()
        self.assertTrue(self.articulo.habilitado)

    def test_sin_token_devuelve_401(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.deshabilitar().status_code, status.HTTP_401_UNAUTHORIZED)

    def test_articulo_inexistente_devuelve_404(self):
        self.url = reverse("articulos:deshabilitar", args=[99999])
        self.assertEqual(self.deshabilitar().status_code, status.HTTP_404_NOT_FOUND)

    def test_solo_acepta_patch(self):
        for metodo in ("get", "post", "put", "delete"):
            with self.subTest(metodo=metodo):
                respuesta = getattr(self.client, metodo)(self.url)
                self.assertEqual(respuesta.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # ------------------------------------- Modelo y base de datos
    def test_el_metodo_del_modelo_no_deshabilita_dos_veces(self):
        self.articulo.deshabilitar(self.comite, MOTIVO)
        with self.assertRaises(ArticuloYaDeshabilitado):
            self.articulo.deshabilitar(self.comite, MOTIVO)

    def test_la_base_de_datos_rechaza_estados_incoherentes(self):
        casos = {
            "deshabilitado sin motivo ni fecha": {"estado": "DESHABILITADO", "habilitado": False},
            "habilitado en estado DESHABILITADO": {"estado": "DESHABILITADO"},
            "no habilitado en estado POSTULADO": {"habilitado": False},
        }
        for caso, cambios in casos.items():
            with self.subTest(caso=caso):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Articulo.objects.filter(pk=self.articulo.pk).update(**cambios)