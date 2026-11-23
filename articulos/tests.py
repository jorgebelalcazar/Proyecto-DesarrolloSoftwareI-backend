"""
Pruebas automáticas para el modelo Articulo (HU-14.1).

Verifica:
- Creación de un artículo asociado a un autor responsable y a una línea temática.
- Generación automática de clave primaria autoincremental.
- Asignación del estado inicial POSTULADO por defecto.
- Validación de longitud máxima en título (200 caracteres) y restricción de línea temática.
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from core.models import LineaTematica
from usuarios.models import Rol, Usuario

from .models import Articulo, AutorArticulo


class ArticuloModelTests(TestCase):
    """Pruebas unitarias de la tabla articulo y su vinculación con Usuario (HU-14.1)."""

    @classmethod
    def setUpTestData(cls):
        """Prepara un autor y una línea temática oficial para las pruebas."""
        cls.rol_autor = Rol.objects.get_or_create(nombre=Rol.Nombre.AUTOR)[0]
        cls.linea_ia = LineaTematica.objects.get_or_create(
            nombre="Inteligencia Artificial"
        )[0]

        cls.autor = Usuario.objects.create_user(
            correo="autor.articulo@conferencia.edu.co",
            password="Password123",
            nombres="Carlos",
            apellidos="Delgado",
            afiliacion="Universidad del Valle",
            pais="Colombia",
        )
        cls.autor.asignar_rol(Rol.Nombre.AUTOR)

    def test_crear_articulo_asigna_estado_postulado_y_clave_primaria(self):
        """Al crear un artículo se genera su PK y el estado inicial es POSTULADO."""
        # Preparar
        datos = {
            "titulo": "Detección temprana de anomalías usando redes neuronales",
            "resumen": "Este trabajo propone una arquitectura ligera para monitoreo.",
            "palabras_clave": "inteligencia artificial, redes neuronales, anomalías",
            "linea_tematica": self.linea_ia,
            "autor_responsable": self.autor,
        }

        # Ejecutar
        articulo = Articulo.objects.create(**datos)

        # Verificar
        self.assertIsNotNone(articulo.id)
        self.assertEqual(articulo.estado, Articulo.Estado.POSTULADO)
        self.assertEqual(articulo.autor_responsable_id, self.autor.id)
        self.assertEqual(articulo.linea_tematica_id, self.linea_ia.id)
        self.assertIsNotNone(articulo.fecha_postulacion)
        self.assertEqual(articulo.observacion_deshabilitacion, "")

    def test_titulo_mayor_a_200_caracteres_falla_validacion(self):
        """El modelo rechaza títulos que superen los 200 caracteres."""
        # Preparar
        articulo = Articulo(
            titulo="A" * 201,
            resumen="Resumen breve de prueba.",
            palabras_clave="prueba, longitud",
            linea_tematica=self.linea_ia,
            autor_responsable=self.autor,
        )

        # Ejecutar y Verificar
        with self.assertRaises(ValidationError):
            articulo.full_clean()

    def test_articulo_sin_linea_tematica_falla_integridad(self):
        """La base de datos impide guardar un artículo sin línea temática asociada."""
        # Preparar
        articulo = Articulo(
            titulo="Artículo sin línea temática",
            resumen="Resumen de prueba.",
            palabras_clave="prueba",
            autor_responsable=self.autor,
        )

        # Ejecutar y Verificar
        with self.assertRaises(IntegrityError):
            articulo.save()


class AutorArticuloModelTests(TestCase):
    """Pruebas unitarias de la tabla autor_articulo sin FK a Usuario (HU-15.1)."""

    @classmethod
    def setUpTestData(cls):
        """Prepara un artículo base para asociar coautores/firmantes."""
        Rol.objects.get_or_create(nombre=Rol.Nombre.AUTOR)
        linea = LineaTematica.objects.get_or_create(
            nombre="Ingeniería de Software"
        )[0]

        autor = Usuario.objects.create_user(
            correo="responsable.hu15@conferencia.edu.co",
            password="Password123",
            nombres="Carlos",
            apellidos="Delgado",
            afiliacion="Universidad del Valle",
            pais="Colombia",
        )
        autor.asignar_rol(Rol.Nombre.AUTOR)

        cls.articulo = Articulo.objects.create(
            titulo="Arquitectura limpia para plataformas académicas",
            resumen="Resumen de prueba para coautores.",
            palabras_clave="arquitectura, software",
            linea_tematica=linea,
            autor_responsable=autor,
        )

    def test_crear_coautor_externo_sin_cuenta_usuario_y_ordenado(self):
        """Permite registrar firmantes sin FK a Usuario y los ordena por orden_firma."""
        # Preparar y Ejecutar
        segundo = AutorArticulo.objects.create(
            articulo=self.articulo,
            nombre_completo="María Fernanda Ruiz",
            afiliacion="Universidad Nacional",
            correo="mf.ruiz@unal.edu.co",
            orden_firma=2,
        )
        primero = AutorArticulo.objects.create(
            articulo=self.articulo,
            nombre_completo="Carlos Enrique Delgado",
            afiliacion="Universidad del Valle",
            correo="carlos.delgado@correounivalle.edu.co",
            orden_firma=1,
        )

        # Verificar
        firmantes = list(self.articulo.coautores.all())
        self.assertEqual([f.id for f in firmantes], [primero.id, segundo.id])
        self.assertEqual(primero.orden_firma, 1)
        self.assertEqual(segundo.orden_firma, 2)

    def test_correo_duplicado_en_mismo_articulo_falla_integridad(self):
        """La base de datos impide repetir correo dentro del mismo artículo."""
        # Preparar
        AutorArticulo.objects.create(
            articulo=self.articulo,
            nombre_completo="Investigador Uno",
            afiliacion="Univalle",
            correo="investigador@univalle.edu.co",
            orden_firma=1,
        )

        # Ejecutar y Verificar
        with self.assertRaises(IntegrityError):
            AutorArticulo.objects.create(
                articulo=self.articulo,
                nombre_completo="Investigador Duplicado",
                afiliacion="Univalle",
                correo="investigador@univalle.edu.co",
                orden_firma=2,
            )