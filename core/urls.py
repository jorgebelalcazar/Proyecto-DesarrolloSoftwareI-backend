"""Rutas de los catálogos compartidos del sistema."""

from django.urls import path

from .views import CriterioEvaluacionListView, LineaTematicaListView

urlpatterns = [
    path("lineas-tematicas/", LineaTematicaListView.as_view(), name="lineas-tematicas"),
    path(
        "criterios-evaluacion/",
        CriterioEvaluacionListView.as_view(),
        name="criterios-evaluacion",
    ),
]
