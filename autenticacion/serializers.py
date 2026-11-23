"""
Serializadores de la autenticación.

Contenido:
  - validar_captcha:          verificación del CAPTCHA compartida (HU-03 y HU-06).
  - LoginSerializer:          inicio de sesión (HU-03).
  - UsuarioSesionSerializer:  datos del usuario en la sesión (HU-03 y HU-04).
  - SolicitarPinSerializer:   solicitud del PIN de recuperación (HU-06).
  - ConfirmarPinSerializer:   confirmación del PIN y nueva clave (HU-07).
  - LogoutSerializer:         cierre de sesión (HU-05).
"""

from django.contrib.auth import authenticate
from rest_framework import serializers

from usuarios.models import Usuario
from usuarios.serializers import validar_fortaleza_clave
from .captcha import CaptchaNoDisponible, verificar_captcha
from .excepciones import CredencialesInvalidas, ServicioCaptchaNoDisponible


def validar_captcha(token, request):
    """
    Verifica con Google el token de CAPTCHA del formulario.

    La comparten el login (HU-03) y la solicitud del PIN (HU-06), que son
    los formularios públicos que un bot podría atacar.

    Resultados:
      - Si el CAPTCHA es válido, no hace nada.
      - Si no es válido, lanza un error 400 en el campo "captcha".
      - Si Google no responde, lanza un error 503 (fallar cerrado).
    """
    # REMOTE_ADDR es la dirección IP de quien hace la petición.
    ip = request.META.get("REMOTE_ADDR") if request else None

    try:
        captcha_valido = verificar_captcha(token, ip)
    except CaptchaNoDisponible:
        # Google no respondió: no es culpa del usuario -> 503.
        raise ServicioCaptchaNoDisponible()

    if not captcha_valido:
        raise serializers.ValidationError(
            {"captcha": ["La verificación CAPTCHA no es válida. Intente de nuevo."]}
        )


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

        # Paso 1: verificar el CAPTCHA con Google (400 o 503 si falla).
        validar_captcha(datos["captcha"], request)

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


class SolicitarPinSerializer(serializers.Serializer):
    """
    Datos del formulario "Olvidé mi clave" (HU-06).

    Entrada (JSON):
      - correo:  correo electrónico de la cuenta.
      - captcha: el token del widget de Google reCAPTCHA.

    El CAPTCHA impide que un bot use este formulario para enviar cientos de
    correos o para probar qué correos están registrados.
    """

    correo = serializers.EmailField()
    captcha = serializers.CharField(write_only=True)

    def validate(self, datos):
        """Verifica el CAPTCHA. El correo ya lo validó EmailField (formato)."""
        validar_captcha(datos["captcha"], self.context.get("request"))
        return datos


class ConfirmarPinSerializer(serializers.Serializer):
    """
    Datos del formulario "Cambiar mi clave con el PIN" (HU-07).

    Entrada (JSON):
      - correo:             correo de la cuenta (el mismo del paso 1).
      - pin:                los 6 dígitos que llegaron por correo.
      - clave:              la nueva clave.
      - confirmacion_clave: la nueva clave, otra vez.

    Aquí solo se valida el FORMATO. El PIN se compara con el hash en el
    servicio confirmar_recuperacion. Así, una clave débil o un PIN mal
    escrito se rechazan sin gastar ninguno de los 3 intentos del código.
    """

    correo = serializers.EmailField()

    # RegexField: el PIN debe ser exactamente 6 dígitos ("^" inicio, "$" final).
    pin = serializers.RegexField(
        r"^\d{6}$",
        write_only=True,
        error_messages={"invalid": "El código debe tener exactamente 6 dígitos."},
    )

    # Mismo manejo de la clave que en el registro (HU-01).
    clave = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )
    confirmacion_clave = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )

    def validate_clave(self, valor):
        """La nueva clave cumple las mismas reglas que la del registro."""
        return validar_fortaleza_clave(valor)

    def validate(self, datos):
        """Verifica que la clave y su confirmación coincidan."""
        if datos["clave"] != datos["confirmacion_clave"]:
            raise serializers.ValidationError({"confirmacion_clave": "Las claves no coinciden."})
        return datos


class LogoutSerializer(serializers.Serializer):
    """
    Datos para cerrar la sesión (HU-05).

    Entrada (JSON):
      - refresh: el token de renovación que entregó el login.

    Solo valida que llegue el campo. Si el token sirve o no, lo decide la
    vista al intentar ponerlo en la lista negra.
    """

    # write_only: el token se recibe, pero nunca se devuelve.
    refresh = serializers.CharField(write_only=True)