"""
Paginación compartida por todos los listados de la API.

Está en "core" para que los módulos de usuarios, artículos y agenda usen
exactamente la misma forma de paginar. Así el front-end maneja todas las
tablas con el mismo código.
"""

from rest_framework.pagination import PageNumberPagination


class PaginacionEstandar(PageNumberPagination):
    """
    Paginación por número de página.

    Uso desde el front-end:
      GET /api/usuarios/?page=2              -> segunda página, 10 registros
      GET /api/usuarios/?page=1&page_size=25 -> primera página, 25 registros

    Formato de la respuesta:
      {
        "count": 37,                                   (total de registros)
        "next": "http://.../api/usuarios/?page=3",     (null en la última página)
        "previous": "http://.../api/usuarios/?page=1", (null en la primera página)
        "results": [ ... ]                             (registros de esta página)
      }

    Evita respuestas pesadas: aunque haya cientos de usuarios, cada petición
    trae como máximo "max_page_size" registros.
    """

    # Registros por página cuando el front-end no indica otro valor.
    page_size = 10

    # Nombre del parámetro con el que el front-end puede pedir otro tamaño.
    page_size_query_param = "page_size"

    # Límite superior: nadie puede pedir, por ejemplo, page_size=100000.
    max_page_size = 100