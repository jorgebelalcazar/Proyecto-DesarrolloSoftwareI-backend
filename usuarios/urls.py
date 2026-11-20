"""
Rutas de la API del dominio de usuarios.

Se montan bajo el prefijo /api/usuarios/ en config/urls.py.
Las demás historias del dominio (HU-02, HU-08, HU-10, HU-11, HU-12)
agregarán sus rutas en esta misma lista.
"""

from django.urls import path

from .views import CrearUsuarioView, RegistroAutorView, ListarUsuariosView
# Espacio de nombres: permite referirse a las rutas como "usuarios:registro-autor",
# sin escribir la dirección completa (se usa en las pruebas con reverse).
app_name = "usuarios"

urlpatterns = [
    # POST /api/usuarios/registro-autor/   (HU-01)
    path("registro-autor/", RegistroAutorView.as_view(), name="registro-autor"),
    
    # POST /api/usuarios/crear/   (HU-02) Solo Administrador o Comité.
    path("crear/", CrearUsuarioView.as_view(), name="crear"),

    # GET /api/usuarios/   (HU-08) Listado paginado de usuarios registrados.
    path("", ListarUsuariosView.as_view(), name="listar"),
]