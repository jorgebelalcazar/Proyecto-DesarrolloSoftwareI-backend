"""
Rutas de la autenticación. Se montan bajo /api/auth/ en config/urls.py.

Aquí también se agregarán las rutas de la recuperación de clave
(HU-06 y HU-07) en las siguientes fases.
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import LoginView, SesionView

app_name = "autenticacion"

urlpatterns = [
    # POST /api/auth/login/    (HU-03)
    path("login/", LoginView.as_view(), name="login"),

    # POST /api/auth/refresh/  Vista que trae Simple JWT: recibe {"refresh": "..."}
    # y devuelve {"access": "..."} con un token de acceso nuevo.
    path("refresh/", TokenRefreshView.as_view(), name="refresh"),

    # GET  /api/auth/sesion/   Datos del usuario del token.
    path("sesion/", SesionView.as_view(), name="sesion"),
]