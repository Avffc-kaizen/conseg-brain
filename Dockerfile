FROM python:3.9-slim

WORKDIR /app

# Instala dependências e limpa cache para ficar leve
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Garante que o Python veja as saídas de print (logs)
ENV PYTHONUNBUFFERED=1

# Comando direto: usa o main.py que configuramos acima
CMD ["python", "main.py"]