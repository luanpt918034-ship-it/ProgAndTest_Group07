FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=5000 SECRET_KEY=change-me
EXPOSE 5000
CMD python seed.py && gunicorn -b 0.0.0.0:5000 "app:create_app()"
