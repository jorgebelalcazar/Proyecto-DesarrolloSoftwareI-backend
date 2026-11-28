"""
Pruebas de las tablas del proceso de revisión (base de las HU-24 a HU-29).

Verifican las reglas que viven en la base de datos:
  - un jurado no se asigna dos veces al mismo artículo (HU-25, criterio 3);
  - una revisión PENDIENTE no tiene decisión ni fecha de entrega, y una
    COMPLETADA tiene las dos;
  - un criterio se califica una sola vez en cada revisión;
  - las evaluaciones no se pierden al intentar borrar artículos, jurados o
    criterios ya usados (PROTECT).
"""

from datetime import timedelta

from django.contrib import admin
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from articulos.models import Articulo
from conferencias.models import Conferencia, CriterioEvaluacion
from core.models import LineaTematica
from usuarios.models import Rol, Usuario

from .models import Calificacion, Revision


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


class ModelosRevisionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        """Datos comunes, creados UNA vez para todas las pruebas de la clase."""
        cls.autor = crear_usuario("autor@ejemplo.com", Rol.Nombre.AUTOR)
        cls.jurado = crear_usuario("jurado@ejemplo.com", Rol.Nombre.COMITE)
        cls.otro_jurado = crear_usuario("jurado2@ejemplo.com", Rol.Nombre.COMITE)
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
        cls.criterio = CriterioEvaluacion.objects.create(
            conferencia=cls.conferencia, nombre="Originalidad", puntaje_maximo=20
        )
        cls.articulo = Articulo.objects.create(
            conferencia=cls.conferencia,
            linea_tematica=LineaTematica.objects.get(nombre="Sistemas Inteligentes"),
            autor_responsable=cls.autor, titulo="Artículo", resumen="Resumen.",
            palabras_clave="IA",
        )

    def crear_revision(self, **datos):
        """Crea una revisión del artículo de prueba con el jurado por defecto."""
        datos.setdefault("articulo", self.articulo)
        datos.setdefault("revisor", self.jurado)
        return Revision.objects.create(**datos)

    def assert_rechazada_por_la_bd(self, **datos):
        """La base de datos debe rechazar la revisión con estos datos."""
        # atomic: tras un IntegrityError la transacción de la prueba sigue usable.
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.crear_revision(**datos)

    # ------------------------------------------------------- Valores iniciales
    def test_revision_nace_pendiente_y_sin_evaluacion(self):
        revision = self.crear_revision(asignado_por=self.otro_jurado)

        self.assertEqual(revision.estado, Revision.Estado.PENDIENTE)
        self.assertEqual(revision.decision, "")
        self.assertEqual(revision.comentarios, "")
        self.assertIsNotNone(revision.fecha_asignacion)
        self.assertIsNone(revision.fecha_entrega)
        self.assertFalse(revision.completada)
        self.assertEqual(revision.asignado_por, self.otro_jurado)

    def test_revision_completada_valida(self):
        revision = self.crear_revision(
            estado=Revision.Estado.COMPLETADA,
            decision=Revision.Decision.ACEPTADO,
            comentarios="Buen trabajo.",
            fecha_entrega=timezone.now(),
        )

        self.assertTrue(revision.completada)

    # ------------------------------------------- Jurado único por artículo
    def test_jurado_no_se_asigna_dos_veces_al_mismo_articulo(self):
        self.crear_revision()

        self.assert_rechazada_por_la_bd()

    def test_el_mismo_articulo_admite_jurados_distintos(self):
        self.crear_revision()
        self.crear_revision(revisor=self.otro_jurado)

        self.assertEqual(self.articulo.revisiones.count(), 2)

    # --------------------------------------------- Estado coherente (CHECK)
    def test_pendiente_no_admite_decision(self):
        self.assert_rechazada_por_la_bd(decision=Revision.Decision.ACEPTADO)

    def test_pendiente_no_admite_fecha_de_entrega(self):
        self.assert_rechazada_por_la_bd(fecha_entrega=timezone.now())

    def test_completada_exige_decision(self):
        self.assert_rechazada_por_la_bd(
            estado=Revision.Estado.COMPLETADA, fecha_entrega=timezone.now()
        )

    def test_completada_exige_fecha_de_entrega(self):
        self.assert_rechazada_por_la_bd(
            estado=Revision.Estado.COMPLETADA, decision=Revision.Decision.RECHAZADO
        )

    def test_decision_invalida_rechazada(self):
        self.assert_rechazada_por_la_bd(
            estado=Revision.Estado.COMPLETADA, decision="APROBADO",
            fecha_entrega=timezone.now(),
        )

    def test_estado_invalido_rechazado(self):
        self.assert_rechazada_por_la_bd(estado="EN_CURSO")

    # ----------------------------------------------------------- Calificación
    def test_calificacion_de_un_criterio(self):
        revision = self.crear_revision()
        calificacion = Calificacion.objects.create(
            revision=revision, criterio=self.criterio, puntaje=18
        )

        self.assertEqual(revision.calificaciones.get(), calificacion)
        self.assertEqual(str(calificacion), "Originalidad: 18/20")

    def test_criterio_se_califica_una_vez_por_revision(self):
        revision = self.crear_revision()
        Calificacion.objects.create(revision=revision, criterio=self.criterio, puntaje=10)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Calificacion.objects.create(revision=revision, criterio=self.criterio, puntaje=12)

    def test_puntaje_negativo_rechazado(self):
        revision = self.crear_revision()

        with self.assertRaises(IntegrityError), transaction.atomic():
            Calificacion.objects.create(revision=revision, criterio=self.criterio, puntaje=-1)

    # ------------------------------------------------- Borrado (on_delete)
    def test_borrar_revision_borra_sus_calificaciones(self):
        revision = self.crear_revision()
        Calificacion.objects.create(revision=revision, criterio=self.criterio, puntaje=10)

        revision.delete()

        self.assertFalse(Calificacion.objects.exists())

    def test_no_se_borra_articulo_con_revisiones(self):
        self.crear_revision()

        with self.assertRaises(ProtectedError):
            self.articulo.delete()

    def test_no_se_borra_jurado_con_revisiones(self):
        self.crear_revision()

        with self.assertRaises(ProtectedError):
            self.jurado.delete()

    def test_no_se_borra_criterio_ya_calificado(self):
        revision = self.crear_revision()
        Calificacion.objects.create(revision=revision, criterio=self.criterio, puntaje=10)

        with self.assertRaises(ProtectedError):
            self.criterio.delete()

    def test_borrar_quien_asigno_conserva_la_revision(self):
        asignador = crear_usuario("asignador@ejemplo.com", Rol.Nombre.COMITE)
        revision = self.crear_revision(asignado_por=asignador)

        asignador.delete()

        revision.refresh_from_db()
        self.assertIsNone(revision.asignado_por)

    # ----------------------------------------------------- Panel de admin
    def test_modelos_registrados_en_el_admin(self):
        self.assertIn(Revision, admin.site._registry)