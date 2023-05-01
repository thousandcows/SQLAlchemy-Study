#!/bin/sh -e
set -x

flake8 .
isort .
black .
#mypy .
