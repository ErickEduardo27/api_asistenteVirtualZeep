# Asistente Virtual API

API completa para un asistente virtual con capacidades de RAG (Retrieval-Augmented Generation), streaming de respuestas, y gestión de documentos.

## Características

- ✅ Autenticación JWT
- ✅ Rate limiting
- ✅ Logging estructurado
- ✅ Chat con streaming (SSE)
- ✅ RAG (Retrieval-Augmented Generation)
- ✅ Gestión de documentos (PDF, DOCX, TXT)
- ✅ Vector database con pgvector
- ✅ Object storage (MinIO/S3)

## Estructura del Proyecto

```
api_asistenteVirtualZeep/
├── app/
│   ├── __init__.py
│   ├── config.py              # Configuración y variables de entorno
│   ├── database.py            # Configuración de base de datos
│   ├── models/                # Modelos SQLAlchemy
│   │   ├── user.py
│   │   ├── conversation.py
│   │   ├── document.py
│   │   └── embedding.py
│   ├── schemas/               # Schemas Pydantic
│   │   ├── auth.py
│   │   ├── chat.py
│   │   └── document.py
│   ├── services/              # Lógica de negocio
│   │   ├── auth.py
│   │   ├── llm.py
│   │   ├── rag.py
│   │   ├── chat_orchestrator.py
│   │   ├── document_processor.py
│   │   └── storage.py
│   ├── routers/               # Endpoints de la API
│   │   ├── auth.py
│   │   ├── chat.py
│   │   ├── documents.py
│   │   └── health.py
│   └── middleware/            # Middleware
│       ├── rate_limit.py
│       └── logging.py
├── alembic/                   # Migraciones de base de datos
├── main.py                    # Punto de entrada
├── requirements.txt
└── .env.example
```

## Instalación

### Opción 1: Con Docker Compose (Recomendado)

1. Clonar el repositorio
2. Configurar variables de entorno:
```bash
cp .env.example .env
# Editar .env con tus configuraciones
```

3. Iniciar servicios (PostgreSQL + MinIO):
```bash
docker-compose up -d
```

4. Crear entorno virtual e instalar dependencias:
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

5. Inicializar base de datos:
```bash
python scripts/init_db.py
```

6. Iniciar el servidor:
```bash
uvicorn main:app --reload
```

### Opción 2: Instalación Manual

1. Clonar el repositorio
2. Crear un entorno virtual:
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. Instalar dependencias:
```bash
pip install -r requirements.txt
```

4. Configurar variables de entorno:
```bash
cp .env.example .env
# Editar .env con tus configuraciones
```

5. Configurar PostgreSQL con pgvector:
```sql
CREATE DATABASE asistente_virtual;
CREATE EXTENSION vector;
```

6. Inicializar base de datos:
```bash
python scripts/init_db.py
```

7. Ejecutar migraciones (opcional, las tablas se crean automáticamente):
```bash
alembic upgrade head
```

8. Iniciar el servidor:
```bash
uvicorn main:app --reload
```

## Endpoints

### Autenticación
- `POST /api/v1/auth/register` - Registro de usuario
- `POST /api/v1/auth/login` - Login (retorna JWT)
- `GET /api/v1/auth/me` - Información del usuario actual

### Chat
- `POST /api/v1/chat/stream` - Chat con streaming (SSE)

### Documentos
- `POST /api/v1/documents/upload` - Subir documento
- `POST /api/v1/documents/{id}/ingest` - Procesar documento (chunking + embeddings)
- `GET /api/v1/documents/` - Listar documentos del usuario

### Health
- `GET /health` - Health check básico
- `GET /health/db` - Health check de base de datos

## Uso

### 1. Registrar un usuario
```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "username": "user",
    "password": "password123"
  }'
```

### 2. Login
```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=user&password=password123"
```

### 3. Subir un documento
```bash
curl -X POST "http://localhost:8000/api/v1/documents/upload" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@document.pdf"
```

### 4. Procesar documento
```bash
curl -X POST "http://localhost:8000/api/v1/documents/1/ingest" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 5. Chat con streaming
```bash
curl -X POST "http://localhost:8000/api/v1/chat/stream" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "¿Qué información hay en el documento?",
    "use_rag": true
  }'
```

## Configuración

### Variables de Entorno Importantes

- `DATABASE_URL`: URL de conexión a PostgreSQL
- `SECRET_KEY`: Clave secreta para JWT (cambiar en producción)
- `OPENAI_API_KEY`: API key de OpenAI
- `MINIO_*`: Configuración de MinIO (opcional, usa almacenamiento local si no está configurado)

## Notas

- En producción, usar Alembic para migraciones en lugar de crear tablas automáticamente
- Configurar CORS apropiadamente
- Usar un secret key fuerte para JWT
- Configurar MinIO o S3 para almacenamiento de documentos en producción

