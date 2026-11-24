"""
Pruebas del endpoint de registro de autores.

Casos de prueba de la guía del Sprint 1:
  - CP-01.A: registro exitoso de un autor, con respuesta HTTP 201.
  - CP-01.B: rechazo por correo duplicado.

Además se prueban las reglas de la clave, la autorización de datos y la
protección contra la asignación de roles por parte del cliente.

APITestCase incluye "self.client", un cliente HTTP de prueba que envía
peticiones a la API sin levantar el servidor.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Rol, Usuario


def datos_validos(**cambios):
    """
    Devuelve un registro válido. Con "cambios" se modifica algún campo.

    Ejemplo: datos_validos(clave="debil") devuelve los mismos datos, pero
    con una clave distinta.
    """
    datos = {
        "correo": "maria.gomez@ejemplo.com",
        "nombres": "María",
        "apellidos": "Gómez",
        "afiliacion": "Universidad del Valle",
        "pais": "Colombia",
        "clave": "ClaveSegura123",
        "confirmacion_clave": "ClaveSegura123",
        "acepta_tratamiento_datos": True,
    }
    datos.update(cambios)
    return datos


class RegistroAutorTests(APITestCase):
    def setUp(self):
        # reverse construye la dirección a partir del nombre de la ruta:
        # "usuarios:registro-autor" -> "/api/usuarios/registro-autor/"
        self.url = reverse("usuarios:registro-autor")

    def test_registro_exitoso_devuelve_201_y_crea_autor(self):
        """CP-01.A: registro exitoso de un autor."""
        # Ejecutar: enviar el formulario con datos válidos (correo con mayúsculas).
        respuesta = self.client.post(
            self.url, datos_validos(correo="Maria.Gomez@Ejemplo.com"), format="json"
        )

        # Verificar: la API responde 201 Created.
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

        # Verificar: la respuesta incluye el rol AUTOR y nunca la clave.
        self.assertEqual(respuesta.data["roles"], ["AUTOR"])
        self.assertNotIn("clave", respuesta.data)
        self.assertNotIn("confirmacion_clave", respuesta.data)

        # Verificar: el usuario quedó guardado con el correo en minúsculas
        # y la clave como hash.
        usuario = Usuario.objects.get(correo="maria.gomez@ejemplo.com")
        self.assertTrue(usuario.check_password("ClaveSegura123"))
        self.assertTrue(usuario.tiene_rol(Rol.Nombre.AUTOR))

    def test_correo_duplicado_devuelve_400(self):
        """CP-01.B: rechazo por correo duplicado."""
        # Preparar: ya existe una cuenta con este correo.
        self.client.post(self.url, datos_validos(), format="json")

        # Ejecutar: registrar el mismo correo con otras mayúsculas.
        respuesta = self.client.post(
            self.url, datos_validos(correo="MARIA.GOMEZ@ejemplo.com"), format="json"
        )

        # Verificar: 400, error en el campo correo y un solo usuario en la base de datos.
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("correo", respuesta.data)
        self.assertEqual(Usuario.objects.count(), 1)

    def test_claves_distintas_devuelve_400(self):
        respuesta = self.client.post(
            self.url, datos_validos(confirmacion_clave="OtraClave123"), format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("confirmacion_clave", respuesta.data)

    def test_clave_debil_devuelve_400(self):
        # subTest ejecuta el mismo caso con varios valores y reporta cada uno por separado.
        claves_debiles = {
            "muy corta": "Corta1A",
            "sin mayúscula": "clavesegura123",
            "sin número": "ClaveSeguraSinNumero",
        }
        for motivo, clave in claves_debiles.items():
            with self.subTest(motivo=motivo):
                respuesta = self.client.post(
                    self.url,
                    datos_validos(clave=clave, confirmacion_clave=clave),
                    format="json",
                )
                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("clave", respuesta.data)

    def test_sin_aceptar_tratamiento_de_datos_devuelve_400(self):
        # Caso 1: la persona responde que NO acepta.
        respuesta = self.client.post(
            self.url, datos_validos(acepta_tratamiento_datos=False), format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

        # Caso 2: el campo no se envía.
        datos = datos_validos()
        del datos["acepta_tratamiento_datos"]
        respuesta = self.client.post(self.url, datos, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_permite_asignarse_roles_ni_volverse_superusuario(self):
        """Seguridad: el cliente no puede elegir sus roles ni sus privilegios."""
        # Ejecutar: intentar registrarse como administrador y superusuario.
        respuesta = self.client.post(
            self.url,
            datos_validos(roles=["ADMIN"], is_superuser=True),
            format="json",
        )

        # Verificar: el registro funciona, pero esos campos se ignoraron.
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        usuario = Usuario.objects.get(correo="maria.gomez@ejemplo.com")
        self.assertFalse(usuario.is_superuser)
        self.assertFalse(usuario.tiene_rol(Rol.Nombre.ADMIN))
        self.assertEqual(list(usuario.roles.values_list("nombre", flat=True)), ["AUTOR"])

    def test_faltan_campos_obligatorios_devuelve_400(self):
        # Ejecutar: enviar un formulario vacío.
        respuesta = self.client.post(self.url, {}, format="json")

        # Verificar: la API informa cada campo obligatorio que falta.
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        for campo in ["correo", "nombres", "apellidos", "afiliacion", "pais", "clave"]:
            self.assertIn(campo, respuesta.data)