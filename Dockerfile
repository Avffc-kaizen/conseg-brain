FROM python:3.9-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD gunicorn main:app --bind 0.0.0.0:$PORT
