OUT_DIR?=dist
SHELL=/bin/bash
INSTALL_MODULES:=.

VENV=$(OUT_DIR)/venv

PYTHON=$(VENV)/bin/python
PYTHON_PIP_VERSION?=pip==9.0.1
PIP=$(VENV)/bin/pip
SETUPTOOLS_VERSION:=setuptools>=20.7.0


######################### HELP ####################################
define HELPTEXT
Mouse locomotion Makefile usage
 Targets:
	devinstall              as install but in development mode to make in-place source changes
	clean                   clean everything generated by make
	pypi-sdist              generate pip packages
	pypi-clean              clean generated pip packages
	download-req            downloads all the requirements into the `dist` directory
	install_simulators      install all the simulators inside the simulators package
	remove_simulators       remove the installed simulators inside the simulators package
	help                    this help
endef

export HELPTEXT
help:
	@echo "$$HELPTEXT"


########################### LOGGING ###############################
#called with $(call WARN,Text to display)
#this is idempotent: it doesn't change the $?
WARN={ res=$$?; [ -n "$$TERM" ] && tput setaf 1; echo "$(1)"; [ -n "$$TERM" ] && tput sgr0; [ $$res -eq 0 ]; }


################## INSTALL SIMULATORS #############################
SIMULATORS = $(filter-out src/simulators/ src/simulators/__pycache__/, $(sort $(dir $(wildcard src/simulators/*/))))

install_simulators:
	$(foreach sim, $(SIMULATORS), $(MAKE) -C $(sim) install_$(shell basename $(sim)) OUT_DIR=../../../$(OUT_DIR) &&) true


###################### INSTALL ####################################
devinstall: virtualenv
	$(PIP) install --pre .

install_all: devinstall install_simulators

virtualenv:
	virtualenv --no-site-packages $(VENV)
	touch $(VENV)/bin/activate
	$(PIP) install '$(PYTHON_PIP_VERSION)'
	$(PIP) install '$(SETUPTOOLS_VERSION)'

#delete everything we don't need
clean: pypi-clean
	for i in '*.pyc' 'pep8.txt' 'pylint.txt'; do \
		find . -name $$i -delete; \
	done


################# DOWNLOAD REQUIREMENTS ###########################
REQUIREMENTS:=$(foreach req, $(INSTALL_MODULES), $(wildcard $(req)/requirements*.txt))
download-req: devinstall
	for d in $(REQUIREMENTS); do \
		yes i | $(PIP) install --ignore-installed -t $(OUT_DIR)/libs -r $$d; \
	done; true


######################### CREATE TAR ##############################
DISTS=$(addprefix sdist_, $(INSTALL_MODULES))

pypi-sdist: $(DISTS)

$(DISTS): sdist_%: devinstall
	@[ -d $* ] || $(call WARN,Missing INSTALL_MODULES directory: $*)
	mkdir -p $(OUT_DIR)
	cd $* && $(PYTHON) setup.py sdist
	if [ "$*" != "." ] ; then mv $*/$(OUT_DIR)/*.tar.gz $(OUT_DIR) ; fi

pypi-clean:
	-rm -rf dist
	for d in $(INSTALL_MODULES); do \
		rm -rf *.egg-info; \
		rm -rf $$d/$(OUT_DIR); \
	done; true


.PHONY: help devinstall clean pypi-sdist pypi-clean install_all