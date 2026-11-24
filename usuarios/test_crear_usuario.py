"""
Pruebas de la creación de usuarios con roles (HU-02).

Cubren el "aislamiento de endpoints por rol" de la subtarea HU-02.3:
  - El Administrador y el Comité pueden crear usuarios.
  - Un Autor recibe 403 (prueba HU-02.7 de QA).
  - Sin autenticación se recibe 401.
  - El permiso revisa el rol ACTIVO, no todos los roles del usuario.
  - Nadie puede darse un rol escribiéndolo en el encabezado.

force_authenticate simula un usuario autenticado sin pasar por el login:
el login ya se probó en la app autenticacion.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import LineaTematica

from .models import Rol, Usuario


def crear_usuario(correo, *roles):
    """Crea un usuario de prueba con los roles indicados."""
    usuario = Usuario.objects.create_user(
        correo, "ClaveSegura123",
        nombres="Prueba", apellidos="Usuario",
        afiliacion="Universidad del Valle", pais="Colombia",
    )
    for rol in roles:
        usuario.asignar_rol(rol)
    return usuario


def datos_nuevo_usuario(**cambios):
    """Datos válidos de la cuenta que se va a crear; "cambios" modifica algún campo."""
    datos = {
        "correo": "nuevo@ejemplo.com",
        "nombres": "Nuevo",
        "apellidos": "Usuario",
        "afiliacion": "Universidad del Valle",
        "pais": "Colombia",
        "clave": "ClaveSegura123",
        "roles": ["AUTOR"],
    }
    datos.update(cambios)
    return datos


class CrearUsuarioTests(APITestCase):
    def setUp(self):
        """Preparación común: un usuario por cada combinación de roles."""
        self.url = reverse("usuarios:crear")
        self.admin = crear_usuario("admin@ejemplo.com", Rol.Nombre.ADMIN)
        self.comite = crear_usuario("comite@ejemplo.com", Rol.Nombre.COMITE)
        self.autor = crear_usuario("autor@ejemplo.com", Rol.Nombre.AUTOR)
        self.multirrol = crear_usuario(
            "multirrol@ejemplo.com", Rol.Nombre.AUTOR, Rol.Nombre.COMITE
        )

    def crear_como(self, usuario, rol_activo=None, **cambios):
        """
        Atajo: envía la petición autenticado como "usuario".

        Si se indica rol_activo, lo envía en el encabezado X-Rol-Activo.
        En las pruebas de Django, los encabezados se escriben con el prefijo
        HTTP_, en mayúsculas y con guiones bajos.
        """
        self.client.force_authenticate(user=usuario)
        encabezados = {"HTTP_X_ROL_ACTIVO": rol_activo} if rol_activo else {}
        return self.client.post(
            self.url, datos_nuevo_usuario(**cambios), format="json", **encabezados
        )

    # ----------------------------------------------------- Quién puede crear
    def test_admin_crea_usuario_con_varios_roles_y_especialidades(self):
        # Preparar: una línea temática de las que cargó la migración.
        linea = LineaTematica.objects.first()

        # Ejecutar: el administrador crea un autor que también es del comité.
        respuesta = self.crear_como(
            self.admin, roles=["AUTOR", "COMITE"], especialidades=[linea.id]
        )

        # Verificar: 201 con los roles y la especialidad, sin la clave.
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(set(respuesta.data["roles"]), {"AUTOR", "COMITE"})
        self.assertEqual(respuesta.data["especialidades"], [linea.id])
        self.assertNotIn("clave", respuesta.data)

        # Verificar: quedó guardado con la clave como hash.
        nuevo = Usuario.objects.get(correo="nuevo@ejemplo.com")
        self.assertTrue(nuevo.check_password("ClaveSegura123"))

    def test_comite_crea_un_autor(self):
        respuesta = self.crear_como(self.comite)
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    def test_admin_puede_crear_administradores(self):
        respuesta = self.crear_como(self.admin, roles=["ADMIN"])
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    # --------------------------------------------- Aislamiento por rol (403)
    def test_autor_recibe_403(self):
        # Ejecutar
        respuesta = self.crear_como(self.autor)

        # Verificar: 403 y no se creó ningún usuario (siguen los 4 del setUp).
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Usuario.objects.count(), 4)

    def test_sin_autenticacion_recibe_401(self):
        respuesta = self.client.post(self.url, datos_nuevo_usuario(), format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_el_rol_activo_decide_el_permiso(self):
        """Un usuario Autor y Comité solo puede crear cuentas trabajando como Comité."""
        # Trabajando como AUTOR: se niega.
        respuesta = self.crear_como(self.multirrol, rol_activo="AUTOR")
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

        # Trabajando como COMITE: se permite.
        respuesta = self.crear_como(self.multirrol, rol_activo="COMITE")
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    def test_multirrol_sin_encabezado_recibe_403(self):
        """Con varios roles y sin X-Rol-Activo no se sabe con cuál trabaja."""
        respuesta = self.crear_como(self.multirrol)
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_se_puede_usar_un_rol_que_no_se_tiene(self):
        """Seguridad: un autor no se vuelve administrador escribiéndolo en el encabezado."""
        respuesta = self.crear_como(self.autor, rol_activo="ADMIN")
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    # ------------------------------------------------ Validaciones de datos
    def test_comite_no_puede_crear_administradores(self):
        respuesta = self.crear_como(self.comite, roles=["ADMIN"])

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("roles", respuesta.data)

    def test_comite_debe_asignar_linea_tematica(self):
        respuesta = self.crear_como(self.comite, roles=["COMITE"])
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("especialidades", respuesta.data)

    def test_roles_vacios_o_inexistentes_devuelven_400(self):
        for roles in ([], ["SUPERADMIN"]):
            with self.subTest(roles=roles):
                respuesta = self.crear_como(self.admin, roles=roles)
                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("roles", respuesta.data)

    def test_especialidades_solo_para_el_comite(self):
        linea = LineaTematica.objects.first()

        respuesta = self.crear_como(self.admin, roles=["AUTOR"], especialidades=[linea.id])

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("especialidades", respuesta.data)

    def test_correo_duplicado_devuelve_400(self):
        # El correo del autor del setUp ya existe.
        respuesta = self.crear_como(self.admin, correo="AUTOR@ejemplo.com")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("correo", respuesta.data)

    def test_clave_debil_devuelve_400(self):
        respuesta = self.crear_como(self.admin, clave="clavedebil")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("clave", respuesta.data)