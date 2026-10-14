PYTHON ?= python
export PYTHONPATH := src

.PHONY: install data pipeline report dashboard test lint all clean

install:            ## install runtime + dev dependencies
	$(PYTHON) -m pip install -r requirements-dev.txt

data:               ## generate raw source CSVs
	$(PYTHON) -m pipeline.generate

pipeline:           ## extract -> transform -> load -> build models -> quality checks
	$(PYTHON) -m pipeline

report:             ## regenerate charts and reports/insights.md
	$(PYTHON) analysis/report.py

dashboard:          ## launch the Streamlit dashboard
	streamlit run dashboard/app.py

test:
	$(PYTHON) -m pytest -q

lint:
	ruff check .

all: data pipeline report test

clean:
	rm -rf data/ .pytest_cache .ruff_cache
