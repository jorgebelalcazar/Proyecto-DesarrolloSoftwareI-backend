"""
Pruebas de la rúbrica de evaluación de cada edición (HU-22.2).

Endpoint: GET y PUT /api/conferencias/{id}/criterios/

Cubren: consulta y configuración por Admin y Comité, acceso por rol, la
rúbrica de cada edición por separado, validaciones de cada criterio
(nombre, puntaje de 1 a 100, nombres repetidos sin importar mayúsculas),
el bloqueo después del cierre de la postulación, que una petición inválida
no borre la rúbrica anterior, y las reglas de la tabla en la base de datos.
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from usuarios.models import Rol, Usuario

from .models import Conferencia, CriterioEvaluacion


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


def crear_conferencia(nombre="Nexo 2027", dias_para_cerrar=30):
    """Edición de la conferencia; con días negativos, la postulación ya cerró."""
    ahora = timezone.now()
    hoy = timezone.localdate()
    return Conferencia.objects.create(
        nombre=nombre,
        limite_postulacion=ahora + timedelta(days=dias_para_cerrar),
        limite_revision=ahora + timedelta(days=45),
        limite_correccion=ahora + timedelta(days=60),
        limite_version_final=ahora + timedelta(days=75),
        fecha_inicio_evento=hoy + timedelta(days=90),
        fecha_fin_evento=hoy + timedelta(days=92),
    )


# Rúbrica de ejemplo que se envía con PUT.
RUBRICA = [
    {"nombre": "Originalidad", "descripcion": "Aporte nuevo al área.", "puntaje_maximo": 30},
    {"nombre": "Metodología", "descripcion": "Rigor del método.", "puntaje_maximo": 40},
    {"nombre": "Redacción", "puntaje_maximo": 30},
]


class RubricaConferenciaTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        """Datos comunes, creados UNA vez para todas las pruebas de la clase."""
        cls.admin = crear_usuario("admin@ejemplo.com", Rol.Nombre.ADMIN)
        cls.comite = crear_usuario("comite@ejemplo.com", Rol.Nombre.COMITE)
        cls.autor = crear_usuario("autor@ejemplo.com", Rol.Nombre.AUTOR)
        cls.conferencia = crear_conferencia()

    def setUp(self):
        self.url = reverse("conferencias:criterios", args=[self.conferencia.id])
        self.client.force_authenticate(user=self.comite)

    def configurar(self, criterios, url=None):
        """Atajo: PUT de la rúbrica completa."""
        return self.client.put(url or self.url, {"criterios": criterios}, format="json")

    # ------------------------------------------- Configurar y consultar
    def test_comite_configura_la_rubrica_y_la_consulta_en_orden(self):
        respuesta = self.configurar(RUBRICA)

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["conferencia"], self.conferencia.id)
        self.assertEqual(respuesta.data["puntaje_total"], 100)
        self.assertEqual(
            [criterio["nombre"] for criterio in respuesta.data["criterios"]],
            ["Originalidad", "Metodología", "Redacción"],
        )

        consulta = self.client.get(self.url)
        self.assertEqual(consulta.status_code, status.HTTP_200_OK)
        self.assertEqual(consulta.data, respuesta.data)

    def test_cada_criterio_trae_sus_datos(self):
        self.configurar(RUBRICA)

        criterio = self.client.get(self.url).data["criterios"][2]

        self.assertEqual(set(criterio), {"id", "nombre", "descripcion", "puntaje_maximo"})
        self.assertEqual(criterio["descripcion"], "")

    def test_el_put_reemplaza_la_rubrica_completa(self):
        self.configurar(RUBRICA)

        respuesta = self.configurar([{"nombre": "Calidad general", "puntaje_maximo": 10}])

        self.assertEqual(respuesta.data["puntaje_total"], 10)
        self.assertEqual(self.conferencia.criterios.count(), 1)

    def test_edicion_sin_rubrica_responde_lista_vacia(self):
        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["criterios"], [])
        self.assertEqual(respuesta.data["puntaje_total"], 0)

    def test_cada_edicion_tiene_su_propia_rubrica(self):
        otra = crear_conferencia(nombre="Nexo 2028")
        self.configurar(RUBRICA)
        self.configurar(
            [{"nombre": "Originalidad", "puntaje_maximo": 50}],
            url=reverse("conferencias:criterios", args=[otra.id]),
        )

        self.assertEqual(self.conferencia.criterios.count(), 3)
        self.assertEqual(otra.criterios.count(), 1)

    # ------------------------------------------------------------ Permisos
    def test_admin_tambien_configura_la_rubrica(self):
        self.client.force_authenticate(user=self.admin)
        respuesta = self.configurar(RUBRICA)
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_autor_no_consulta_ni_configura(self):
        self.client.force_authenticate(user=self.autor)

        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.configurar(RUBRICA).status_code, status.HTTP_403_FORBIDDEN)

    def test_cuenta_el_rol_activo_no_todos_los_roles(self):
        multirrol = crear_usuario("multi@ejemplo.com", Rol.Nombre.AUTOR, Rol.Nombre.COMITE)
        self.client.force_authenticate(user=multirrol)

        como_comite = self.client.get(self.url, HTTP_X_ROL_ACTIVO="COMITE")
        como_autor = self.client.get(self.url, HTTP_X_ROL_ACTIVO="AUTOR")

        self.assertEqual(como_comite.status_code, status.HTTP_200_OK)
        self.assertEqual(como_autor.status_code, status.HTTP_403_FORBIDDEN)

    def test_sin_token_devuelve_401(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_edicion_inexistente_devuelve_404(self):
        url = reverse("conferencias:criterios", args=[99999])
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)

    # -------------------------------------------------------- Validaciones
    def test_criterios_invalidos_responden_400_en_la_fila(self):
        casos = {
            "sin nombre": ({"puntaje_maximo": 10}, "nombre"),
            "nombre en blanco": ({"nombre": "   ", "puntaje_maximo": 10}, "nombre"),
            "nombre de 101 caracteres": ({"nombre": "x" * 101, "puntaje_maximo": 10}, "nombre"),
            "sin puntaje": ({"nombre": "Claridad"}, "puntaje_maximo"),
            "puntaje 0": ({"nombre": "Claridad", "puntaje_maximo": 0}, "puntaje_maximo"),
            "puntaje 101": ({"nombre": "Claridad", "puntaje_maximo": 101}, "puntaje_maximo"),
            "puntaje con texto": (
                {"nombre": "Claridad", "puntaje_maximo": "alto"}, "puntaje_maximo"
            ),
        }
        for caso, (criterio, campo) in casos.items():
            with self.subTest(caso=caso):
                respuesta = self.configurar([RUBRICA[0], criterio])

                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(campo, respuesta.data["criterios"][1])

    def test_nombre_repetido_sin_importar_mayusculas(self):
        respuesta = self.configurar([RUBRICA[0], {"nombre": "ORIGINALIDAD", "puntaje_maximo": 5}])

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(respuesta.data["criterios"][0], {})
        self.assertIn("nombre", respuesta.data["criterios"][1])

    def test_rubrica_vacia_devuelve_400(self):
        respuesta = self.configurar([])

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("criterios", respuesta.data)

    def test_una_peticion_invalida_no_borra_la_rubrica_anterior(self):
        self.configurar(RUBRICA)

        self.configurar([{"nombre": "Incompleto", "puntaje_maximo": 0}])

        self.assertEqual(self.conferencia.criterios.count(), 3)

    # ----------------------------------------- Bloqueo durante la revisión
    def test_con_la_postulacion_cerrada_no_se_modifica(self):
        cerrada = crear_conferencia(nombre="Nexo 2026", dias_para_cerrar=-1)
        url = reverse("conferencias:criterios", args=[cerrada.id])

        respuesta = self.configurar(RUBRICA, url=url)

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("ya no se puede modificar", respuesta.data["detail"])
        self.assertFalse(cerrada.criterios.exists())

        # Pero se sigue pudiendo consultar.
        self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK)


class ReglasCriterioEvaluacionTests(APITestCase):
    """Restricciones de la tabla criterio_evaluacion en la base de datos."""

    @classmethod
    def setUpTestData(cls):
        cls.conferencia = crear_conferencia()
        CriterioEvaluacion.objects.create(
            conferencia=cls.conferencia, nombre="Originalidad", puntaje_maximo=20
        )

    def test_rechaza_criterios_invalidos(self):
        casos = {
            "nombre repetido en otra forma": ("originalidad", 10),
            "puntaje 0": ("Claridad", 0),
            "puntaje 101": ("Claridad", 101),
        }
        for caso, (nombre, puntaje) in casos.items():
            with self.subTest(caso=caso):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    CriterioEvaluacion.objects.create(
                        conferencia=self.conferencia, nombre=nombre, puntaje_maximo=puntaje
                    )

    def test_el_mismo_nombre_si_puede_estar_en_otra_edicion(self):
        otra = crear_conferencia(nombre="Nexo 2028")
        CriterioEvaluacion.objects.create(
            conferencia=otra, nombre="Originalidad", puntaje_maximo=20
        )
        self.assertEqual(CriterioEvaluacion.objects.filter(nombre="Originalidad").count(), 2)