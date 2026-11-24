"""
Rutas de la API del dominio de usuarios.

Se montan bajo el prefijo /api/usuarios/ en config/urls.py.
Las demás historias del dominio (HU-02, HU-08, HU-10, HU-11, HU-12)
agregarán sus rutas en esta misma lista.
"""

from django.urls import path

from .views import (
    CrearUsuarioView,
    GestionUsuarioView,
    ListarUsuariosView,
    MiPerfilView,
    RegistroAutorView,
)

# Espacio de nombres: permite referirse a las rutas como "usuarios:registro-autor",
# sin escribir la dirección completa (se usa en las pruebas con reverse).
app_name = "usuarios"

urlpatterns = [
    # POST /api/usuarios/registro-autor/   (HU-01)
    path("registro-autor/", RegistroAutorView.as_view(), name="registro-autor"),

    # POST /api/usuarios/crear/   (HU-02) Solo Administrador o Comité.
    path("crear/", CrearUsuarioView.as_view(), name="crear"),

    # GET y PATCH /api/usuarios/mi-perfil/   (HU-10) Perfil del usuario del token.
    path("mi-perfil/", MiPerfilView.as_view(), name="mi-perfil"),

    # GET, PATCH y DELETE /api/usuarios/{id}/   (HU-11 y HU-12) Cuenta de otro
    # usuario, para ADMIN y COMITE. DELETE es una baja lógica: no borra la fila.
    # <int:pk> solo acepta números: /api/usuarios/abc/ responde 404.
    path("<int:pk>/", GestionUsuarioView.as_view(), name="gestion"),

    # GET /api/usuarios/   (HU-08) Directorio paginado; los campos dependen del rol activo.
    path("", ListarUsuariosView.as_view(), name="listar"),
]