"""
Rutas de la API del dominio de artículos científicos.
"""

from django.urls import path

from .views import CrearArticuloView

app_name = "articulos"

urlpatterns = [
    path("", CrearArticuloView.as_view(), name="crear-articulo"),
]