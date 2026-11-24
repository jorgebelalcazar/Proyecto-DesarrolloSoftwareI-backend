"""
Serializadores del dominio de artículos.

Contenido:
  - CoautorSerializer y validar_coautores: firmantes del artículo (HU-15).
  - CrearArticuloSerializer: postular un artículo, con sus coautores (HU-14 y HU-15).
  - CoautoresArticuloSerializer: reemplazar la lista de coautores (HU-15).
  - ArticuloResumenSerializer: una fila de los listados de artículos (HU-17).
  - ArticuloCatalogoSerializer: una fila del catálogo, con su autor (HU-18).
  - SubirVersionInicialSerializer y VersionArticuloSerializer: PDF inicial (HU-16).
"""

from django.db import transaction
from rest_framework import serializers

from conferencias.models import Conferencia
from core.models import LineaTematica
from core.serializers import LineaTematicaSerializer
from usuarios.models import Usuario
from .almacenamiento import crear_url_firmada_pdf
from .excepciones import AlmacenamientoNoDisponible

TTL_URL_FIRMADA_SEGUNDOS = 900

from .excepciones import PostulacionCerrada
from .models import (
    Articulo,
    AutorArticulo,
    VersionArticulo,
    HistorialEstado,
    mensaje_plazo_vencido,
)
from .validadores_archivo import validar_pdf

# Límites de la HU-14 (criterio 3).
MAX_CARACTERES_TITULO = 200
MAX_PALABRAS_RESUMEN = 300


# ===========================================================================
# HU-15: COAUTORES O FIRMANTES
# ===========================================================================
class CoautorSerializer(serializers.ModelSerializer):
    """
    Un coautor o firmante del artículo (HU-15).

    Entrada (JSON): {"nombre_completo": "...", "afiliacion": "...", "correo": "..."}
      - Los tres son obligatorios y no pueden quedar en blanco (DRF quita
        los espacios de los extremos y responde 400 si queda vacío).
      - El correo debe tener formato válido (EmailField).

    "orden" es de solo lectura: lo asigna el servidor según la posición en
    la lista (ver validar_coautores).
    """

    class Meta:
        model = AutorArticulo
        fields = ["nombre_completo", "afiliacion", "correo", "orden"]
        read_only_fields = ["orden"]

    def validate_correo(self, valor):
        """Correo en minúsculas: "Ana@X.co" y "ana@x.co" son el mismo firmante."""
        return valor.lower()


def validar_coautores(coautores):
    """
    Valida la lista completa de coautores y les asigna su orden de firma.

    Reglas (HU-15, criterio 3):
      - Un correo no se repite en la lista. El error se marca en la fila
        repetida, para que el front-end lo muestre junto a ese firmante:
            {"coautores": [{}, {}, {"correo": ["Este correo ya está..."]}]}
      - El orden de firma es la posición en la lista: el primero es 1, el
        segundo 2... Para reordenar, el front-end envía la lista en el
        nuevo orden. Así nunca hay posiciones repetidas ni saltos.
    """
    # Paso 1: buscar correos repetidos; cada fila tiene su propio diccionario de errores.
    errores = []
    correos_vistos = set()
    for coautor in coautores:
        if coautor["correo"] in correos_vistos:
            errores.append({"correo": ["Este correo ya está en la lista de coautores."]})
        else:
            errores.append({})
            correos_vistos.add(coautor["correo"])

    if any(errores):
        raise serializers.ValidationError(errores)

    # Paso 2: el orden de firma es la posición en la lista, empezando en 1.
    for posicion, coautor in enumerate(coautores, start=1):
        coautor["orden"] = posicion

    return coautores


def guardar_coautores(articulo, coautores):
    """
    Reemplaza los coautores del artículo por la lista recibida (ya validada).

    Debe llamarse dentro de una transacción: si falla, el artículo conserva
    su lista anterior completa, nunca queda a medias.
    """
    articulo.coautores.all().delete()
    AutorArticulo.objects.bulk_create(
        AutorArticulo(articulo=articulo, **coautor) for coautor in coautores
    )

