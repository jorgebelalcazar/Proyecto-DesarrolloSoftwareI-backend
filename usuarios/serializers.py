"""
Serializadores del dominio de usuarios.

Un serializador cumple dos funciones:
  1. Traducir entre JSON (lo que envía y recibe la API) y los modelos de Django.
  2. Validar los datos ANTES de guardarlos. Es la "validación del lado del
     servidor" que exige el enunciado: aunque el front-end valide, alguien
     podría enviar peticiones directamente a la API, saltándose React.

Contenido:
  - Validaciones compartidas: correo disponible, fortaleza de la clave y
    especialidades de los miembros del comité.
  - RegistroAutorSerializer: auto-registro de autores (HU-01).
  - CrearUsuarioSerializer:  creación de usuarios por el Administrador
                             o el Comité (HU-02).
  - UsuarioDirectorioSerializer y UsuarioDirectorioGestionSerializer:
    directorio de usuarios (HU-08).
  - PerfilUsuarioSerializer: consultar y editar el perfil propio (HU-10).
  - GestionUsuarioSerializer: consultar y editar la cuenta de otro usuario,
                              por el Administrador o el Comité (HU-11).
"""

import re

from django.contrib.auth.password_validation import validate_password as validar_clave_django
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from core.models import LineaTematica
from core.serializers import LineaTematicaSerializer

from .models import Especialidad, Rol, SinAdministradorActivo, Usuario, UsuarioRol
from .permisos import obtener_rol_activo

# Mensaje reutilizado: en la validación del correo y cuando la base de datos
# rechaza un correo duplicado.
MENSAJE_CORREO_DUPLICADO = "Ya existe una cuenta registrada con este correo."

# Mensajes de la regla de las especialidades (HU-02, HU-10 y HU-11).
MENSAJE_ESPECIALIDADES_SOLO_COMITE = (
    "Las especialidades solo aplican a los miembros del comité científico."
)
MENSAJE_COMITE_SIN_ESPECIALIDAD = (
    "Asigne al menos una línea temática a los miembros del comité científico."
)


# ===========================================================================
# VALIDACIONES COMPARTIDAS
# Las usan el registro de autores (HU-01), la creación de usuarios (HU-02),
# el perfil (HU-10) y la edición de usuarios (HU-11).
# ===========================================================================
def validar_correo_disponible(valor, excluir=None):
    """
    Normaliza el correo y verifica que no esté registrado.

    "excluir" es el usuario que se está editando (HU-11): su propio correo no
    cuenta como duplicado, así puede conservarlo o cambiar solo mayúsculas.

    Devuelve el correo en minúsculas, que es como se guarda en la base de datos.
    """
    # Paso 1: normalizar, igual que lo hace el modelo al guardar.
    correo = valor.strip().lower()

    # Paso 2: buscar si ya existe. iexact compara sin importar mayúsculas.
    otros = Usuario.objects.filter(correo__iexact=correo)
    if excluir is not None:
        otros = otros.exclude(pk=excluir.pk)
    if otros.exists():
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


