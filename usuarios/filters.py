import django_filters
from .models import Usuario

class UsuarioFilter(django_filters.FilterSet):
    """
    Filtros exactos para el directorio de usuarios (HU-09).
    Permite combinar búsqueda por rol (texto), especialidad (ID) y estado (booleano).
    """
    rol = django_filters.CharFilter(field_name="roles__nombre")
    especialidad = django_filters.NumberFilter(field_name="especialidades__id")
    estado = django_filters.BooleanFilter(field_name="activo")

    class Meta:
        model = Usuario
        fields = ["rol", "especialidad", "estado"]