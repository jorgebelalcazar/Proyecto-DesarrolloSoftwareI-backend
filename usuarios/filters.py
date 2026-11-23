"""
Filtros y búsqueda del directorio de usuarios (HU-09).

Se aplican a GET /api/usuarios/ con parámetros en la URL, y se pueden
combinar entre sí y con la paginación:

    /api/usuarios/?rol=COMITE&especialidad=1&search=valle&page=2

  - UsuarioFilter (HU-09.1):     filtros exactos por rol, especialidad y estado.
  - BusquedaDirectorio (HU-09.2): búsqueda libre por texto, con campos que
                                  dependen del rol activo.
"""

import django_filters
from rest_framework.filters import SearchFilter

from core.models import LineaTematica

from .models import Rol, Usuario


class UsuarioFilter(django_filters.FilterSet):
    """
    Filtros exactos del directorio (HU-09.1).

    Parámetros:
      - rol:          código del rol: ADMIN, COMITE o AUTOR.
      - especialidad: id de una línea temática (ver GET /api/lineas-tematicas/).
      - estado:       true (activos) o false (desactivados).

    Un valor que no existe (por ejemplo ?rol=SUPERADMIN o una especialidad
    con un id inexistente) responde 400 en lugar de una lista vacía, para
    que el front-end detecte el error de inmediato.
    """

    # ChoiceFilter solo acepta los valores de la lista; cualquier otro -> 400.
    rol = django_filters.ChoiceFilter(field_name="roles__nombre", choices=Rol.Nombre.choices)

    # ModelChoiceFilter verifica que la línea temática exista; si no -> 400.
    especialidad = django_filters.ModelChoiceFilter(
        field_name="especialidades", queryset=LineaTematica.objects.all()
    )

    # Filtra por la columna "activo". Un Autor solo recibe usuarios activos
    # (lo decide la vista), así que para él "estado=false" devuelve una lista vacía.
    estado = django_filters.BooleanFilter(field_name="activo")

    class Meta:
        model = Usuario
        fields = ["rol", "especialidad", "estado"]


class BusquedaDirectorio(SearchFilter):
    """
    Búsqueda libre por texto en el directorio (HU-09.2): ?search=texto

    Busca coincidencias parciales, sin importar mayúsculas, en los campos
    que indique la vista. El correo solo se incluye para quienes gestionan
    usuarios: si un Autor pudiera buscar por correo, escribiría un correo y
    descubriría a quién pertenece, aunque el directorio no se lo muestre (HU-08).
    """

    def get_search_fields(self, view, request):
        """Campos públicos para todos; agrega los de gestión si el rol activo es ADMIN o COMITE."""
        campos = list(view.search_fields)
        if view.es_gestor():
            campos += view.search_fields_gestion
        return campos