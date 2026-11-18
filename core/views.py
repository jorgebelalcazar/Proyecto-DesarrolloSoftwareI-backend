"""
Vistas compartidas del sistema.

Contiene el endpoint de prueba de integración creado en el Sprint 0.
"""

from django.db import connection
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def salud(request):
    """
    GET /api/salud/

    Confirma que la API responde y que la base de datos está conectada.

    Es público (AllowAny): desde la HU-03 todos los endpoints exigen
    autenticación por defecto, pero este debe poder consultarse sin
    iniciar sesión, porque lo usa la prueba de integración del front-end.
    """
    # Le pide su versión a PostgreSQL: si responde, la conexión funciona.
    with connection.cursor() as cursor:
        cursor.execute("SELECT version();")
        version_bd = cursor.fetchone()[0]

    return Response({
        "estado": "ok",
        "mensaje": "API de la conferencia funcionando",
        "base_de_datos": version_bd,
    })