"""
Pruebas automáticas para el endpoint POST /api/articulos/ (HU-14.2 y CP-10).

Verifica:
- Camino exitoso (201 Created): crea el artículo con autor_responsable=request.user,
  estado POSTULADO y registra trazabilidad en HistorialEstado.
- Rechazo por fecha límite expirada (400 Bad Request) y aceptación antes del cierre.
- Validación de título (máx. 200 caracteres), resumen (máx. 300 palabras),
  palabras clave obligatorias y línea temática existente.
- Seguridad: 401 sin token y 403 si el rol activo no es AUTOR (ej. COMITE o ADMIN).
"""

from datetime import timedelta

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import LineaTematica
from usuarios.models import Rol, Usuario

from .models import Articulo, HistorialEstado


class CrearArticuloTests(APITestCase):
    """Pruebas de integración para POST /api/articulos/ (HU-14.2)."""

    @classmethod
    def setUpTestData(cls):
        """Crea roles, usuarios y una línea temática oficial para las pruebas."""
        cls.rol_autor = Rol.objects.get_or_create(nombre=Rol.Nombre.AUTOR)[0]
        cls.rol_comite = Rol.objects.get_or_create(nombre=Rol.Nombre.COMITE)[0]
        cls.rol_admin = Rol.objects.get_or_create(nombre=Rol.Nombre.ADMIN)[0]

        cls.linea_ia = LineaTematica.objects.get_or_create(
            nombre="Inteligencia Artificial"
        )[0]

        cls.autor = Usuario.objects.create_user(
            correo="autor.postulante@conferencia.edu.co",
            password="Password123",
            nombres="Laura",
            apellidos="Gómez",
            afiliacion="Universidad del Valle",
            pais="Colombia",
        )
        cls.autor.asignar_rol(Rol.Nombre.AUTOR)

        cls.comite = Usuario.objects.create_user(
            correo="comite.revisor@conferencia.edu.co",
            password="Password123",
            nombres="Andrés",
            apellidos="Pérez",
            afiliacion="Universidad del Valle",
            pais="Colombia",
        )
        cls.comite.asignar_rol(Rol.Nombre.COMITE)

        cls.url = reverse("articulos:crear-articulo")

    def payload_valido(self):
        """Devuelve un cuerpo válido para postular un artículo."""
        return {
            "titulo": "Arquitecturas híbridas para procesamiento de lenguaje natural",
            "resumen": "Este artículo presenta una evaluación experimental de modelos compactos.",
            "palabras_clave": "PLN, modelos híbridos, aprendizaje profundo",
            "linea_tematica": self.linea_ia.id,
        }

    def test_crear_articulo_exitoso_en_plazo_crea_historial(self):
        """Un AUTOR dentro del plazo crea el artículo en POSTULADO y registra HistorialEstado."""
        # Preparar
        fecha_futura = (timezone.now() + timedelta(days=3)).isoformat()
        self.client.force_authenticate(user=self.autor)

        # Ejecutar
        with override_settings(FECHA_LIMITE_POSTULACION=fecha_futura):
            respuesta = self.client.post(
                self.url,
                self.payload_valido(),
                format="json",
                HTTP_X_ROL_ACTIVO="AUTOR",
            )

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.data["autor_responsable"], self.autor.id)
        self.assertEqual(respuesta.data["estado"], Articulo.Estado.POSTULADO)
        self.assertEqual(
            respuesta.data["linea_tematica"],
            {"id": self.linea_ia.id, "nombre": self.linea_ia.nombre},
        )

        articulo = Articulo.objects.get(id=respuesta.data["id"])
        historial = HistorialEstado.objects.filter(articulo=articulo)
        self.assertEqual(historial.count(), 1)
        registro = historial.first()
        self.assertEqual(registro.estado_anterior, "")
        self.assertEqual(registro.estado_nuevo, Articulo.Estado.POSTULADO)
        self.assertEqual(registro.usuario_id, self.autor.id)

    def test_crear_articulo_con_fecha_limite_expirada_devuelve_400(self):
        """CP-10: Si fecha_actual > fecha_limite_postulacion retorna 400 y no crea artículo."""
        # Preparar
        fecha_vencida = (timezone.now() - timedelta(minutes=5)).isoformat()
        self.client.force_authenticate(user=self.autor)

        # Ejecutar
        with override_settings(FECHA_LIMITE_POSTULACION=fecha_vencida):
            respuesta = self.client.post(
                self.url,
                self.payload_valido(),
                format="json",
                HTTP_X_ROL_ACTIVO="AUTOR",
            )

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fecha_limite", respuesta.data)
        self.assertEqual(Articulo.objects.count(), 0)
        self.assertEqual(HistorialEstado.objects.count(), 0)

    def test_resumen_mayor_a_300_palabras_devuelve_400(self):
        """Rechaza resúmenes que superen las 300 palabras con 400 Bad Request."""
        # Preparar
        self.client.force_authenticate(user=self.autor)
        datos = self.payload_valido()
        datos["resumen"] = " ".join(["palabra"] * 301)

        # Ejecutar
        respuesta = self.client.post(
            self.url, datos, format="json", HTTP_X_ROL_ACTIVO="AUTOR"
        )

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("resumen", respuesta.data)

    def test_titulo_mayor_a_200_caracteres_devuelve_400(self):
        """Rechaza títulos con más de 200 caracteres con 400 Bad Request."""
        # Preparar
        self.client.force_authenticate(user=self.autor)
        datos = self.payload_valido()
        datos["titulo"] = "T" * 201

        # Ejecutar
        respuesta = self.client.post(
            self.url, datos, format="json", HTTP_X_ROL_ACTIVO="AUTOR"
        )

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("titulo", respuesta.data)

    def test_linea_tematica_inexistente_devuelve_400(self):
        """Rechaza una línea temática que no pertenezca al catálogo oficial."""
        # Preparar
        self.client.force_authenticate(user=self.autor)
        datos = self.payload_valido()
        datos["linea_tematica"] = 99999

        # Ejecutar
        respuesta = self.client.post(
            self.url, datos, format="json", HTTP_X_ROL_ACTIVO="AUTOR"
        )

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("linea_tematica", respuesta.data)

    def test_sin_autenticacion_devuelve_401(self):
        """Una petición sin token JWT recibe 401 Unauthorized."""
        # Ejecutar
        respuesta = self.client.post(
            self.url, self.payload_valido(), format="json"
        )

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rol_distinto_de_autor_devuelve_403(self):
        """Un usuario con rol activo COMITE recibe 403 Forbidden."""
        # Preparar
        self.client.force_authenticate(user=self.comite)

        # Ejecutar
        respuesta = self.client.post(
            self.url,
            self.payload_valido(),
            format="json",
            HTTP_X_ROL_ACTIVO="COMITE",
        )

        # Verificar
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)