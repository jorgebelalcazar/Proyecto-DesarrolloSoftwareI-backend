"""
Serializadores del dominio de usuarios.

Un serializador cumple dos funciones:
  1. Traducir entre JSON (lo que envía y recibe la API) y los modelos de Django.
  2. Validar los datos ANTES de guardarlos. Es la "validación del lado del
     servidor" que exige el enunciado: aunque el front-end valide, alguien
     podría enviar peticiones directamente a la API, saltándose React.
"""

import re

from django.contrib.auth.password_validation import validate_password as validar_clave_django
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from .models import Rol, Usuario

# Mensaje reutilizado en dos lugares: en la validación del correo
# y cuando la base de datos rechaza un correo duplicado.
MENSAJE_CORREO_DUPLICADO = "Ya existe una cuenta registrada con este correo."


class RegistroAutorSerializer(serializers.ModelSerializer):
    """
    Datos del formulario de auto-registro de autores (HU-01).

    Entrada (JSON que envía el front-end):
      - Obligatorios: correo, nombres, apellidos, afiliacion, pais, clave,
        confirmacion_clave y acepta_tratamiento_datos.
      - Opcionales: tipo_documento, numero_documento y telefono.

    Salida (JSON que devuelve la API):
      - Los datos del usuario creado y sus roles, SIN la clave.

    Seguridad:
      - Campos como "is_superuser" o "roles" NO están en la lista de campos
        editables. Si alguien los envía, se ignoran. Así nadie puede
        registrarse como administrador (protección contra "asignación masiva").
    """

    # write_only=True: la clave se recibe, pero nunca aparece en la respuesta.
    # trim_whitespace=False: los espacios forman parte de la clave, no se recortan.
    # style: en la API navegable de DRF el campo se muestra oculto (con puntos).
    clave = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )
    confirmacion_clave = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )

    # Roles del usuario creado, solo de lectura: aparecen en la respuesta,
    # pero el cliente no puede enviarlos. El rol AUTOR lo asigna el sistema.
    # slug_field="nombre" muestra el nombre del rol ("AUTOR") en lugar de su id.
    roles = serializers.SlugRelatedField(many=True, read_only=True, slug_field="nombre")

    class Meta:
        model = Usuario

        # Campos que maneja el serializador, en el orden en que aparecen en el JSON.
        fields = [
            "id", "correo", "nombres", "apellidos", "tipo_documento",
            "numero_documento", "afiliacion", "pais", "telefono",
            "acepta_tratamiento_datos", "clave", "confirmacion_clave",
            "roles", "fecha_registro",
        ]

        # El id y la fecha de registro los genera el sistema.
        read_only_fields = ["id", "fecha_registro"]

        extra_kwargs = {
            # Quitamos el validador automático de DRF para el correo, porque
            # nosotros lo validamos sin importar mayúsculas y con un mensaje propio.
            "correo": {"validators": []},
            # En el modelo este campo tiene valor por defecto (False), y DRF lo
            # volvería opcional. Lo hacemos obligatorio: la persona debe responder.
            "acepta_tratamiento_datos": {"required": True},
        }

        # Desactiva las validaciones automáticas de unicidad a nivel de objeto;
        # la unicidad del correo ya se valida en validate_correo.
        validators = []

    # -----------------------------------------------------------------------
    # Validaciones por campo.
    # DRF ejecuta automáticamente cada método "validate_<campo>".
    # -----------------------------------------------------------------------
    def validate_correo(self, valor):
        """
        Normaliza el correo y verifica que no esté registrado (caso CP-01.B).

        Devuelve el correo en minúsculas, que es como se guarda en la base de datos.
        """
        # Paso 1: normalizar, igual que lo hace el modelo al guardar.
        correo = valor.strip().lower()

        # Paso 2: buscar si ya existe. iexact compara sin importar mayúsculas.
        if Usuario.objects.filter(correo__iexact=correo).exists():
            raise serializers.ValidationError(MENSAJE_CORREO_DUPLICADO)

        return correo

    def validate_clave(self, valor):
        """
        Aplica las reglas de seguridad de la clave.

        Reglas del proyecto (restricción de calidad del Sprint 0):
          - al menos una letra mayúscula;
          - al menos un número.
        Reglas de Django (configuradas en settings.py):
          - mínimo 8 caracteres;
          - no puede ser una clave común, como "12345678";
          - no puede tener solo números.
        """
        # Paso 1: reglas propias del proyecto.
        if not re.search(r"[A-Z]", valor):
            raise serializers.ValidationError(
                "La clave debe tener al menos una letra mayúscula."
            )
        if not re.search(r"\d", valor):
            raise serializers.ValidationError("La clave debe tener al menos un número.")

        # Paso 2: validadores de Django.
        # Si alguno falla, Django lanza su propio tipo de error; lo convertimos al
        # tipo de DRF para que la API responda 400 con los mensajes en español.
        try:
            validar_clave_django(valor)
        except DjangoValidationError as error:
            raise serializers.ValidationError(list(error.messages))

        return valor

    def validate_acepta_tratamiento_datos(self, valor):
        """Exige la autorización de tratamiento de datos (Ley 1581 de 2012)."""
        if not valor:
            raise serializers.ValidationError(
                "Debe aceptar el tratamiento de datos personales para registrarse."
            )
        return valor

    # -----------------------------------------------------------------------
    # Validación de varios campos a la vez.
    # DRF la ejecuta después de las validaciones por campo.
    # -----------------------------------------------------------------------
    def validate(self, datos):
        """Verifica que la clave y su confirmación coincidan."""
        if datos["clave"] != datos["confirmacion_clave"]:
            raise serializers.ValidationError(
                {"confirmacion_clave": "Las claves no coinciden."}
            )
        return datos

    # -----------------------------------------------------------------------
    # Creación del usuario.
    # DRF la ejecuta cuando todas las validaciones pasaron.
    # -----------------------------------------------------------------------
    def create(self, datos):
        """
        Crea el usuario con el rol AUTOR.

        Usa una transacción: o se crean el usuario Y su rol, o no se crea nada.
        Así nunca queda un usuario sin rol si algo falla a mitad de camino.
        """
        # Paso 1: separar los campos que no son columnas del modelo.
        datos.pop("confirmacion_clave")
        clave = datos.pop("clave")

        try:
            # Paso 2: crear usuario y rol dentro de una misma transacción.
            with transaction.atomic():
                # create_user guarda la clave como hash PBKDF2 (ver UsuarioManager).
                usuario = Usuario.objects.create_user(password=clave, **datos)
                usuario.asignar_rol(Rol.Nombre.AUTOR)
        except IntegrityError:
            # Paso 3: caso límite. Si dos personas se registran con el mismo correo
            # al mismo tiempo, ambas pasan validate_correo, pero la base de datos
            # rechaza la segunda gracias a uk_usuario_correo. Respondemos 400.
            raise serializers.ValidationError({"correo": [MENSAJE_CORREO_DUPLICADO]})

        return usuario