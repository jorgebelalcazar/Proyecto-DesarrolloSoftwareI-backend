"""
Rutas de la conferencia. Se montan bajo /api/conferencias/ en config/urls.py.
"""

from django.urls import path

from .views import (
    ConferenciaDetalleView,
    ConferenciaListCreateView,
    ConferenciaVigenteView,
    RubricaConferenciaView,
)

app_name = "conferencias"

urlpatterns = [
    # GET y POST /api/conferencias/   (HU-13) Lista y creación de ediciones.
    path("", ConferenciaListCreateView.as_view(), name="lista"),

    # GET /api/conferencias/vigente/   (HU-13) La edición que no ha terminado.
    # Va antes de <int:pk>/; igual, "vigente" no es un número y no se confunde.
    path("vigente/", ConferenciaVigenteView.as_view(), name="vigente"),

    # GET, PUT y PATCH /api/conferencias/{id}/   (HU-13) Una edición.
    path("<int:pk>/", ConferenciaDetalleView.as_view(), name="detalle"),

    # GET y PUT /api/conferencias/{id}/criterios/   (HU-22.2) Rúbrica de evaluación.
    path("<int:pk>/criterios/", RubricaConferenciaView.as_view(), name="criterios"),
]