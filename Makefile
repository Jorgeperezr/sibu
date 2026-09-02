.PHONY: install migrate run up worker perfil demo seed setup test lint fmt help

help:         ## Mostrar esta ayuda
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:      ## Instalar dependencias de desarrollo
	pip install -r requirements/dev.txt

migrate:      ## Aplicar migraciones
	python manage.py migrate

run:          ## Servidor de desarrollo (sin derivar variables de Codespaces)
	python manage.py runserver 0.0.0.0:8000

up:           ## Arranque completo: variables + BD + migraciones + servidor
	bash scripts/dev.sh

worker:       ## Worker + beat de Celery
	celery -A config worker -B -l info

seed:         ## Cargar datos base (secciones, servicios, roles)
	python manage.py seed_inicial

perfil:       ## Dar al superusuario un perfil de dev con todos los servicios
	python manage.py perfil_dev

demo:         ## Sembrar usuarios, pacientes y actividad para probar el sistema
	python manage.py datos_demo

setup:        ## Primera vez: migraciones + datos base + RBAC
	python manage.py migrate
	python manage.py seed_inicial
	python manage.py configurar_rbac
	@echo ""
	@echo "Listo. Cree un superusuario con 'python manage.py createsuperuser',"
	@echo "asígnele perfil con 'make perfil' y arranque con 'make up'."

test:         ## Ejecutar pruebas con cobertura
	pytest --cov=apps

lint:         ## Ruff + bandit (separados: el && oculta el fallo de format)
	ruff check .
	ruff format --check .
	bandit -r apps config -ll

fmt:          ## Formatear con ruff
	ruff format .
	ruff check --fix .
