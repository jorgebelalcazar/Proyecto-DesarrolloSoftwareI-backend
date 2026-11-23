"""
Serializadores del dominio de usuarios.

Un serializador cumple dos funciones:
  1. Traducir entre JSON (lo que envía y recibe la API) y los modelos de Django.
  2. Validar los datos ANTES de guardarlos. Es la "validación del lado del
     servidor" que exige el enunciado: aunque el front-end valide, alguien
     podría enviar peticiones directamente a la API, saltándose React.

Contenido:
  - Validaciones compartidas: correo disponible y fortaleza de la clave.
  - RegistroAutorSerializer: auto-registro de autores (HU-01).
  - CrearUsuarioSerializer:  creación de usuarios por el Administrador
                             o el Comité (HU-02).
  - UsuarioDirectorioSerializer y UsuarioDirectorioGestionSerializer:
    directorio de usuarios (HU-08).
"""

import re

from django.contrib.auth.password_validation import validate_password as validar_clave_django
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from autenticacion.captcha import CaptchaNoDisponible, verificar_captcha
from autenticacion.excepciones import ServicioCaptchaNoDisponible
from core.models import LineaTematica
from core.serializers import LineaTematicaSerializer

from .models import Especialidad, Rol, Usuario, UsuarioRol
from .permisos import obtener_rol_activo

# Mensaje reutilizado: en la validación del correo y cuando la base de datos
# rechaza un correo duplicado.
MENSAJE_CORREO_DUPLICADO = "Ya existe una cuenta registrada con este correo."


# ===========================================================================
# VALIDACIONES COMPARTIDAS
# Las usan el registro de autores (HU-01) y la creación de usuarios (HU-02).
# ===========================================================================
def validar_correo_disponible(valor):
    """
    Normaliza el correo y verifica que no esté registrado.

    Devuelve el correo en minúsculas, que es como se guarda en la base de datos.
    """
    # Paso 1: normalizar, igual que lo hace el modelo al guardar.
    correo = valor.strip().lower()

    # Paso 2: buscar si ya existe. iexact compara sin importar mayúsculas.
    if Usuario.objects.filter(correo__iexact=correo).exists():
        raise serializers.ValidationError(MENSAJE_CORREO_DUPLICADO)

    return correo


def validar_fortaleza_clave(valor):
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
        raise serializers.ValidationError("La clave debe tener al menos una letra mayúscula.")
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


# ===========================================================================
# HU-01: REGISTRO DE AUTOR
# ===========================================================================
class RegistroAutorSerializer(serializers.ModelSerializer):
    """
    Datos del formulario de auto-registro de autores (HU-01).

    Entrada (JSON que envía el front-end):
      - Obligatorios: correo, nombres, apellidos, afiliacion, pais, clave,
        confirmacion_clave y acepta_tratamiento_datos.
      - Opcionales: tipo_documento, numero_documento y telefono.

    Salida (JSON que devuelve la API): los datos del usuario creado y sus
    roles, SIN la clave.

    Seguridad: campos como "is_superuser" o "roles" NO están en la lista de
    campos editables. Si alguien los envía, se ignoran (protección contra la
    "asignación masiva"). El rol AUTOR lo asigna el sistema.
    """

    # write_only=True: la clave se recibe, pero nunca aparece en la respuesta.
    # trim_whitespace=False: los espacios forman parte de la clave.
    clave = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )
    confirmacion_clave = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )
    captcha = serializers.CharField(write_only=True)

    # Solo de lectura: aparecen en la respuesta, pero el cliente no puede enviarlos.
    # slug_field="nombre" muestra "AUTOR" en lugar del id del rol.
    roles = serializers.SlugRelatedField(many=True, read_only=True, slug_field="nombre")

    class Meta:
        model = Usuario
        fields = [
            "id", "correo", "nombres", "apellidos", "tipo_documento",
            "numero_documento", "afiliacion", "pais", "telefono",
            "acepta_tratamiento_datos", "clave", "confirmacion_clave",
            "captcha", "roles", "fecha_registro",
        ]
        read_only_fields = ["id", "fecha_registro"]
        extra_kwargs = {
            # La unicidad del correo la validamos nosotros, sin importar mayúsculas.
            "correo": {"validators": []},
            # En el modelo tiene valor por defecto (False) y DRF lo volvería
            # opcional; lo hacemos obligatorio para que la persona responda.
            "acepta_tratamiento_datos": {"required": True},
        }
        # Desactiva las validaciones automáticas de unicidad a nivel de objeto.
        validators = []

    def validate_correo(self, valor):
        """Correo no registrado (caso CP-01.B)."""
        return validar_correo_disponible(valor)

    def validate_clave(self, valor):
        """Clave fuerte, según las reglas compartidas."""
        return validar_fortaleza_clave(valor)

    def validate_acepta_tratamiento_datos(self, valor):
        """Exige la autorización de tratamiento de datos (Ley 1581 de 2012)."""
        if not valor:
            raise serializers.ValidationError(
                "Debe aceptar el tratamiento de datos personales para registrarse."
            )
        return valor

    def validate_captcha(self, valor):
        """Verifica ante Google el CAPTCHA exigido por HU-01."""
        request = self.context.get("request")
        ip = request.META.get("REMOTE_ADDR") if request else None
        try:
            valido = verificar_captcha(valor, ip)
        except CaptchaNoDisponible as error:
            raise ServicioCaptchaNoDisponible() from error
        if not valido:
            raise serializers.ValidationError(
                "La verificación CAPTCHA no es válida. Intente de nuevo."
            )
        return valor

    def validate(self, datos):
        """Verifica que la clave y su confirmación coincidan."""
        if datos["clave"] != datos["confirmacion_clave"]:
            raise serializers.ValidationError({"confirmacion_clave": "Las claves no coinciden."})
        return datos

    def create(self, datos):
        """
        Crea el usuario con el rol AUTOR.

        Usa una transacción: o se crean el usuario Y su rol, o no se crea nada.
        """
        # Paso 1: separar los campos que no son columnas del modelo.
        datos.pop("confirmacion_clave")
        datos.pop("captcha")
        clave = datos.pop("clave")

        try:
            # Paso 2: crear usuario y rol dentro de una misma transacción.
            with transaction.atomic():
                usuario = Usuario.objects.create_user(password=clave, **datos)
                usuario.asignar_rol(Rol.Nombre.AUTOR)
        except IntegrityError:
            # Paso 3: caso límite de dos registros simultáneos con el mismo correo.
            raise serializers.ValidationError({"correo": [MENSAJE_CORREO_DUPLICADO]})

        return usuario


