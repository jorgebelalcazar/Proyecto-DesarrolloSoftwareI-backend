"""
Filtros de los listados de artículos.

Se aplican con parámetros en la URL y se combinan con la paginación:

    /api/articulos/mis-articulos/?estado=POSTULADO&linea_tematica=1&page=2

  - ArticuloFilter (HU-17): filtros por estado y línea temática.
  - ArticuloCatalogoFilter (HU-18): agrega el filtro por autor para el catálogo
    del Comité y el Administrador. La búsqueda por texto (?search=) la hace
    SearchFilter, configurado en la vista.
"""

import django_filters

from core.models import LineaTematica
from usuarios.models import Usuario

from .models import Articulo


class ArticuloFilter(django_filters.FilterSet):
    """
    Filtros exactos de los artículos (HU-17, criterio 3).

    Parámetros:
      - estado:         POSTULADO, EN_REVISION, APROBADO, RECHAZADO o DESHABILITADO.
      - linea_tematica: id de una línea temática (ver GET /api/lineas-tematicas/).

    Un valor que no existe (por ejemplo ?estado=INVENTADO o un id de línea
    inexistente) responde 400 en lugar de una lista vacía, para que el
    front-end detecte el error de inmediato. Es la misma regla de la HU-09.
    """

    # ChoiceFilter solo acepta los valores de la lista; cualquier otro -> 400.
    estado = django_filters.ChoiceFilter(choices=Articulo.Estado.choices)

    # ModelChoiceFilter verifica que la línea temática exista; si no -> 400.
    linea_tematica = django_filters.ModelChoiceFilter(queryset=LineaTematica.objects.all())

    class Meta:
        model = Articulo
        fields = ["estado", "linea_tematica"]


class ArticuloCatalogoFilter(ArticuloFilter):
    """
    Filtros del catálogo de artículos (HU-18.2).

    Hereda estado y línea temática de ArticuloFilter, y agrega:
      - autor: id del autor responsable (por ejemplo, desde el directorio HU-08).

    Igual que los demás filtros, un autor que no existe responde 400.
    """

    autor = django_filters.ModelChoiceFilter(
        field_name="autor_responsable", queryset=Usuario.objects.all()
    )

    class Meta(ArticuloFilter.Meta):
        fields = ArticuloFilter.Meta.fields + ["autor"]