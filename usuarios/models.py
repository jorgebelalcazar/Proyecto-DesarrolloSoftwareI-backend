"""
Modelos del dominio de usuarios y acceso.

Este archivo define las tablas del modelo relacional del Sprint 0:
  - usuario:             personas que usan el sistema.
  - rol:                 ADMIN, COMITE y AUTOR.
  - usuario_rol:         qué roles tiene cada usuario (relación N:M).
  - especialidad:        en qué líneas temáticas se especializa cada usuario (N:M).
  - codigo_recuperacion: PIN para recuperar la clave (HU-06 y HU-07).
"""

from datetime import timedelta

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# ROL
# ---------------------------------------------------------------------------
class Rol(models.Model):
    """
    Rol que puede tener un usuario (tabla "rol").

    Un usuario puede tener varios roles a la vez, por ejemplo Autor y
    Miembro del comité. Al iniciar sesión elige con cuál trabajar
    (respuesta de la profesora G03-R2).
    """

    class Nombre(models.TextChoices):
        # Cada opción tiene dos partes:
        #   - el valor que se guarda en la base de datos ("ADMIN");
        #   - la etiqueta que ve la persona ("Administrador").
        ADMIN = "ADMIN", "Administrador"
        COMITE = "COMITE", "Miembro del comité científico"
        AUTOR = "AUTOR", "Autor"

    # choices limita los valores posibles a las tres opciones de arriba.
    # unique=True impide que el mismo rol exista dos veces en la tabla.
    nombre = models.CharField(
        "nombre", max_length=20, choices=Nombre.choices, unique=True
    )

    class Meta:
        db_table = "rol"
        verbose_name = "rol"
        verbose_name_plural = "roles"

    def __str__(self):
        # get_nombre_display() devuelve la etiqueta: "Administrador" en vez de "ADMIN".
        return self.get_nombre_display()


# ---------------------------------------------------------------------------
# ADMINISTRADOR DE USUARIOS (MANAGER)
# ---------------------------------------------------------------------------
class UsuarioManager(BaseUserManager):
    """
    Encargado de crear y buscar usuarios.

    Django lo usa en el comando "createsuperuser" y al iniciar sesión,
    y nosotros lo usaremos en la API (HU-01 y HU-02).

    Garantiza dos reglas en TODOS los caminos de creación de usuarios:
      - el correo se guarda normalizado y en minúsculas;
      - la clave se guarda como hash, nunca en texto plano.
    """

    # Permite que las migraciones también usen este manager.
    use_in_migrations = True

    def _crear(self, correo, password, **campos):
        """
        Lógica común para crear usuarios normales y superusuarios.

        El guion bajo al inicio del nombre indica que es de uso interno:
        desde fuera se usan create_user o create_superuser.
        """
        # Paso 1: validar que llegue el correo, porque es el dato de inicio de sesión.
        if not correo:
            raise ValueError("El correo electrónico es obligatorio.")

        # Paso 2: construir el usuario en memoria (todavía no se guarda).
        # normalize_email arregla el dominio del correo y lower() pasa todo a minúsculas.
        usuario = self.model(correo=self.normalize_email(correo).lower(), **campos)

        # Paso 3: convertir la clave en hash.
        # set_password aplica PBKDF2-SHA256 con sal, el mismo algoritmo del
        # Taller AAA. En la base de datos queda algo como "pbkdf2_sha256$...".
        usuario.set_password(password)

        # Paso 4: guardar en la base de datos (INSERT en la tabla "usuario").
        usuario.save(using=self._db)
        return usuario

    def create_user(self, correo, password=None, **campos):
        """
        Crea un usuario normal.

        Se usa en el registro de autores (HU-01) y en la creación de usuarios
        por parte del Administrador o del Comité (HU-02).
        """
        # Un usuario normal nunca es superusuario, salvo que se indique lo contrario.
        campos.setdefault("is_superuser", False)
        return self._crear(correo, password, **campos)

    def create_superuser(self, correo, password=None, **campos):
        """
        Crea el administrador principal del sistema.

        Se usa con el comando "python manage.py createsuperuser".
        """
        campos["is_superuser"] = True
        usuario = self._crear(correo, password, **campos)

        # Además de ser superusuario, recibe el rol ADMIN del sistema.
        usuario.asignar_rol(Rol.Nombre.ADMIN)
        return usuario

    def get_by_natural_key(self, correo):
        """
        Busca un usuario por su correo al iniciar sesión.

        Django la llama dentro de authenticate(). Como guardamos los correos
        en minúsculas, también pasamos a minúsculas lo que escribe la persona.
        Así, "Ana@Correo.com" y "ana@correo.com" encuentran al mismo usuario.
        """
        return self.get(correo=correo.strip().lower())


