<!-- 
      This is the main README.md file at the top of the folder hierarchy of the git repository. 
      Since the GitHub repository is used as the project's homepage, this file is meant to welcome people
      who might not know anything about HDC yet.
-->

<a name="readme-top"></a>

# The HDC protocol
Specification and implementation of the **Host Device Communication** protocol, whose purpose is to simplify the 
communication between the firmware of a device with severely limited computing resources and the software 
on the computer to which it's connected via a serial communication link, like UART / USB-CDC / Virtual COM Port.

> WARNING:  The [HDC-Spec](https://github.com/kiksotik/hdc/blob/main/doc/spec/HDC-Spec.pdf) is still work in progress!

## Features

- Despite the long list of features below, HDC is quite lightweight on microcontroller resources.
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
	
  - Encourages source-code modularity and re-usability.
    Device ``features`` can be reused across different device-implementations.  
	Both, their device side and their host side implementations.

	
- [Introspection](https://en.wikipedia.org/wiki/Type_introspection)
  - Hosts can dynamically query details about the capabilities implemented by any HDC-device.
  
  - Allows for automated source-code generation of proxy-classes for any HDC-device in whatever 
    programming language the host is written in. _(Work in progress and not fully implemented yet!)_
  
  - Much more than just data-types can be introspected:
  	- Human-readable documentation of ``features``, ``properties``, ``commands``, ``events`` 
	  and ``states`` in the manner of [docstrings](https://en.wikipedia.org/wiki/Docstring)
	  
    - Revision number of a ``feature``'s implementation  
	  Because hosts may need to figure out if they are talking to a buggy old device.

- Properties
  - Each ``feature`` can expose its own set of properties and define their data-type, 
    whether it's read-only, its human-readable name and docstring.

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
	each ``EventID`` constitutes a _stream_, and it's always up to the device to 
	decide when it sends the next data-item or chunk, without having to care about 
	buffer management, because the ``hdc_device`` driver takes care of sending data almost 
	immediately to the HDC-host.  
	On the receiving end, the corresponding proxy-class takes care of buffering the 
	received data, thus unburdening the host application of having to poll or even 
	care at all about any received data.
	Data type of the streamed data-items can be as simple or as complex as the device 
	developer may require. Also, whether a stream is initiated and stopped by ``commands`` 
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
An HDC-host uses predefined 
[proxy-classes](https://github.com/kiksotik/hdc/blob/main/python/hdcproto/hdcproto/demo/minimal/minimal_proxy.py) as an 
API to [communicate](https://github.com/kiksotik/hdc/blob/main/python/hdcproto/hdcproto/demo/minimal/showcase_minimal.py) 
with the [firmware](https://github.com/kiksotik/hdc/blob/main/STM32/demo/Demo_Minimal_NUCLEO-F303RE/Core/Src/feature_core.c) 
of an HDC-device.

Target specific documentation:
- [STM32](https://github.com/kiksotik/hdc/blob/main/STM32/README.md)
- [Python](https://github.com/kiksotik/hdc/blob/main/python/README.md)
    

## Alternatives
The HDC protocol addresses the needs of a quite specific scenario.  
Please consider the following list of alternatives and related technologies, which might be a better fit 
for your project:

- [Modbus](https://modbus.org/faq.php)
  - Widespread industry standard for networking of distributed automation devices.

- [TinyProto](https://github.com/lexus2k/tinyproto)
  - An implementation of [RFC 1662](https://www.rfc-editor.org/rfc/rfc1662), which is only OSI layer 2.
  - Excellent [arduino implementation](https://www.arduino.cc/reference/en/libraries/tinyproto/)

- [nanoFramework](https://github.com/nanoframework/nf-interpreter)
  - Not a protocol, but C# code for embedded systems: https://www.nanoframework.net/
  - Designed to support many targets: STM32, ESP32, NXP, TI, ... 


## Roadmap
- [X] Setup a public repository.
- [X] Publish first [pre-alpha package on PyPi](https://pypi.org/project/hdcproto/0.0.7).
- [ ] Freeze HDC-spec version 1.0
- [ ] Release first beta version
- [ ] Release first stable version

See the [open issues](https://github.com/kiksotik/hdc/issues) for a full list of proposed features (and known issues).


## Contributing
I'm a newbie to open-source and am grateful for any suggestion on how to be a better maintainer.  
The HDC-spec is currently work in progress; any feedback on how I could improve HDC is very welcome.  
Use the [issue tracker](https://github.com/kiksotik/hdc/issues) to report your feedback 
or drop me an [email](mailto:kiksotik@gmail.com).  

Pull-requests are not a good idea at this point in time, since the HDC-spec is still in pre-alpha and 
also because I'm still rearranging the basic folder structure of this repository on a weekly basis.  


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
