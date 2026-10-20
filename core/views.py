from django.db import connection
from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def salud(request):
    """Endpoint de prueba: confirma que la API responde y que la base de datos está conectada."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT version();")
        version_bd = cursor.fetchone()[0]
    return Response({
        "estado": "ok",
        "mensaje": "API de la conferencia funcionando",
        "base_de_datos": version_bd,
    })