class ArticuloDetalleSerializer(serializers.ModelSerializer):
    linea_tematica = serializers.SerializerMethodField()
    palabras_clave = serializers.SerializerMethodField()
    firmantes = serializers.SerializerMethodField()
    tiene_pdf = serializers.SerializerMethodField()
    pdf_url = serializers.SerializerMethodField()
    pdf_expira_en = serializers.SerializerMethodField()

    class Meta:
        model = Articulo
        fields = [
            "id",
            "titulo",
            "estado",
            "linea_tematica",
            "fecha_postulacion",
            "resumen",
            "palabras_clave",
            "firmantes",
            "tiene_pdf",
            "pdf_url",
            "pdf_expira_en",
        ]

    def get_linea_tematica(self, obj):
        if not obj.linea_tematica:
            return None
        return {
            "id": obj.linea_tematica.id,
            "nombre": obj.linea_tematica.nombre,
        }

    def get_palabras_clave(self, obj):
        if isinstance(obj.palabras_clave, list):
            return obj.palabras_clave
        if not obj.palabras_clave:
            return []
        return [kw.strip() for kw in str(obj.palabras_clave).split(",") if kw.strip()]

    def get_firmantes(self, obj):
        firmantes = []

        # 1. Autor responsable como firmante principal
        autor = obj.autor_responsable
        if autor:
            nombre_autor = f"{getattr(autor, 'nombres', '')} {getattr(autor, 'apellidos', '')}".strip()
            firmantes.append({
                "orden": 1,
                "es_principal": True,
                "nombre_completo": nombre_autor or autor.correo,
                "correo": autor.correo,
                "afiliacion": getattr(autor, "afiliacion", "") or "",
            })

        # 2. Coautores en su orden de firma (HU-15)
        for coautor in obj.coautores.all():
            firmantes.append({
                "orden": coautor.orden + 1,
                "es_principal": False,
                "nombre_completo": coautor.nombre_completo,
                "correo": coautor.correo,
                "afiliacion": coautor.afiliacion,
            })

        return firmantes

    def _obtener_ultima_version(self, obj):
        # Aprovecha el prefetch_related("versiones") ordenado por ["articulo", "numero"]
        versiones = list(obj.versiones.all())
        return versiones[-1] if versiones else None

    def get_tiene_pdf(self, obj) -> bool:
        return self._obtener_ultima_version(obj) is not None

    def get_pdf_url(self, obj) -> str | None:
        version = self._obtener_ultima_version(obj)
        if not version or not version.ruta_pdf:
            return None
        try:
            return crear_url_firmada_pdf(version.ruta_pdf, expira_en=TTL_URL_FIRMADA_SEGUNDOS)
        except (AlmacenamientoNoDisponible, Exception):
            return None

    def get_pdf_expira_en(self, obj) -> int | None:
        return TTL_URL_FIRMADA_SEGUNDOS if self.get_tiene_pdf(obj) else None

class CoautoresArticuloSerializer(serializers.Serializer):
    """
    Lista completa de coautores de un artículo, para reemplazarla (HU-15).

    Entrada (JSON): {"coautores": [{...}, {...}]}
    Una lista vacía quita todos los coautores (artículo de un solo autor).
    """

    coautores = CoautorSerializer(many=True)

    def validate_coautores(self, coautores):
        return validar_coautores(coautores)


