"""
Rutas principales del proyecto.

Cada app define sus propias rutas en su archivo urls.py, y aquí solo se
conectan con un prefijo. Así, cada integrante trabaja en las rutas de su
app sin tocar este archivo.
"""

from django.contrib import admin
from django.urls import include, path

from core.views import LineaTematicaListView, salud

urlpatterns = [
    # Panel de administración de Django.
    path("admin/", admin.site.urls),

    # Endpoint de prueba de integración (Sprint 0).
    path("api/salud/", salud),

    # Catálogo de líneas temáticas (HU-02.8).
    path("api/lineas-tematicas/", LineaTematicaListView.as_view(), name="lineas-tematicas"),

    # API del dominio de usuarios: registro, creación, consulta, etc.
    path("api/usuarios/", include("usuarios.urls")),

    # Autenticación: login, renovación de tokens y sesión (HU-03).
    path("api/auth/", include("autenticacion.urls")),

    # Ediciones de la conferencia y sus plazos (HU-13).
    path("api/conferencias/", include("conferencias.urls")),
]