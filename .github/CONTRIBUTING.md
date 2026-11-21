# Guía de contribución — Back-end del proyecto Nexo

Esta guía reúne las reglas que sigue todo el código del back-end. Su objetivo es que cualquier integrante pueda leer, probar y modificar el trabajo de otro sin sorpresas.

**Léela antes de crear tu primera rama.** Cada Pull Request se revisa contra la [lista de verificación](#10-lista-de-verificación-antes-del-pull-request) del final.

## Contenido

1. [Preparar el entorno](#1-preparar-el-entorno)
2. [Flujo de trabajo con Git](#2-flujo-de-trabajo-con-git)
3. [Estructura del proyecto](#3-estructura-del-proyecto)
4. [Estilo del código](#4-estilo-del-código)
5. [Seguridad y permisos por rol](#5-seguridad-y-permisos-por-rol)
6. [Convenciones de la API](#6-convenciones-de-la-api)
7. [Pruebas automáticas](#7-pruebas-automáticas)
8. [Base de datos y migraciones](#8-base-de-datos-y-migraciones)
9. [Pull Requests y revisión](#9-pull-requests-y-revisión)
10. [Lista de verificación antes del Pull Request](#10-lista-de-verificación-antes-del-pull-request)

---

## 1. Preparar el entorno

Requisitos: Python 3.13 o 3.14 y Git.

```powershell
git clone https://github.com/jorgebelalcazar/Proyecto-DesarrolloSoftwareI-backend.git
cd Proyecto-DesarrolloSoftwareI-backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copia `.env.example` como `.env` y completa los valores. Pide la cadena de conexión de la base de datos por mensaje privado.

```powershell
python manage.py migrate
python manage.py test
python manage.py runserver
```

Todas las pruebas deben terminar en `OK` antes de empezar a trabajar.

### Problemas frecuentes

| Problema | Solución |
|---|---|
| `Activate.ps1` no se puede ejecutar | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `could not translate host name` | Usa la cadena del **Session pooler** de Supabase, no la conexión directa (IPv6) |
| `git push` o `pip install` fallan por la red de la universidad | Repite el comando o usa otra red; la red institucional tiene cortes |

---

## 2. Flujo de trabajo con Git

`main` está protegida: **nadie sube cambios directamente**. Todo entra por un Pull Request aprobado por otra persona.

### Crear una rama

Primero se actualiza `main` y **después** se crea la rama:

```powershell
git switch main
git pull origin main
git switch -c JIB/HU-12-desactivar-usuario
```

Formato del nombre: **`INICIALES/HU-XX-descripcion-corta`**. Si quieres, agrega la clave de Jira: `CDR/HU-08-SCRUM-97-listar-usuarios`.

| Integrante | Iniciales |
|---|---|
| Jorge Iván Belalcázar | `JIB` |
| Jefferson Steven Trullot | `JST` |
| Carlos Enrique Delgado | `CDR` |

### Mantener la rama al día

Si `main` cambió mientras trabajabas, trae esos cambios a tu rama antes del Pull Request:

```powershell
git switch main
git pull origin main
git switch tu-rama
git merge main
```

### Mensajes de commit

Formato: **`tipo(alcance): descripción en español (HU-XX.Y)`**

| Tipo | Cuándo |
|---|---|
| `feat` | Funcionalidad nueva |
| `fix` | Corrección de un error |
| `refactor` | Cambio interno sin alterar el comportamiento |
| `test` | Solo pruebas |
| `perf` | Mejora de rendimiento |
| `docs` | Documentación |
| `chore` | Configuración, dependencias, tareas de mantenimiento |

El alcance es la app afectada: `core`, `usuarios`, `autenticacion` o `config`.

```text
feat(usuarios): endpoint PATCH /api/usuarios/mi-perfil/ (HU-10.1)
fix(autenticacion): rechazar PIN vencido al confirmar la clave (HU-07.1)
```

Evita mensajes como `wip`, `cambios` o `arreglos`: el historial es parte de la evidencia del proyecto. Si es la primera vez que usas Git en tu equipo, configura tu nombre y correo **antes** del primer commit:

```powershell
git config --global user.name "Tu Nombre"
git config --global user.email "tu-correo@correounivalle.edu.co"
```

---

## 3. Estructura del proyecto

| App | Responsabilidad | Ejemplos |
|---|---|---|
| `config` | Configuración global y rutas principales | `settings.py`, `urls.py` |
| `core` | Lo que comparten varios módulos | Líneas temáticas, paginación, `/api/salud/` |
| `usuarios` | Gestión de cuentas y roles | Registro, crear, listar, editar y desactivar usuarios; permisos por rol |
| `autenticacion` | Acceso al sistema | Login, tokens, logout, CAPTCHA, recuperación de clave |

Archivos de cada app:

| Archivo | Contenido |
|---|---|
| `models.py` | Tablas de la base de datos |
| `serializers.py` | Validación y formato JSON |
| `views.py` | Endpoints |
| `urls.py` | Rutas de la app (con `app_name`) |
| `permisos.py` | Permisos de DRF |
| `test_<tema>.py` | Pruebas de una historia, por ejemplo `test_listar_usuarios.py` |

Las rutas se agregan en el `urls.py` de la app, no en `config/urls.py`.

---

## 4. Estilo del código

### Documentación en español

Todo módulo, clase y función lleva su comentario de documentación (docstring) en español. Los endpoints documentan siempre lo mismo:

```python
class ListarUsuariosView(generics.ListAPIView):
    """
    GET /api/usuarios/   (HU-08)

    Qué hace, en una o dos frases.

    Requiere:
      - Token JWT en el encabezado Authorization.

    Respuestas:
      - 200 OK:           qué devuelve.
      - 401 Unauthorized: no se envió un token válido.
      - 403 Forbidden:    el rol activo no tiene permiso.
    """
```

Cuando una función tiene varios pasos, se numeran en comentarios: `# Paso 1: ...`, `# Paso 2: ...`. Los comentarios explican **por qué** se hace algo, no repiten lo que ya dice el código.

### Nombres y formato

- Variables, funciones, clases y campos en español: `obtener_rol_activo`, `fecha_registro`.
  Se exceptúan los nombres que exige Django o DRF (`get_queryset`, `has_permission`) y los fijados en Jira (`IsAdminOrComitePermission`).
- Los nombres de las tablas (`db_table`) coinciden con el modelo relacional del Sprint 0.
- Imports en tres bloques: librería estándar, librerías externas y apps del proyecto.
- Sin espacios al final de las líneas y con un salto de línea al final de cada archivo.

---

## 5. Seguridad y permisos por rol

### Permisos por defecto

`settings.py` aplica a **todos** los endpoints:

- `IsAuthenticated`: exige un token válido.
- `usuarios.permisos.ValidarRolActivo`: si llega el encabezado `X-Rol-Activo`, el usuario debe tener ese rol.

> **No escribas `permission_classes = [IsAuthenticated]`.** Reemplaza los permisos por defecto y desactiva la validación del rol activo. Si el endpoint solo necesita un usuario autenticado, no declares `permission_classes`.

### Endpoints restringidos por rol

```python
from usuarios.models import Rol
from usuarios.permisos import RequiereRolActivo


class CrearArticuloView(generics.CreateAPIView):
    permission_classes = [RequiereRolActivo]
    roles_permitidos = [Rol.Nombre.AUTOR]
```

- El rol activo se obtiene **solo** con `obtener_rol_activo(request)`. No leas el encabezado directamente.
- El encabezado se llama **`X-Rol-Activo`** y sus valores son `ADMIN`, `COMITE` o `AUTOR`.
- Si un usuario tiene un solo rol, el encabezado es opcional.

### Endpoints públicos

Solo el registro, el login y `/api/salud/` son públicos. Un endpoint público declara `permission_classes = [AllowAny]` y explica en un comentario por qué lo es.

### Reglas de seguridad

| Regla | Cómo se aplica |
|---|---|
| Validar en el servidor | Toda regla del formulario se valida también en el serializador |
| Lista cerrada de campos | Los serializadores declaran `fields`; nunca `"__all__"` |
| Nunca devolver secretos | Claves y PIN con `write_only=True`; nunca se exponen documentos ni hashes |
| Mínimo privilegio | Cada rol recibe solo los datos que necesita |
| Mensajes que no revelan información | El login responde igual si el correo no existe o la clave es incorrecta |
| Fallar cerrado | Si un servicio externo no responde o un permiso está mal configurado, se niega el acceso |
| Operaciones completas | Lo que cambia varias tablas va dentro de `transaction.atomic()` |
| Borrado lógico | Usuarios y artículos no se eliminan: se desactivan |
| Secretos fuera del código | Claves y contraseñas solo en `.env`; si agregas una variable, actualiza `.env.example` |

---

## 6. Convenciones de la API

| Situación | Código |
|---|---|
| Consulta exitosa | `200 OK` |
| Recurso creado | `201 Created` |
| Datos inválidos | `400 Bad Request`, con los errores por campo |
| Sin token o token inválido | `401 Unauthorized` |
| Autenticado, pero sin permiso | `403 Forbidden` |
| Servicio externo caído | `503 Service Unavailable` |

- Los errores de validación llegan por campo: `{"correo": ["Ya existe una cuenta..."]}`.
- Todo listado usa la paginación compartida, `core.paginacion.PaginacionEstandar`: `{count, next, previous, results}`.
- Los roles se devuelven por su código: `["AUTOR", "COMITE"]`.
- Las líneas temáticas se devuelven como `{"id": 1, "nombre": "..."}`, igual que `GET /api/lineas-tematicas/`.
- Los campos de texto opcionales se envían vacíos (`""`) u omitidos, nunca como `null`.
- Cada endpoint nuevo se comunica al responsable del front-end con su **contrato**: método, ruta, encabezados, cuerpo y respuestas. Ese contrato va también en el Pull Request.

---

## 7. Pruebas automáticas

**Toda historia de usuario llega con sus pruebas.** Un Pull Request sin pruebas no se aprueba.

```powershell
python manage.py test
```

- Las pruebas usan SQLite en memoria: son rápidas, no necesitan internet y no tocan Supabase.
- Cada prueba sigue el orden **Preparar → Ejecutar → Verificar**, marcado con comentarios.
- Los nombres describen el caso: `test_autor_recibe_403`, `test_correo_duplicado_devuelve_400`.
- Los servicios externos (Google reCAPTCHA, correo) se simulan con `unittest.mock.patch`.
- Usa valores explícitos (`Rol.Nombre.COMITE`, `"ana@correo.com"`), no valores calculados que oculten qué se prueba.

Cada endpoint se prueba, como mínimo, en estos casos:

| Caso | Ejemplo |
|---|---|
| Camino exitoso | `201` con los datos esperados |
| Sin autenticación | `401` |
| Rol sin permiso | `403` |
| Datos inválidos | `400` con el error en el campo correcto |
| Reglas de negocio | Correo duplicado, rol activo ajeno, datos que no debe ver otro rol |

---

## 8. Base de datos y migraciones

- Si cambias un modelo, ejecuta `python manage.py makemigrations` y **sube la migración** en el mismo Pull Request.
- No modifiques una migración que ya está en `main`: crea una nueva.
- Los datos iniciales (roles, líneas temáticas) se cargan con migraciones de datos que usan `apps.get_model`.
- Las reglas que la base de datos puede garantizar (unicidad, llaves foráneas) se declaran en el modelo; las demás van en los serializadores o en la lógica de las vistas.
- Si una migración obliga al equipo a hacer algo (por ejemplo, `migrate` o reiniciar tablas), indícalo en el Pull Request en la sección **Impacto para el equipo**.

### Dependencias nuevas

```powershell
pip install nombre-del-paquete
pip freeze | Out-File -Encoding utf8 requirements.txt
```

Usa `Out-File -Encoding utf8`; con `>` PowerShell guarda el archivo en una codificación que falla al desplegar.

---

## 9. Pull Requests y revisión

1. Sube tu rama: `git push -u origin tu-rama`.
2. Abre el Pull Request. GitHub carga la plantilla automáticamente; complétala.
3. Pide la revisión a **otra persona**: nadie aprueba su propio Pull Request.
4. Si la revisión propone cambios, se agregan como commits **encima** de los tuyos, en tu misma rama, avisándote antes. Así tu trabajo conserva tu autoría.
5. Cuando esté aprobado y sin conversaciones pendientes, únelo con **"Crear una confirmación de fusión"** (no "Aplastar" ni "Rebase").
6. Borra la rama en GitHub y actualiza tu `main`.
7. Mueve tus subtareas a **Finalizada** en Jira.

---

## 10. Lista de verificación antes del Pull Request

- [ ] La rama sale del `main` actualizado y tiene el formato `INICIALES/HU-XX-descripcion`
- [ ] Los commits siguen el formato `tipo(alcance): descripción (HU-XX.Y)`
- [ ] Todo el código nuevo está documentado en español
- [ ] No hay `permission_classes = [IsAuthenticated]`; los endpoints por rol usan `RequiereRolActivo`
- [ ] Los serializadores tienen lista cerrada de campos y no exponen secretos
- [ ] Hay pruebas para el caso exitoso, `401`, `403` y `400`
- [ ] `python manage.py test` termina en `OK`
- [ ] Las migraciones nuevas están incluidas
- [ ] `requirements.txt` y `.env.example` están actualizados si hubo cambios
- [ ] El `.env` **no** aparece en el Pull Request
- [ ] La descripción incluye el contrato de la API y el impacto para el equipo
