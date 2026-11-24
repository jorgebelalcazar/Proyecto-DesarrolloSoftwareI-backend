"""
Rutas del dominio de artículos. Se montan bajo /api/articulos/ en config/urls.py.
"""

from django.urls import path

from .views import (
    ArticulosView,
    CoautoresArticuloView,
    MisArticulosView,
    SubirVersionInicialView,
)

app_name = "articulos"

urlpatterns = [
    # GET y POST /api/articulos/   (HU-18 y HU-14) Catálogo para Admin y Comité;
    # postulación para el Autor.
    path("", ArticulosView.as_view(), name="lista"),

    # GET /api/articulos/mis-articulos/   (HU-17) Artículos del autor del token.
    path("mis-articulos/", MisArticulosView.as_view(), name="mis-articulos"),

    # GET y PUT /api/articulos/{id}/coautores/   (HU-15) Coautores del artículo.
    path("<int:pk>/coautores/", CoautoresArticuloView.as_view(), name="coautores"),

    # POST /api/articulos/{id}/versiones/   (HU-16) PDF inicial del artículo.
    path("<int:pk>/versiones/", SubirVersionInicialView.as_view(), name="versiones"),
]