=============================
mdssprep
=============================

Prepare directories for archiving to mdssprep

.. image:: https://readthedocs.org/projects/mdssprep/badge/?version=latest
  :target: https://readthedocs.org/projects/mdssprep/?badge=latest
.. image:: https://travis-ci.org/coecms/mdssprep.svg?branch=master
  :target: https://travis-ci.org/coecms/mdssprep
.. image:: https://circleci.com/gh/coecms/mdssprep.svg?style=shield
  :target: https://circleci.com/gh/coecms/mdssprep
.. image:: http://codecov.io/github/coecms/mdssprep/coverage.svg?branch=master
  :target: http://codecov.io/github/coecms/mdssprep?branch=master
.. image:: https://landscape.io/github/coecms/mdssprep/master/landscape.svg?style=flat
  :target: https://landscape.io/github/coecms/mdssprep/master
.. image:: https://codeclimate.com/github/coecms/mdssprep/badges/gpa.svg
  :target: https://codeclimate.com/github/coecms/mdssprep
.. image:: https://badge.fury.io/py/mdssprep.svg
  :target: https://pypi.python.org/pypi/mdssprep

.. content-marker-for-sphinx

-------
Install
-------

Conda install::

    conda install -c coecms mdssprep

Pip install (into a virtual environment)::

    pip install mdssprep

---
Use
---

-------
Develop
-------

Development install::

    git checkout https://github.com/coecms/mdssprep
    cd mdssprep
    conda env create -f conda/dev-environment.yml
    source activate mdssprep-dev
    pip install -e '.[dev]'

The `dev-environment.yml` file is for speeding up installs and installing
packages unavailable on pypi, `requirements.txt` is the source of truth for
dependencies.

Run tests::

    py.test

Build documentation::

    python setup.py build_sphinx
    firefox docs/_build/index.html

Upload documentation::

    git subtree push --prefix docs/_build/html/ origin gh-pages
