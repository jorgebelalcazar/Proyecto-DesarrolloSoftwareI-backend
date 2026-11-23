"""
Rutas de la API del dominio de artículos científicos.
"""

from django.urls import path

from .views import CrearArticuloView, GestionCoautoresArticuloView

app_name = "articulos"

urlpatterns = [
    path("", CrearArticuloView.as_view(), name="crear-articulo"),
    path(
        "<int:articulo_id>/coautores/",
        GestionCoautoresArticuloView.as_view(),
        name="gestion-coautores",
    ),
]