# ===========================================================================
# HU-02: CREAR USUARIO CON ROLES (ADMINISTRADOR O COMITÉ)
# ===========================================================================
class CrearUsuarioSerializer(serializers.ModelSerializer):
    """
    Datos para que el Administrador o el Comité creen una cuenta (HU-02).

    Entrada (JSON):
      - Obligatorios: correo, nombres, apellidos, afiliacion, pais, clave y
        roles (lista de nombres, por ejemplo ["AUTOR", "COMITE"]).
      - Opcionales: tipo_documento, numero_documento, telefono y
        especialidades (lista de ids de líneas temáticas, solo para el comité).

    Salida: los datos del usuario creado, sus roles y sus especialidades,
    SIN la clave.

    No incluye acepta_tratamiento_datos: la autorización la da cada persona,
    no quien crea la cuenta. Queda en False hasta que el usuario la acepte.
    """

    clave = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )

    # A diferencia del registro, aquí los roles SÍ se envían.
    # queryset indica dónde buscarlos: si llega un nombre que no existe en la
    # tabla "rol", DRF responde 400 automáticamente.
    roles = serializers.SlugRelatedField(
        many=True, slug_field="nombre", queryset=Rol.objects.all()
    )

    # Las especialidades se envían como ids de líneas temáticas, por ejemplo [1, 3].
    # Si llega un id que no existe, DRF responde 400 automáticamente.
    especialidades = serializers.PrimaryKeyRelatedField(
        many=True, queryset=LineaTematica.objects.all(), required=False
    )

    class Meta:
        model = Usuario
        fields = [
            "id", "correo", "nombres", "apellidos", "tipo_documento",
            "numero_documento", "afiliacion", "pais", "telefono", "clave",
            "roles", "especialidades", "fecha_registro",
        ]
        read_only_fields = ["id", "fecha_registro"]
        extra_kwargs = {"correo": {"validators": []}}
        validators = []

    def validate_correo(self, valor):
        """Correo no registrado."""
        return validar_correo_disponible(valor)

    def validate_clave(self, valor):
        """Clave fuerte, según las reglas compartidas."""
        return validar_fortaleza_clave(valor)

    def validate_roles(self, roles):
        """
        Valida la lista de roles.

          - Debe haber al menos un rol.
          - Los roles repetidos se ignoran.
          - Un miembro del comité no puede crear administradores: nadie puede
            otorgar un privilegio mayor que el suyo.
        """
        # Paso 1: al menos un rol.
        if not roles:
            raise serializers.ValidationError("Debe asignar al menos un rol.")

        # Paso 2: quitar repetidos conservando el orden.
        # dict.fromkeys guarda cada elemento una sola vez.
        roles = list(dict.fromkeys(roles))

        # Paso 3: revisar el privilegio de quien crea la cuenta.
        # El serializador recibe la petición en su contexto, desde la vista.
        rol_activo = obtener_rol_activo(self.context["request"])
        nombres = {rol.nombre for rol in roles}
        if rol_activo == Rol.Nombre.COMITE and Rol.Nombre.ADMIN in nombres:
            raise serializers.ValidationError(
                "Un miembro del comité no puede asignar el rol de Administrador."
            )

        return roles

    def validate(self, datos):
        """Las especialidades solo aplican a los miembros del comité."""
        especialidades = datos.get("especialidades", [])
        nombres = {rol.nombre for rol in datos["roles"]}

        if especialidades and Rol.Nombre.COMITE not in nombres:
            raise serializers.ValidationError(
                {"especialidades": ["Las especialidades solo aplican a los miembros del comité científico."]}
            )
        if Rol.Nombre.COMITE in nombres and not especialidades:
            raise serializers.ValidationError(
                {"especialidades": ["Asigne al menos una línea temática a los miembros del comité científico."]}
            )
        return datos

    def create(self, datos):
        """
        Crea el usuario con sus roles y especialidades.

        Usa una transacción: si falla cualquier parte, no se guarda nada.
        Nunca queda un usuario sin roles ni con especialidades a medias.
        """
        # Paso 1: separar lo que no son columnas de la tabla "usuario".
        clave = datos.pop("clave")
        roles = datos.pop("roles")
        especialidades = datos.pop("especialidades", [])

        try:
            with transaction.atomic():
                # Paso 2: crear el usuario; create_user guarda la clave como hash.
                usuario = Usuario.objects.create_user(password=clave, **datos)

                # Paso 3: crear sus filas en la tabla intermedia "usuario_rol".
                for rol in roles:
                    UsuarioRol.objects.create(usuario=usuario, rol=rol)

                # Paso 4: crear sus filas en la tabla intermedia "especialidad".
                for linea in especialidades:
                    Especialidad.objects.create(usuario=usuario, linea_tematica=linea)
        except IntegrityError:
            # Caso límite: dos peticiones simultáneas con el mismo correo.
            raise serializers.ValidationError({"correo": [MENSAJE_CORREO_DUPLICADO]})

        return usuario


