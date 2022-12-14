/*
 * Host-Device Communication (HDC)
 *
 * Generic device-side implementation.
 */

#ifndef INC_HDC_DEVICE_H_
#define INC_HDC_DEVICE_H_

#include <stdio.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#define HDC_VERSION_STRING "HDC 1.0.0-alpha.12"

/////////////////////////////////////////////////
// Import and validate user-defined configuration
#include "hdc_device_conf.h"

#if (HDC_MAX_REQ_MESSAGE_SIZE > 254)
#error "Current implementation of hdc_device driver can only cope with request-messages of up to 254 bytes!"
#endif

#if (HDC_MAX_REQ_MESSAGE_SIZE < 5)
#error "Configuring HDC_MAX_REQ_MESSAGE_SIZE to less than 5 bytes surely is wrong! (e.g. request of a UINT8 property-setter requires 5 byte)"
#endif

#if (HDC_BUFFER_SIZE_TX < 258)
#warning "Won't be able to compose reply-messages larger than (HDC_BUFFER_SIZE_TX-3) bytes, because composition of multi-packet messages requires at least HDC_BUFFER_SIZE_TX=258 bytes!"
#endif

#if (HDC_BUFFER_SIZE_TX < 8)
#error "Configuring HDC_BUFFER_SIZE_TX to less than 8 bytes surely is wrong! (e.g. reply of a UINT8 property-getter requires 5 byte + 3 byte of the packet)"
#endif

#if (HDC_BUFFER_SIZE_TX > UINT16_MAX)
#error "Current implementation of hdc_device driver can only cope with HDC_BUFFER_SIZE_TX of up to UINT16_MAX bytes!"
#endif


/////////////////////////////////////////////////////////////
// Import HAL driver for the targeted microcontroller
#if !defined  (USE_HAL_DRIVER)
#error "The hdc_device driver currently relies on the HAL drivers to use UART via DMA."
#endif

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


////////////////////////////////////////////////////////////////////////
// Buffer sizes for reception and transmission of data via UART & DMA.
// Computed based on private configuration of hdc_device driver provided by the hdc_device_conf.h header file.
#define HDC_PACKET_OVERHEAD 3      // PayloadSize ; Checksum ; Terminator
#define HDC_MAX_REQ_PACKET_SIZE (HDC_MAX_REQ_MESSAGE_SIZE + HDC_PACKET_OVERHEAD)
#define HDC_BUFFER_SIZE_RX HDC_MAX_REQ_PACKET_SIZE

// Forward declaration of HDC structs and their typedefs,
// which we need in the following function-pointer typedefs
struct HDC_Descriptor_Feature_struct;
typedef struct HDC_Descriptor_Feature_struct HDC_Descriptor_Feature_t;

struct HDC_Descriptor_Property_struct;
typedef struct HDC_Descriptor_Property_struct HDC_Descriptor_Property_t;

// Improve readability of function-pointer types
typedef bool (*HDC_MessageHandler_t)(
    const uint8_t* pMessage,
    const uint8_t Size);

typedef void (*HDC_CommandHandler_t)(
    const HDC_Descriptor_Feature_t *hHDC_Feature,
    const uint8_t* pRequestMessage,
    const uint8_t Size);

typedef void (*HDC_PropertyValueGetter_t)(
    const HDC_Descriptor_Feature_t *hHDC_Feature,
    const HDC_Descriptor_Property_t *hHDC_Property,
    const uint8_t* pRequestMessage,
    const uint8_t RequestMessageSize);

typedef void (*HDC_PropertyValueSetter_t)(
    HDC_Descriptor_Feature_t *hHDC_Feature,
    const HDC_Descriptor_Property_t *hHDC_Property,
    const uint8_t* pRequestMessage,
    const uint8_t RequestMessageSize);


///////////////////////////////
// Magic numbers defined by the HDC specification
#define HDC_PACKET_TERMINATOR 0x1E


//////////////////////////////
// Enums

typedef enum {
  HDC_MessageTypeID_Meta = 0xF0,
  HDC_MessageTypeID_Echo = 0xF1,
  HDC_MessageTypeID_Command = 0xF2,
  HDC_MessageTypeID_Event = 0xF3,
} HDC_MessageTypeID_t;

typedef enum {
  HDC_MetaID_HdcVersion = 0xF0,
  HDC_MetaID_MaxReq = 0xF1,
  HDC_MetaID_IdlJson = 0xF2,
} HDC_MetaID_t;


typedef enum {
  HDC_FeatureID_Core = 0x00,
} HDC_FeatureID_t;

typedef enum {
  HDC_CommandID_GetPropertyValue = 0xF0,
  HDC_CommandID_SetPropertyValue = 0xF1,
} HDC_CommandID_t;