# ===========================================================================
# HU-14: POSTULAR UN ARTÍCULO
# ===========================================================================
class CrearArticuloSerializer(serializers.ModelSerializer):
    """
    Datos para postular un artículo (HU-14).

    Entrada (JSON):
      - titulo:         máximo 200 caracteres.
      - resumen:        máximo 300 palabras.
      - palabras_clave: separadas por comas, por ejemplo "IA, redes, salud".
      - linea_tematica: id de una de las 5 líneas oficiales
                        (ver GET /api/lineas-tematicas/).
      - coautores:      opcional (HU-15); lista de firmantes en orden,
                        cada uno con nombre_completo, afiliacion y correo.

    Lo asigna el servidor, no el cliente: la conferencia (la edición vigente),
    el autor responsable (el usuario del token), el estado (POSTULADO) y la
    fecha de postulación. Si alguien los envía, se ignoran.

    Salida: el artículo creado, con la línea temática como {id, nombre} y
    sus coautores con su orden de firma.
    """

    linea_tematica = serializers.PrimaryKeyRelatedField(
        queryset=LineaTematica.objects.all(),
        error_messages={
            "required": "Debe seleccionar una línea temática.",
            "null": "Debe seleccionar una línea temática.",
            "does_not_exist": "La línea temática seleccionada no existe.",
            "incorrect_type": "El identificador de la línea temática debe ser numérico.",
        },
    )

    # Coautores en la misma petición: se guardan junto con el artículo, en
    # una sola transacción (serializador anidado, HU-15.2).
    coautores = CoautorSerializer(many=True, required=False)

    class Meta:
        model = Articulo
        fields = [
            "id", "titulo", "resumen", "palabras_clave", "linea_tematica",
            "coautores", "conferencia", "autor_responsable", "estado",
            "fecha_postulacion",
        ]
        read_only_fields = [
            "id", "conferencia", "autor_responsable", "estado", "fecha_postulacion",
        ]
        # La columna admite 300 caracteres (modelo relacional), pero la HU-14
        # limita el título a 200: este límite es el que se valida en la API.
        extra_kwargs = {"titulo": {"max_length": MAX_CARACTERES_TITULO}}

    def validate_titulo(self, valor):
        """Título sin espacios sobrantes; no puede quedar vacío."""
        limpio = valor.strip()
        if not limpio:
            raise serializers.ValidationError("El título del artículo es obligatorio.")
        return limpio

    def validate_resumen(self, valor):
        """Resumen obligatorio de máximo 300 palabras."""
        limpio = valor.strip()
        if not limpio:
            raise serializers.ValidationError("El resumen del artículo es obligatorio.")

        # split() separa por cualquier espacio, salto de línea o tabulación.
        cantidad = len(limpio.split())
        if cantidad > MAX_PALABRAS_RESUMEN:
            raise serializers.ValidationError(
                f"El resumen no puede superar las {MAX_PALABRAS_RESUMEN} palabras "
                f"(tiene {cantidad})."
            )
        return limpio

    def validate_palabras_clave(self, valor):
        """
        Al menos una palabra clave. Se normaliza el formato:
        " IA ,redes,, salud " -> "IA, redes, salud".
        """
        etiquetas = [etiqueta.strip() for etiqueta in valor.split(",") if etiqueta.strip()]
        if not etiquetas:
            raise serializers.ValidationError("Debe ingresar al menos una palabra clave.")
        return ", ".join(etiquetas)

    def validate_coautores(self, coautores):
        """Correos sin repetir y orden de firma por posición (HU-15)."""
        return validar_coautores(coautores)

    def validate(self, datos):
        """
        Verifica que la postulación esté abierta (HU-14, criterio 1).

        La fecha límite es la de la edición vigente de la conferencia (HU-13).
        Si está abierta, deja esa edición en los datos para guardarla con el
        artículo.
        """
        conferencia = Conferencia.objects.vigente()

        # Caso 1: nadie ha configurado una edición que no haya terminado.
        if conferencia is None:
            raise PostulacionCerrada(
                "No hay una edición de la conferencia abierta para postulaciones."
            )

        # Caso 2: la edición existe, pero su plazo de postulación ya venció.
        if not conferencia.postulacion_abierta():
            raise PostulacionCerrada(mensaje_plazo_vencido(conferencia))

        datos["conferencia"] = conferencia
        return datos

    def create(self, datos):
        """
        Crea el artículo en estado POSTULADO, sus coautores y su primera fila
        en el historial.

        Usa una transacción: o se crea todo, o nada. Así nunca queda un
        artículo sin sus coautores ni sin la trazabilidad de su postulación.
        """
        # Los coautores no son una columna de "articulo": se guardan aparte.
        coautores = datos.pop("coautores", [])

        # autor_responsable llega desde la vista: serializer.save(autor_responsable=...).
        with transaction.atomic():
            articulo = Articulo.objects.create(**datos)
            guardar_coautores(articulo, coautores)
            HistorialEstado.objects.create(
                articulo=articulo,
                usuario=articulo.autor_responsable,
                estado_anterior="",
                estado_nuevo=Articulo.Estado.POSTULADO,
                observacion="Postulación inicial del artículo.",
            )
        return articulo

    def to_representation(self, instance):
        """
        Devuelve la línea temática como {"id": 1, "nombre": "..."}, el mismo
        formato del directorio (HU-08) y de GET /api/lineas-tematicas/.
        """
        datos = super().to_representation(instance)
        datos["linea_tematica"] = LineaTematicaSerializer(instance.linea_tematica).data
        return datos


