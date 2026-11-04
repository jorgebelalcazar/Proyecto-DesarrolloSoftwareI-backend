"""
Rutas principales del proyecto.

Cada app define sus propias rutas en su archivo urls.py, y aquí solo se
conectan con un prefijo. Así, cada integrante trabaja en las rutas de su
app sin tocar este archivo.
"""

from django.contrib import admin
from django.urls import include, path

from core.views import salud

urlpatterns = [
    # Panel de administración de Django.
    path("admin/", admin.site.urls),

    # Endpoint de prueba de integración.
    path("api/salud/", salud),

    # API del dominio de usuarios: registro, creación, consulta, etc.
    path("api/usuarios/", include("usuarios.urls")),
]