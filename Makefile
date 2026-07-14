.PHONY: install migrate run worker test lint fmt seed

install:      ## Instalar dependencias de desarrollo
	pip install -r requirements/dev.txt

migrate:      ## Aplicar migraciones
	python manage.py migrate

run:          ## Servidor de desarrollo
	python manage.py runserver 0.0.0.0:8000

worker:       ## Worker + beat de Celery
	celery -A config worker -B -l info

test:         ## Ejecutar pruebas con cobertura
	pytest --cov=apps

lint:         ## Ruff + bandit
	ruff check . && bandit -r apps config -ll

fmt:          ## Formatear con ruff
	ruff format . && ruff check --fix .

seed:         ## Cargar datos base (secciones, servicios, roles)
	python manage.py seed_inicial
