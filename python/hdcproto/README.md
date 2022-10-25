<!-- 
      This is the README.md file used for the publication of the hdcproto package on PyPi and is only meant for 
      users of the hdcproto package. Any information intended for contributors should **NOT** be placed here, but 
      in the other README.md in the parent directory.
-->

# The HDC protocol
The purpose of the [Host Device Communication](https://github.com/kiksotik/hdc) protocol is to simplify the 
communication between the firmware of a device with limited computing resources and the software on the computer 
to which it's connected via a serial communication link, like UART / USB-CDC / Virtual COM Port.


# Python implementation of the HDC protocol
The ``hdcproto`` package contains the Python implementation of the HDC protocol, and it's mainly meant for the 
implementation of HDC-host software.

Note, however, how implementing HDC-devices in Python offers some interesting possibilities:  
- Mocking an HDC-device:
  - For demonstration purposes of the HDC-host software, whenever a physical device is not available.
  - For testing purposes, to create test-scenarios for the HDC-host software, which would otherwise 
    be difficult to recreate on a physical HDC-device. e.g.: A Continuous Integration build server.
- Implementing an actual HDC-device on sufficiently powerful hardware:
  - Because you can. ;-) 
  - In most cases, though, you would be better off using more conventional technologies 
    like [gRPC](https://en.wikipedia.org/wiki/GRPC) 
    or [RESTful API](https://en.wikipedia.org/wiki/Representational_state_transfer)  

> WARNING: The HDC-device implementation in the ``hdcproto`` package is still work in progress.


## Usage
The ```hdcproto.host.proxy``` module implements generic proxy base-classes that can be used as building blocks to
define proxy-classes that are specific for a given device and provide a convenient API for the HDC-host 
software to interact with the HDC-device.

Have a look at the ``hdcproto.demo.minimal`` sub-package, where you'll see an example of how 
[proxy-classes are defined](https://github.com/kiksotik/hdc/blob/main/python/hdcproto/hdcproto/demo/minimal/minimal_proxy.py) 
and 
[how they are used](https://github.com/kiksotik/hdc/blob/main/python/hdcproto/hdcproto/demo/minimal/showcase_minimal.py) 
to communicate with an HDC-device running the [Demo_Minimal firmware](https://github.com/kiksotik/hdc/blob/main/STM32/demo/Demo_Minimal_NUCLEO-F303RE/Core/Src/feature_core.c) example.


## Build with

[![python][python-shield]][python-url]  
[![PyCharm][PyCharm-shield]][PyCharm-url]


<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->

[python-shield]: https://img.shields.io/badge/python-v3.10-brightgreen
[python-url]: https://www.python.org/downloads/release/python-3100/
[PyCharm-shield]: https://img.shields.io/badge/PyCharm-2022.2.3-brightgreen
[PyCharm-url]: https://www.jetbrains.com/pycharm/