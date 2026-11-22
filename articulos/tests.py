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

from .models import Articulo


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