# ===========================================================================
# HU-17: LISTADOS DE ARTÍCULOS
# ===========================================================================
class ArticuloResumenSerializer(serializers.ModelSerializer):
    """
    Datos resumidos de un artículo, para una fila de tabla (HU-17).

    Es lo que muestra la tabla "Mis artículos": título, línea temática,
    estado y fecha. No incluye el resumen completo ni los coautores, que se
    consultan en el detalle (HU-19): así la respuesta es liviana y rápida.

    Formato de salida:
      {
        "id": 7, "titulo": "...",
        "linea_tematica": {"id": 1, "nombre": "Sistemas Inteligentes"},
        "estado": "POSTULADO", "estado_nombre": "Postulado",
        "conferencia": 1, "fecha_postulacion": "2027-02-10T15:30:00-05:00"
      }
    """

    # Línea temática con id y nombre, el formato de toda la API.
    linea_tematica = LineaTematicaSerializer(read_only=True)

    # Nombre del estado para mostrarlo; "estado" (el código) sirve para el color del badge.
    estado_nombre = serializers.CharField(source="get_estado_display", read_only=True)

    class Meta:
        model = Articulo
        fields = [
            "id", "titulo", "linea_tematica", "estado", "estado_nombre",
            "conferencia", "fecha_postulacion",
        ]
        read_only_fields = fields


class AutorResponsableSerializer(serializers.ModelSerializer):
    """
    Datos del autor responsable en el catálogo (HU-18).

    Solo lo ven el Comité y el Administrador, que ya ven los correos en el
    directorio de usuarios (HU-08). No incluye documento ni teléfono.
    """

    class Meta:
        model = Usuario
        fields = ["id", "nombres", "apellidos", "correo"]
        read_only_fields = fields


class ArticuloCatalogoSerializer(ArticuloResumenSerializer):
    """
    Una fila del catálogo de artículos para el Comité y el Administrador (HU-18).

    Hereda las columnas de "Mis artículos" (HU-17) y agrega el autor
    responsable, que en el catálogo sí hace falta porque hay artículos de
    todos los autores.
    """

    autor_responsable = AutorResponsableSerializer(read_only=True)

    class Meta(ArticuloResumenSerializer.Meta):
        fields = ArticuloResumenSerializer.Meta.fields + ["autor_responsable"]
        read_only_fields = fields


# ===========================================================================
# HU-16: PDF INICIAL DEL ARTÍCULO
# ===========================================================================
class SubirVersionInicialSerializer(serializers.Serializer):
    """
    Archivo PDF que envía el autor (HU-16.2).

    Entrada (multipart/form-data): un campo "archivo" con el PDF.
    Los errores quedan en ese campo, igual que en el resto de la API:
        {"archivo": ["El archivo debe tener extensión .pdf."]}
    """

    archivo = serializers.FileField(
        error_messages={
            "required": "Debe adjuntar el PDF del artículo.",
            "empty": "El archivo está vacío.",
        },
    )

    def validate_archivo(self, archivo):
        """Extensión .pdf, máximo 10 MB y firma %PDF (validadores_archivo.py)."""
        return validar_pdf(archivo)


class VersionArticuloSerializer(serializers.ModelSerializer):

    tipo_nombre = serializers.CharField(source="get_tipo_display", read_only=True)

    class Meta:
        model = VersionArticulo
        fields = ["id", "articulo", "tipo", "tipo_nombre", "numero", "fecha_subida"]
        read_only_fields = fields