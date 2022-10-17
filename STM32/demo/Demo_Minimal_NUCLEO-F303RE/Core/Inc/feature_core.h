/*
 * API and HDC-feature of the Demo_Minimal Core-feature
 */

// Define to prevent recursive inclusion
#ifndef INC_FEATURE_CORE_H_
#define INC_FEATURE_CORE_H_

#include "hdc_device.h"

typedef enum {
  Core_State_Off = 0x00,
  Core_State_Initializing = 0x01,
  Core_State_Ready = 0x02,
  Core_State_Error = 0xFF
} Core_State_t;

///////////////////////////////
// API of the Feature
void Core_Init(UART_HandleTypeDef *huart);
void Core_UpdateState(void);
void Core_ErrorHandler(HDC_EventLogLevel_t logLevel, char* errorMessage);


#endif // INC_FEATURE_CORE_H_
