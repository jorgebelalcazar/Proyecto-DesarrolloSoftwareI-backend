"""
Pruebas de la configuración de la conferencia y sus plazos (HU-13).

Cubren el caso de prueba CP-09 de la subtarea de QA HU-13.5:
  - fechas fuera de orden -> 400 en el campo afectado;
  - un Autor no puede crear ni modificar plazos -> 403.
Y además: creación y edición por Admin y Comité, PATCH parcial, zona horaria
de Colombia, edición vigente, restricciones de la base de datos y el método
postulacion_abierta() que usarán la HU-14 y la HU-20.
"""

from datetime import date, datetime, time, timedelta

from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from usuarios.models import Rol, Usuario

from .models import Conferencia


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


def fechas_validas(**cambios):
    """
    Datos de una edición con todas las fechas en orden, en hora de Colombia.

    Las fechas se calculan desde hoy para que la prueba no "venza" con el tiempo.
    """
    hoy = timezone.localdate()
    datos = {
        "nombre": "Nexo 2027",
        "fecha_inicio_postulacion": f"{hoy + timedelta(days=15)}T08:00:00-05:00",
        "limite_postulacion": f"{hoy + timedelta(days=30)}T23:59:00-05:00",
        "limite_revision": f"{hoy + timedelta(days=45)}T23:59:00-05:00",
        "limite_correccion": f"{hoy + timedelta(days=60)}T23:59:00-05:00",
        "limite_version_final": f"{hoy + timedelta(days=75)}T23:59:00-05:00",
        "fecha_inicio_evento": str(hoy + timedelta(days=90)),
        "fecha_fin_evento": str(hoy + timedelta(days=92)),
    }
    datos.update(cambios)
    return datos


def crear_conferencia(inicio_en_dias, fin_en_dias, nombre="Nexo"):
    """Crea una edición directamente en la base de datos, con el evento en los días indicados."""
    ahora = timezone.now()
    hoy = timezone.localdate()
    return Conferencia.objects.create(
        nombre=nombre,
        fecha_inicio_postulacion=ahora + timedelta(days=inicio_en_dias - 55),
        limite_postulacion=ahora + timedelta(days=inicio_en_dias - 40),
        limite_revision=ahora + timedelta(days=inicio_en_dias - 30),
        limite_correccion=ahora + timedelta(days=inicio_en_dias - 20),
        limite_version_final=ahora + timedelta(days=inicio_en_dias - 10),
        fecha_inicio_evento=hoy + timedelta(days=inicio_en_dias),
        fecha_fin_evento=hoy + timedelta(days=fin_en_dias),
    )


class ConferenciaApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        """Datos comunes, creados UNA vez para todas las pruebas de la clase."""
        cls.admin = crear_usuario("admin@ejemplo.com", Rol.Nombre.ADMIN)
        cls.comite = crear_usuario("comite@ejemplo.com", Rol.Nombre.COMITE)
        cls.autor = crear_usuario("autor@ejemplo.com", Rol.Nombre.AUTOR)

    def setUp(self):
        self.url = reverse("conferencias:lista")

    def crear_como(self, usuario, datos):
        """Atajo: POST /api/conferencias/ autenticado como "usuario"."""
        self.client.force_authenticate(user=usuario)
        return self.client.post(self.url, datos, format="json")

    # ------------------------------------------------------- Crear (POST)
    def test_admin_crea_una_edicion(self):
        respuesta = self.crear_como(self.admin, fechas_validas())

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Conferencia.objects.count(), 1)

    def test_comite_crea_una_edicion(self):
        respuesta = self.crear_como(self.comite, fechas_validas())
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    # ------------------------------------------- CP-09: bloqueo por rol
    def test_autor_no_puede_crear_ediciones(self):
        respuesta = self.crear_como(self.autor, fechas_validas())

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Conferencia.objects.exists())

    def test_autor_no_puede_modificar_plazos(self):
        conferencia = crear_conferencia(90, 92)
        self.client.force_authenticate(user=self.autor)

        respuesta = self.client.patch(
            reverse("conferencias:detalle", args=[conferencia.pk]),
            {"nombre": "Otra"}, format="json",
        )

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_sin_token_devuelve_401(self):
        respuesta = self.client.post(self.url, fechas_validas(), format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    # ---------------------------------- CP-09: validación cronológica
    def test_plazos_fuera_de_orden_devuelven_400_en_el_campo_afectado(self):
        valido = fechas_validas()
        casos = {
            # campo que queda mal: valor que lo deja antes del plazo anterior
            "limite_revision": valido["limite_postulacion"],
            "limite_correccion": valido["limite_postulacion"],
            "limite_version_final": valido["limite_revision"],
            "fecha_fin_evento": str(timezone.localdate() + timedelta(days=80)),
        }
        for campo, valor in casos.items():
            with self.subTest(campo=campo):
                respuesta = self.crear_como(self.admin, fechas_validas(**{campo: valor}))

                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(campo, respuesta.data)

        self.assertFalse(Conferencia.objects.exists())

    def test_dos_plazos_iguales_tambien_se_rechazan(self):
        """El orden es estricto: dos etapas no pueden cerrar en el mismo instante."""
        valido = fechas_validas()
        respuesta = self.crear_como(
            self.admin, fechas_validas(limite_revision=valido["limite_postulacion"])
        )

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("limite_revision", respuesta.data)

    def test_inicio_de_postulacion_debe_ser_anterior_al_limite(self):
        """CP-09 rechaza el inicio igual o posterior al cierre de postulaciones."""
        valido = fechas_validas()
        respuesta = self.crear_como(
            self.admin,
            fechas_validas(fecha_inicio_postulacion=valido["limite_postulacion"]),
        )

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("limite_postulacion", respuesta.data)

    def test_fecha_inicio_postulacion_se_guarda_y_se_devuelve(self):
        """La API expone el inicio que completa la secuencia cronológica."""
        datos = fechas_validas()
        respuesta = self.crear_como(self.admin, datos)

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            respuesta.data["fecha_inicio_postulacion"],
            datos["fecha_inicio_postulacion"],
        )

    def test_el_evento_empieza_despues_del_limite_de_version_final(self):
        valido = fechas_validas()
        dia_version_final = valido["limite_version_final"][:10]

        # El evento empieza el MISMO día del límite de versión final -> 400.
        respuesta = self.crear_como(
            self.admin, fechas_validas(fecha_inicio_evento=dia_version_final)
        )

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fecha_inicio_evento", respuesta.data)

    def test_version_final_la_noche_anterior_al_evento_es_valida(self):
        """
        22:00 en Colombia son las 03:00 del día siguiente en UTC. La regla
        compara el día en hora de Colombia, así que la entrega la noche
        anterior al evento es válida.
        """
        hoy = timezone.localdate()
        inicio = hoy + timedelta(days=90)
        noche_anterior = timezone.make_aware(
            datetime.combine(inicio - timedelta(days=1), time(22, 0))
        )
        conferencia = crear_conferencia(90, 92)
        Conferencia.objects.filter(pk=conferencia.pk).update(limite_version_final=noche_anterior)
        self.client.force_authenticate(user=self.admin)

        # PATCH de otro campo: el orden se valida con la fecha guardada (en UTC).
        respuesta = self.client.patch(
            reverse("conferencias:detalle", args=[conferencia.pk]),
            {"nombre": "Nexo 2027"}, format="json",
        )

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_evento_de_un_solo_dia_es_valido(self):
        valido = fechas_validas()
        respuesta = self.crear_como(
            self.admin, fechas_validas(fecha_fin_evento=valido["fecha_inicio_evento"])
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    # ------------------------------------------------ Modificar (PUT/PATCH)
    def test_patch_valida_el_orden_con_las_fechas_que_ya_tiene(self):
        conferencia = crear_conferencia(90, 92)
        self.client.force_authenticate(user=self.admin)
        url = reverse("conferencias:detalle", args=[conferencia.pk])

        # Solo se envía el límite de revisión, y queda antes del de postulación.
        antes = conferencia.limite_postulacion - timedelta(days=1)
        respuesta = self.client.patch(url, {"limite_revision": antes.isoformat()}, format="json")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("limite_revision", respuesta.data)

    def test_comite_extiende_el_plazo_de_postulacion_con_patch(self):
        conferencia = crear_conferencia(90, 92)
        self.client.force_authenticate(user=self.comite)
        nuevo = conferencia.limite_postulacion + timedelta(days=2)

        respuesta = self.client.patch(
            reverse("conferencias:detalle", args=[conferencia.pk]),
            {"limite_postulacion": nuevo.isoformat()}, format="json",
        )

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        conferencia.refresh_from_db()
        self.assertEqual(conferencia.limite_postulacion, nuevo)

    def test_put_reemplaza_todos_los_datos(self):
        conferencia = crear_conferencia(90, 92)
        self.client.force_authenticate(user=self.admin)

        respuesta = self.client.put(
            reverse("conferencias:detalle", args=[conferencia.pk]),
            fechas_validas(nombre="Nexo 2027 - edición ajustada"), format="json",
        )

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["nombre"], "Nexo 2027 - edición ajustada")

    def test_delete_no_esta_permitido(self):
        conferencia = crear_conferencia(90, 92)
        self.client.force_authenticate(user=self.admin)

        respuesta = self.client.delete(reverse("conferencias:detalle", args=[conferencia.pk]))

        self.assertEqual(respuesta.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(Conferencia.objects.exists())

    # --------------------------------------------------------- Consultar
    def test_autor_si_puede_consultar_los_plazos(self):
        crear_conferencia(90, 92)
        self.client.force_authenticate(user=self.autor)

        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(len(respuesta.data), 1)

    def test_las_fechas_se_responden_en_hora_de_colombia(self):
        # Se envía en UTC: las 04:59 del día siguiente en UTC son las 23:59 en Colombia.
        valido = fechas_validas()
        dia = valido["limite_postulacion"][:10]
        siguiente = (date.fromisoformat(dia) + timedelta(days=1)).isoformat()
        respuesta = self.crear_como(
            self.admin, fechas_validas(limite_postulacion=f"{siguiente}T04:59:00Z")
        )

        self.assertEqual(respuesta.data["limite_postulacion"], f"{dia}T23:59:00-05:00")

    def test_fecha_con_hora_sin_zona_se_interpreta_en_hora_de_colombia(self):
        valido = fechas_validas()
        dia = valido["limite_postulacion"][:10]
        respuesta = self.crear_como(
            self.admin, fechas_validas(limite_postulacion=f"{dia}T23:59:00")
        )

        self.assertEqual(respuesta.data["limite_postulacion"], f"{dia}T23:59:00-05:00")


class ConferenciaVigenteTests(APITestCase):
    """GET /api/conferencias/vigente/ y Conferencia.objects.vigente()."""

    def setUp(self):
        self.client.force_authenticate(user=crear_usuario("autor@ejemplo.com", Rol.Nombre.AUTOR))
        self.url = reverse("conferencias:vigente")

    def test_sin_ediciones_devuelve_404(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)

    def test_devuelve_la_proxima_edicion_que_no_ha_terminado(self):
        crear_conferencia(-30, -28, nombre="Pasada")
        proxima = crear_conferencia(60, 62, nombre="Próxima")
        crear_conferencia(400, 402, nombre="Lejana")

        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["id"], proxima.id)

    def test_una_edicion_en_curso_sigue_siendo_la_vigente(self):
        """Termina mañana: todavía es la vigente aunque ya empezó."""
        en_curso = crear_conferencia(-1, 1, nombre="En curso")
        crear_conferencia(60, 62, nombre="Próxima")

        self.assertEqual(Conferencia.objects.vigente(), en_curso)


class ConferenciaModeloTests(APITestCase):
    """Reglas del modelo: postulacion_abierta() y restricciones de la base de datos."""

    def test_postulacion_abierta_antes_del_limite_y_cerrada_despues(self):
        conferencia = crear_conferencia(90, 92)
        self.assertTrue(conferencia.postulacion_abierta())

        conferencia.limite_postulacion = timezone.now() - timedelta(minutes=1)
        self.assertFalse(conferencia.postulacion_abierta())

    def test_la_base_de_datos_rechaza_plazos_fuera_de_orden(self):
        """Aunque se guarde sin pasar por la API, PostgreSQL rechaza el desorden."""
        ahora = timezone.now()
        with self.assertRaises(IntegrityError):
            Conferencia.objects.create(
                nombre="Desordenada",
                limite_postulacion=ahora + timedelta(days=10),
                limite_revision=ahora + timedelta(days=5),   # antes de la postulación
                limite_correccion=ahora + timedelta(days=20),
                limite_version_final=ahora + timedelta(days=30),
                fecha_inicio_evento=date.today() + timedelta(days=40),
                fecha_fin_evento=date.today() + timedelta(days=41),
            )
