"""
Rutas de la autenticación. Se montan bajo /api/auth/ en config/urls.py.

La recuperación de clave tiene dos pasos: solicitar-pin/ (HU-06) y
confirmar-pin/ (HU-07).
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import ConfirmarPinView, LoginView, SesionView, SolicitarPinView

app_name = "autenticacion"

urlpatterns = [
    # POST /api/auth/login/    (HU-03)
    path("login/", LoginView.as_view(), name="login"),

    # POST /api/auth/refresh/  Vista que trae Simple JWT: recibe {"refresh": "..."}
    # y devuelve {"access": "..."} con un token de acceso nuevo.
    path("refresh/", TokenRefreshView.as_view(), name="refresh"),

    # GET  /api/auth/sesion/   Datos del usuario del token.
    path("sesion/", SesionView.as_view(), name="sesion"),
    
    # POST /api/auth/solicitar-pin/   (HU-06) Envía el PIN de recuperación por correo.
    path("solicitar-pin/", SolicitarPinView.as_view(), name="solicitar-pin"),
    
    # POST /api/auth/confirmar-pin/   (HU-07) Verifica el PIN y cambia la clave.
    path("confirmar-pin/", ConfirmarPinView.as_view(), name="confirmar-pin"),
]