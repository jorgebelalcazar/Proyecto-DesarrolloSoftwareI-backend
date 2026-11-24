"""Pruebas de consulta de la rúbrica de evaluación (HU-22)."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from usuarios.models import Rol, Usuario

from .models import CriterioEvaluacion


class CriteriosEvaluacionApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        """Prepara un usuario de comité, un autor y criterios activos e inactivos."""
        cls.comite = Usuario.objects.create_user(
            "comite@ejemplo.com", "ClaveSegura123", nombres="Ana",
            apellidos="Prueba", afiliacion="Universidad", pais="Colombia",
        )
        cls.comite.asignar_rol(Rol.Nombre.COMITE)
        cls.autor = Usuario.objects.create_user(
            "autor@ejemplo.com", "ClaveSegura123", nombres="Luis",
            apellidos="Prueba", afiliacion="Universidad", pais="Colombia",
        )
        cls.autor.asignar_rol(Rol.Nombre.AUTOR)
        CriterioEvaluacion.objects.create(nombre="Metodología", peso=40, orden=2)
        CriterioEvaluacion.objects.create(nombre="Aporte", peso=60, orden=1)
        CriterioEvaluacion.objects.create(nombre="Archivado", peso=10, activo=False)

    def setUp(self):
        """Resuelve la ruta del catálogo para cada caso."""
        self.url = reverse("criterios-evaluacion")

    def test_sin_autenticacion_recibe_401(self):
        """La rúbrica requiere sesión."""
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_comite_recibe_criterios_activos_en_orden(self):
        """El comité ve todos los criterios activos en el orden configurado."""
        self.client.force_authenticate(user=self.comite)
        respuesta = self.client.get(self.url, HTTP_X_ROL_ACTIVO="COMITE")
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [fila["nombre"] for fila in respuesta.data["results"]],
            ["Aporte", "Metodología"],
        )
        self.assertEqual(respuesta.data["results"][0]["peso"], 60)
        self.assertEqual(respuesta.data["count"], 2)

    def test_autor_recibe_403(self):
        """El autor no puede consultar la rúbrica de trabajo del comité."""
        self.client.force_authenticate(user=self.autor)
        respuesta = self.client.get(self.url, HTTP_X_ROL_ACTIVO="AUTOR")
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)
