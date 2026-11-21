"""
Serializadores de la autenticación (HU-03).

El login valida, en este orden:
  1. Que lleguen los tres datos: correo, clave y token de CAPTCHA.
  2. Que el CAPTCHA sea válido (verificado con Google).
  3. Que el correo y la clave correspondan a un usuario ACTIVO.
"""

from django.contrib.auth import authenticate
from rest_framework import serializers

from usuarios.models import Usuario

from .captcha import CaptchaNoDisponible, verificar_captcha
from .excepciones import CredencialesInvalidas, ServicioCaptchaNoDisponible


class LoginSerializer(serializers.Serializer):
    """
    Datos del formulario de inicio de sesión.

    Entrada (JSON):
      - correo:  correo electrónico del usuario.
      - clave:   su contraseña.
      - captcha: el token que entregó el widget de Google reCAPTCHA.

    Si todo es válido, deja el usuario autenticado en validated_data["usuario"].
    """

    correo = serializers.EmailField()

    # write_only: la clave se recibe pero nunca se devuelve.
    # trim_whitespace=False: los espacios forman parte de la clave.
    clave = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )
    captcha = serializers.CharField(write_only=True)

    def validate(self, datos):
        """
        Verifica el CAPTCHA y después las credenciales.

        El CAPTCHA va PRIMERO: si un bot intenta adivinar claves, se le
        detiene antes de que el servidor gaste tiempo calculando hashes.
        """
        request = self.context.get("request")

        # Paso 1: verificar el CAPTCHA con Google.
        # REMOTE_ADDR es la dirección IP de quien hace la petición.
        ip = request.META.get("REMOTE_ADDR") if request else None
        try:
            captcha_valido = verificar_captcha(datos["captcha"], ip)
        except CaptchaNoDisponible:
            # Google no respondió: no es culpa del usuario -> 503.
            raise ServicioCaptchaNoDisponible()

        if not captcha_valido:
            raise serializers.ValidationError(
                {"captcha": ["La verificación CAPTCHA no es válida. Intente de nuevo."]}
            )

        # Paso 2: verificar el correo y la clave.
        # authenticate devuelve el usuario si todo es correcto, o None si:
        #   - el correo no existe;
        #   - la clave es incorrecta;
        #   - el usuario está desactivado (activo=False), porque consulta
        #     la propiedad is_active del modelo Usuario.
        # Además, si el correo no existe, Django calcula igual un hash de
        # la clave, para que la respuesta tarde lo mismo en todos los casos
        # y no revele qué correos existen (protección contra ataques de tiempo).
        usuario = authenticate(request, correo=datos["correo"], password=datos["clave"])

        if usuario is None:
            # Mismo mensaje para todos los casos -> 401.
            raise CredencialesInvalidas()

        # Paso 3: entregar el usuario a la vista para que genere los tokens.
        datos["usuario"] = usuario
        return datos


class UsuarioSesionSerializer(serializers.ModelSerializer):
    """
    Datos básicos del usuario que inició sesión.

    Se devuelven en el login y en /api/auth/sesion/, para que el front-end
    muestre el nombre del usuario y sus roles sin hacer otra petición.
    """

    # Todos los roles del usuario (tabla usuario_rol), por nombre: ["AUTOR", "COMITE"].
    # El front-end los usa para mostrar el selector de rol activo (HU-04.1).
    # Mismo formato que en RegistroAutorSerializer y CrearUsuarioSerializer.
    roles = serializers.SlugRelatedField(many=True, read_only=True, slug_field="nombre")

    class Meta:
        model = Usuario
        fields = ["id", "correo", "nombres", "apellidos", "roles"]