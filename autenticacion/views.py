"""
Vistas (endpoints) de la autenticación.

  POST /api/auth/login/    -> inicia sesión y entrega los tokens (HU-03).
  POST /api/auth/refresh/  -> renueva el token de acceso (vista de Simple JWT).
  GET  /api/auth/sesion/   -> devuelve los datos del usuario del token.
  POST /api/auth/solicitar-pin/ -> envía el PIN de recuperación de clave (HU-06).
"""

from django.contrib.auth.models import update_last_login
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from usuarios.models import CodigoRecuperacion

from .excepciones import ServicioCorreoNoDisponible
from .recuperacion import CorreoNoEnviado, solicitar_recuperacion
from .serializers import LoginSerializer, SolicitarPinSerializer, UsuarioSesionSerializer

# Respuesta única de la solicitud del PIN: es la misma exista o no el correo.
MENSAJE_PIN_SOLICITADO = (
    "Si el correo corresponde a una cuenta activa, recibirá un código de "
    "recuperación en los próximos minutos."
)


class LoginView(APIView):
    """
    POST /api/auth/login/   (HU-03)

    Inicia sesión con correo, clave y CAPTCHA.

    Respuestas:
      - 200 OK: devuelve "access", "refresh" y los datos del usuario.
      - 400 Bad Request: faltan datos o el CAPTCHA no es válido.
      - 401 Unauthorized: correo o clave incorrectos, o usuario desactivado.
      - 503 Service Unavailable: Google no respondió al verificar el CAPTCHA.
    """

    # Endpoint público: quien inicia sesión todavía no tiene token.
    permission_classes = [AllowAny]

    # No se autentica a nadie en esta ruta. Si el front-end enviara por error
    # un token viejo o vencido, no debe impedir que el usuario inicie sesión.
    authentication_classes = []

    def post(self, request):
        # Paso 1: validar datos, CAPTCHA y credenciales.
        # Si algo falla, DRF responde automáticamente con 400, 401 o 503.
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        usuario = serializer.validated_data["usuario"]

        # Paso 2: generar los tokens.
        # RefreshToken.for_user crea el token de renovación, y a partir de él
        # se obtiene el token de acceso. Ambos van firmados con la SECRET_KEY.
        refresh = RefreshToken.for_user(usuario)

        # Paso 3: registrar la fecha del último inicio de sesión (columna last_login).
        update_last_login(None, usuario)

        # Paso 4: responder con los tokens y los datos básicos del usuario.
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "usuario": UsuarioSesionSerializer(usuario).data,
            },
            status=status.HTTP_200_OK,
        )


class SesionView(APIView):
    """
    GET /api/auth/sesion/

    Devuelve los datos del usuario dueño del token.

    Requiere autenticación: usa la configuración por defecto de settings.py
    (IsAuthenticated). Sin token, o con un token inválido, responde 401.

    El front-end lo usa al recargar la página, para recuperar los datos
    del usuario a partir del token guardado.
    """

    def get(self, request):
        # request.user es el usuario que DRF identificó a partir del token.
        return Response(UsuarioSesionSerializer(request.user).data)



class SolicitarPinView(APIView):
    """
    POST /api/auth/solicitar-pin/   (HU-06)

    Paso 1 de la recuperación de clave: si el correo tiene una cuenta activa,
    le envía un PIN de 6 dígitos que vence en 15 minutos.

    Respuestas:
      - 200 OK: siempre el mismo mensaje, exista o no el correo, para no
        revelar qué correos están registrados.
      - 400 Bad Request: falta el correo, su formato no es válido o el
        CAPTCHA no es válido.
      - 503 Service Unavailable: Google no respondió al verificar el CAPTCHA,
        o el servidor de correo no aceptó el mensaje.
    """

    # Endpoint público: quien olvidó su clave no puede iniciar sesión.
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        # Paso 1: validar el correo y el CAPTCHA (400 o 503 si fallan).
        serializer = SolicitarPinSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        # Paso 2: generar y enviar el PIN, si corresponde.
        try:
            solicitar_recuperacion(serializer.validated_data["correo"])
        except CorreoNoEnviado:
            raise ServicioCorreoNoDisponible()

        # Paso 3: responder siempre lo mismo.
        return Response(
            {
                "detail": MENSAJE_PIN_SOLICITADO,
                "vigencia_minutos": CodigoRecuperacion.VIGENCIA_MINUTOS,
            },
            status=status.HTTP_200_OK,
        )