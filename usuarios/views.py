"""
Vistas (endpoints) de la API del dominio de usuarios.

Una vista recibe la petición HTTP, usa un serializador para validar los datos
y devuelve la respuesta en JSON con el código de estado correspondiente.
"""

from rest_framework import generics
from rest_framework.permissions import AllowAny

from .models import Usuario
from .serializers import RegistroAutorSerializer


class RegistroAutorView(generics.CreateAPIView):
    """
    POST /api/usuarios/registro-autor/   (HU-01)

    Permite que una persona nueva cree su propia cuenta con el rol Autor

    Respuestas:
      - 201 Created:     cuenta creada; devuelve los datos del usuario sin la clave.
      - 400 Bad Request: datos inválidos; devuelve los errores por campo.
      - 405 Method Not Allowed: se intentó un método distinto de POST.

    CreateAPIView ya trae todo el flujo:
      1. Recibe el JSON.
      2. Ejecuta las validaciones del serializador.
      3. Si son correctas, llama a serializer.create() y responde 201.
      4. Si fallan, responde 400 con los errores.
    """

    serializer_class = RegistroAutorSerializer

    # Algunas herramientas de DRF, como la API navegable, consultan el queryset de la vista.
    queryset = Usuario.objects.all()

    # Endpoint público: quien se registra todavía no tiene cuenta.
    permission_classes = [AllowAny]

    # No se autentica a nadie en esta ruta. Así, aunque el navegador tenga una
    # sesión abierta del panel de administración, no se mezcla con el registro.
    authentication_classes = []