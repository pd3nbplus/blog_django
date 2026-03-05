.PHONY: install migrate test unit-test api-test lint format docs run collectstatic check

install:
	pip install -r requirements.txt

migrate:
	python manage.py makemigrations
	python manage.py migrate

test:
	python manage.py test apps.common.tests apps.users.tests apps.articles.tests

unit-test:
	python manage.py test --tag=unit

api-test:
	python manage.py test --tag=api

lint:
	ruff check .
	mypy .

format:
	black .
	ruff check . --fix

docs:
	python manage.py spectacular --file schema.yml

run:
	python manage.py runserver

collectstatic:
	python manage.py collectstatic --noinput

check:
	python manage.py check
