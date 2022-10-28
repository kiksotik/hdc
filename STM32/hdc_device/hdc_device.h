/*
 * Host-Device Communication (HDC)
 *
 * Generic device-side implementation.
 */

#ifndef INC_HDC_DEVICE_H_
#define INC_HDC_DEVICE_H_

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "hdc_device_conf.h"

// Sanity checks
#if !defined  (USE_HAL_DRIVER)
#error "The hdc_device driver currently relies on the HAL drivers to use UART via DMA."
#endif

// Import HAL driver for the targeted microcontroller
// ToDo: Add support for as many microcontroller types as possible
#if defined(STM32F303xE)  // As on NUCLEO-F303RE
#include "stm32f3xx_hal.h"
#elif defined(STM32G431xx)  // As on NUCLEO-G431KB
#include "stm32g4xx_hal.h"
#else
#error "The hdc_device driver doesn't know about the microcontroller type your are targeting. " \
       "Please modify hdc_device.h if you know what you are doing. " \
       "Also please send a pull request if it turns out the driver works on other MCU's as well!"
#endif

// Buffer sizes for reception and transmission of data via UART & DMA.
// Computed based on private configuration of hdc_device driver provided by the hdc_device_conf.h header file.
#define HDC_PACKAGE_OVERHEAD 3      // PayloadSize ; Checksum ; Terminator
#define HDC_MAX_REQ_PACKAGE_SIZE (HDC_MAX_REQ_MESSAGE_SIZE + HDC_PACKAGE_OVERHEAD)
#define HDC_BUFFER_SIZE_RX HDC_MAX_REQ_PACKAGE_SIZE

// Forward declaration of HDC structs and their typedefs,
// which we need in the following function-pointer typedefs
struct HDC_Feature_struct;
typedef struct HDC_Feature_struct HDC_Feature_Descriptor_t;

struct HDC_Property_struct;
typedef struct HDC_Property_struct HDC_Property_Descriptor_t;

// Improve readability of function-pointer types
typedef void (*HDC_CommandHandler_t)(
    const HDC_Feature_Descriptor_t *hHDC_Feature,
    const uint8_t* pRequestMessage,
    const uint8_t Size);

typedef void (*HDC_PropertyValueGetter_t)(
    const HDC_Feature_Descriptor_t *hHDC_Feature,
    const HDC_Property_Descriptor_t *hHDC_Property,
    const uint8_t* pRequestMessage,
    const uint8_t RequestMessageSize);

typedef void (*HDC_PropertyValueSetter_t)(
    HDC_Feature_Descriptor_t *hHDC_Feature,
    const HDC_Property_Descriptor_t *hHDC_Property,
    const uint8_t* pRequestMessage,
    const uint8_t RequestMessageSize);


///////////////////////////////
// Magic numbers defined by the HDC specification
#define HDC_PACKAGE_TERMINATOR 0x1E


//////////////////////////////
// Enums

typedef enum {
  HDC_MessageTypeID_EchoCommand = 0xCE,
  HDC_MessageTypeID_FeatureCommand = 0xCF,
  HDC_MessageTypeID_FeatureEvent = 0xEF,
} HDC_MessageTypeID_t;

typedef enum {
  HDC_FeatureID_Core = 0x00,
} HDC_FeatureID_t;

typedef enum {
  HDC_CommandID_GetPropertyName = 0xF0,
  HDC_CommandID_GetPropertyType = 0xF1,
  HDC_CommandID_GetPropertyReadonly = 0xF2,
  HDC_CommandID_GetPropertyValue = 0xF3,
  HDC_CommandID_SetPropertyValue = 0xF4,
  HDC_CommandID_GetPropertyDescription = 0xF5,
  HDC_CommandID_GetCommandName = 0xF6,
  HDC_CommandID_GetCommandDescription = 0xF7,
  HDC_CommandID_GetEventName = 0xF8,
  HDC_CommandID_GetEventDescription = 0xF9,
} HDC_CommandID_t;

typedef enum {
  HDC_ReplyErrorCode_NO_ERROR = 0x00,
  HDC_ReplyErrorCode_UNKNOWN_FEATURE = 0xF0,
  HDC_ReplyErrorCode_UNKNOWN_COMMAND = 0xF1,
  HDC_ReplyErrorCode_UNKNOWN_PROPERTY = 0xF2,
  HDC_ReplyErrorCode_UNKNOWN_EVENT = 0xF3,
  HDC_ReplyErrorCode_INCORRECT_COMMAND_ARGUMENTS = 0xF4,
  HDC_ReplyErrorCode_COMMAND_NOT_ALLOWED_NOW = 0xF5,
  HDC_ReplyErrorCode_COMMAND_FAILED = 0xF6,
  HDC_ReplyErrorCode_INVALID_PROPERTY_VALUE = 0xF7,
  HDC_ReplyErrorCode_PROPERTY_IS_READONLY = 0xF8,
} HDC_ReplyErrorCode_t;

