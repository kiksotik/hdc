<a name="readme-top"></a>

# HDC: A generic, multipurpose Host Device Communication protocol
Specification and implementation of a generic host-device communication protocol, which is 
meant to lower the typical *impedance* between microcontroller firmware and the software 
communicating with it on a hosting PC.

Warning: The [HDC-Spec](https://github.com/kiksotik/hdc/blob/main/doc/spec/HDC-Spec.pdf) is still work in progress!


## Getting Started

### Device firmware for STM32 microcontrollers
Create your own STM32CubeIDE workspace directly in the ``STM32`` folder and import the demo 
project that matches the version of the NUCLEO prototyping board of your choice.  
For further details refer to [STM32/README.md](https://github.com/kiksotik/hdc/blob/main/STM32/README.md)

[![STM32CubeIDE][STM32CubeIDE-shield]][STM32CubeIDE-url]

### Host example in python
* Load the ``python`` folder as a PyCharm project.
* Connect a HDC-device to the PC
* Run any of the generic demo command-line showcase scripts.

[![python][python-shield]][python-url]
[![PyCharm][PyCharm-shield]][PyCharm-url]


## Usage
Please refer to the demo projects:
* Minimal_Demo:
  * HDC-device implementation in [``STM32/demo/Demo_Minimal_NUCLEO-F303RE/Core/Src/feature_core.c``](https://github.com/kiksotik/hdc/blob/main/STM32/demo/Demo_Minimal_NUCLEO-F303RE/Core/Src/feature_core.c)  
    _The remainder of that example's source-code is just the very bloated way the STM32CubeIDE wizzard sets up a HAL based project._
	
  * HDC-host python implementation in ["python/demo/cli_minimal/minimal_proxy.py"](https://github.com/kiksotik/hdc/blob/main/python/demo/cli_minimal/minimal_proxy.py)  
    How to use said python proxy is demonstrated in ["python/demo/cli_minimal/showcase_minimal.py"](https://github.com/kiksotik/hdc/blob/main/python/demo/cli_minimal/showcase_minimal.py)  


## Roadmap
- [X] Setup a public repository.
- [ ] Optimize repository structure for ease of use and extensibility.
- [ ] Mature the HDC-Spec, challenging it with increasingly realistic use-cases.
- [ ] Release first sufficiently mature version.

See the [open issues](https://github.com/kiksotik/hdc/issues) for a full list of proposed features (and known issues).


## Contributing
I'm a newbie to open-source and am grateful for any suggestion on how to be a better maintainer.  
Also any feedback on how I could improve the setup of the repo or the architecture of the protocol is greatly appreciated.  
Note, however, that I'm currently still setting up this repo and its content is still work in progress, thus any PR might suffer from this initial chaos.  


## License
Distributed under the MIT License.  
See `LICENSE.txt` for more information.


## Contact
Axel T. J. Rohde - kiksotik@gmail.com

Project Link: [https://github.com/kiksotik/hdc](https://github.com/kiksotik/hdc)


## Acknowledgments
* Thanks to the great guys at [QAware](https://www.qaware.de/) for hosting just the 
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
