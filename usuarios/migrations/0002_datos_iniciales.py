"""
Migración de datos: carga la información que el sistema necesita para funcionar.

  - Los 3 roles del sistema: ADMIN, COMITE y AUTOR.
  - Las 5 líneas temáticas definidas en el enunciado del proyecto.

Gracias a esta migración, cualquier integrante del equipo que ejecute
"python manage.py migrate" obtiene exactamente los mismos datos iniciales,
sin cargarlos a mano.
"""

from django.db import migrations

ROLES = ["ADMIN", "COMITE", "AUTOR"]

LINEAS_TEMATICAS = [
    "Sistemas Inteligentes",
    "Tecnologías en Informática",
    "Educación en Informática",
    "Sistemas de Software",
    "Software en la práctica",
]


def crear_datos(apps, schema_editor):
    """
    Inserta los roles y las líneas temáticas.

    Se ejecuta al aplicar la migración (python manage.py migrate).
    """
    # apps.get_model obtiene la versión del modelo que existía en ESTA migración.
    # Nunca se importa el modelo directamente, porque el código actual del
    # modelo puede cambiar en el futuro y romper migraciones antiguas.
    Rol = apps.get_model("usuarios", "Rol")
    LineaTematica = apps.get_model("core", "LineaTematica")

    # get_or_create evita duplicados si la migración se ejecuta más de una vez.
    for nombre in ROLES:
        Rol.objects.get_or_create(nombre=nombre)
    for nombre in LINEAS_TEMATICAS:
        LineaTematica.objects.get_or_create(nombre=nombre)


def borrar_datos(apps, schema_editor):
    """
    Deshace la migración: elimina los datos que insertó crear_datos.

    Se ejecuta si alguien revierte la migración con "migrate usuarios 0001".
    """
    apps.get_model("usuarios", "Rol").objects.filter(nombre__in=ROLES).delete()
    apps.get_model("core", "LineaTematica").objects.filter(
        nombre__in=LINEAS_TEMATICAS
    ).delete()


class Migration(migrations.Migration):
    # Esta migración se ejecuta DESPUÉS de crear las tablas de ambas apps.
    dependencies = [
        ("usuarios", "0001_initial"),
        ("core", "0001_initial"),
    ]

    # RunPython ejecuta código Python dentro de la migración.
    # Recibe la función para aplicarla y la función para revertirla.
    operations = [migrations.RunPython(crear_datos, borrar_datos)]