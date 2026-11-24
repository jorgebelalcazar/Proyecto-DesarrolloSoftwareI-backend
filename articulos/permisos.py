"""
Permisos del dominio de artículos (HU-15, HU-16, HU-19 y, más adelante, HU-20).

Un permiso de DRF responde una sola pregunta antes de ejecutar la vista:
"¿esta petición puede continuar?". Si no, DRF responde 403 Forbidden.
"""

from rest_framework.permissions import BasePermission

from usuarios.models import Rol
from usuarios.permisos import obtener_rol_activo


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


class PuedeVerArticulo(BasePermission):
    """
    Decide quién puede ver el detalle de un artículo (HU-19, criterio 3).

      - Con rol activo ADMIN o COMITE: cualquier artículo.
      - Con rol activo AUTOR: solo los artículos de los que es autor
        responsable, igual que en "Mis artículos" (HU-17). Si no, 403.

    Usa obtener_rol_activo (HU-04), el único lugar que decide el rol activo:
    así funciona también para quien tiene un solo rol y no envía el
    encabezado X-Rol-Activo.
    """

    message = "Solo puede consultar los artículos de los que es autor responsable."

    def has_object_permission(self, request, view, obj):
        if obtener_rol_activo(request) in (Rol.Nombre.ADMIN, Rol.Nombre.COMITE):
            return True
        return obj.autor_responsable_id == request.user.id