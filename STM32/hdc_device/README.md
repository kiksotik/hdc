# About
This folder contains the ``hdc_device`` driver for the [STM32](https://en.wikipedia.org/wiki/STM32) family of microcontrollers.

For more details on HDC, please refer to https://github.com/kiksotik/hdc 


# HowTo

## How to deploy this ``hdc_device`` driver into your own projects
Current ``hdc_device`` implementation is hardcoded to use USART via DMA via their HAL drivers.

This is how you should set up your project:
* Use the STM32 project creation wizzard to set up a new STM32CubeMX based project 
  for the kind of microcontroller or prototyping board of your choice.
  
* Copy the ''STM32/hdc_device/'' folder of this repository into the ``Drivers/`` folder of your project.

* Open the ioc file of your project and tweak the following:
  * Enable a USART module to be used for HDC communication.  
    Projects for NUCLEO boards are typically already set up with the USART which uses the 
    integrated ST-LINK as a gateway exposed as a USB Virtual-COM-Port at the USB connector of the NUCLEO board.  
    Code snipets below refer to USART2. Make sure to change those to whatever USART module number you are using for HDC in your project. 
    Also double-check the baudrate setting. NUCLEO-F303RE project was incorrectly initialized to 38400, instead of 115200 baud!
    
  * Enable DMA feature for that USART  
    In configuration pane at ``Connectivity / USARTx / DMA`` add DMA settings for both ``USARTx_RX`` and ``USARTx_TX``  

  * Configure DMA mode of RX channel to *Circular*  
    In configuration pane at ``Connectivity / USARTx / DMA`` select the RX channel and chose Mode=Circular.  
    (Otherwise reception will be stopped in HAL_UARTEx_ReceiveToIdle_DMA() on every IDLE interrupt, which is OK 
    whenever a full packet has been received, but occasionally IDLE happens before the full request was received 
    and the ``hdc_device`` driver would wait eternally for the remainder to arrive.)
     
  * Enable global interrupt for that USART  
    In configuration pane at ``Connectivity / USARTx / NVIC`` enable the checkbox ``USART global interrupt``.  
	 
* Implement interrupt handlers for DMA transfers in your ``*_it.c`` file:

  * Include the hdc_device header in the ``USER CODE Includes`` section:
    ```C
    /* USER CODE BEGIN Includes */
    #include "hdc_device.h"
    /* USER CODE END Includes */
    ```

  * Copy the following into the ``USER CODE 1`` section:
    ```C
    /* USER CODE BEGIN 1 */
    void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart) {
      HDC_RxCpltCallback(huart);
    }

    void HAL_UART_TxCpltCallback(UART_HandleTypeDef *huart) {
      HDC_TxCpltCallback(huart);
    }
    /* USER CODE END 1 */
    ```
	 
  * Copy the following into the ``USER CODE USARTx_IRQn`` section:  
    (Section will be missing if you forgot to enable the ``USART global interrupt`` option of the ioc file.)
    ```C
    /* USER CODE BEGIN USART2_IRQn 1 */
    HDC_IrqRedirection_UartIdle();  // Redirects the IDLE event into the HDC_RxCpltCallback() handler.
    /* USER CODE END USART2_IRQn 1 */
    ```
	
  * Copy the file ``hdc_device_conf_TEMPLATE.h`` from this folder to the ``Core/Src`` folder of 
    your project and rename it to ``hdc_device_conf.h``.  
	The definitions contained therein only need to be tweaked if your project requires to reduce 
	the RAM consumption of the ``hdc_device`` driver.
	
  * Implement the core-feature of your application.  
    You can use as a template the ``feature_core.c/h`` files of the ``DEMO_MINIMAL`` example 
	project at ``STM32/demo/DEMO_MINIMAL_NUCLEO-\*/Core/Src``.
	
  * Include, initialize and update your core-feature in your project's ``main.c`` file.
  
  * You may consider implementing additional HDC-features for your device.
   
## How to verify if data is being transfered correctly?
  Set a breakpoint in ``hdc_device.c`` in ``HDC_RxCpltCallback()`` and check whether any bytes have been sent 
  when running i.e. ``demo_introspection.py`` script on the host.
  If the handler is called when the HDC-host has sent a request, but zero bytes 
  have been received, it might be an indication that you may need to fix the 
  USART parameters (i.e. the baudrate) or the wiring of your device.


# License
Distributed under the MIT License.  
See `LICENSE.txt` for more information.