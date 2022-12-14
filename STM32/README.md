<!-- 
      This is the README.md file with specific information meant 
      for device firmware developers targeting the STM32 family of microcontrollers.
-->

# About
The ``STM32`` sub-folder contains source-code for 
the [STM32](https://en.wikipedia.org/wiki/STM32) family of microcontrollers.

* Sub-folder ``hdc_device``  
  HDC-device driver implementation that is portable to many STM32 
  microcontrollers, because it's based on the HAL Library Drivers.  
  Please refer to [``STM32/hdc_device/README.md``](https://github.com/kiksotik/hdc/blob/main/STM32/hdc_device/README.md) 
  for detailed instructions on how to deploy and troubleshoot this driver into your own projects.
  
* Sub-folder ``demos``  
  Contains STM32CubeIDE projects that demonstrate how to use the hdc_device driver 
  in a mock-up application that will run on off-the-shelf NUCLEO prototyping boards 
  and the like.  
  Please refer to [``STM32/demos/README.md``](https://github.com/kiksotik/hdc/blob/main/STM32/demos/README.md) 
  for detailed instruction on how to run those example projects.

## Getting Started

### Device firmware for STM32 microcontrollers
Create your own STM32CubeIDE workspace directly in the ``STM32`` folder and import the demo 
project that matches the version of the NUCLEO prototyping board of your choice.  
For further details refer to [``STM32/README.md``](https://github.com/kiksotik/hdc/blob/main/STM32/README.md)

[![STM32CubeIDE][STM32CubeIDE-shield]][STM32CubeIDE-url]


# ToDo

* [ ] Refactor ``hdc_device`` implementation for a cleaner separation of UART / USB-VCP / etc implementations.
  * Abstracting the interface to the transport layer may not be worth it, because it might degrade the 
    clarity and performance of the implementation!


<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->

[STM32CubeIDE-shield]: https://img.shields.io/badge/STM32CubeIDE-v1.10.1-brightgreen
[STM32CubeIDE-url]: https://www.st.com/en/development-tools/stm32cubeide.html
