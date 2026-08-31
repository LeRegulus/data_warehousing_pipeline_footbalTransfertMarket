# Image unique utilisée à la fois pour l'ETL et le dashboard
# (la commande réelle est fournie par docker-compose.yml, pas ici)
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY sql/ ./sql/

# data/ est monté en volume par docker-compose.yml (pas copié dans l'image :
# les CSV sources sont volumineux et ne doivent pas gonfler l'image)

EXPOSE 8501
