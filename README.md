<a name="readme-top"></a>

# HDC: Host Device Communication protocol
Specification and implementation of the "Host Device Communication" protocol, which is meant 
to lower the typical _impedance_ between microcontroller firmware and the software 
communicating with it on a hosting PC.

Warning: The [HDC-Spec](https://github.com/kiksotik/hdc/blob/main/doc/spec/HDC-Spec.pdf) is still work in progress!

## Features

- Despite the long list of features below, HDC is quite lightweigt on microcontroller resources.
  - A typical HDC-device implementation consumes less than 10KB of FLASH and 1KB of RAM.
  
  - Protocol overhead is typically 6 bytes per HDC-message.  
    Message payloads can be as big as the microcontroller can cope with.
	
  - Firmware developers can configure the amount of resources dedicated to the ``hdc_device`` driver:
    - RAM requirements can be configured via the ``hdc_device_config.h`` private header file.
    - Docstrings are optional and typically stored in FLASH memory.
  
  - The ``hdc_device`` driver does **not** use any dynamic memory allocation! (a.k.a. ``malloc()``)
  
	
- Object oriented
  - Device capabilities are grouped into ``features`` which implement ``properties``, ``commands`` and ``events``.  
    This allows for the seamless mapping of device features into ``proxy-classes`` on the host side, which 
	provide a more natural API for host software developers.
	
  - Enforces _good practice_ on device firmware coders, while respecting the usual 
    constraints imposed on them by the limited availability of resources on microcontrollers.  
	i.e.: The ``hdc_device`` driver is writen in plain and simple C.  
	There's no obligation to code in C++ nor Objective-C!
	
  - Encourages source-code modularity and reusability.
    Device ``features`` can be reused accross different device-implementations.  
	Both, their device side as well as their host side implementations.

	
- [Introspection](https://en.wikipedia.org/wiki/Type_introspection)
  - Hosts can dynamically query details about the capabilities implemented by any HDC-device.
  
  - Allows for automated source-code generation of proxy-classes for any HDC-device in whatever 
    programming language the host is written in. _(Work in progress and not fully implemented yet!)_
  
  - Much more than just data-types can be introspected:
  	- Human readable documentation of ``features``, ``properties``, ``commands``, ``events`` 
	  and ``states`` in the manner of [docstrings](https://en.wikipedia.org/wiki/Docstring)
	  
    - Revision number of a ``feature``'s implementation  
	  Because hosts may need to figure out if they are talking to a buggy old device.

- Properties
  - Each ``feature`` can expose its own set of properties and define their data-type, 
    whether it's read-only, its human readable name and docstring.

- Commands
  - Those are essentially *Remote Procedure Calls* of methods implemented on a ``feature``
    and can carry any number of arguments and reply with any number of return values.
	HDC also standardizes how ``commands`` return error codes, such that proxy-classes can 
	translate those into more comfortable exceptions thrown on the host side.

- Events
  - Raised at any moment by a ``feature`` and send almost immediately to the host.  
    Can carry any number of data-items as their payload.  
	Each feature can implement multiple kinds of events.
	Proxy-classes are able to buffer events, thus allowing for a much simpler, 
	non-concurrent processing of events by the host software.

- Streaming
  - Each ``feature`` can send multiple, independent streams of data to the host.
    Streamed data-items are actually handled in the same manner as regular ``events``, 
	each ``EventID`` constitutes a _stream_ and it's always up to the device to 
	decide when it sends the next data-item or chunk, whithout having to care about 
	buffer management, because the ``hdc_device`` driver takes care of sending data almost 
	immediately to the HDC-host.  
	On the receiving end, the corresponding proxy-class takes care of buffering the 
	received data, thus unburdening the host application of having to poll or even 
	care at all about any received data.
	Data type of the streamed data-items can be as simple or as complex as the device 
	developer may require. Also whether a stream is initiated and stopped by ``commands`` 
	or otherwise is also up to the device developer to decide.
	
- Logging
  - Each ``feature`` has its own logger, which the proxy-class can seamlessly map into the native logging infrastructure of the host.
 
  - Logging directly from the firmware to the host software provides an incredibly 
    powerful tool to debug and troubleshoot issues, without any need for any JTAG or SWD probes.  
	
  - Hosts can tune the log verbosity in a similar manner as python handles
    [logging levels](https://docs.python.org/3/library/logging.html#logging-levels).
	
- Feature states
  - HDC standardizes how ``features`` can expose their state-machine, because states are 
    essential in most device firmware implementations and hosts usually need to know about it.


## Usage
Please refer to the demo projects:
- Minimal_Demo:
  - HDC-device implementation in [``STM32/demo/Demo_Minimal_NUCLEO-F303RE/Core/Src/feature_core.c``](https://github.com/kiksotik/hdc/blob/main/STM32/demo/Demo_Minimal_NUCLEO-F303RE/Core/Src/feature_core.c)  
    _The remainder of that example's source-code is just the very bloated way the STM32CubeMX wizzard sets up a HAL based project._
	
  - HDC-host python implementation in [``python/demo/cli_minimal/minimal_proxy.py``](https://github.com/kiksotik/hdc/blob/main/python/demo/cli_minimal/minimal_proxy.py)  
    How to use said python proxy is demonstrated in [``python/demo/cli_minimal/showcase_minimal.py``](https://github.com/kiksotik/hdc/blob/main/python/demo/cli_minimal/showcase_minimal.py)  


## Getting Started

### Device firmware for STM32 microcontrollers
Create your own STM32CubeIDE workspace directly in the ``STM32`` folder and import the demo 
project that matches the version of the NUCLEO prototyping board of your choice.  
For further details refer to [``STM32/README.md``](https://github.com/kiksotik/hdc/blob/main/STM32/README.md)

[![STM32CubeIDE][STM32CubeIDE-shield]][STM32CubeIDE-url]

### Host example in python
- Load the ``python`` folder as a PyCharm project.
- Connect a HDC-device to the PC
- Run any of the generic demo command-line showcase scripts.

[![python][python-shield]][python-url]
[![PyCharm][PyCharm-shield]][PyCharm-url]


## Roadmap
- [X] Setup a public repository.
- [ ] Optimize repository structure for ease of use and extensibility.
- [ ] Mature the HDC-Spec, challenging it with increasingly realistic use-cases.
- [ ] Release first sufficiently mature version.

See the [open issues](https://github.com/kiksotik/hdc/issues) for a full list of proposed features (and known issues).


## Contributing
I'm a newbie to open-source and am grateful for any suggestion on how to be a better maintainer.  
The HDC-spec is currently work in progress; any feedback on how I could improve HDC is very welcome.  
Pull-requests are not yet appropriate at this point in time, since I'm still rearranging the folder structure of this repository.  


## License
Distributed under the MIT License.  
See [``LICENSE.txt``](https://github.com/kiksotik/hdc/blob/main/LICENSE.txt) for more information.


## Contact
Axel T. J. Rohde - kiksotik@gmail.com

Project Link: [https://github.com/kiksotik/hdc](https://github.com/kiksotik/hdc)


## Acknowledgments
- Thanks to the great guys at [QAware](https://www.qaware.de/) for hosting just the 
  right Hacktoberfest 2022 event for me to finally get to publish my first open-source project.
  
  
<p align="right">(<a href="#readme-top">back to top</a>)</p>


<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->

[STM32CubeIDE-shield]: https://img.shields.io/badge/STM32CubeIDE-v1.10.1-brightgreen
[STM32CubeIDE-url]: https://www.st.com/en/development-tools/stm32cubeide.html
[python-shield]: https://img.shields.io/badge/python-v3.10-brightgreen
[python-url]: https://www.python.org/downloads/release/python-3100/
[PyCharm-shield]: https://img.shields.io/badge/PyCharm-2021.2.2-brightgreen
[PyCharm-url]: https://www.jetbrains.com/pycharm/