# ---------------------------------------------------------------------------
# USUARIO
# ---------------------------------------------------------------------------
class Usuario(AbstractBaseUser, PermissionsMixin):
    """
    Usuario del sistema (tabla "usuario").

    Hereda de:
      - AbstractBaseUser: aporta la clave (columna "password", que guarda el
        hash) y el último inicio de sesión (columna "last_login").
      - PermissionsMixin: aporta "is_superuser" y el sistema de permisos de Django.

    Reglas importantes:
      - Inicia sesión con el correo electrónico, no con un nombre de usuario.
      - Los usuarios no se borran: se desactivan con "activo" (HU-12).
    """

    class TipoDocumento(models.TextChoices):
        CC = "CC", "Cédula de ciudadanía"
        CE = "CE", "Cédula de extranjería"
        PASAPORTE = "PAS", "Pasaporte"

    # --- Datos de acceso -------------------------------------------------
    # La unicidad del correo se define abajo, en Meta, con el nombre
    # "uk_usuario_correo" que pide la subtarea HU-01.1.
    correo = models.EmailField("correo electrónico", max_length=254)

    # --- Datos personales ------------------------------------------------
    nombres = models.CharField("nombres", max_length=100)
    apellidos = models.CharField("apellidos", max_length=100)

    # blank=True: el documento es opcional, porque la elicitación (G04-R1)
    # solo exige nombre, afiliación y correo de los autores.
    tipo_documento = models.CharField(
        "tipo de documento", max_length=10, choices=TipoDocumento.choices, blank=True
    )
    numero_documento = models.CharField("número de documento", max_length=20, blank=True)

    # La afiliación es la universidad o institución del usuario (G04-R1).
    afiliacion = models.CharField("afiliación", max_length=200)
    pais = models.CharField("país", max_length=60)
    telefono = models.CharField("teléfono", max_length=20, blank=True)

    # Autorización de tratamiento de datos personales (Ley 1581 de 2012).
    acepta_tratamiento_datos = models.BooleanField(
        "acepta el tratamiento de datos", default=False
    )

    # --- Estado de la cuenta (borrado lógico) ----------------------------
    # activo=False significa "usuario desactivado": no puede iniciar sesión,
    # pero conserva su historial (artículos, revisiones, avales).
    activo = models.BooleanField("activo", default=True)

    # auto_now_add=True: Django pone la fecha automáticamente al crear el registro.
    fecha_registro = models.DateTimeField("fecha de registro", auto_now_add=True)

    # null=True: queda vacía mientras el usuario esté activo (HU-12).
    fecha_desactivacion = models.DateTimeField(
        "fecha de desactivación", null=True, blank=True
    )

    # --- Relaciones N:M --------------------------------------------------
    # through indica la tabla intermedia que definimos más abajo.
    # related_name permite el camino inverso: rol.usuarios.all()
    roles = models.ManyToManyField(
        Rol, through="UsuarioRol", related_name="usuarios", verbose_name="roles"
    )

    # Se escribe "core.LineaTematica" como texto porque el modelo está en otra app.
    especialidades = models.ManyToManyField(
        "core.LineaTematica",
        through="Especialidad",
        related_name="especialistas",
        blank=True,
        verbose_name="especialidades",
    )

    # --- Configuración que Django necesita -------------------------------
    # Le indica a Django que use nuestro manager (creación y búsqueda de usuarios).
    objects = UsuarioManager()

    # Campo con el que se inicia sesión.
    USERNAME_FIELD = "correo"

    # Campo que Django usa cuando necesita el correo del usuario.
    EMAIL_FIELD = "correo"

    # Campos que "createsuperuser" pide además del correo y la clave.
    REQUIRED_FIELDS = ["nombres", "apellidos", "afiliacion", "pais"]

    class Meta:
        db_table = "usuario"
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["apellidos", "nombres"]

        # Restricción de unicidad del correo: la base de datos rechaza
        # cualquier intento de registrar dos usuarios con el mismo correo.
        constraints = [
            models.UniqueConstraint(fields=["correo"], name="uk_usuario_correo")
        ]

    def __str__(self):
        return f"{self.nombres} {self.apellidos} <{self.correo}>"

    def save(self, *args, **kwargs):
        """
        Guarda el usuario asegurando que el correo quede en minúsculas.

        Así, "Ana@x.co" y "ana@x.co" se consideran el mismo usuario y la
        restricción de unicidad funciona sin importar las mayúsculas.
        """
        self.correo = self.correo.strip().lower()
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        """
        Indica si la cuenta está habilitada.

        Django (authenticate) y Simple JWT (HU-03) consultan "is_active" para
        permitir o negar el inicio de sesión. La conectamos con nuestro campo
        "activo" para que el equipo trabaje siempre con un solo campo.
        """
        return self.activo

    @property
    def is_staff(self):
        """
        Indica si el usuario puede entrar al panel de administración de Django.

        Solo pueden los administradores activos: los superusuarios o quienes
        tengan el rol ADMIN.
        """
        return self.activo and (self.is_superuser or self.tiene_rol(Rol.Nombre.ADMIN))

    def tiene_rol(self, nombre):
        """
        Indica si el usuario tiene un rol.

        Ejemplo de uso en los permisos (HU-02):
            usuario.tiene_rol(Rol.Nombre.COMITE)  ->  True o False
        """
        # exists() pregunta a la base de datos si hay al menos un registro,
        # sin cargarlos todos: es la consulta más eficiente para esta pregunta.
        return self.roles.filter(nombre=nombre).exists()

    def asignar_rol(self, nombre):
        """
        Asigna un rol al usuario. Si ya lo tiene, no lo duplica.

        Ejemplo: usuario.asignar_rol(Rol.Nombre.AUTOR)
        """
        # Paso 1: buscar el rol en la tabla "rol".
        rol = Rol.objects.get(nombre=nombre)

        # Paso 2: crear la relación en "usuario_rol" solo si no existe.
        # get_or_create busca primero; si no encuentra, crea.
        UsuarioRol.objects.get_or_create(usuario=self, rol=rol)


