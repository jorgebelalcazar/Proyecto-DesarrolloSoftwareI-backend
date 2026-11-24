"""
Rutas del dominio de artículos. Se montan bajo /api/articulos/ en config/urls.py.
"""

from django.urls import path

from .views import CrearArticuloView, SubirVersionInicialView

app_name = "articulos"

urlpatterns = [
    # POST /api/articulos/   (HU-14) Postular un artículo.
    # La HU-18 agregará aquí mismo el GET del catálogo de artículos.
    path("", CrearArticuloView.as_view(), name="lista"),
    # POST /api/articulos/{id}/versiones/ guarda el PDF inicial (HU-16).
    path("<int:articulo_id>/versiones/", SubirVersionInicialView.as_view(), name="subir-version-inicial"),
]