def validar_especialidades_comite(es_comite, especialidades):
    """
    Regla de las especialidades, la misma en HU-02, HU-10 y HU-11.

      - es_comite:      si el usuario tendrá el rol COMITE después del cambio.
      - especialidades: las líneas temáticas que tendrá después del cambio.

    Reglas:
      - Quien no es del comité no tiene especialidades.
      - Todo miembro del comité tiene al menos una. Las especialidades sirven
        para sugerir revisores según la línea temática del artículo
        (elicitación G03-R6); un miembro sin ellas no se le podría sugerir
        a ningún artículo.

    Está en una sola función para que la regla no se pueda saltar por otro
    endpoint: crear (HU-02), editar el perfil (HU-10) y editar la cuenta (HU-11).
    """
    if especialidades and not es_comite:
        raise serializers.ValidationError(
            {"especialidades": [MENSAJE_ESPECIALIDADES_SOLO_COMITE]}
        )
    if es_comite and not especialidades:
        raise serializers.ValidationError(
            {"especialidades": [MENSAJE_COMITE_SIN_ESPECIALIDAD]}
        )


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

    # Solo de lectura: aparecen en la respuesta, pero el cliente no puede enviarlos.
    # slug_field="nombre" muestra "AUTOR" en lugar del id del rol.
    roles = serializers.SlugRelatedField(many=True, read_only=True, slug_field="nombre")

    class Meta:
        model = Usuario
        fields = [
            "id", "correo", "nombres", "apellidos", "tipo_documento",
            "numero_documento", "afiliacion", "pais", "telefono",
            "acepta_tratamiento_datos", "clave", "confirmacion_clave",
            "roles", "fecha_registro",
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
      - especialidades (lista de ids de líneas temáticas): obligatorias para
        el comité (al menos una) y no permitidas para los demás roles.
      - Opcionales: tipo_documento, numero_documento y telefono.

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
        """
        Especialidades coherentes con los roles: solo el comité las tiene, y
        todo miembro del comité tiene al menos una.
        """
        es_comite = any(rol.nombre == Rol.Nombre.COMITE for rol in datos["roles"])
        validar_especialidades_comite(es_comite, datos.get("especialidades", []))
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


# ===========================================================================
# HU-10: MI PERFIL (CONSULTAR Y EDITAR LOS DATOS PROPIOS)
# ===========================================================================
class PerfilUsuarioSerializer(serializers.ModelSerializer):
    """
    Datos del perfil del usuario que inició sesión (HU-10).

    Lectura (GET): sus datos, sus roles y sus especialidades.

    Edición (PATCH), solo estos campos (CAMPOS_EDITABLES):
      - nombres, apellidos, tipo_documento, numero_documento, afiliacion,
        pais y telefono;
      - especialidades (lista de ids), solo si el usuario es del comité, y
        nunca vacía: un miembro del comité conserva al menos una.

    Seguridad (HU-10.2, bloqueo de auto-escalación):
    Se usa una lista PERMITIDA, no una lista prohibida. Cualquier campo que no
    esté en CAMPOS_EDITABLES, como roles, activo, correo, is_superuser o
    password, se rechaza con 400. Así, un campo nuevo del modelo queda
    bloqueado hasta que alguien decida, a propósito, permitir su edición.
    """

    # Campos que el usuario puede cambiar en su propio perfil.
    CAMPOS_EDITABLES = {
        "nombres", "apellidos", "tipo_documento", "numero_documento",
        "afiliacion", "pais", "telefono", "especialidades",
    }

    # Roles por código, solo de lectura: nadie se asigna roles desde su perfil.
    roles = serializers.SlugRelatedField(many=True, read_only=True, slug_field="nombre")

    # Escritura: lista de ids de líneas temáticas, por ejemplo [1, 3].
    # La lectura se arma en to_representation con el formato {id, nombre}.
    especialidades = serializers.PrimaryKeyRelatedField(
        many=True, queryset=LineaTematica.objects.all(), required=False, write_only=True
    )

    class Meta:
        model = Usuario
        fields = [
            "id", "correo", "nombres", "apellidos", "tipo_documento",
            "numero_documento", "afiliacion", "pais", "telefono",
            "roles", "especialidades", "fecha_registro",
        ]
        read_only_fields = ["id", "correo", "roles", "fecha_registro"]

    def validate(self, datos):
        """
        Rechaza los campos que no se pueden editar y valida las especialidades.

          - Campos fuera de CAMPOS_EDITABLES -> 400 en cada uno (HU-10.2).
          - Especialidades sin el rol COMITE, o un miembro del comité que
            deja su lista vacía -> 400, la misma regla de la HU-02.
        """
        # Paso 1: campos recibidos que no están permitidos.
        # initial_data es el JSON original, antes de que DRF descarte lo desconocido.
        no_permitidos = set(self.initial_data) - self.CAMPOS_EDITABLES
        if no_permitidos:
            raise serializers.ValidationError({
                campo: ["Este campo no se puede modificar desde el perfil."]
                for campo in sorted(no_permitidos)
            })

        # Paso 2: si se envían especialidades, aplicar la regla del comité.
        # Se revisa que la persona TENGA el rol, sin importar con cuál trabaja ahora.
        if "especialidades" in datos:
            validar_especialidades_comite(
                self.instance.tiene_rol(Rol.Nombre.COMITE), datos["especialidades"]
            )

        return datos

    def to_representation(self, instance):
        """
        Agrega las especialidades a la respuesta con el formato {id, nombre},
        igual que el directorio (HU-08) y el catálogo GET /api/lineas-tematicas/.
        """
        datos = super().to_representation(instance)
        datos["especialidades"] = LineaTematicaSerializer(
            instance.especialidades.all(), many=True
        ).data
        return datos

    def update(self, instance, datos):
        """
        Guarda los datos personales y las especialidades en una sola transacción.

        especialidades.set() deja exactamente la lista recibida: crea las nuevas
        filas en la tabla "especialidad", borra las que sobran y no toca las que
        se mantienen.
        """
        especialidades = datos.pop("especialidades", None)

        with transaction.atomic():
            instance = super().update(instance, datos)
            if especialidades is not None:
                instance.especialidades.set(especialidades)

        return instance


# ===========================================================================
# HU-11: GESTIONAR LA CUENTA DE OTRO USUARIO (ADMINISTRADOR Y COMITÉ)
# ===========================================================================
class GestionUsuarioSerializer(serializers.ModelSerializer):
    """
    Datos de la cuenta de un usuario, para el Administrador y el Comité (HU-11).

    Lectura (GET): todos sus datos, sus roles, sus especialidades {id, nombre},
    el estado de la cuenta y sus fechas. Nunca la clave.

    Edición (PATCH), solo estos campos:
      - nombres, apellidos, tipo_documento, numero_documento, afiliacion,
        pais y telefono;
      - roles: lista de códigos, por ejemplo ["AUTOR", "COMITE"];
      - especialidades: lista de ids de líneas temáticas, solo para el comité;
      - correo: SOLO el Administrador (ver CAMPOS_SOLO_ADMIN).

    Igual que en el perfil (HU-10), se usa una lista PERMITIDA: cualquier otro
    campo se rechaza con 400. En particular "activo": desactivar una cuenta
    también debe guardar su fecha de desactivación, y eso lo hace la HU-12.

    Reglas que valida el servidor:
      - Debe quedar al menos un rol.
      - El Comité no puede asignar el rol ADMIN (la misma regla de la HU-02).
      - Las especialidades solo aplican a quien tendrá el rol COMITE, y todo
        miembro del comité debe tener al menos una.
      - Siempre debe quedar un Administrador activo (regla del modelo, HU-11.2).
      - El correo no puede pertenecer a otra cuenta.
    La regla "el Comité no modifica Administradores" la revisa la vista, con
    el permiso ComiteNoModificaAdministradores, antes de llegar aquí.
    """

    # Campos que el Administrador y el Comité pueden cambiar.
    CAMPOS_EDITABLES = {
        "nombres", "apellidos", "tipo_documento", "numero_documento",
        "afiliacion", "pais", "telefono", "roles", "especialidades",
    }

    # Campos que solo el Administrador puede cambiar. El correo es el usuario
    # para iniciar sesión y el destino del PIN de recuperación (HU-06): quien
    # lo cambia puede quedarse con la cuenta. Por eso se reserva al rol mayor.
    CAMPOS_SOLO_ADMIN = {"correo"}

    # Roles por su código, igual que en la HU-02. Si llega un código que no
    # existe en la tabla "rol", DRF responde 400 automáticamente.
    roles = serializers.SlugRelatedField(
        many=True, slug_field="nombre", queryset=Rol.objects.all()
    )

    # Escritura: lista de ids, por ejemplo [1, 3]. La lectura se arma en
    # to_representation con el formato {id, nombre}.
    especialidades = serializers.PrimaryKeyRelatedField(
        many=True, queryset=LineaTematica.objects.all(), required=False, write_only=True
    )

    class Meta:
        model = Usuario
        fields = [
            "id", "correo", "nombres", "apellidos", "tipo_documento",
            "numero_documento", "afiliacion", "pais", "telefono",
            "roles", "especialidades",
            "activo", "fecha_registro", "fecha_desactivacion",
        ]
        read_only_fields = ["id", "activo", "fecha_registro", "fecha_desactivacion"]

        # La unicidad del correo la valida validate_correo, que excluye al
        # propio usuario y devuelve el mensaje del proyecto.
        extra_kwargs = {"correo": {"validators": []}}

    def campos_permitidos(self):
        """Campos que puede cambiar quien hace la petición, según su rol activo."""
        if obtener_rol_activo(self.context["request"]) == Rol.Nombre.ADMIN:
            return self.CAMPOS_EDITABLES | self.CAMPOS_SOLO_ADMIN
        return self.CAMPOS_EDITABLES

    def validate_correo(self, valor):
        """Correo que no pertenezca a OTRA cuenta."""
        return validar_correo_disponible(valor, excluir=self.instance)

    def validate_roles(self, roles):
        """
        Valida la nueva lista de roles.

          - Debe haber al menos un rol.
          - Los roles repetidos se ignoran.
          - El Comité no puede asignar el rol ADMIN. No hace falta revisar si
            lo QUITA: el Comité no puede modificar cuentas de Administradores.
        """
        # Paso 1: al menos un rol.
        if not roles:
            raise serializers.ValidationError("Debe asignar al menos un rol.")

        # Paso 2: quitar repetidos conservando el orden.
        roles = list(dict.fromkeys(roles))

        # Paso 3: nadie otorga un privilegio mayor que el suyo.
        rol_activo = obtener_rol_activo(self.context["request"])
        if rol_activo == Rol.Nombre.COMITE and any(rol.nombre == Rol.Nombre.ADMIN for rol in roles):
            raise serializers.ValidationError(
                "Un miembro del comité no puede asignar el rol de Administrador."
            )

        return roles

    def validate(self, datos):
        """
        Rechaza los campos que no se pueden editar y valida las especialidades.

          - Campos fuera de la lista permitida -> 400 en cada uno.
          - Especialidades incoherentes con los roles que tendrá -> 400:
            especialidades sin el rol COMITE, o un miembro del comité sin
            ninguna (la misma regla de la HU-02).
        """
        # Paso 1: campos recibidos que este rol no puede cambiar.
        # initial_data es el JSON original, antes de que DRF descarte lo desconocido.
        no_permitidos = set(self.initial_data) - self.campos_permitidos()
        if no_permitidos:
            raise serializers.ValidationError({
                campo: ["Este campo no se puede modificar con su rol activo."]
                for campo in sorted(no_permitidos)
            })

        # Paso 2: la regla solo se revisa si la petición cambia roles o
        # especialidades. Así, corregir el teléfono de alguien no se bloquea
        # por datos que no se están tocando.
        if "roles" not in datos and "especialidades" not in datos:
            return datos

        # Paso 3: roles que tendrá el usuario: los nuevos si llegaron; si no, los actuales.
        if "roles" in datos:
            sera_comite = any(rol.nombre == Rol.Nombre.COMITE for rol in datos["roles"])
        else:
            sera_comite = self.instance.tiene_rol(Rol.Nombre.COMITE)

        # Paso 4: especialidades que tendrá después del cambio.
        if "especialidades" in datos:
            finales = datos["especialidades"]           # las que llegaron
        elif sera_comite:
            finales = list(self.instance.especialidades.all())  # conserva las suyas
        else:
            finales = []                                # update() se las quita

        # Paso 5: la misma regla de la HU-02.
        validar_especialidades_comite(sera_comite, finales)

        return datos

    def to_representation(self, instance):
        """
        Agrega las especialidades con el formato {id, nombre}, igual que el
        directorio (HU-08), el perfil (HU-10) y GET /api/lineas-tematicas/.
        """
        datos = super().to_representation(instance)
        datos["especialidades"] = LineaTematicaSerializer(
            instance.especialidades.all(), many=True
        ).data
        return datos

    def update(self, instance, datos):
        """
        Guarda los datos, los roles y las especialidades en una sola transacción:
        si una parte falla, no se guarda nada.

        roles.set() y especialidades.set() dejan exactamente la lista recibida:
        crean las filas nuevas, borran las que sobran y NO tocan las que se
        mantienen. Así, si un Administrador conserva su rol ADMIN, esa fila
        nunca se borra y la regla del último Administrador no se dispara.
        """
        # Paso 1: separar lo que no son columnas de la tabla "usuario".
        roles = datos.pop("roles", None)
        especialidades = datos.pop("especialidades", None)

        try:
            with transaction.atomic():
                # Paso 2: datos personales y correo.
                instance = super().update(instance, datos)

                # Paso 3: roles. Si se quita el último ADMIN activo, el modelo
                # lanza SinAdministradorActivo y la transacción se deshace.
                if roles is not None:
                    instance.roles.set(roles)

                    # Quien deja de ser del comité no conserva especialidades.
                    if not any(rol.nombre == Rol.Nombre.COMITE for rol in roles):
                        especialidades = []

                # Paso 4: especialidades.
                if especialidades is not None:
                    instance.especialidades.set(especialidades)
        except SinAdministradorActivo as error:
            raise serializers.ValidationError({"roles": error.messages})
        except IntegrityError:
            # Caso límite: dos peticiones simultáneas con el mismo correo.
            raise serializers.ValidationError({"correo": [MENSAJE_CORREO_DUPLICADO]})

        return instance