typedef enum {
  // The ID values of each DataType can be interpreted as follows:
  //
  // Upper Nibble: Kind of DataType
  //       0x0_ --> Unsigned integer number
  //       0x1_ --> Signed integer number
  //       0x2_ --> Floating point number
  //       0xB_ --> Binary data
  //                (Either variable size 0xBF, or boolean 0xB0)
  //       0xF_ --> UTF-8 encoded string
  //                (Always variable size: 0xFF)
  //
  // Lower Nibble: Size of DataType, given in number of bytes
  //               i.e. 0x14 --> INT32, whose size is 4 bytes
  //               (Exception to the rule: 0x_F denotes a variable size DataType)
  //               (Exception to the rule: 0xB0 --> BOOL, whose size is 1 bytes)

  HDC_DataTypeID_UINT8 = 0x01,
  HDC_DataTypeID_UINT16 = 0x02,
  HDC_DataTypeID_UINT32 = 0x04,
  HDC_DataTypeID_INT8 = 0x11,
  HDC_DataTypeID_INT16 = 0x12,
  HDC_DataTypeID_INT32 = 0x14,
  HDC_DataTypeID_FLOAT = 0x24,
  HDC_DataTypeID_DOUBLE = 0x28,
  HDC_DataTypeID_BOOL = 0xB0,
  HDC_DataTypeID_BLOB = 0xBF,
  HDC_DataTypeID_UTF8 = 0xFF
} HDC_DataTypeID_t;


typedef enum {
  HDC_PropertyID_FeatureName = 0xF0,
  HDC_PropertyID_FeatureTypeName = 0xF1,
  HDC_PropertyID_FeatureTypeRevision = 0xF2,
  HDC_PropertyID_FeatureDescription = 0xF3,
  HDC_PropertyID_FeatureTags = 0xF4,
  HDC_PropertyID_AvailableCommands = 0xF5,
  HDC_PropertyID_AvailableEvents = 0xF6,
  HDC_PropertyID_AvailableProperties = 0xF7,
  HDC_PropertyID_FeatureState = 0xF8,
  HDC_PropertyID_LogEventThreshold = 0xF9,
  HDC_PropertyID_AvailableFeatures = 0xFA,  // Only mandatory for the Core-feature
  HDC_PropertyID_MaxReqMsgSize = 0xFB,  // Only mandatory for the Core-feature
} HDC_PropertyID_t;


typedef enum {
  HDC_EventID_Log = 0xF0,
  HDC_EventID_FeatureStateTransition = 0xF1,
} HDC_EventID_t;


// Using same numeric LogLevel values as Python's logging module
typedef enum {
  HDC_EventLogLevel_DEBUG = 10,
  HDC_EventLogLevel_INFO = 20,
  HDC_EventLogLevel_WARNING = 30,
  HDC_EventLogLevel_ERROR = 40,
  HDC_EventLogLevel_CRITICAL = 50
} HDC_EventLogLevel_t;


//////////////////////////////
// Protocol stuff descriptors
typedef struct {
  uint8_t CommandID;
  char* CommandName;
  HDC_CommandHandler_t CommandHandler;
  char* CommandDescription;
} HDC_Command_Descriptor_t;


typedef struct {
  uint8_t EventID;
  char* EventName;
  char* EventDescription;
} HDC_Event_Descriptor_t;


typedef struct HDC_Property_struct {
  uint8_t PropertyID;
  char* PropertyName;
  HDC_DataTypeID_t PropertyDataType;
  bool PropertyIsReadonly;
  HDC_PropertyValueGetter_t GetPropertyValue;
  HDC_PropertyValueSetter_t SetPropertyValue;
  void *pValue;
  size_t ValueSize; // Only required for PropertyDataType=HDC_DataTypeID_BLOB, will otherwise be overridden by size of PropertyDataType
  char* PropertyDescription;
} HDC_Property_Descriptor_t;