typedef enum {
  // The ID values (roughly) obey the following mnemonic system:
  //
  // Upper Nibble: Kind of DataType
  //       0x0_ --> Unsigned integer number
  //       0x1_ --> Signed integer number
  //       0x2_ --> Floating point number
  //       0xA_ --> UTF-8 encoded string (Always variable size: 0xAF)
  //       0xB_ --> Binary data (Either variable size 0xBF, or boolean 0xB1)
  //       0xD_ --> DataType (Currently only 0xD1, encoding for DataType itself)
  //
  // Lower Nibble: Size of the data type, given in number of bytes
  //               i.e. 0x14 --> INT32, whose size is 4 bytes
  //               (Exception to the rule: 0x_F denotes a variable size DataType)
  //               (Special case 0xB1 --> BOOL size is 1 byte, although only using 1 bit)

  HDC_DataTypeID_UINT8 = 0x01,
  HDC_DataTypeID_UINT16 = 0x02,
  HDC_DataTypeID_UINT32 = 0x04,
  HDC_DataTypeID_INT8 = 0x11,
  HDC_DataTypeID_INT16 = 0x12,
  HDC_DataTypeID_INT32 = 0x14,
  HDC_DataTypeID_FLOAT = 0x24,
  HDC_DataTypeID_DOUBLE = 0x28,
  HDC_DataTypeID_UTF8 = 0xAF,
  HDC_DataTypeID_BOOL = 0xB1,
  HDC_DataTypeID_BLOB = 0xBF,
  HDC_DataTypeID_DTYPE = 0xD1,
} HDC_DataTypeID_t;


typedef enum {
  HDC_PropertyID_LogEventThreshold = 0xF0,
  HDC_PropertyID_FeatureState = 0xF1,
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
  HDC_DataTypeID_t dtype;
  char* name;
  char* doc;
} HDC_Descriptor_Arg_t;

typedef struct {
  HDC_DataTypeID_t dtype;
  char* name;
  char* doc;
} HDC_Descriptor_Ret_t;

typedef struct {
  uint8_t id;
  char* name;
  char* doc;
} HDC_Descriptor_Exc_t;

extern const HDC_Descriptor_Exc_t HDC_Descriptor_Exc_CommandFailed;
extern const HDC_Descriptor_Exc_t HDC_Descriptor_Exc_UnknownFeature;
extern const HDC_Descriptor_Exc_t HDC_Descriptor_Exc_UnknownCommand;
extern const HDC_Descriptor_Exc_t HDC_Descriptor_Exc_InvalidArgs;
extern const HDC_Descriptor_Exc_t HDC_Descriptor_Exc_NotNow;
extern const HDC_Descriptor_Exc_t HDC_Descriptor_Exc_UnknownProperty;
extern const HDC_Descriptor_Exc_t HDC_Descriptor_Exc_ReadOnlyProperty;

typedef struct {
  uint8_t CommandID;
  char* CommandName;
  HDC_CommandHandler_t CommandHandler;
  char* CommandDescription;
  const HDC_Descriptor_Arg_t *arg1;
  const HDC_Descriptor_Arg_t *arg2;
  const HDC_Descriptor_Arg_t *arg3;
  const HDC_Descriptor_Arg_t *arg4;
  const HDC_Descriptor_Ret_t *ret1;
  const HDC_Descriptor_Ret_t *ret2;
  const HDC_Descriptor_Ret_t *ret3;
  const HDC_Descriptor_Ret_t *ret4;
  const HDC_Descriptor_Exc_t **raises;
  uint8_t numraises;
} HDC_Descriptor_Command_t;


typedef struct {
  uint8_t EventID;
  char* EventName;
  char* EventDescription;
  const HDC_Descriptor_Arg_t *arg1;
  const HDC_Descriptor_Arg_t *arg2;
  const HDC_Descriptor_Arg_t *arg3;
  const HDC_Descriptor_Arg_t *arg4;
} HDC_Descriptor_Event_t;


typedef struct HDC_Descriptor_Property_struct {
  uint8_t PropertyID;
  char* PropertyName;
  HDC_DataTypeID_t PropertyDataType;
  bool PropertyIsReadonly;
  HDC_PropertyValueGetter_t GetPropertyValue;
  HDC_PropertyValueSetter_t SetPropertyValue;
  void *pValue;
  size_t ValueSize; // Only required for PropertyDataType=HDC_DataTypeID_BLOB, will otherwise be overridden by size of PropertyDataType
  char* PropertyDescription;
} HDC_Descriptor_Property_t;

