FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.115,<0.116" "uvicorn[standard]>=0.32,<0.35"
COPY app.py /app/app.py
COPY static /app/static
EXPOSE 8088
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8088"]
