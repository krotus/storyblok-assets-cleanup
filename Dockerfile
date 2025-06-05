# Usar la imagen base de Python 3.9 desde Docker Hub
FROM python:3.9-slim

# Establecer el directorio de trabajo en el contenedor
WORKDIR /app

# Copiar el directorio actual (donde está el Dockerfile) al contenedor en /app
COPY . /app

# Instalar las dependencias del script
RUN pip install --no-cache-dir -r requirements.txt

# Establecer el comando base que se ejecutará cuando inicies el contenedor
ENTRYPOINT [ "python", "./storyblok_assets_cleanup.py" ]
