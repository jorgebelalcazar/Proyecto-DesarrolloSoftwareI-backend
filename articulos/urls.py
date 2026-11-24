"""
Rutas del dominio de artículos. Se montan bajo /api/articulos/ en config/urls.py.
"""

from django.urls import path

from .views import CoautoresArticuloView, CrearArticuloView, MisArticulosView

app_name = "articulos"

urlpatterns = [
    # POST /api/articulos/   (HU-14) Postular un artículo.
    # La HU-18 agregará aquí mismo el GET del catálogo de artículos.
    path("", CrearArticuloView.as_view(), name="lista"),

    # GET /api/articulos/mis-articulos/   (HU-17) Artículos del autor del token.
    path("mis-articulos/", MisArticulosView.as_view(), name="mis-articulos"),

    # GET y PUT /api/articulos/{id}/coautores/   (HU-15) Coautores del artículo.
    path("<int:pk>/coautores/", CoautoresArticuloView.as_view(), name="coautores"),
]