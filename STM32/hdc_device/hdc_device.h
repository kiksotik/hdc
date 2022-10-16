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
#elif defined(STM32G431KBTx)  // As on NUCLEO-G431KB
#include "stm32g4xx_hal.h"
#else
#error "The hdc_device driver doesn't know about the microcontroller type your are targeting. Please modify hdc_device.h if you know what you are doing. Also please send a pull request if it turns out the driver works on other MCU's as well!"
#endif

// Buffer sizes for reception and transmission of data via UART & DMA.
// Computed based on private configuration of hdc_device driver provided by the hdc_device_conf.h header file.
#define HDC_PACKAGE_OVERHEAD 3      // PayloadSize ; Checksum ; Terminator
#define HDC_MAX_REQ_PACKAGE_SIZE (HDC_MAX_REQ_MESSAGE_SIZE + HDC_PACKAGE_OVERHEAD)
#define HDC_BUFFER_SIZE_RX HDC_MAX_REQ_PACKAGE_SIZE

// Forward declaration of HDC structs which we need in the following function-pointer typedef
struct HDC_Feature_struct;
struct HDC_Property_struct;

// Improve readability of function-pointer types
typedef void (*HDC_RequestHandler_t)(
		const struct HDC_Feature_struct *hHDC_Feature,
		const uint8_t* RequestMessage,
		const uint8_t Size);

typedef void (*HDC_PropertyValueGetter_t)(
		const struct HDC_Feature_struct *hHDC_Feature,
		const struct HDC_Property_struct *hHDC_Property,
		const uint8_t* RequestMessage,
		const uint8_t RequestMessageSize);

typedef void (*HDC_PropertyValueSetter_t)(
		struct HDC_Feature_struct *hHDC_Feature,
		const struct HDC_Property_struct *hHDC_Property,
		const uint8_t* RequestMessage,
		const uint8_t RequestMessageSize);


///////////////////////////////
// Magic numbers defined by the HDC specification
#define HDC_PACKAGE_TERMINATOR 0x1E
#define HDC_FEATUREID_CORE 0x00


//////////////////////////////
// Enums

typedef enum {
	HDC_MessageType_COMMAND_ECHO = 0xCE,
	HDC_MessageType_COMMAND_FEATURE = 0xCF,
	HDC_MessageType_EVENT_FEATURE = 0xEF,
} HDC_MessageType_t;

typedef enum {
	HDC_ReplyErrorCode_NO_ERROR = 0x00,
	HDC_ReplyErrorCode_UNKNOWN_FEATURE = 0x01,
	HDC_ReplyErrorCode_UNKNOWN_COMMAND = 0x02,
	HDC_ReplyErrorCode_INCORRECT_COMMAND_ARGUMENTS = 0x03,
	HDC_ReplyErrorCode_COMMAND_NOT_ALLOWED_NOW = 0x04,
	HDC_ReplyErrorCode_COMMAND_FAILED = 0x05,
	HDC_ReplyErrorCode_UNKNOWN_PROPERTY = 0xF0,
	HDC_ReplyErrorCode_INVALID_PROPERTY_VALUE = 0xF1,
	HDC_ReplyErrorCode_PROPERTY_IS_READONLY = 0xF2,
	HDC_ReplyErrorCode_UNKNOWN_EVENT = 0xF3
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

	HDC_DataType_UINT8 = 0x01,
	HDC_DataType_UINT16 = 0x02,
	HDC_DataType_UINT32 = 0x04,
	HDC_DataType_INT8 = 0x11,
	HDC_DataType_INT16 = 0x12,
	HDC_DataType_INT32 = 0x14,
	HDC_DataType_FLOAT = 0x24,
	HDC_DataType_DOUBLE = 0x28,
	HDC_DataType_BOOL = 0xB0,
	HDC_DataType_BLOB = 0xBF,
	HDC_DataType_UTF8 = 0xFF
} HDC_DataType_t;

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
	HDC_RequestHandler_t HandleRequest;
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
	HDC_DataType_t PropertyDataType;
	bool PropertyIsReadonly;
	HDC_PropertyValueGetter_t GetPropertyValue;
	HDC_PropertyValueSetter_t SetPropertyValue;
	void *pValue;
	size_t ValueSize; // Only required for PropertyDataType=HDC_DataType_BLOB, will otherwise be overridden by size of PropertyDataType
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

///////////////////////////////
// API

void HDC_Init(
		UART_HandleTypeDef *huart,
		HDC_Feature_Descriptor_t **HDC_Features,
		uint8_t NumFeatures);

uint32_t HDC_UpdateState();

void HDC_Flush(void);

void HDC_FeatureStateTransition(HDC_Feature_Descriptor_t *hFeature, uint8_t newState);

void HDC_Reply_Raw(
		const uint8_t* pMsg,
		const uint16_t MsgSize);

void HDC_Reply_BlobValue(
		const uint8_t* pBlob,
		const uint16_t BlobSize,
		const uint8_t* pMsgHeader,
		const HDC_ReplyErrorCode_t ReplyErrorCode);

void HDC_Reply_Error_WithDescription(
		const HDC_ReplyErrorCode_t ReplyErrorCode,
		const char* ErrorDescription,
		const uint8_t* pMsgHeader);

void HDC_Reply_Error(
		const HDC_ReplyErrorCode_t ReplyErrorCode,
		const uint8_t* pMsgHeader);

void HDC_Reply_BoolValue(
		const bool value,
		const uint8_t* pMsgHeader);

void HDC_Reply_UInt8Value(
		const uint8_t value,
		const uint8_t* pMsgHeader);

void HDC_Reply_UInt16Value(
		const uint16_t value,
		const uint8_t* pMsgHeader);

void HDC_Reply_UInt32Value(
		const uint32_t value,
		const uint8_t* pMsgHeader);

void HDC_Reply_Int8Value(
		const int8_t value,
		const uint8_t* pMsgHeader);

void HDC_Reply_Int16Value(
		const int16_t value,
		const uint8_t* pMsgHeader);

void HDC_Reply_Int32Value(
		const int32_t value,
		const uint8_t* pMsgHeader);

void HDC_Reply_FloatValue(
		const float value,
		const uint8_t* pMsgHeader);

void HDC_Reply_DoubleValue(
		const double value,
		const uint8_t* pMsgHeader);

void HDC_Reply_StringValue(
		const char* value,
		const uint8_t* pMsgHeader);

void HDC_Reply_Event_Log(
		const HDC_Feature_Descriptor_t *hHdcFeature,
		HDC_EventLogLevel_t logLevel,
		char* logText);

void HDC_GetTxBufferWithCapacityForAtLeast(uint16_t capacity, uint8_t **pBuffer, uint16_t **pNumBytesInBuffer);

//////////////////////////////////////
// Descriptor instances that must be
// implemented by the core feature.

extern const HDC_Property_Descriptor_t HDC_MandatoryCoreProperty_MaxReqMsgSize;
extern const HDC_Property_Descriptor_t HDC_MandatoryCoreProperty_AvailableFeatures;


#endif /* INC_HDC_DEVICE_H_ */