# ---------------------------------------------------------------------------
# TABLAS INTERMEDIAS (RELACIONES N:M)
# ---------------------------------------------------------------------------
class UsuarioRol(models.Model):
    """
    Tabla intermedia entre usuario y rol (tabla "usuario_rol").

    Cada fila dice "este usuario tiene este rol".
    """

    # on_delete=CASCADE: si se borrara el usuario, se borran sus roles.
    # (En la práctica los usuarios no se borran, se desactivan.)
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)

    # on_delete=PROTECT: impide borrar un rol mientras algún usuario lo tenga.
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT)

    class Meta:
        db_table = "usuario_rol"
        verbose_name = "rol del usuario"
        verbose_name_plural = "roles del usuario"

        # Un usuario no puede tener dos veces el mismo rol.
        # Cumple la misma función que la llave compuesta del modelo relacional.
        constraints = [
            models.UniqueConstraint(fields=["usuario", "rol"], name="uk_usuario_rol")
        ]

    def __str__(self):
        return f"{self.usuario.correo} → {self.rol}"


class Especialidad(models.Model):
    """
    Línea temática en la que se especializa un usuario (tabla "especialidad").

    Sirve para sugerir revisores adecuados para cada artículo (G03-R6).
    """

    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    linea_tematica = models.ForeignKey("core.LineaTematica", on_delete=models.PROTECT)

    class Meta:
        db_table = "especialidad"
        verbose_name = "especialidad"
        verbose_name_plural = "especialidades"

        # Un usuario no puede tener dos veces la misma especialidad.
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "linea_tematica"], name="uk_especialidad"
            )
        ]

    def __str__(self):
        return f"{self.usuario.correo} → {self.linea_tematica}"