typedef struct HDC_Feature_struct {
  uint8_t FeatureID;
  char* FeatureName;
  char* FeatureTypeName;
  uint8_t FeatureTypeRevision;
  char* FeatureDescription;
  char* FeatureTags;
  char* FeatureStatesDescription;

  const HDC_Command_Descriptor_t** Commands;
  uint8_t NumCommands;

  const HDC_Event_Descriptor_t** Events;
  uint8_t NumEvents;

  const HDC_Property_Descriptor_t** Properties;
  uint8_t NumProperties;

  // Optional pointer to the API handle of a feature.
  // e.g. HDC_Feature_AxisX.hAPI points to Axis_HandleTypeDef
  // Mainly used by Command and Get/SetParameterValue handlers, who are
  // just given a HDC-feature descriptor and need to infer the API handler.
  void* hAPI;


  //////////////////////////////////////
  // Mandatory and mutable properties

  uint8_t FeatureState;
  uint8_t LogEventThreshold;

} HDC_Feature_Descriptor_t;


///////////////////////////////////////
// Interrupt handlers and redirection

void HDC_RxCpltCallback(UART_HandleTypeDef *huart);  // Must be called from HAL_UART_RxCpltCallback
void HDC_TxCpltCallback(UART_HandleTypeDef *huart);  // Must be called from HAL_UART_TxCpltCallback

// Must be called from the USARTx_IRQHandler(), to redirect UART-IDLE events into
// the HDC_RxCpltCallback() handler, for it to notice that a request is complete.
void HDC_IrqRedirection_UartIdle(void);

/////////////////////////////////////////////////////////////////////
// API

void HDC_Init(
    UART_HandleTypeDef *huart,
    HDC_Feature_Descriptor_t **HDC_Features,
    uint8_t NumFeatures);

uint32_t HDC_Work();

void HDC_Flush(void);


/////////////////////////////////////////
// HDC replies to FeatureCommand requests

void HDC_Reply_Void(
    const uint8_t* pMsgHeader);

void HDC_Reply_From_Pieces(
    const uint8_t FeatureID,
    const uint8_t CmdID,
    const HDC_ReplyErrorCode_t ReplyErrorCode,
    const uint8_t* pMsgPayloadPrefix,
    const size_t MsgPayloadPrefixSize,
    const uint8_t* pMsgPayloadSuffix,
    const size_t MsgPayloadSuffixSize);

void HDC_Reply_Error_WithDescription(
    const HDC_ReplyErrorCode_t ReplyErrorCode,
    const char* ErrorDescription,
    const uint8_t* pMsgHeader);

void HDC_Reply_Error(  // Without error-description string.
    const HDC_ReplyErrorCode_t ReplyErrorCode,
    const uint8_t* pMsgHeader);

//////////////////////////////////////////
// HDC replies to PropertyGet/Set requests

void HDC_Reply_BlobValue(const uint8_t* pBlob, const size_t BlobSize, const uint8_t* pMsgHeader);

void HDC_Reply_BoolValue(const bool value, const uint8_t* pMsgHeader);

void HDC_Reply_UInt8Value(const uint8_t value, const uint8_t* pMsgHeader);

void HDC_Reply_UInt16Value(const uint16_t value, const uint8_t* pMsgHeader);

void HDC_Reply_UInt32Value(const uint32_t value, const uint8_t* pMsgHeader);

void HDC_Reply_Int8Value(const int8_t value, const uint8_t* pMsgHeader);

void HDC_Reply_Int16Value(const int16_t value, const uint8_t* pMsgHeader);

void HDC_Reply_Int32Value(const int32_t value, const uint8_t* pMsgHeader);

void HDC_Reply_FloatValue(const float value, const uint8_t* pMsgHeader);

void HDC_Reply_DoubleValue(const double value, const uint8_t* pMsgHeader);

void HDC_Reply_StringValue(const char* value, const uint8_t* pMsgHeader);

////////////////////
// Raising of events

void HDC_Raise_Event(
    const HDC_Feature_Descriptor_t *hHdcFeature,
    const uint8_t EventID,
    const uint8_t* pEvtPayloadPrefix,
    const size_t EvtPayloadPrefixSize,
    const uint8_t* pEvtPayloadSuffix,
    const size_t EvtPayloadSuffixSize);

void HDC_Raise_Event_Log(
    const HDC_Feature_Descriptor_t *hHdcFeature,
    HDC_EventLogLevel_t logLevel,
    char* logText);


/////////////////////
// FeatureState

void HDC_FeatureStateTransition(
    HDC_Feature_Descriptor_t *hHDC_Feature,
    uint8_t newState);


#endif /* INC_HDC_DEVICE_H_ */
