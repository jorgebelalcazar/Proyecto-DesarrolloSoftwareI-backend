"""
Permisos del dominio de artículos (HU-15 y, más adelante, HU-20).

Un permiso de DRF responde una sola pregunta antes de ejecutar la vista:
"¿esta petición puede continuar?". Si no, DRF responde 403 Forbidden.
"""

from rest_framework.permissions import BasePermission


class EsAutorResponsable(BasePermission):
    """
    Permite la operación solo al autor responsable del artículo (HU-15, criterio 2).

    Es un permiso "de objeto": DRF lo revisa cuando la vista ya encontró el
    artículo de la ruta (get_object), por eso lo recibe en "obj". Si otro
    usuario, aunque también sea Autor, intenta gestionar un artículo ajeno,
    recibe 403.
    """

    message = "Solo el autor responsable del artículo puede realizar esta acción."

    def has_object_permission(self, request, view, obj):
        return obj.autor_responsable_id == request.user.id