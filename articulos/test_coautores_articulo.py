"""
Pruebas automáticas para la gestión de coautores/firmantes (HU-15.2 y CP-11).

Verifica:
- Registro, ordenamiento y edición transaccional de firmantes externos sin cuenta
  de usuario (200 OK).
- Prevención de correos electrónicos duplicados dentro del mismo artículo (400 Bad Request),
  incluso variando mayúsculas/minúsculas.
- Validación de formato de correo electrónico inválido (400 Bad Request).
- Seguridad: solo el autor responsable del artículo tiene permiso (403 Forbidden a otro autor
  o rol COMITE; 401 Unauthorized sin token).
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import LineaTematica
from usuarios.models import Rol, Usuario

from .models import Articulo, AutorArticulo


class CoautoresArticuloTests(APITestCase):
    """Pruebas de integración para GET/PUT /api/articulos/<id>/coautores/ (HU-15.2)."""

    @classmethod
    def setUpTestData(cls):
        """Prepara dos autores, un miembro del comité y un artículo propio."""
        Rol.objects.get_or_create(nombre=Rol.Nombre.AUTOR)
        Rol.objects.get_or_create(nombre=Rol.Nombre.COMITE)

        linea = LineaTematica.objects.get_or_create(
            nombre="Inteligencia Artificial"
        )[0]

        cls.autor_responsable = Usuario.objects.create_user(
            correo="responsable@conferencia.edu.co",
            password="Password123",
            nombres="Carlos",
            apellidos="Delgado",
            afiliacion="Universidad del Valle",
            pais="Colombia",
        )
        cls.autor_responsable.asignar_rol(Rol.Nombre.AUTOR)

        cls.otro_autor = Usuario.objects.create_user(
            correo="otro.autor@conferencia.edu.co",
            password="Password123",
            nombres="Diana",
            apellidos="Martínez",
            afiliacion="Universidad ICESI",
            pais="Colombia",
        )
        cls.otro_autor.asignar_rol(Rol.Nombre.AUTOR)

        cls.comite = Usuario.objects.create_user(
            correo="comite.hu15@conferencia.edu.co",
            password="Password123",
            nombres="Jorge",
            apellidos="Belalcázar",
            afiliacion="Universidad del Valle",
            pais="Colombia",
        )
        cls.comite.asignar_rol(Rol.Nombre.COMITE)

        cls.articulo = Articulo.objects.create(
            titulo="Modelos generativos aplicados a educación superior",
            resumen="Resumen de prueba para gestionar coautores externos.",
            palabras_clave="modelos generativos, educación",
            linea_tematica=linea,
            autor_responsable=cls.autor_responsable,
        )

        cls.url = reverse(
            "articulos:gestion-coautores",
            kwargs={"articulo_id": cls.articulo.id},
        )

    def test_registrar_ordenar_y_editar_coautores_externos_exitoso(self):
        """CP-11: Permite registrar y reordenar firmantes externos sin cuenta de usuario."""
        # Preparar
        self.client.force_authenticate(user=self.autor_responsable)
        payload_inicial = {
            "coautores": [
                {
                    "nombre_completo": "Carlos Enrique Delgado",
                    "afiliacion": "Universidad del Valle",
                    "correo": "carlos.delgado@correounivalle.edu.co",
                    "orden_firma": 1,
                },
                {
                    "nombre_completo": "Dra. Elena Rojas",
                    "afiliacion": "MIT",
                    "correo": "erojas@mit.edu",
                    "orden_firma": 2,
                },
            ]
        }

        # Ejecutar creación inicial
        respuesta_crear = self.client.put(
            self.url,
            payload_inicial,
            format="json",
            HTTP_X_ROL_ACTIVO="AUTOR",
        )

        # Verificar creación inicial
        self.assertEqual(respuesta_crear.status_code, status.HTTP_200_OK)
        self.assertEqual(len(respuesta_crear.data["coautores"]), 2)
        self.assertEqual(AutorArticulo.objects.filter(articulo=self.articulo).count(), 2)

        # Ejecutar edición y reordenamiento de firmantes
        payload_editado = {
            "coautores": [
                {
                    "nombre_completo": "Dra. Elena Rojas",
                    "afiliacion": "Massachusetts Institute of Technology",
                    "correo": "erojas@mit.edu",
                    "orden_firma": 1,
                },
                {
                    "nombre_completo": "Carlos Enrique Delgado",
                    "afiliacion": "Universidad del Valle",
                    "correo": "carlos.delgado@correounivalle.edu.co",
                    "orden_firma": 2,
                },
            ]
        }
        respuesta_editar = self.client.put(
            self.url,
            payload_editado,
            format="json",
            HTTP_X_ROL_ACTIVO="AUTOR",
        )

        # Verificar edición y orden final
        self.assertEqual(respuesta_editar.status_code, status.HTTP_200_OK)
        nombres_ordenados = [
            item["nombre_completo"] for item in respuesta_editar.data["coautores"]
        ]
        self.assertEqual(
            nombres_ordenados,
            ["Dra. Elena Rojas", "Carlos Enrique Delgado"],
        )
        self.assertEqual(AutorArticulo.objects.filter(articulo=self.articulo).count(), 2)

    def test_correos_duplicados_en_mismo_articulo_devuelve_400(self):
        """CP-11: Impide registrar correos repetidos dentro del mismo artículo."""
        # Preparar
        self.client.force_authenticate(user=self.autor_responsable)
        payload = {
            "coautores": [
                {
                    "nombre_completo": "Primer Firmante",
                    "afiliacion": "Univalle",
                    "correo": "investigador@univalle.edu.co",
                    "orden_firma": 1,
                },
                {
                    "nombre_completo": "Segundo Firmante Duplicado",
                    "afiliacion": "Univalle",
                    "correo": "INVESTIGADOR@univalle.edu.co",
                    "orden_firma": 2,
                },
            ]
        }

        # Ejecutar
        respuesta = self.client.put(
            self.url,
            payload,
            format="json",
            HTTP_X_ROL_ACTIVO="AUTOR",
        )

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("coautores", respuesta.data)
        self.assertEqual(AutorArticulo.objects.filter(articulo=self.articulo).count(), 0)

    def test_formato_correo_invalido_devuelve_400(self):
        """Rechaza firmantes con correo electrónico mal formado."""
        # Preparar
        self.client.force_authenticate(user=self.autor_responsable)
        payload = {
            "coautores": [
                {
                    "nombre_completo": "Investigador Sin Correo Valido",
                    "afiliacion": "Univalle",
                    "correo": "correo-no-valido",
                    "orden_firma": 1,
                }
            ]
        }

        # Ejecutar
        respuesta = self.client.put(
            self.url,
            payload,
            format="json",
            HTTP_X_ROL_ACTIVO="AUTOR",
        )

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("coautores", respuesta.data)

    def test_otro_autor_no_responsable_recibe_403(self):
        """Solo el autor responsable puede modificar los coautores de su artículo."""
        # Preparar
        self.client.force_authenticate(user=self.otro_autor)
        payload = {
            "coautores": [
                {
                    "nombre_completo": "Intruso",
                    "afiliacion": "ICESI",
                    "correo": "intruso@icesi.edu.co",
                    "orden_firma": 1,
                }
            ]
        }

        # Ejecutar
        respuesta = self.client.put(
            self.url,
            payload,
            format="json",
            HTTP_X_ROL_ACTIVO="AUTOR",
        )

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_rol_comite_recibe_403(self):
        """Un usuario con rol activo COMITE recibe 403 Forbidden."""
        # Preparar
        self.client.force_authenticate(user=self.comite)

        # Ejecutar
        respuesta = self.client.get(self.url, HTTP_X_ROL_ACTIVO="COMITE")

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_sin_autenticacion_recibe_401(self):
        """Una petición sin token JWT recibe 401 Unauthorized."""
        # Ejecutar
        respuesta = self.client.get(self.url)

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)