# ===========================================================================
# HU-08: DIRECTORIO DE USUARIOS (LISTAR Y CONSULTAR)
# ===========================================================================
class UsuarioDirectorioSerializer(serializers.ModelSerializer):
    """
    Datos públicos de un usuario en el directorio (HU-08).

    Es lo que ve un Autor: nombre, afiliación, país, roles y especialidades.
    Por el principio de mínimo privilegio NO incluye el correo, el documento,
    el teléfono, el estado de la cuenta ni, por supuesto, la clave.

    Formato de salida:
      {
        "id": 4, "nombres": "Carolina", "apellidos": "Comité",
        "afiliacion": "Universidad del Valle", "pais": "Colombia",
        "roles": ["COMITE"],
        "especialidades": [{"id": 1, "nombre": "Sistemas Inteligentes"}]
      }
    """

    # Roles por su código ("ADMIN", "COMITE", "AUTOR"), igual que en el login,
    # el registro y la creación de usuarios.
    roles = serializers.SlugRelatedField(many=True, read_only=True, slug_field="nombre")

    # Especialidades con id y nombre, en el mismo formato del catálogo
    # GET /api/lineas-tematicas/: el front-end muestra el nombre (Chips de la
    # HU-08.4) y puede usar el id para filtrar (HU-09) o editar (HU-11).
    especialidades = LineaTematicaSerializer(many=True, read_only=True)

    class Meta:
        model = Usuario
        fields = [
            "id", "nombres", "apellidos", "afiliacion", "pais",
            "roles", "especialidades",
        ]
        # Serializador solo de lectura: el directorio no modifica usuarios.
        read_only_fields = fields


class UsuarioDirectorioGestionSerializer(UsuarioDirectorioSerializer):
    """
    Datos del directorio para quienes gestionan usuarios: Administrador y Comité (HU-08).

    Hereda los campos públicos y agrega los que necesitan para administrar
    cuentas (HU-11 y HU-12): el correo, el estado de la cuenta y sus fechas.
    """

    class Meta(UsuarioDirectorioSerializer.Meta):
        fields = UsuarioDirectorioSerializer.Meta.fields + [
            "correo", "activo", "fecha_registro", "fecha_desactivacion",
        ]
        read_only_fields = fields