# ---------------------------------------------------------------------------
# CÓDIGO DE RECUPERACIÓN DE CLAVE
# ---------------------------------------------------------------------------
class CodigoRecuperacion(models.Model):
    """
    PIN de recuperación de clave (tabla "codigo_recuperacion").

    Flujo de uso:
      - HU-06 (Juan Camilo): genera el PIN, guarda su hash y lo envía por correo.
      - HU-07 (Jorge): verifica el PIN y permite cambiar la clave.

    Reglas de seguridad:
      - El PIN se guarda como hash, nunca en texto plano.
      - Vence a los 15 minutos.
      - Admite un máximo de 3 intentos fallidos.
      - Solo se puede usar una vez.
    """

    # Constantes de seguridad. Están en un solo lugar para cambiarlas fácilmente.
    VIGENCIA_MINUTOS = 15
    MAX_INTENTOS = 3

    # related_name permite consultar: usuario.codigos_recuperacion.all()
    usuario = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name="codigos_recuperacion"
    )
    pin_hash = models.CharField("hash del PIN", max_length=255)
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    expira_en = models.DateTimeField("expira en")
    intentos = models.PositiveSmallIntegerField("intentos fallidos", default=0)
    usado = models.BooleanField("usado", default=False)

    class Meta:
        db_table = "codigo_recuperacion"
        verbose_name = "código de recuperación"
        verbose_name_plural = "códigos de recuperación"

        # El signo "-" ordena de forma descendente: primero los más recientes.
        ordering = ["-creado_en"]

    def __str__(self):
        return f"PIN de {self.usuario.correo} ({self.creado_en:%Y-%m-%d %H:%M})"

    def save(self, *args, **kwargs):
        """Guarda el código calculando su vencimiento si no se indicó."""
        # Si es un código nuevo sin fecha de vencimiento, vence en 15 minutos.
        if not self.expira_en:
            self.expira_en = timezone.now() + timedelta(minutes=self.VIGENCIA_MINUTOS)
        super().save(*args, **kwargs)

    def asignar_pin(self, pin):
        """
        Guarda el hash del PIN.

        Se usa en la HU-06 al generar el código. El PIN en texto plano solo
        viaja en el correo que recibe el usuario; en la base de datos queda
        únicamente su hash.
        """
        self.pin_hash = make_password(pin)

    def verificar_pin(self, pin):
        """
        Comprueba si el PIN que escribió el usuario corresponde al hash guardado.

        Se usa en la HU-07. Devuelve True si coincide y False si no.
        check_password compara en tiempo constante, igual que en el Taller AAA.
        """
        return check_password(pin, self.pin_hash)

    def esta_disponible(self):
        """
        Indica si el PIN todavía se puede usar.

        Debe cumplir las tres condiciones a la vez:
          - no se ha usado;
          - no agotó sus intentos;
          - no ha vencido.
        """
        return (
            not self.usado
            and self.intentos < self.MAX_INTENTOS
            and timezone.now() < self.expira_en
        )