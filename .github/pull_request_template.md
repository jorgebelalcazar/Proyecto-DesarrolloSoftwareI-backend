## Resumen
<!-- Qué hace este Pull Request y qué subtareas de Jira cubre (HU-XX.Y). -->

## Contrato de la API
<!-- Para cada endpoint nuevo o modificado: método, ruta, encabezados, cuerpo y respuestas.
     Borra esta sección si no hay cambios en la API. -->

**MÉTODO** `/api/...`

Encabezados: `Authorization: Bearer <access>`, `X-Rol-Activo: ...`

| Campo | Obligatorio | Notas |
|---|---|---|
| | | |

Respuestas: `200`/`201` ..., `400` ..., `401` ..., `403` ...

## Decisiones de diseño
<!-- Por qué se resolvió así: reglas de negocio, seguridad, permisos por rol. -->

## ⚠️ Impacto para el equipo
<!-- Migraciones, dependencias o variables de entorno nuevas; cambios que afecten
     el trabajo de otros. Escribe "Ninguno" si no aplica. -->

## Cómo probar
1. `python manage.py test` → N pruebas en OK
2. <!-- Prueba manual: ruta, rol y resultado esperado -->

## Checklist
- [ ] Rama y commits con el formato de la guía de contribución
- [ ] Código documentado en español
- [ ] Pruebas del caso exitoso, 401, 403 y 400
- [ ] `python manage.py test` en OK
- [ ] Migraciones, `requirements.txt` y `.env.example` actualizados si aplica
- [ ] Sin credenciales en el repositorio
