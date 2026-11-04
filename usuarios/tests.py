"""
Pruebas automáticas del dominio de usuarios.

Se ejecutan con:  python manage.py test usuarios

Cada prueba corre sobre una base de datos SQLite en memoria que Django crea
y destruye automáticamente, con las migraciones aplicadas. Por eso los roles
y las líneas temáticas ya existen en cada prueba, y los datos de una prueba
no afectan a las demás.
"""

from datetime import timedelta

from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from core.models import LineaTematica

from .models import CodigoRecuperacion, Rol, Usuario

# Datos obligatorios de un usuario, reutilizados en todas las pruebas.
DATOS = {
    "nombres": "Ana",
    "apellidos": "Pérez",
    "afiliacion": "Universidad del Valle",
    "pais": "Colombia",
}


class DatosInicialesTests(TestCase):
    """Comprueba que la migración de datos cargó la información base."""

    def test_existen_los_tres_roles(self):
        # Ejecutar: obtener los nombres de los roles guardados.
        nombres = set(Rol.objects.values_list("nombre", flat=True))

        # Verificar: deben ser exactamente los tres roles del sistema.
        self.assertEqual(nombres, {"ADMIN", "COMITE", "AUTOR"})

    def test_existen_las_cinco_lineas_tematicas(self):
        # Verificar: las 5 líneas del enunciado están cargadas.
        self.assertEqual(LineaTematica.objects.count(), 5)


class UsuarioTests(TestCase):
    """Comprueba las reglas del modelo Usuario."""

    def test_crear_usuario_normaliza_correo_y_guarda_hash(self):
        # Ejecutar: crear un usuario con mayúsculas en el correo.
        usuario = Usuario.objects.create_user("Ana.Perez@Correo.COM", "ClaveSegura123", **DATOS)

        # Verificar: el correo quedó en minúsculas.
        self.assertEqual(usuario.correo, "ana.perez@correo.com")

        # Verificar: la clave se guardó como hash PBKDF2, no en texto plano.
        self.assertTrue(usuario.password.startswith("pbkdf2_sha256$"))

        # Verificar: aun así, la clave original sigue sirviendo para validar.
        self.assertTrue(usuario.check_password("ClaveSegura123"))

    def test_correo_duplicado_es_rechazado(self):
        # Preparar: ya existe un usuario con este correo.
        Usuario.objects.create_user("ana@correo.com", "ClaveSegura123", **DATOS)

        # Ejecutar y verificar: registrar el mismo correo, aunque cambien las
        # mayúsculas, debe fallar con IntegrityError (restricción uk_usuario_correo).
        # transaction.atomic() aísla el error para que la prueba pueda terminar.
        with self.assertRaises(IntegrityError), transaction.atomic():
            Usuario.objects.create_user("ANA@correo.com", "OtraClave123", **DATOS)

    def test_inicio_de_sesion_sin_importar_mayusculas(self):
        # Preparar: usuario registrado con el correo en minúsculas.
        Usuario.objects.create_user("ana@correo.com", "ClaveSegura123", **DATOS)

        # Ejecutar: iniciar sesión escribiendo el correo con mayúsculas.
        resultado = authenticate(correo="ANA@Correo.com", password="ClaveSegura123")

        # Verificar: authenticate encontró al usuario (no devolvió None).
        self.assertIsNotNone(resultado)

    def test_usuario_inactivo_no_puede_iniciar_sesion(self):
        # Preparar: usuario desactivado (borrado lógico de la HU-12).
        usuario = Usuario.objects.create_user("ana@correo.com", "ClaveSegura123", **DATOS)
        usuario.activo = False
        usuario.save()

        # Ejecutar: intentar iniciar sesión con la clave correcta.
        resultado = authenticate(correo="ana@correo.com", password="ClaveSegura123")

        # Verificar: Django niega el acceso aunque la clave sea correcta.
        self.assertIsNone(resultado)

    def test_un_usuario_puede_tener_varios_roles(self):
        # Preparar
        usuario = Usuario.objects.create_user("ana@correo.com", "ClaveSegura123", **DATOS)

        # Ejecutar: asignar dos roles, repitiendo uno de ellos.
        usuario.asignar_rol(Rol.Nombre.AUTOR)
        usuario.asignar_rol(Rol.Nombre.COMITE)
        usuario.asignar_rol(Rol.Nombre.AUTOR)  # Repetir un rol no debe duplicarlo

        # Verificar: tiene exactamente dos roles.
        self.assertEqual(usuario.roles.count(), 2)
        self.assertTrue(usuario.tiene_rol(Rol.Nombre.COMITE))

        # Verificar: sin el rol ADMIN, no puede entrar al panel de administración.
        self.assertFalse(usuario.is_staff)

    def test_superusuario_tiene_rol_admin_y_acceso_al_panel(self):
        # Ejecutar: crear un superusuario, como lo hace "createsuperuser".
        admin = Usuario.objects.create_superuser("admin@correo.com", "ClaveSegura123", **DATOS)

        # Verificar: recibió el rol ADMIN y puede entrar al panel.
        self.assertTrue(admin.tiene_rol(Rol.Nombre.ADMIN))
        self.assertTrue(admin.is_staff)


class CodigoRecuperacionTests(TestCase):
    """Comprueba las reglas de seguridad del PIN de recuperación."""

    def setUp(self):
        """Preparación común: se ejecuta antes de CADA prueba de esta clase."""
        self.usuario = Usuario.objects.create_user("ana@correo.com", "ClaveSegura123", **DATOS)
        self.codigo = CodigoRecuperacion(usuario=self.usuario)
        self.codigo.asignar_pin("123456")
        self.codigo.save()

    def test_pin_se_guarda_como_hash_y_vence_en_15_minutos(self):
        # Verificar: el PIN no aparece en texto plano en la base de datos.
        self.assertNotIn("123456", self.codigo.pin_hash)

        # Verificar: el PIN correcto se acepta y uno incorrecto se rechaza.
        self.assertTrue(self.codigo.verificar_pin("123456"))
        self.assertFalse(self.codigo.verificar_pin("654321"))

        # Verificar: el código vence 15 minutos después de crearse.
        minutos = (self.codigo.expira_en - self.codigo.creado_en).total_seconds() / 60
        self.assertAlmostEqual(minutos, 15, delta=0.1)

        # Verificar: recién creado, el código está disponible.
        self.assertTrue(self.codigo.esta_disponible())

    def test_pin_deja_de_servir_si_vence_se_usa_o_agota_intentos(self):
        # Caso 1: el código venció hace un minuto.
        self.codigo.expira_en = timezone.now() - timedelta(minutes=1)
        self.assertFalse(self.codigo.esta_disponible())

        # Caso 2: el código está vigente, pero ya se usó.
        self.codigo.expira_en = timezone.now() + timedelta(minutes=10)
        self.codigo.usado = True
        self.assertFalse(self.codigo.esta_disponible())

        # Caso 3: el código no se ha usado, pero agotó sus intentos.
        self.codigo.usado = False
        self.codigo.intentos = CodigoRecuperacion.MAX_INTENTOS
        self.assertFalse(self.codigo.esta_disponible())