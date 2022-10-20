# About
The ``STM32`` sub-folder contains source-code for the [STM32](https://en.wikipedia.org/wiki/STM32) family of microcontrollers.

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


# ToDo
* Are there better ways to share STM32 source code?
  Learn how others setup their STM32 repositories:
  * https://github.com/afiskon/stm32-ssd1306

* Refactor ``hdc_device`` implementation for a cleaner separation of USART / USB-VCP / etc implementations.
  * Abstracting the interface to the transport layer may not be worth it, because it might degrade the clarity and performance of the implementation!
