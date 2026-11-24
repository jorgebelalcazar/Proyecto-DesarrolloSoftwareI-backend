"""
Pruebas del catálogo de líneas temáticas (HU-02.8).

Las 5 líneas existen en la base de datos de pruebas porque las carga la
migración de datos "usuarios/0002_datos_iniciales".
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from usuarios.models import Rol, Usuario

# Las 5 líneas temáticas definidas en el enunciado del proyecto.
LINEAS_DEL_ENUNCIADO = {
    "Sistemas Inteligentes",
    "Tecnologías en Informática",
    "Educación en Informática",
    "Sistemas de Software",
    "Software en la práctica",
}


class LineaTematicaListTests(APITestCase):
    def setUp(self):
        """Prepara el catálogo y un autor con rol activo válido."""
        self.url = reverse("lineas-tematicas")
        self.usuario = Usuario.objects.create_user(
            "ana@correo.com", "ClaveSegura123",
            nombres="Ana", apellidos="Pérez",
            afiliacion="Universidad del Valle", pais="Colombia",
        )
        self.usuario.asignar_rol(Rol.Nombre.AUTOR)

    def test_usuario_autenticado_obtiene_las_cinco_lineas(self):
        # Ejecutar: consultar el catálogo autenticado.
        self.client.force_authenticate(user=self.usuario)
        respuesta = self.client.get(self.url, HTTP_X_ROL_ACTIVO="AUTOR")

        # Verificar: 200 con las 5 líneas del enunciado.
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        nombres = {linea["nombre"] for linea in respuesta.data["results"]}
        self.assertEqual(nombres, LINEAS_DEL_ENUNCIADO)
        self.assertEqual(respuesta.data["count"], 5)

        # Verificar: cada línea trae exactamente su id y su nombre.
        for linea in respuesta.data["results"]:
            self.assertEqual(set(linea.keys()), {"id", "nombre"})

    def test_rechaza_un_rol_activo_que_el_usuario_no_tiene(self):
        """El encabezado no permite adoptar un rol ajeno."""
        self.client.force_authenticate(user=self.usuario)
        respuesta = self.client.get(self.url, HTTP_X_ROL_ACTIVO="COMITE")
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_sin_autenticacion_recibe_401(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_el_catalogo_es_de_solo_lectura(self):
        # Ejecutar: intentar crear una línea nueva, aun estando autenticado.
        self.client.force_authenticate(user=self.usuario)
        respuesta = self.client.post(
            self.url,
            {"nombre": "Línea nueva"},
            format="json",
            HTTP_X_ROL_ACTIVO="AUTOR",
        )

        # Verificar: 405 Method Not Allowed; el endpoint solo acepta GET.
        self.assertEqual(respuesta.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
