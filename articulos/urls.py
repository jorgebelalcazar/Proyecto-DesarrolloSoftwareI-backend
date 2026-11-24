"""
Rutas del dominio de artículos. Se montan bajo /api/articulos/ en config/urls.py.
"""

from django.urls import path

from .views import CoautoresArticuloView, CrearArticuloView, SubirVersionInicialView

app_name = "articulos"

urlpatterns = [
    # POST /api/articulos/ (HU-14) permite postular con metadatos y coautores.
    path("", CrearArticuloView.as_view(), name="lista"),
    # POST /api/articulos/{id}/versiones/ guarda el PDF inicial (HU-16).
    path(
        "<int:articulo_id>/versiones/",
        SubirVersionInicialView.as_view(),
        name="subir-version-inicial",
    ),
    # GET y PUT /api/articulos/{id}/coautores/ gestionan los firmantes (HU-15).
    path("<int:pk>/coautores/", CoautoresArticuloView.as_view(), name="coautores"),
]
