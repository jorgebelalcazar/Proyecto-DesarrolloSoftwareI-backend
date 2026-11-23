"""
Permisos específicos del dominio de artículos científicos (HU-15 y HU-20).
"""

from rest_framework.permissions import BasePermission


class EsAutorResponsableArticulo(BasePermission):
    """
    Permite la operación únicamente al usuario registrado como
    autor_responsable del artículo.

    Si otro usuario autenticado (incluso con rol AUTOR) intenta gestionar
    un artículo ajeno, DRF responde 403 Forbidden.
    """

    message = "Solo el autor responsable del artículo tiene permiso para realizar esta acción."

    def has_object_permission(self, request, view, obj):
        return obj.autor_responsable_id == request.user.id