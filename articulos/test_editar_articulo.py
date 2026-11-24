"""
Pruebas de la modificación de un artículo propio (HU-20).

Endpoint: PUT y PATCH /api/articulos/{id}/

Cubren el caso de prueba CP-16 de la subtarea de QA HU-20.5:
  - el Autor responsable modifica su artículo;
  - se rechaza la edición desde otra cuenta (403) o fuera de fecha (400).
Y además: artículo deshabilitado, validaciones heredadas de la postulación,
coautores, campos que asigna el servidor y acceso por rol.
"""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from conferencias.models import Conferencia
from core.models import LineaTematica
from usuarios.models import Rol, Usuario

from .models import Articulo, AutorArticulo


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


def crear_conferencia(dias_para_cerrar=30):
    """Edición de la conferencia; con días negativos, la postulación ya cerró."""
    ahora = timezone.now()
    hoy = timezone.localdate()
    return Conferencia.objects.create(
        nombre="Nexo 2027",
        limite_postulacion=ahora + timedelta(days=dias_para_cerrar),
        limite_revision=ahora + timedelta(days=45),
        limite_correccion=ahora + timedelta(days=60),
        limite_version_final=ahora + timedelta(days=75),
        fecha_inicio_evento=hoy + timedelta(days=90),
        fecha_fin_evento=hoy + timedelta(days=92),
    )


class EditarArticuloTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        """Datos comunes, creados UNA vez para todas las pruebas de la clase."""
        cls.autor = crear_usuario("autor@ejemplo.com", Rol.Nombre.AUTOR)
        cls.otro_autor = crear_usuario("otro@ejemplo.com", Rol.Nombre.AUTOR)
        cls.comite = crear_usuario("comite@ejemplo.com", Rol.Nombre.COMITE)
        cls.inteligentes = LineaTematica.objects.get(nombre="Sistemas Inteligentes")
        cls.software = LineaTematica.objects.get(nombre="Sistemas de Software")
        cls.conferencia = crear_conferencia()

    def setUp(self):
        self.articulo = Articulo.objects.create(
            conferencia=self.conferencia, linea_tematica=self.inteligentes,
            autor_responsable=self.autor, titulo="Título original",
            resumen="Resumen original.", palabras_clave="IA",
        )
        AutorArticulo.objects.create(
            articulo=self.articulo, nombre_completo="Laura Gómez",
            afiliacion="Univalle", correo="laura@externo.com", orden=1,
        )
        self.url = reverse("articulos:detalle", args=[self.articulo.id])
        self.client.force_authenticate(user=self.autor)

    def modificar(self, datos, metodo="patch"):
        """Atajo: PATCH (o PUT) del artículo."""
        return getattr(self.client, metodo)(self.url, datos, format="json")

    # ------------------------------------- Edición válida (CP-16, criterio 1)
    def test_autor_modifica_los_metadatos_con_patch(self):
        respuesta = self.modificar({
            "titulo": "  Título corregido  ",
            "palabras_clave": "IA , redes",
            "linea_tematica": self.software.id,
        })

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.articulo.refresh_from_db()
        self.assertEqual(self.articulo.titulo, "Título corregido")
        self.assertEqual(self.articulo.palabras_clave, "IA, redes")
        self.assertEqual(self.articulo.linea_tematica, self.software)
        self.assertEqual(self.articulo.resumen, "Resumen original.")
        self.assertEqual(respuesta.data["linea_tematica"]["nombre"], "Sistemas de Software")

    def test_put_reemplaza_todos_los_metadatos(self):
        respuesta = self.modificar({
            "titulo": "Nuevo título", "resumen": "Nuevo resumen.",
            "palabras_clave": "datos", "linea_tematica": self.software.id,
        }, metodo="put")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.articulo.refresh_from_db()
        self.assertEqual(self.articulo.resumen, "Nuevo resumen.")

    def test_put_incompleto_devuelve_400(self):
        respuesta = self.modificar({"titulo": "Solo el título"}, metodo="put")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("resumen", respuesta.data)

    def test_modifica_los_coautores_si_llegan(self):
        respuesta = self.modificar({"coautores": [
            {"nombre_completo": "Diego Ruiz", "afiliacion": "ICESI", "correo": "diego@x.com"},
            {
                "nombre_completo": "Laura Gómez", "afiliacion": "Univalle",
                "correo": "laura@externo.com",
            },
        ]})

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [c["correo"] for c in respuesta.data["coautores"]],
            ["diego@x.com", "laura@externo.com"],
        )

    def test_lista_vacia_quita_los_coautores(self):
        respuesta = self.modificar({"coautores": []})

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertFalse(self.articulo.coautores.exists())

    def test_sin_coautores_en_la_peticion_no_se_tocan(self):
        self.modificar({"titulo": "Otro título"})
        self.assertEqual(self.articulo.coautores.count(), 1)

    def test_los_campos_del_servidor_no_cambian(self):
        otra = crear_conferencia()
        self.modificar({
            "titulo": "Título válido", "estado": "APROBADO",
            "autor_responsable": self.otro_autor.id, "conferencia": otra.id,
        })

        self.articulo.refresh_from_db()
        self.assertEqual(self.articulo.estado, Articulo.Estado.POSTULADO)
        self.assertEqual(self.articulo.autor_responsable, self.autor)
        self.assertEqual(self.articulo.conferencia, self.conferencia)

    # ------------------------------ Validaciones del servidor (criterio 3)
    def test_reutiliza_las_validaciones_de_la_postulacion(self):
        casos = {
            "titulo": "x" * 201,
            "resumen": "palabra " * 301,
            "palabras_clave": " , , ",
            "linea_tematica": 99999,
        }
        for campo, valor in casos.items():
            with self.subTest(campo=campo):
                respuesta = self.modificar({campo: valor})

                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(campo, respuesta.data)

    def test_coautor_repetido_devuelve_400_en_la_fila(self):
        fila = {"nombre_completo": "Ana", "afiliacion": "X", "correo": "ana@x.com"}
        respuesta = self.modificar({"coautores": [fila, fila]})

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("correo", respuesta.data["coautores"][1])

    # --------------------------------- Bloqueos (CP-16, criterios 1 y 2)
    def test_otro_autor_recibe_403(self):
        self.client.force_authenticate(user=self.otro_autor)

        respuesta = self.modificar({"titulo": "Intento ajeno"})

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)
        self.articulo.refresh_from_db()
        self.assertEqual(self.articulo.titulo, "Título original")

    def test_comite_puede_ver_pero_no_modificar(self):
        self.client.force_authenticate(user=self.comite)

        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.modificar({"titulo": "Cambio"}).status_code, status.HTTP_403_FORBIDDEN
        )

    def test_con_el_plazo_vencido_devuelve_400(self):
        self.articulo.conferencia = crear_conferencia(dias_para_cerrar=-1)
        self.articulo.save()

        respuesta = self.modificar({"titulo": "Fuera de fecha"})

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("venció", respuesta.data["detail"])

    def test_deshabilitado_devuelve_400_aunque_los_datos_sean_invalidos(self):
        self.articulo.deshabilitar(self.comite, "Fuera del alcance del evento.")

        respuesta = self.modificar({"titulo": ""})

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("deshabilitado", respuesta.data["detail"])

    def test_sin_token_devuelve_401(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.modificar({"titulo": "X"}).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_delete_no_esta_permitido(self):
        respuesta = self.client.delete(self.url)
        self.assertEqual(respuesta.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)