"""
Rutas del proceso de revisión y arbitraje, bajo el prefijo /api/revisiones/.

Cada historia agrega aquí su ruta, sin tocar config/urls.py:
  - HU-25: asignar-automatico/   (asignación automática de jurados)
  - HU-27: mis-asignaciones/     (bandeja del jurado)
  - HU-28: <id>/evaluar/         (registro de la evaluación)
"""

app_name = "revisiones"

urlpatterns = []