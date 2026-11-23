# Nexo — Back-end

API REST del sistema de gestión científica de conferencias del proyecto Nexo
(Desarrollo de Software I, Universidad del Valle).

**Tecnologías:** Python, Django, Django REST Framework, Simple JWT y PostgreSQL (Supabase).

## Inicio rápido

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Copia .env.example como .env y completa los valores
python manage.py migrate
python manage.py test
python manage.py runserver
```

La API queda en `http://127.0.0.1:8000/`. Para comprobar que funciona: `GET /api/salud/`.

## Módulos

| App | Responsabilidad |
|---|---|
| `core` | Catálogos compartidos (líneas temáticas), paginación y prueba de salud |
| `usuarios` | Registro, gestión de cuentas, roles y permisos por rol activo |
| `autenticacion` | Inicio de sesión con JWT y reCAPTCHA, sesión y recuperación de clave |

## Cómo contribuir

Antes de crear tu primera rama, lee la **[guía de contribución](CONTRIBUTING.md)**:
flujo de Git, estilo del código, permisos por rol, pruebas y Pull Requests.
