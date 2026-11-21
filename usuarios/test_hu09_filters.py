from django.urls import reverse
from rest_framework.test import APITestCase
from usuarios.models import Usuario, Rol
from core.models import LineaTematica

class FiltrosDirectorioTests(APITestCase):
    """Pruebas para la HU-09: Filtrado del directorio de usuarios."""

    @classmethod
    def setUpTestData(cls):
        # Usamos get_or_create()[0] para usar los roles y especialidades si ya existen en la BD de pruebas
        cls.rol_autor = Rol.objects.get_or_create(nombre=Rol.Nombre.AUTOR)[0]
        cls.rol_admin = Rol.objects.get_or_create(nombre=Rol.Nombre.ADMIN)[0]
        cls.especialidad1 = LineaTematica.objects.get_or_create(nombre="Sistemas Inteligentes")[0]
        
        cls.u1 = Usuario.objects.create_user(correo="autor1@test.com", password="123", nombres="Juan", apellidos="A")
        cls.u1.roles.add(cls.rol_autor)
        cls.u1.especialidades.add(cls.especialidad1)
        
        cls.u2 = Usuario.objects.create_user(correo="admin@test.com", password="123", nombres="Pedro", apellidos="B", activo=False)
        cls.u2.roles.add(cls.rol_admin)
        
        cls.admin = Usuario.objects.create_user(correo="jefe@test.com", password="123", nombres="Jefe", apellidos="C")
        cls.admin.roles.add(cls.rol_admin)

    def setUp(self):
        # Generar la URL dinámicamente usando app_name y name de urls.py
        self.url = reverse("usuarios:listar")
        
        # Autenticar al cliente de pruebas como el administrador
        self.client.force_authenticate(user=self.admin)
        self.client.credentials(HTTP_X_ROL_ACTIVO=Rol.Nombre.ADMIN)

    def test_filtro_por_rol(self):
        response = self.client.get(f"{self.url}?rol=AUTOR")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["correo"], "autor1@test.com")

    def test_filtro_por_estado_inactivo(self):
        response = self.client.get(f"{self.url}?estado=false")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["correo"], "admin@test.com")

    def test_filtros_combinados(self):
        response = self.client.get(f"{self.url}?rol=AUTOR&especialidad={self.especialidad1.id}")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["correo"], "autor1@test.com")