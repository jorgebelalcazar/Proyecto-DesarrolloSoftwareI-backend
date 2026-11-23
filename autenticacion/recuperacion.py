"""
Servicio de recuperación de clave (HU-06 y HU-07).

Flujo completo de la recuperación:
  1. HU-06 (este archivo): el usuario escribe su correo; si tiene una cuenta
     activa, se genera un PIN de 6 dígitos, se guarda su hash y se le envía
     por correo.
  2. HU-07 (confirmar_recuperacion): el usuario escribe su correo, el PIN y
     su nueva clave; si el PIN es válido, se cambia la clave y el PIN queda usado.

La lógica vive aquí, y no en la vista, para que la vista solo reciba la
petición y responda, y para poder probar estas reglas por separado.
"""

import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from usuarios.models import CodigoRecuperacion, Usuario

logger = logging.getLogger(__name__)

# Tiempo mínimo entre dos solicitudes del mismo usuario, en segundos.
# Evita que alguien llene de correos la bandeja de otra persona.
ESPERA_ENTRE_SOLICITUDES_SEGUNDOS = 60


class CorreoNoEnviado(Exception):
    """El servidor de correo no aceptó el mensaje. La vista lo convierte en 503."""


def generar_pin():
    """
    Genera un PIN aleatorio de 6 dígitos, por ejemplo "048213".

    Usa el módulo "secrets", pensado para seguridad: sus números no se pueden
    predecir. El módulo "random" no sirve para esto, porque quien vea varios
    resultados puede llegar a adivinar los siguientes.

    El formato "06d" completa con ceros a la izquierda: 48213 -> "048213".
    """
    return f"{secrets.randbelow(10**6):06d}"


def enviar_correo_pin(usuario, pin):
    """
    Envía el correo con el PIN, en texto plano y en HTML.

    Las plantillas están en autenticacion/templates/autenticacion/.
    Lanza CorreoNoEnviado si el servidor de correo falla.
    """
    # Datos que se reemplazan en las plantillas.
    contexto = {
        "nombres": usuario.nombres,
        "pin": pin,
        "vigencia_minutos": CodigoRecuperacion.VIGENCIA_MINUTOS,
    }

    try:
        send_mail(
            subject="Nexo · Código para recuperar tu clave",
            message=render_to_string("autenticacion/correo_pin.txt", contexto),
            html_message=render_to_string("autenticacion/correo_pin.html", contexto),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[usuario.correo],
        )
    except OSError as error:
        # OSError cubre los fallos de red y del servidor SMTP (smtplib los
        # hereda). Se registra en la consola del servidor para diagnosticarlo.
        logger.error("No fue posible enviar el PIN a %s: %s", usuario.correo, error)
        raise CorreoNoEnviado() from error


def solicitar_recuperacion(correo):
    """
    Genera y envía un PIN de recuperación si el correo tiene una cuenta activa.

    No devuelve nada a propósito: la vista responde SIEMPRE el mismo mensaje,
    exista o no el correo. Si respondiera "ese correo no está registrado",
    un atacante podría averiguar qué correos tienen cuenta (enumeración de usuarios).

    Casos en los que NO se envía nada, en silencio:
      - el correo no está registrado;
      - la cuenta está desactivada (HU-12);
      - ya se solicitó un PIN hace menos de ESPERA_ENTRE_SOLICITUDES_SEGUNDOS.

    Lanza CorreoNoEnviado si el servidor de correo falla.
    """
    # Paso 1: buscar una cuenta ACTIVA con ese correo, sin importar mayúsculas.
    usuario = Usuario.objects.filter(correo__iexact=correo.strip(), activo=True).first()
    if usuario is None:
        return

    # Paso 2: limitar la frecuencia de las solicitudes.
    # first() trae el código más reciente, porque el modelo ordena por "-creado_en".
    ultimo = usuario.codigos_recuperacion.first()
    limite = timezone.now() - timedelta(seconds=ESPERA_ENTRE_SOLICITUDES_SEGUNDOS)
    if ultimo is not None and ultimo.creado_en > limite:
        return

    pin = generar_pin()

    # Pasos 3 a 5 en una transacción: si el correo falla, se deshace todo y
    # no queda guardado un PIN que el usuario nunca recibió.
    with transaction.atomic():
        # Paso 3: invalidar los PIN anteriores que no se usaron.
        # Así solo sirve el último PIN enviado.
        usuario.codigos_recuperacion.filter(usado=False).update(usado=True)

        # Paso 4: guardar el nuevo código. Solo se guarda el hash del PIN;
        # la fecha de vencimiento (15 minutos) la calcula el modelo al guardar.
        codigo = CodigoRecuperacion(usuario=usuario)
        codigo.asignar_pin(pin)
        codigo.save()

        # Paso 5: enviar el PIN. Es la única copia en texto plano.
        enviar_correo_pin(usuario, pin)

def confirmar_recuperacion(correo, pin, clave_nueva):
    """
    Verifica el PIN y, si es válido, cambia la clave del usuario (HU-07).

    Devuelve True si la clave se cambió y False si no. Ante cualquier fallo
    la vista responde el MISMO mensaje, para no revelar si el correo existe
    ni por qué falló el PIN.

    El PIN se rechaza si:
      - el correo no corresponde a una cuenta activa;
      - no hay un código disponible: no se solicitó, ya se usó, venció
        (15 minutos) o agotó sus 3 intentos;
      - el PIN no coincide con el hash guardado. En este caso se suma un
        intento: al tercer error el código queda inutilizable.
    """
    # Paso 1: buscar una cuenta ACTIVA con ese correo.
    usuario = Usuario.objects.filter(correo__iexact=correo.strip(), activo=True).first()
    if usuario is None:
        # Se calcula un hash igual, para que la respuesta tarde lo mismo que
        # cuando la cuenta existe y no revele qué correos están registrados.
        make_password(pin)
        return False

    with transaction.atomic():
        # Paso 2: tomar el código más reciente que no se ha usado.
        # select_for_update bloquea la fila hasta terminar la transacción:
        # si llegan dos peticiones al mismo tiempo con el mismo PIN, la
        # segunda espera y encuentra el código ya usado. Así un PIN no se
        # puede usar dos veces.
        codigo = (
            CodigoRecuperacion.objects.select_for_update()
            .filter(usuario=usuario, usado=False)
            .order_by("-creado_en")
            .first()
        )

        # Paso 3: el código debe existir y estar disponible (vigente y con intentos).
        if codigo is None or not codigo.esta_disponible():
            return False

        # Paso 4: comparar el PIN con el hash guardado.
        if not codigo.verificar_pin(pin):
            # Se suma el intento fallido y se guarda; el return confirma la
            # transacción, así el intento queda registrado aunque el PIN falle.
            codigo.intentos += 1
            codigo.save(update_fields=["intentos"])
            return False

        # Paso 5 (HU-07.2): cambiar la clave y marcar el PIN como usado.
        # Ambos cambios ocurren en la misma transacción: o se hacen los dos,
        # o ninguno. Nunca queda la clave cambiada con el PIN todavía disponible.
        usuario.set_password(clave_nueva)
        usuario.save(update_fields=["password"])
        codigo.usado = True
        codigo.save(update_fields=["usado"])

    return True