typedef struct {
  uint8_t id;
  char* name;
  char* doc;
} HDC_Descriptor_State_t;

typedef struct HDC_Descriptor_Feature_struct {
  uint8_t FeatureID;
  char* FeatureName;
  char* FeatureClassName;
  char* FeatureClassVersion;
  char* FeatureDescription;

  const HDC_Descriptor_State_t** States;
  uint8_t NumStates;

  const HDC_Descriptor_Command_t** Commands;
  uint8_t NumCommands;

  const HDC_Descriptor_Event_t** Events;
  uint8_t NumEvents;

  const HDC_Descriptor_Property_t** Properties;
  uint8_t NumProperties;

  // Optional pointer to the API handle of a feature.
  // e.g. HDC_Feature_AxisX.hAPI points to Axis_HandleTypeDef
  // Mainly used by Command and Get/SetParameterValue handlers, who are
  // just given a HDC-feature descriptor and need to infer the API handler.
  void* hAPI;


  //////////////////////////////////////
  // Mandatory and mutable properties
  uint8_t LogEventThreshold;
  uint8_t FeatureState;


} HDC_Descriptor_Feature_t;


///////////////////////////////////////
// Interrupt handlers and redirection

void HDC_RxEventCallback(UART_HandleTypeDef *huart, uint16_t Size);  // Must be called from HAL_UARTEx_RxEventCallback
void HDC_TxCpltCallback(UART_HandleTypeDef *huart);  // Must be called from HAL_UART_TxCpltCallback


/////////////////////////////////////////////////////////////////////
// API

void HDC_Init(
    UART_HandleTypeDef *huart,
    HDC_Descriptor_Feature_t **HDC_Features,
    uint8_t NumFeatures);

uint32_t HDC_Work();

void HDC_Flush(void);


/////////////////////////////////////////
// HDC replies to Command requests

void HDC_CmdReply_Void(
    const uint8_t* pRequestMessage);

void HDC_CmdReply_From_Pieces(
    const uint8_t FeatureID,
    const uint8_t CmdID,
    const uint8_t ExcID,
    const uint8_t* pMsgPayloadPrefix,
    const size_t MsgPayloadPrefixSize,
    const uint8_t* pMsgPayloadSuffix,
    const size_t MsgPayloadSuffixSize);

void HDC_CmdReply_Error_WithDescription(
    const uint8_t ExcID,
    const char* ErrorDescription,
    const uint8_t* pRequestMessage);

void HDC_CmdReply_Error(  // Without error-description string.
    const uint8_t ExcID,
    const uint8_t* pRequestMessage);

//////////////////////////////////////////
// HDC replies to PropertyGet/Set requests

void HDC_CmdReply_BlobValue(const uint8_t* pBlob, const size_t BlobSize, const uint8_t* pRequestMessage);

void HDC_CmdReply_BoolValue(const bool value, const uint8_t* pRequestMessage);

void HDC_CmdReply_UInt8Value(const uint8_t value, const uint8_t* pRequestMessage);

void HDC_CmdReply_UInt16Value(const uint16_t value, const uint8_t* pRequestMessage);

void HDC_CmdReply_UInt32Value(const uint32_t value, const uint8_t* pRequestMessage);

void HDC_CmdReply_Int8Value(const int8_t value, const uint8_t* pRequestMessage);

void HDC_CmdReply_Int16Value(const int16_t value, const uint8_t* pRequestMessage);

void HDC_CmdReply_Int32Value(const int32_t value, const uint8_t* pRequestMessage);

void HDC_CmdReply_FloatValue(const float value, const uint8_t* pRequestMessage);

void HDC_CmdReply_DoubleValue(const double value, const uint8_t* pRequestMessage);

void HDC_CmdReply_StringValue(const char* value, const uint8_t* pRequestMessage);

void HDC_CmdReply_DTypeValue(const HDC_DataTypeID_t value, const uint8_t* pRequestMessage);

////////////////////
// Raising of events

void HDC_EvtMsg(
    const HDC_Descriptor_Feature_t *hHdcFeature,
    const uint8_t EventID,
    const uint8_t* pEvtPayloadPrefix,
    const size_t EvtPayloadPrefixSize,
    const uint8_t* pEvtPayloadSuffix,
    const size_t EvtPayloadSuffixSize);

void HDC_EvtMsg_Log(
    const HDC_Descriptor_Feature_t *hHdcFeature,
    HDC_EventLogLevel_t logLevel,
    char* logText);


/////////////////////
// FeatureState

void HDC_FeatureStateTransition(
    HDC_Descriptor_Feature_t *hHDC_Feature,
    uint8_t newState);


#endif /* INC_HDC_DEVICE_H_ */
