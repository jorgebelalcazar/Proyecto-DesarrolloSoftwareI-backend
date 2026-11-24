"""
Pruebas de los coautores o firmantes del artículo (HU-15).

Endpoints:
  - POST /api/articulos/                     (coautores al postular)
  - GET y PUT /api/articulos/{id}/coautores/ (consultar y reemplazar la lista)

Cubren el caso de prueba CP-11 de la subtarea de QA HU-15.5:
  - postulación con 3 coautores sin cuenta en el sistema -> 201;
  - dos correos idénticos en la lista -> 400 y no se guarda nada.
Y además: orden de firma, formato de correo, solo el autor responsable,
artículo deshabilitado o fuera de plazo, y reglas en la base de datos.
"""

from datetime import timedelta

from django.db import IntegrityError
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


def crear_conferencia():
    """Edición vigente con el plazo de postulación abierto por 30 días más."""
    ahora = timezone.now()
    hoy = timezone.localdate()
    return Conferencia.objects.create(
        nombre="Nexo 2027",
        limite_postulacion=ahora + timedelta(days=30),
        limite_revision=ahora + timedelta(days=45),
        limite_correccion=ahora + timedelta(days=60),
        limite_version_final=ahora + timedelta(days=75),
        fecha_inicio_evento=hoy + timedelta(days=90),
        fecha_fin_evento=hoy + timedelta(days=92),
    )


def coautor(numero, correo=None):
    """Datos de un coautor sin cuenta en el sistema."""
    return {
        "nombre_completo": f"Investigador {numero}",
        "afiliacion": "Universidad Nacional",
        "correo": correo or f"investigador{numero}@externo.org",
    }


class CoautoresArticuloTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        """Datos comunes, creados UNA vez para todas las pruebas de la clase."""
        cls.linea = LineaTematica.objects.get(nombre="Sistemas Inteligentes")
        cls.autor = crear_usuario("autor@ejemplo.com", Rol.Nombre.AUTOR)
        cls.conferencia = crear_conferencia()

    def setUp(self):
        self.client.force_authenticate(user=self.autor)

    def postular(self, coautores):
        """Atajo: POST /api/articulos/ con la lista de coautores indicada."""
        datos = {
            "titulo": "Redes neuronales para el monitoreo agrícola",
            "resumen": "Este trabajo propone una arquitectura ligera.",
            "palabras_clave": "redes neuronales, agricultura",
            "linea_tematica": self.linea.id,
            "coautores": coautores,
        }
        return self.client.post(reverse("articulos:lista"), datos, format="json")

    def crear_articulo(self, *coautores, autor=None):
        """Crea un artículo directamente en la base de datos, con sus coautores."""
        articulo = Articulo.objects.create(
            conferencia=self.conferencia,
            linea_tematica=self.linea,
            autor_responsable=autor or self.autor,
            titulo="Artículo de prueba",
            resumen="Resumen.",
            palabras_clave="prueba",
        )
        for orden, datos in enumerate(coautores, start=1):
            AutorArticulo.objects.create(articulo=articulo, orden=orden, **datos)
        return articulo

    def url(self, articulo):
        """Dirección de los coautores: /api/articulos/{id}/coautores/."""
        return reverse("articulos:coautores", args=[articulo.pk])

    def reemplazar(self, articulo, coautores):
        """Atajo: PUT de la lista completa de coautores."""
        return self.client.put(self.url(articulo), {"coautores": coautores}, format="json")

    @staticmethod
    def correos(articulo):
        """Correos de los coautores guardados, en orden de firma."""
        return list(articulo.coautores.values_list("correo", flat=True))

    # ------------------------------------------ CP-11: postular con coautores
    def test_postulacion_con_tres_coautores_sin_cuenta(self):
        respuesta = self.postular([coautor(1), coautor(2), coautor(3)])

        # Verificar: 201 y los tres firmantes en orden, sin necesitar cuenta.
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual([c["orden"] for c in respuesta.data["coautores"]], [1, 2, 3])
        self.assertEqual(AutorArticulo.objects.count(), 3)
        self.assertFalse(Usuario.objects.filter(correo__endswith="@externo.org").exists())

    def test_postulacion_sin_coautores_es_valida(self):
        respuesta = self.postular([])

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.data["coautores"], [])

    def test_correos_repetidos_bloquean_la_postulacion_completa(self):
        """El repetido se detecta sin importar mayúsculas, y se marca en su fila."""
        respuesta = self.postular([
            coautor(1, "ana@externo.org"),
            coautor(2),
            coautor(3, "ANA@Externo.org"),
        ])

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        filas = respuesta.data["coautores"]
        self.assertEqual(filas[0], {})
        self.assertEqual(filas[1], {})
        self.assertIn("correo", filas[2])

        # Verificar: no se guardó ni el artículo ni ningún coautor.
        self.assertFalse(Articulo.objects.exists())
        self.assertFalse(AutorArticulo.objects.exists())

    def test_correo_invalido_o_campos_en_blanco_devuelven_400_en_la_fila(self):
        casos = {
            "correo": coautor(1, "no-es-un-correo"),
            "nombre_completo": {**coautor(1), "nombre_completo": "   "},
            "afiliacion": {**coautor(1), "afiliacion": ""},
        }
        for campo, datos in casos.items():
            with self.subTest(campo=campo):
                respuesta = self.postular([coautor(2), datos])

                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(campo, respuesta.data["coautores"][1])

    # --------------------------------------------- Reemplazar la lista (PUT)
    def test_autor_agrega_edita_quita_y_reordena_en_una_sola_peticion(self):
        articulo = self.crear_articulo(coautor(1), coautor(2), coautor(3))

        # Nueva lista: el 3 pasa de primero, el 1 cambia de afiliación,
        # el 2 sale y entra el 4.
        nuevo_1 = {**coautor(1), "afiliacion": "Universidad de Antioquia"}
        respuesta = self.reemplazar(articulo, [coautor(3), nuevo_1, coautor(4)])

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(self.correos(articulo), [
            "investigador3@externo.org",
            "investigador1@externo.org",
            "investigador4@externo.org",
        ])
        self.assertEqual(respuesta.data["coautores"][1]["afiliacion"], "Universidad de Antioquia")
        self.assertEqual([c["orden"] for c in respuesta.data["coautores"]], [1, 2, 3])

    def test_el_orden_lo_da_la_posicion_aunque_el_cliente_envie_otro(self):
        articulo = self.crear_articulo()

        respuesta = self.reemplazar(articulo, [
            {**coautor(1), "orden": 7},
            {**coautor(2), "orden": 7},
        ])

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual([c["orden"] for c in respuesta.data["coautores"]], [1, 2])

    def test_lista_vacia_quita_todos_los_coautores(self):
        articulo = self.crear_articulo(coautor(1), coautor(2))

        respuesta = self.reemplazar(articulo, [])

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertFalse(articulo.coautores.exists())

    def test_correos_repetidos_en_el_put_no_cambian_la_lista_anterior(self):
        articulo = self.crear_articulo(coautor(1))

        respuesta = self.reemplazar(articulo, [coautor(2), coautor(3, "investigador2@externo.org")])

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.correos(articulo), ["investigador1@externo.org"])

    def test_consultar_los_coautores_en_orden(self):
        articulo = self.crear_articulo(coautor(1), coautor(2))

        respuesta = self.client.get(self.url(articulo))

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["articulo"], articulo.id)
        self.assertEqual([c["orden"] for c in respuesta.data["coautores"]], [1, 2])

    # -------------------------------------------- Solo el autor responsable
    def test_otro_autor_recibe_403_y_la_lista_no_cambia(self):
        articulo = self.crear_articulo(coautor(1))
        self.client.force_authenticate(user=crear_usuario("otro@ejemplo.com", Rol.Nombre.AUTOR))

        consulta = self.client.get(self.url(articulo))
        cambio = self.reemplazar(articulo, [coautor(9)])

        self.assertEqual(consulta.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(cambio.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.correos(articulo), ["investigador1@externo.org"])

    def test_rol_activo_distinto_de_autor_recibe_403(self):
        articulo = self.crear_articulo()
        self.client.force_authenticate(user=crear_usuario("comite@ejemplo.com", Rol.Nombre.COMITE))

        self.assertEqual(self.client.get(self.url(articulo)).status_code, status.HTTP_403_FORBIDDEN)

    def test_sin_token_401_y_articulo_inexistente_404(self):
        articulo = self.crear_articulo()

        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.get(self.url(articulo)).status_code, status.HTTP_401_UNAUTHORIZED
        )

        self.client.force_authenticate(user=self.autor)
        inexistente = reverse("articulos:coautores", args=[99999])
        self.assertEqual(self.client.get(inexistente).status_code, status.HTTP_404_NOT_FOUND)

    # ------------------------------------------- Artículo que ya no se edita
    def test_fuera_de_plazo_no_se_cambian_los_coautores(self):
        articulo = self.crear_articulo(coautor(1))
        Conferencia.objects.filter(pk=self.conferencia.pk).update(
            limite_postulacion=timezone.now() - timedelta(minutes=1)
        )

        respuesta = self.reemplazar(articulo, [coautor(2)])

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("venció", str(respuesta.data["detail"]))
        self.assertEqual(self.correos(articulo), ["investigador1@externo.org"])

    def test_articulo_deshabilitado_no_cambia_sus_coautores(self):
        articulo = self.crear_articulo(coautor(1))
        Articulo.objects.filter(pk=articulo.pk).update(estado=Articulo.Estado.DESHABILITADO)

        respuesta = self.reemplazar(articulo, [coautor(2)])

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("deshabilitado", str(respuesta.data["detail"]))

    # ----------------------------------------------- Reglas en la base de datos
    def test_la_base_de_datos_rechaza_un_correo_repetido_en_el_articulo(self):
        """Aunque se guarde sin pasar por la API, PostgreSQL rechaza el repetido."""
        articulo = self.crear_articulo(coautor(1))

        with self.assertRaises(IntegrityError):
            AutorArticulo.objects.create(articulo=articulo, orden=2, **coautor(1))