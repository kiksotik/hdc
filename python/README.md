<!-- 
      This is the README.md file with information intended for contributors to the python code-base and documentation.
      Any information intended for users of the hdcproto package should **NOT** be placed here, but 
      in the other README.md in the child directory.
-->

# About
This is the directory containing all python subprojects of the main HDC project.  
Currently everything is bundled in a single package: 
[hdcproto](https://github.com/kiksotik/hdc/blob/main/python/hdcproto/README.md)

## Getting started
- Load the ``python/hdcproto`` folder as a PyCharm project.
- Create a python 3.10 based pipenv environment and install all packages required by the pipfile.
- Connect a HDC-device to the PC
- Run any of the generic demo command-line showcase scripts from folder ``python/hdcproto/demo/generic/``

## How to publish a new package
- Edit and double-check the ``pyproject.toml`` file:
  - Manually bump the version number.
  - Check dependencies.
- Check in the lower right corner of the PyCharm window, whether the correct pipenv environment is active.
- Open a PyCharm terminal in the context of the ``hdcproto`` project and build the wheels and source packages with:
  ```shell
   python -m build
  ```
- Inspect the packages (located in ``python/hdcproto/dist``) by unzipping with 7zip or the like:
  - Are any files being included/missing in/from the package?
  - Is the metadata correct and up to date?
  - Are there any obsolete packages still lying around in the dist folder? Remove them.
- Upload packages to the PyPi **test**-repository by executing this command in the PyCharm terminal:
  ```shell
   twine upload --repository testpypi dist/*
  ```
  For this to work you have to have created an account on Test-PyPi, created an API-Token 
  and save your credentials in a ``%userprofile%/.pypirc`` file, as 
  explained [here](https://packaging.python.org/en/latest/specifications/pypirc/). 


## Build with

[![python][python-shield]][python-url]  
[![pyserial][pyserial-shield]][pyserial-url]  

[![PyCharm][PyCharm-shield]][PyCharm-url]


<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->

[python-shield]: https://img.shields.io/pypi/pyversions/hdcproto
[python-url]: https://www.python.org/downloads/release/python-3100/
[pyserial-shield]: https://img.shields.io/badge/pyserial-3.5-brightgreen
[pyserial-url]: https://pyserial.readthedocs.io/en/latest/
[PyCharm-shield]: https://img.shields.io/badge/PyCharm-2022.2.3-brightgreen
[PyCharm-url]: https://www.jetbrains.com/pycharm/