
 /*
 * Host-Device Communication (HDC)
 *
 * Generic device-side implementation for STM32 microcontrollers.
 *
 *
 * Copyright (c) 2022 Axel T. J. Rohde
 *
 * This software is licensed under terms that can be found in the LICENSE file
 * in the root directory of this software component.
 */


#include "hdc_device.h"

#define NUM_MANDATORY_COMMANDS 10
#define NUM_MANDATORY_EVENTS 2
#define NUM_MANDATORY_PROPERTIES 10
#define NUM_MANDATORY_PROPERTIES_OF_CORE_FEATURE 2

///////////////////////////////////////
// Error handler implemented
// in main application
extern void Error_Handler(void);


/////////////////////////
// Macro utilities
#define CONSTRAIN(x, lower, upper) \
  ((x) < (lower) ? (lower) : ((x) > (upper) ? (upper) : (x)))

/////////////////////////
// Forward declarations
const HDC_Command_Descriptor_t *HDC_MandatoryCommands[];
const HDC_Event_Descriptor_t *HDC_MandatoryEvents[];
const HDC_Property_Descriptor_t *HDC_MandatoryProperties[];
const HDC_Property_Descriptor_t *HDC_MandatoryPropertiesOfCoreFeature[];
void HDC_ProcessRxPacket(const uint8_t *packet);

/////////////////////////////////
// Handle of the HDC singleton
struct HDC_struct {

	// Configuration
	UART_HandleTypeDef* huart;

	// A single buffer for receiving request from the HDC-host.
	// We do not expect more than a single request until we reply to it.
	// We only expect single-packet messages of at most HDC_MAX_REQ_MESSAGE_SIZE bytes.
	uint8_t BufferRx[HDC_BUFFER_SIZE_RX];
	volatile uint16_t NumBytesInBufferRx;

	// Two buffers for sending replies and events to the HDC-host.
	// While one is being sent via DMA, the other is being composed.
	uint8_t BufferTx[2][HDC_BUFFER_SIZE_TX];
	uint16_t NumBytesInBufferTx[2];

	//
	HDC_Feature_Descriptor_t** Features;
	uint8_t NumFeatures;

	// State
	bool isInitialized;
	volatile bool isDmaRxComplete;
	volatile bool isDmaTxComplete;
	uint8_t currentDmaBufferTx;

	// Issues to be reported via LogEvent messages on the next possible occasion
	uint16_t PendingEvent_ReadingFrameError;

} hHDC = { 0 };

void HDC_Init(UART_HandleTypeDef *huart, HDC_Feature_Descriptor_t **HDC_Features, uint8_t NumFeatures) {

	hHDC.huart = huart;
	hHDC.Features = HDC_Features;
	hHDC.NumFeatures = NumFeatures;

	hHDC.NumBytesInBufferRx = 0;
	hHDC.NumBytesInBufferTx[0] = 0;
	hHDC.NumBytesInBufferTx[1] = 0;

	hHDC.currentDmaBufferTx = 0;

	hHDC.isDmaRxComplete = false;
	hHDC.isDmaTxComplete = true;

	hHDC.PendingEvent_ReadingFrameError = 0;

	// Start reception of the first chunk
	if (HAL_UART_Receive_DMA(hHDC.huart, hHDC.BufferRx, HDC_BUFFER_SIZE_RX) != HAL_OK)
		Error_Handler();
	// We need to explicitly enable the IDLE interrupt!
	// http://www.bepat.de/2020/12/02/stm32f103c8-uart-with-dma-buffer-and-idle-detection/
	__HAL_UART_ENABLE_IT(hHDC.huart, UART_IT_IDLE);

	hHDC.isInitialized = true;
}

uint8_t* HDC_ProcessRxBuffer() {
	uint8_t *packet_candidate = hHDC.BufferRx;
	uint16_t chunk_size = hHDC.NumBytesInBufferRx;

	hHDC.PendingEvent_ReadingFrameError = 0;

	// Search for package directly in the RX buffer
	while (chunk_size >= HDC_PACKAGE_OVERHEAD) {
		uint8_t payload_size = packet_candidate[0];

		if (payload_size > HDC_MAX_REQ_MESSAGE_SIZE) {
			// Might be a reading-frame error. Skip first byte and try again.
			packet_candidate += 1;
			chunk_size -= 1;
			hHDC.PendingEvent_ReadingFrameError += 1;
			continue; // Try to de-queue another message from the remainder of the chunk
		}

		if (payload_size + HDC_PACKAGE_OVERHEAD > chunk_size)
			return NULL; // Seems the chunk is not yet a full package. Give further bytes a chance to arrive!

		uint16_t terminatorIndex = payload_size + 2;
		if (packet_candidate[terminatorIndex] == HDC_PACKAGE_TERMINATOR) {
			uint8_t checksum = 0;
			for (uint16_t i=1; i < terminatorIndex; i++)
				checksum += packet_candidate[i];
			if (checksum == 0) {

				// We found a full packet!

				// Do NOT try to de-queue any further packet from
				// the remainder of the chunk, because HDC-host
				// should not be sending any further request
				// before the previous one has not been processed.

				// Sanity check whether there's any crap beyond this packet
				// and report it as being a reading-frame-error
				hHDC.PendingEvent_ReadingFrameError += chunk_size - (payload_size + HDC_PACKAGE_OVERHEAD);

				return packet_candidate;
			} else {
				// Most likely a reading-frame error. Skip first byte and try again.
				packet_candidate += 1;
				chunk_size -= 1;
				hHDC.PendingEvent_ReadingFrameError += 1;
				continue;
			}
		} else {
			// Most likely a reading-frame error. Skip first byte and try again.
			packet_candidate += 1;
			chunk_size -= 1;
			hHDC.PendingEvent_ReadingFrameError += 1;
			continue;
		}
	}

	// Chunk is too small to be any packet Give further bytes a chance to arrive!
	return NULL;
}

uint32_t HDC_UpdateState() {

	// Did we receive a chunk?
	if (hHDC.isDmaRxComplete) {

		// Attempt to get a single, full packet out of the chunk of data received
		uint8_t *packet = HDC_ProcessRxBuffer(hHDC);

		if (packet != NULL)
			HDC_ProcessRxPacket(packet);

		if (packet != NULL
				|| hHDC.PendingEvent_ReadingFrameError > 0
				|| hHDC.NumBytesInBufferRx == HDC_BUFFER_SIZE_RX)
		{
			// Usually the DMA transfer does not reach the RxCplt interrupt, which is
			// why we have to abort it before starting the next one.
			if ( HAL_UART_GetState(hHDC.huart) & HAL_UART_STATE_BUSY_RX)
				HAL_UART_AbortReceive(hHDC.huart);

			// Start receiving next request.
			// Note how on processing the preceding request we already composed
			// its reply, but we haven't actually sent it to the HDC-host yet, which
			// is why at this point we don't need to worry for the HDC-host to be sending its next request.
			hHDC.NumBytesInBufferRx = 0;
			if (HAL_UART_Receive_DMA(hHDC.huart, hHDC.BufferRx, HDC_BUFFER_SIZE_RX) != HAL_OK)
				Error_Handler();
		}

		if (hHDC.PendingEvent_ReadingFrameError > 0) {
			HDC_Reply_Event_Log(NULL, HDC_EventLogLevel_WARNING, "Reading-frame-errors detected while parsing request message on device.");
			hHDC.PendingEvent_ReadingFrameError = 0;
		}

		hHDC.isDmaRxComplete = false;
	}

	// Is there anything waiting to be sent? (And did we complete the previous transmission?)
	uint8_t indexOfBufferCurrentlyBeingComposed = hHDC.currentDmaBufferTx == 0 ? 1 : 0;  // The buffer not being sent is the one being composed.
	if (hHDC.isDmaTxComplete && hHDC.NumBytesInBufferTx[indexOfBufferCurrentlyBeingComposed] > 0) {

		// Clear the buffer that was already sent via DMA
		hHDC.NumBytesInBufferTx[hHDC.currentDmaBufferTx] = 0;

		// Exchange Tx buffers
		if (hHDC.currentDmaBufferTx == 0)
			hHDC.currentDmaBufferTx = 1;
		else
			hHDC.currentDmaBufferTx = 0;

		// Start transmitting via DMA the buffer containing the replies that have been composed
		hHDC.isDmaTxComplete = false;
		if (HAL_UART_Transmit_DMA(hHDC.huart, hHDC.BufferTx[hHDC.currentDmaBufferTx], hHDC.NumBytesInBufferTx[hHDC.currentDmaBufferTx]) != HAL_OK)
			Error_Handler();
	}

	return 0; // Update an every possible occasion
}

// Interrupt handler that must be called from HAL_UART_RxCpltCallback
void HDC_RxCpltCallback(UART_HandleTypeDef *huart) {
	if (huart != hHDC.huart)
		return;

	// Note how this Callback is mainly being called due to IDLE events that we are redirecting here.
	// We actually never expect to receive a "complete" buffer, because buffer is larger than the largest packet we expect to ever be sent.
	// We instead attempt to parse a packet on every UART IDLE event.
	hHDC.NumBytesInBufferRx = HDC_BUFFER_SIZE_RX - (uint16_t)hHDC.huart->hdmarx->Instance->CNDTR;
	if (hHDC.NumBytesInBufferRx > 0)  // To skip the pointless IDLE event that happens on starting each reception.
		hHDC.isDmaRxComplete = true;
	__HAL_UART_CLEAR_IDLEFLAG(hHDC.huart);  // Make sure IDLE flag is cleared again. We lazy bastards do not care whether it was set to begin with. :o)
}

// Interrupt handler that must be called from HAL_UART_TxCpltCallback
void HDC_TxCpltCallback(UART_HandleTypeDef *huart) {
	if (huart != hHDC.huart)
		return;

	hHDC.isDmaTxComplete = true;
}

// Must be called from the USARTx_IRQHandler(), to redirect UART-IDLE events into
// the HDC_RxCpltCallback() handler, for it to notice that a request is complete.
// See http://www.bepat.de/2020/12/02/stm32f103c8-uart-with-dma-buffer-and-idle-detection/
void HDC_IrqRedirection_UartIdle(void) {
	if(__HAL_UART_GET_FLAG(hHDC.huart, UART_FLAG_IDLE))
		HDC_RxCpltCallback(hHDC.huart);
}


////////////////////////////////////////////
// Utility methods
HDC_Feature_Descriptor_t* HDC_GetFeature(const uint8_t featureID) {
	for (int i=0 ; i < hHDC.NumFeatures; i++) {
		if (hHDC.Features[i]->FeatureID == featureID)
			return hHDC.Features[i];
	}
	return NULL;
}

const HDC_Command_Descriptor_t* HDC_GetCommand(const HDC_Feature_Descriptor_t *feature, const uint8_t commandID) {
	for (uint8_t i=0; i< feature->NumCommands;i++)
		if (feature->Commands[i]->CommandID == commandID)
			return feature->Commands[i];

	for (uint8_t i=0; i<NUM_MANDATORY_COMMANDS;i++)
			if (HDC_MandatoryCommands[i]->CommandID == commandID)
				return HDC_MandatoryCommands[i];
	return NULL;
}

const HDC_Event_Descriptor_t* HDC_GetEvent(const HDC_Feature_Descriptor_t *feature, const uint8_t eventID) {
	for (uint8_t i = 0; i < feature->NumEvents; i++)
		if (feature->Events[i]->EventID == eventID)
			return feature->Events[i];

	for (uint8_t i=0; i<NUM_MANDATORY_EVENTS ; i++)
			if (HDC_MandatoryEvents[i]->EventID == eventID)
				return HDC_MandatoryEvents[i];
	return NULL;
}

const HDC_Property_Descriptor_t* HDC_GetProperty(const HDC_Feature_Descriptor_t *hFeature, const uint8_t propertyID) {

	for (int i=0 ; i < hFeature->NumProperties ; i++)
		if (hFeature->Properties[i]->PropertyID == propertyID)
			return hFeature->Properties[i];

	for (uint8_t i=0; i<NUM_MANDATORY_PROPERTIES ; i++)
		if (HDC_MandatoryProperties[i]->PropertyID == propertyID)
			return HDC_MandatoryProperties[i];

	if (hFeature->FeatureID == HDC_FEATUREID_CORE) {
		for (uint8_t i=0; i<NUM_MANDATORY_PROPERTIES_OF_CORE_FEATURE ; i++)
			if (HDC_MandatoryPropertiesOfCoreFeature[i]->PropertyID == propertyID)
				return HDC_MandatoryPropertiesOfCoreFeature[i];
	}

	return NULL;
}

void HDC_GetTxBufferWithCapacityForAtLeast(uint16_t capacity, uint8_t **pBuffer, uint16_t **pNumBytesInBuffer) {
	assert_param(capacity <= HDC_BUFFER_SIZE_TX);

	// The buffer not being transmitted is the one we are currently composing into.
	uint8_t indexOfBufferBeingComposed = hHDC.currentDmaBufferTx == 0 ? 1 : 0;

	// Is there enough space left in the current composition buffer?
	if (hHDC.NumBytesInBufferTx[indexOfBufferBeingComposed] + capacity <= HDC_BUFFER_SIZE_TX) {
		*pBuffer = hHDC.BufferTx[indexOfBufferBeingComposed];
		*pNumBytesInBuffer = &hHDC.NumBytesInBufferTx[indexOfBufferBeingComposed];
		return;
	}

	// Wait for current transmission to complete and switch buffers
	while (!hHDC.isDmaTxComplete);

	// Clear the buffer that was already sent via DMA
	hHDC.NumBytesInBufferTx[hHDC.currentDmaBufferTx] = 0;

	// Switch Tx buffers
	if (hHDC.currentDmaBufferTx == 0)
		hHDC.currentDmaBufferTx = 1;
	else
		hHDC.currentDmaBufferTx = 0;

	// Start transmitting via DMA the buffer containing the replies that have been composed so far
	hHDC.isDmaTxComplete = false;
	if (HAL_UART_Transmit_DMA(hHDC.huart, hHDC.BufferTx[hHDC.currentDmaBufferTx], HDC_BUFFER_SIZE_TX) != HAL_OK)
		Error_Handler();

	// Use the other buffer for composing further reply messages
	indexOfBufferBeingComposed = hHDC.currentDmaBufferTx == 0 ? 1 : 0;

	*pBuffer = hHDC.BufferTx[indexOfBufferBeingComposed];
	*pNumBytesInBuffer = &hHDC.NumBytesInBufferTx[indexOfBufferBeingComposed];
}

void HDC_Flush(void) {
	// By requesting the maximum capacity, we ensure that any messages
	// in the current composition buffer are being sent now.
	uint8_t *pBuffer = 0;
	uint16_t *pNumBytesInBuffer = 0;
	HDC_GetTxBufferWithCapacityForAtLeast(HDC_BUFFER_SIZE_TX, &pBuffer, &pNumBytesInBuffer);

	// Wait for current transmission to complete
	uint32_t timeout = HAL_GetTick() + 100;
	while (!hHDC.isDmaTxComplete) {
		if (HAL_GetTick() > timeout) {
			// This might be a handy spot to set a break-point during debug sessions.
			// Note how calling the Error_Handler() might cause infinite recursion.
			return;
		}
	}
}

void HDC_Reply_EmptyPacket() {
	const uint8_t PktSize = 0;		// Actually just the size of the packet's payload.

	uint8_t *pBuffer = 0;
	uint16_t *pNumBytesInBuffer = 0;
	HDC_GetTxBufferWithCapacityForAtLeast(PktSize + HDC_PACKAGE_OVERHEAD, &pBuffer, &pNumBytesInBuffer);

	pBuffer[(*pNumBytesInBuffer)++] = PktSize;					// Payload size
	pBuffer[(*pNumBytesInBuffer)++] = 0x00;						// Checksum
	pBuffer[(*pNumBytesInBuffer)++] = HDC_PACKAGE_TERMINATOR;	// Terminator
}

void HDC_Reply_Raw(const uint8_t* pMsg, const uint16_t MsgSize) {
	uint16_t nMsg = 0;
	uint8_t PktSize;
	do {
		PktSize = MsgSize - nMsg < 255 ? MsgSize - nMsg : 255;  // Actually just the size of the packet's payload.
		uint8_t *pBuffer = 0;
		uint16_t *pNumBytesInBuffer = 0;
		HDC_GetTxBufferWithCapacityForAtLeast(PktSize + HDC_PACKAGE_OVERHEAD, &pBuffer, &pNumBytesInBuffer);
		uint8_t checksum = 0;
		pBuffer[(*pNumBytesInBuffer)++] = PktSize;
		for (uint8_t nPkt=0; nPkt<PktSize; nPkt++){
			checksum += pMsg[nMsg];
			pBuffer[(*pNumBytesInBuffer)++] = pMsg[nMsg++];
		}
		pBuffer[(*pNumBytesInBuffer)++] = (uint8_t)0xFF - checksum + 1;
		pBuffer[(*pNumBytesInBuffer)++] = HDC_PACKAGE_TERMINATOR;
	} while (nMsg < MsgSize);

	if (PktSize==255) {
		// Last packet had a payload of exactly 255 bytes.
		// We must therefore send an empty packet, to signal
		// that the multi-package message is complete.
		HDC_Reply_EmptyPacket(hHDC);
	}

}

void HDC_Reply_BlobValue(
		const uint8_t* pBlob,
		const uint16_t BlobSize,
		const uint8_t* pMsgHeader,
		const HDC_ReplyErrorCode_t ReplyErrorCode)
{
	const uint8_t MsgHeaderSize = 4; // MessageType ; FeatureID ; CommandID ; ReplyErrorCode
	const uint16_t MsgSize = MsgHeaderSize + BlobSize;
	uint8_t PktSize;
	uint16_t nMsg = 0;
	do {
		PktSize = MsgSize - nMsg < 255 ? MsgSize - nMsg : 255;  // Actually just the packet's payload size.
		uint8_t *pBuffer = 0;
		uint16_t *pNumBytesInBuffer = 0;
		HDC_GetTxBufferWithCapacityForAtLeast(PktSize + HDC_PACKAGE_OVERHEAD, &pBuffer, &pNumBytesInBuffer);
		uint8_t checksum = 0;
		pBuffer[(*pNumBytesInBuffer)++] = PktSize;
		uint8_t nPkt=0;
		while (nMsg < MsgHeaderSize-1) {
			checksum += pMsgHeader[nMsg];
			pBuffer[(*pNumBytesInBuffer)++] = pMsgHeader[nMsg];
			nMsg++;
			nPkt++;
		}
		if (nMsg == MsgHeaderSize-1) {
			checksum += (uint8_t)ReplyErrorCode;
			pBuffer[(*pNumBytesInBuffer)++] = (uint8_t)ReplyErrorCode;
			nMsg++;
			nPkt++;
		}
		while (nPkt < PktSize) {
			const uint16_t nBlob = nMsg - MsgHeaderSize;
			checksum += pBlob[nBlob];
			pBuffer[(*pNumBytesInBuffer)++] = pBlob[nBlob];
			nMsg++;
			nPkt++;
		}
		pBuffer[(*pNumBytesInBuffer)++] = (uint8_t)0xFF - checksum + 1;
		pBuffer[(*pNumBytesInBuffer)++] = HDC_PACKAGE_TERMINATOR;
	} while (nMsg < MsgSize);

	if (PktSize==255) {
		// Last packet had a payload of exactly 255 bytes.
		// We must therefore send an empty packet, to signal
		// that the multi-package message is complete.
		HDC_Reply_EmptyPacket();
	}
}

void HDC_Reply_Error_WithDescription(
		const HDC_ReplyErrorCode_t ReplyErrorCode,
		const char* ErrorDescription,
		const uint8_t* pMsgHeader)
{
	assert_param(ReplyErrorCode != HDC_ReplyErrorCode_NO_ERROR || ErrorDescription == NULL);  // It is only legal to include a description in the reply when an error happened. When no error happened, we must reply as expected for the given command!

	if (ErrorDescription == NULL)  // The error description is optional
		return HDC_Reply_BlobValue(NULL, 0, pMsgHeader, ReplyErrorCode);

	uint32_t msgLength = strlen(ErrorDescription);
	if (msgLength > UINT16_MAX)
		msgLength = UINT16_MAX;

	HDC_Reply_BlobValue((uint8_t*) ErrorDescription, (uint16_t)msgLength, pMsgHeader, ReplyErrorCode);
}

void HDC_Reply_Error(
		const HDC_ReplyErrorCode_t ReplyErrorCode,
		const uint8_t* pMsgHeader)
{
	HDC_Reply_Error_WithDescription(ReplyErrorCode, NULL, pMsgHeader);
}

void HDC_Reply_BoolValue(const bool value, const uint8_t* pMsgHeader) {
	HDC_Reply_BlobValue((uint8_t*)&value, 1, pMsgHeader, HDC_ReplyErrorCode_NO_ERROR);
}

void HDC_Reply_UInt8Value(const uint8_t value, const uint8_t* pMsgHeader) {
	HDC_Reply_BlobValue(&value, 1, pMsgHeader, HDC_ReplyErrorCode_NO_ERROR);
}

void HDC_Reply_UInt16Value(const uint16_t value, const uint8_t* pMsgHeader) {
	// Note that STM32 is little-endian
	HDC_Reply_BlobValue((uint8_t*)&value, 2, pMsgHeader, HDC_ReplyErrorCode_NO_ERROR);
}

void HDC_Reply_UInt32Value(const uint32_t value, const uint8_t* pMsgHeader) {
	// Note that STM32 is little-endian
	HDC_Reply_BlobValue((uint8_t*)&value, 4, pMsgHeader, HDC_ReplyErrorCode_NO_ERROR);
}

void HDC_Reply_Int8Value(const int8_t value, const uint8_t* pMsgHeader) {
	HDC_Reply_BlobValue((uint8_t*)&value, 1, pMsgHeader, HDC_ReplyErrorCode_NO_ERROR);
}

void HDC_Reply_Int16Value(const int16_t value, const uint8_t* pMsgHeader) {
	// Note that STM32 is little-endian
	HDC_Reply_BlobValue((uint8_t*)&value, 2, pMsgHeader, HDC_ReplyErrorCode_NO_ERROR);
}

void HDC_Reply_Int32Value(const int32_t value, const uint8_t* pMsgHeader) {
	// Note that STM32 is little-endian
	HDC_Reply_BlobValue((uint8_t*)&value, 4, pMsgHeader, HDC_ReplyErrorCode_NO_ERROR);
}

void HDC_Reply_FloatValue(const float value, const uint8_t* pMsgHeader) {
	// Note that STM32 is little-endian
	HDC_Reply_BlobValue((uint8_t*)&value, 4, pMsgHeader, HDC_ReplyErrorCode_NO_ERROR);
}

void HDC_Reply_DoubleValue(const double value, const uint8_t* pMsgHeader) {
	// Note that STM32 is little-endian
	HDC_Reply_BlobValue((uint8_t*)&value, 8, pMsgHeader, HDC_ReplyErrorCode_NO_ERROR);
}

void HDC_Reply_StringValue(const char* value, const uint8_t* pMsgHeader) {
	if (value == NULL)
		// Treat null-pointer in the same way as an "empty string"
		return HDC_Reply_BlobValue(NULL, 0, pMsgHeader, HDC_ReplyErrorCode_NO_ERROR);

	// Omit string's zero-termination byte! Note how the string's length is determined by the packet size.
	HDC_Reply_BlobValue((uint8_t*)value, strlen(value), pMsgHeader, HDC_ReplyErrorCode_NO_ERROR);
}


////////////////////////////////////////////
// Request Handlers for Mandatory Commands

void HDC_MandatoryCmd_Echo(
		const HDC_Feature_Descriptor_t *hHDC_Feature,
		const uint8_t* RequestMessage,
		const uint8_t Size)
{
	assert_param(RequestMessage[0] == HDC_MessageType_COMMAND_ECHO);
	assert_param(hHDC_Feature == NULL);

	HDC_Reply_Raw(RequestMessage, Size); // Reply message must be exactly equal to the full request message. Do not include any reply-error code!
}

void HDC_MandatoryCmd_GetPropertyName(
		const HDC_Feature_Descriptor_t *hHDC_Feature,
		const uint8_t* RequestMessage,
		const uint8_t Size)
{
	if (Size != 4)
		return HDC_Reply_Error(HDC_ReplyErrorCode_INCORRECT_COMMAND_ARGUMENTS, RequestMessage);

	assert_param(RequestMessage[0] == HDC_MessageType_COMMAND_FEATURE);
	assert_param(RequestMessage[2] == 0xF1);  // CommandID

	uint8_t FeatureID = RequestMessage[1];
	uint8_t PropertyID = RequestMessage[3];

	const HDC_Feature_Descriptor_t* feature = HDC_GetFeature(FeatureID);

	if (feature == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_FEATURE, RequestMessage);

	const HDC_Property_Descriptor_t* property = HDC_GetProperty(feature, PropertyID);

	if (property == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_PROPERTY, RequestMessage);

	HDC_Reply_StringValue(property->PropertyName, RequestMessage);
}


void HDC_MandatoryCmd_GetPropertyType(
		const HDC_Feature_Descriptor_t *hHDC_Feature,
		const uint8_t* RequestMessage,
		const uint8_t Size)
{
	if (Size != 4)
		return HDC_Reply_Error(HDC_ReplyErrorCode_INCORRECT_COMMAND_ARGUMENTS, RequestMessage);

	assert_param(RequestMessage[0] == HDC_MessageType_COMMAND_FEATURE);
	assert_param(RequestMessage[2] == 0xF2);  // CommandID

	uint8_t FeatureID = RequestMessage[1];
	uint8_t PropertyID = RequestMessage[3];

	const HDC_Feature_Descriptor_t* feature = HDC_GetFeature(FeatureID);

	if (feature == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_FEATURE, RequestMessage);

	const HDC_Property_Descriptor_t* property = HDC_GetProperty(feature, PropertyID);

	if (property == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_PROPERTY, RequestMessage);

	HDC_Reply_UInt8Value(property->PropertyDataType, RequestMessage);
}

void HDC_MandatoryCmd_GetPropertyReadonly(
		const HDC_Feature_Descriptor_t *hHDC_Feature,
		const uint8_t* RequestMessage,
		const uint8_t Size)
{
	if (Size != 4)
		return HDC_Reply_Error(HDC_ReplyErrorCode_INCORRECT_COMMAND_ARGUMENTS, RequestMessage);

	assert_param(RequestMessage[0] == HDC_MessageType_COMMAND_FEATURE);
	assert_param(RequestMessage[2] == 0xF3);  // CommandID

	uint8_t FeatureID = RequestMessage[1];
	uint8_t PropertyID = RequestMessage[3];

	const HDC_Feature_Descriptor_t* feature = HDC_GetFeature(FeatureID);

	if (feature == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_FEATURE, RequestMessage);

	const HDC_Property_Descriptor_t *property = HDC_GetProperty(feature, PropertyID);

	if (property == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_PROPERTY, RequestMessage);

	HDC_Reply_BoolValue(property->PropertyIsReadonly, RequestMessage);
}

void HDC_MandatoryCmd_GetPropertyValue(
		const HDC_Feature_Descriptor_t *hHDC_Feature,
		const uint8_t* RequestMessage,
		const uint8_t Size)
{
	uint8_t CommandID = RequestMessage[2];
	if (CommandID==0x04 && Size != 4)  // Skip validation whenever called from HDC_MandatoryCmd_SetPropertyValue()
		return HDC_Reply_Error(HDC_ReplyErrorCode_INCORRECT_COMMAND_ARGUMENTS, RequestMessage);

	assert_param(RequestMessage[0] == HDC_MessageType_COMMAND_FEATURE);
	assert_param(CommandID == 0xF4 || CommandID == 0xF5);  // This may have been called via HDC_MandatoryCmd_SetPropertyValue()

	uint8_t FeatureID = RequestMessage[1];
	uint8_t PropertyID = RequestMessage[3];

	const HDC_Feature_Descriptor_t* feature = HDC_GetFeature(FeatureID);

	if (feature == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_FEATURE, RequestMessage);

	const HDC_Property_Descriptor_t* property = HDC_GetProperty(feature, PropertyID);

	if (property == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_PROPERTY, RequestMessage);

	if (property->GetPropertyValue != NULL)
		return property->GetPropertyValue(feature, property, RequestMessage, Size);

	if (property->pValue == NULL)
		Error_Handler();  // ToDo: Complain about incorrect descriptor.

	switch (property->PropertyDataType) {

	case HDC_DataType_BOOL:
		return HDC_Reply_BoolValue(*(bool*)property->pValue, RequestMessage);

	case HDC_DataType_UINT8:
		return HDC_Reply_UInt8Value(*(uint8_t*)property->pValue, RequestMessage);

	case HDC_DataType_UINT16:
		return HDC_Reply_UInt16Value(*(uint16_t*)property->pValue, RequestMessage);

	case HDC_DataType_UINT32:
		return HDC_Reply_UInt32Value(*(uint32_t*)property->pValue, RequestMessage);

	case HDC_DataType_INT8:
		return HDC_Reply_Int8Value(*(int8_t*)property->pValue, RequestMessage);

	case HDC_DataType_INT16:
		return HDC_Reply_Int16Value(*(int16_t*)property->pValue, RequestMessage);

	case HDC_DataType_INT32:
		return HDC_Reply_Int32Value(*(int32_t*)property->pValue, RequestMessage);

	case HDC_DataType_FLOAT:
		return HDC_Reply_FloatValue(*(float*)property->pValue, RequestMessage);

	case HDC_DataType_DOUBLE:
		return HDC_Reply_DoubleValue(*(double*)property->pValue, RequestMessage);

	case HDC_DataType_UTF8:
		return HDC_Reply_StringValue((char *)property->pValue, RequestMessage);

	case HDC_DataType_BLOB:
		if (property->ValueSize == 0)
			Error_Handler();  // ToDo: Complain about incorrect descriptor.
		return HDC_Reply_BlobValue(
				(uint8_t *)property->pValue,
				property->ValueSize,
				RequestMessage,
				HDC_ReplyErrorCode_NO_ERROR);
	default:
		Error_Handler();  // ToDo: Complain about unknown property-data-type
	}
}

void HDC_MandatoryCmd_SetPropertyValue(
		const HDC_Feature_Descriptor_t *hHDC_Feature,
		const uint8_t* RequestMessage,
		const uint8_t Size)
{
	assert_param(RequestMessage[0] == HDC_MessageType_COMMAND_FEATURE);
	assert_param(RequestMessage[2] == 0xF5);  // CommandID

	uint8_t FeatureID = RequestMessage[1];
	uint8_t PropertyID = RequestMessage[3];

	HDC_Feature_Descriptor_t* feature = HDC_GetFeature(FeatureID);

	if (feature == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_FEATURE, RequestMessage);

	const HDC_Property_Descriptor_t *property = HDC_GetProperty(feature, PropertyID);

	if (property == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_PROPERTY, RequestMessage);

	if (property->PropertyIsReadonly)
		return HDC_Reply_Error(HDC_ReplyErrorCode_PROPERTY_IS_READONLY, RequestMessage);

	// Validate size of received value
	uint8_t receivedValueSize = Size - 4;
	const uint8_t *pNewValueAsRawBytes = RequestMessage + 4;

	// Lower nibble of a DataType's ID provides a hint about the size.
	const uint8_t lowerNibble = property->PropertyDataType & 0x0F;

	if (lowerNibble == 0x0F) {  // Exception is 0x_F, which means it's a variable size data-type
		if (property->ValueSize == 0)
			Error_Handler();  // ToDo: Complain about incorrect descriptor!

		// Check for buffer overflow
		if (receivedValueSize >= property->ValueSize)  // Comparing with greater-or-equal to reserve one byte for the zero-terminator!
			return HDC_Reply_Error(HDC_ReplyErrorCode_INVALID_PROPERTY_VALUE, RequestMessage);

		// Otherwise it's legal to receive a shorter value :-)
		// Note how empty values are legal, too.

	} else {
		const size_t expectedValueSize =
				(lowerNibble == 0)  // Special case for BOOL, whose DataTypeID is 0x00
				? 1
				: lowerNibble;

		if (receivedValueSize != expectedValueSize)
			return HDC_Reply_Error(HDC_ReplyErrorCode_INVALID_PROPERTY_VALUE, RequestMessage);
	}

	if (property->SetPropertyValue != NULL)
		return property->SetPropertyValue(feature, property, RequestMessage, Size);

	if (property->pValue == NULL)
		Error_Handler();  // ToDo: Complain about incorrect descriptor.

	memcpy(property->pValue, pNewValueAsRawBytes, receivedValueSize);

	if (property->PropertyDataType == HDC_DataType_UTF8)
		*(((uint8_t*)property->pValue)+receivedValueSize) = 0;  // Zero-terminator for the string!

	// Note how the reply of a SetPropertyValue request is essentially
	// the same as for the GetPropertyValue request, except for the CommandID.
	return HDC_MandatoryCmd_GetPropertyValue(hHDC_Feature, RequestMessage, Size);

}

void HDC_MandatoryCmd_GetPropertyDescription(
		const HDC_Feature_Descriptor_t *hHDC_Feature,
		const uint8_t* RequestMessage,
		const uint8_t Size)
{
	if (Size != 4)
		return HDC_Reply_Error(HDC_ReplyErrorCode_INCORRECT_COMMAND_ARGUMENTS, RequestMessage);

	assert_param(RequestMessage[0] == HDC_MessageType_COMMAND_FEATURE);
	assert_param(RequestMessage[2] == 0xF6);  // CommandID

	uint8_t FeatureID = RequestMessage[1];
	uint8_t PropertyID = RequestMessage[3];

	const HDC_Feature_Descriptor_t* feature = HDC_GetFeature(FeatureID);

	if (feature == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_FEATURE, RequestMessage);

	// Special treatment of the mandatory FeatureState property, whose description
	// is provided by the Feature descriptor, because it's up to each feature's
	// implementation to define its state-machine.
	// Only if it doesn't we default to the one-size-fits-all default description.
	if (PropertyID == 0xF8 && hHDC_Feature->FeatureStatesDescription != NULL)
		return HDC_Reply_StringValue(hHDC_Feature->FeatureStatesDescription, RequestMessage);

	const HDC_Property_Descriptor_t* property = HDC_GetProperty(feature, PropertyID);

	if (property == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_PROPERTY, RequestMessage);

	HDC_Reply_StringValue(property->PropertyDescription, RequestMessage);
}

void HDC_MandatoryCmd_GetCommandName(
		const HDC_Feature_Descriptor_t *hHDC_Feature,
		const uint8_t* RequestMessage,
		const uint8_t Size)
{
	if (Size != 4)
		return HDC_Reply_Error(HDC_ReplyErrorCode_INCORRECT_COMMAND_ARGUMENTS, RequestMessage);

	assert_param(RequestMessage[0] == HDC_MessageType_COMMAND_FEATURE);
	assert_param(RequestMessage[2] == 0xF7);  // CommandID of the GetCommandName command

	uint8_t FeatureID = RequestMessage[1];
	uint8_t CommandID = RequestMessage[3];  // Not the CommandID of the GetCommandName command, but the CommandID whose name is being requested here. :o)


	const HDC_Feature_Descriptor_t* feature = HDC_GetFeature(FeatureID);

	if (feature == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_FEATURE, RequestMessage);

	const HDC_Command_Descriptor_t* command = HDC_GetCommand(feature, CommandID);

	if (command == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_COMMAND, RequestMessage);

	HDC_Reply_StringValue(command->CommandName, RequestMessage);
}

void HDC_MandatoryCmd_GetCommandDescription(
		const HDC_Feature_Descriptor_t *hHDC_Feature,
		const uint8_t* RequestMessage,
		const uint8_t Size)
{
	if (Size != 4)
		return HDC_Reply_Error(HDC_ReplyErrorCode_INCORRECT_COMMAND_ARGUMENTS, RequestMessage);

	assert_param(RequestMessage[0] == HDC_MessageType_COMMAND_FEATURE);
	assert_param(RequestMessage[2] == 0xF8);  // CommandID of the GetCommandDescription command

	uint8_t FeatureID = RequestMessage[1];
	uint8_t CommandID = RequestMessage[3];  // Not the CommandID of the GetCommandName command, but the CommandID whose name is being requested here. :o)

	const HDC_Feature_Descriptor_t* feature = HDC_GetFeature(FeatureID);

	if (feature == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_FEATURE, RequestMessage);

	const HDC_Command_Descriptor_t* command = HDC_GetCommand(feature, CommandID);

	if (command == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_COMMAND, RequestMessage);

	HDC_Reply_StringValue(command->CommandDescription, RequestMessage);
}

void HDC_MandatoryCmd_GetEventName(
		const HDC_Feature_Descriptor_t *hHDC_Feature,
		const uint8_t* RequestMessage,
		const uint8_t Size)
{
	if (Size != 4)
		return HDC_Reply_Error(HDC_ReplyErrorCode_INCORRECT_COMMAND_ARGUMENTS, RequestMessage);

	assert_param(RequestMessage[0] == HDC_MessageType_COMMAND_FEATURE);
	assert_param(RequestMessage[2] == 0xF9);  // CommandID

	uint8_t FeatureID = RequestMessage[1];
	uint8_t EventID = RequestMessage[3];

	const HDC_Feature_Descriptor_t* feature = HDC_GetFeature(FeatureID);

	if (feature == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_FEATURE, RequestMessage);

	const HDC_Event_Descriptor_t* event = HDC_GetEvent(feature, EventID);

	if (event == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_EVENT, RequestMessage);

	HDC_Reply_StringValue(event->EventName, RequestMessage);
}

void HDC_MandatoryCmd_GetEventDescription(
		const HDC_Feature_Descriptor_t *hHDC_Feature,
		const uint8_t* RequestMessage,
		const uint8_t Size)
{
	if (Size != 4)
		return HDC_Reply_Error(HDC_ReplyErrorCode_INCORRECT_COMMAND_ARGUMENTS, RequestMessage);

	assert_param(RequestMessage[0] == HDC_MessageType_COMMAND_FEATURE);
	assert_param(RequestMessage[2] == 0xFA);  // CommandID

	uint8_t FeatureID = RequestMessage[1];
	uint8_t EventID = RequestMessage[3];

	const HDC_Feature_Descriptor_t* feature = HDC_GetFeature(FeatureID);

	if (feature == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_FEATURE, RequestMessage);

	const HDC_Event_Descriptor_t* event = HDC_GetEvent(feature, EventID);

	if (event == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_EVENT, RequestMessage);

	HDC_Reply_StringValue(event->EventDescription, RequestMessage);
}

const HDC_Command_Descriptor_t *HDC_MandatoryCommands[NUM_MANDATORY_COMMANDS] = {
	&(HDC_Command_Descriptor_t){
		.CommandID = 0xF1,
		.CommandName = "GetPropertyName",
		.HandleRequest = &HDC_MandatoryCmd_GetPropertyName,
		.CommandDescription = "(UINT8 PropertyID) -> UTF8"
	},

	&(HDC_Command_Descriptor_t){
		.CommandID = 0xF2,
		.CommandName = "GetPropertyType",
		.HandleRequest = &HDC_MandatoryCmd_GetPropertyType,
		.CommandDescription = "(UINT8 PropertyID) -> UINT8"
	},

	&(HDC_Command_Descriptor_t){
		.CommandID = 0xF3,
		.CommandName = "GetPropertyReadonly",
		.HandleRequest = &HDC_MandatoryCmd_GetPropertyReadonly,
		.CommandDescription = "(UINT8 PropertyID) -> BOOL"
	},

	&(HDC_Command_Descriptor_t){
		.CommandID = 0xF4,
		.CommandName = "GetPropertyValue",
		.HandleRequest = &HDC_MandatoryCmd_GetPropertyValue,
		.CommandDescription = "(UINT8 PropertyID) -> PropertyType"
	},

	&(HDC_Command_Descriptor_t){
		.CommandID = 0xF5,
		.CommandName = "SetPropertyValue",
		.HandleRequest = &HDC_MandatoryCmd_SetPropertyValue,
		.CommandDescription = "(UINT8 PropertyID, PropertyType NewValue) -> return value as for GetPropertyValue.\n"
				"Returned value might differ from NewValue argument, i.e. because of trimming to valid range or discretisation."
	},

	&(HDC_Command_Descriptor_t){
			.CommandID = 0xF6,
			.CommandName = "GetPropertyDescription",
			.HandleRequest = &HDC_MandatoryCmd_GetPropertyDescription,
			.CommandDescription = "(UINT8 PropertyID) -> UTF8"
		},

	&(HDC_Command_Descriptor_t){
		.CommandID = 0xF7,
		.CommandName = "GetCommandName",
		.HandleRequest = &HDC_MandatoryCmd_GetCommandName,
		.CommandDescription = "(UINT8 CommandID) -> UTF8"
	},

	&(HDC_Command_Descriptor_t){
		.CommandID = 0xF8,
		.CommandName = "GetCommandDescription",
		.HandleRequest = &HDC_MandatoryCmd_GetCommandDescription,
		.CommandDescription = "(UINT8 CommandID) -> UTF8"
	},


	&(HDC_Command_Descriptor_t){
		.CommandID = 0xF9,
		.CommandName = "GetEventName",
		.HandleRequest = &HDC_MandatoryCmd_GetEventName,
		.CommandDescription = "(UINT8 EventID) -> UTF8"
	},

	&(HDC_Command_Descriptor_t){
		.CommandID = 0xFA,
		.CommandName = "GetEventDescription",
		.HandleRequest = &HDC_MandatoryCmd_GetEventDescription,
		.CommandDescription = "(UINT8 EventID) -> UTF8"
	}
};

////////////////////////////////////////////////////
// Mandatory Events

const HDC_Event_Descriptor_t HDC_MandatoryEvent_Log = {
	.EventID = 0xF0,
	.EventName = "Log",
	.EventDescription =
			"-> UINT8 LogLevel, UTF8 LogText\n"
			"Software logging. LogLevels are the same as defined in python's logging module."
};

void HDC_Reply_Event_Log(
		const HDC_Feature_Descriptor_t *hHdcFeature,
		HDC_EventLogLevel_t logLevel,
		char* logText)
{
	if (hHdcFeature == NULL)
		hHdcFeature = hHDC.Features[0];  // Default to Core-Feature, which by convention is the first array item.

	if (logLevel < hHdcFeature->LogEventThreshold)
		return;

	const uint8_t HeaderSize = 4; // MsgType + FeatureID + EventID + LogLevel
	const uint16_t MsgSize = HeaderSize + strlen(logText);
	uint8_t PktSize;
	uint16_t nMsg = 0;
	do {
		PktSize = MsgSize - nMsg < 255 ? MsgSize - nMsg : 255;  // Actually just the packet's payload size.
		uint8_t *pBuffer = 0;
		uint16_t *pNumBytesInBuffer = 0;
		HDC_GetTxBufferWithCapacityForAtLeast(PktSize + HDC_PACKAGE_OVERHEAD, &pBuffer, &pNumBytesInBuffer);
		uint8_t checksum = 0;
		pBuffer[(*pNumBytesInBuffer)++] = PktSize;
		uint8_t nPkt=0;

		if (nMsg==0) { // Is this the first packet of this message?

			// MessageType as HDC_DataType_UINT8
			checksum += HDC_MessageType_EVENT_FEATURE;
			pBuffer[(*pNumBytesInBuffer)++] = HDC_MessageType_EVENT_FEATURE;
			nMsg++;
			nPkt++;

			// FeatureID as HDC_DataType_UINT8
			checksum += hHdcFeature->FeatureID;
			pBuffer[(*pNumBytesInBuffer)++] = hHdcFeature->FeatureID;
			nMsg++;
			nPkt++;

			// EventID as HDC_DataType_UINT8
			checksum += HDC_MandatoryEvent_Log.EventID;
			pBuffer[(*pNumBytesInBuffer)++] = HDC_MandatoryEvent_Log.EventID;
			nMsg++;
			nPkt++;

			// LogLevel as HDC_DataType_UINT8
			checksum += (uint8_t)logLevel;
			pBuffer[(*pNumBytesInBuffer)++] = (uint8_t)logLevel;
			nMsg++;
			nPkt++;
		}

		// LogText as HDC_DataType_UTF8
		while (nPkt < PktSize) {
			checksum += logText[nMsg - HeaderSize];
			pBuffer[(*pNumBytesInBuffer)++] = logText[nMsg - HeaderSize];
			nMsg++;
			nPkt++;
		}

		pBuffer[(*pNumBytesInBuffer)++] = (uint8_t)0xFF - checksum + 1;
		pBuffer[(*pNumBytesInBuffer)++] = HDC_PACKAGE_TERMINATOR;
	} while (nMsg < MsgSize);

	if (PktSize==255) {
		// Last packet had a payload of exactly 255 bytes.
		// We must therefore send an empty packet, to signal
		// that the multi-package message is complete.
		HDC_Reply_EmptyPacket();
	}
}


const HDC_Event_Descriptor_t HDC_MandatoryEvent_FeatureStateTransition = {
	.EventID = 0xF1,
	.EventName = "FeatureStateTransition",
	.EventDescription =
			"-> UINT8 PreviousStateID , UINT8 CurrentStateID\n"
			"Notifies host about transitions of this feature's state-machine."
};

void HDC_Reply_Event_FeatureStateTransition(
		uint8_t FeatureID,
		uint8_t previousStateID,
		uint8_t newStateID)
{
	const uint16_t MsgSize = 5; // MsgType + FeatureID + EventID + PreviousStateID + NewStateID

	uint8_t *pBuffer = 0;
	uint16_t *pNumBytesInBuffer = 0;
	HDC_GetTxBufferWithCapacityForAtLeast(MsgSize + HDC_PACKAGE_OVERHEAD, &pBuffer, &pNumBytesInBuffer);
	uint8_t checksum = 0;

	pBuffer[(*pNumBytesInBuffer)++] = MsgSize;

	// MessageType
	checksum += HDC_MessageType_EVENT_FEATURE;
	pBuffer[(*pNumBytesInBuffer)++] = HDC_MessageType_EVENT_FEATURE;

	// FeatureID
	checksum += FeatureID;
	pBuffer[(*pNumBytesInBuffer)++] = FeatureID;

	// EventID
	checksum += HDC_MandatoryEvent_FeatureStateTransition.EventID;
	pBuffer[(*pNumBytesInBuffer)++] = HDC_MandatoryEvent_FeatureStateTransition.EventID;

	// PreviousStateID
	checksum += previousStateID;
	pBuffer[(*pNumBytesInBuffer)++] = previousStateID;

	// NewStateID
	checksum += newStateID;
	pBuffer[(*pNumBytesInBuffer)++] = newStateID;

	pBuffer[(*pNumBytesInBuffer)++] = (uint8_t)0xFF - checksum + 1;
	pBuffer[(*pNumBytesInBuffer)++] = HDC_PACKAGE_TERMINATOR;
}

void HDC_FeatureStateTransition(HDC_Feature_Descriptor_t *hFeature, uint8_t newState) {
	if (newState == hFeature->FeatureState)
		return;  // Avoid transition into the same state we already are.
	HDC_Reply_Event_FeatureStateTransition(hFeature->FeatureID, hFeature->FeatureState, newState);
	hFeature->FeatureState = newState;
}

const HDC_Event_Descriptor_t *HDC_MandatoryEvents[NUM_MANDATORY_EVENTS] = {
		&HDC_MandatoryEvent_Log,
		&HDC_MandatoryEvent_FeatureStateTransition
};

////////////////////////////////////////////////////////////
// Properties that are mandatory for all features

void HDC_Property_FeatureName_get(const HDC_Feature_Descriptor_t *hHDC_Feature, const struct HDC_Property_struct *hHDC_Property, const uint8_t* RequestMessage, const uint8_t RequestMessageSize) {
	return HDC_Reply_StringValue(hHDC_Feature->FeatureName, RequestMessage);
}

void HDC_Property_FeatureTypeName_get(const HDC_Feature_Descriptor_t *hHDC_Feature, const struct HDC_Property_struct *hHDC_Property, const uint8_t* RequestMessage, const uint8_t RequestMessageSize) {
	return HDC_Reply_StringValue(hHDC_Feature->FeatureTypeName, RequestMessage);
}

void HDC_Property_FeatureTypeRevision_get(const HDC_Feature_Descriptor_t *hHDC_Feature, const struct HDC_Property_struct *hHDC_Property, const uint8_t* RequestMessage, const uint8_t RequestMessageSize) {
	return HDC_Reply_UInt8Value(hHDC_Feature->FeatureTypeRevision, RequestMessage);
}

void HDC_Property_FeatureDescription_get(const HDC_Feature_Descriptor_t *hHDC_Feature, const struct HDC_Property_struct *hHDC_Property, const uint8_t* RequestMessage, const uint8_t RequestMessageSize) {
	return HDC_Reply_StringValue(hHDC_Feature->FeatureDescription, RequestMessage);
}

void HDC_Property_FeatureTags_get(const HDC_Feature_Descriptor_t *hHDC_Feature, const struct HDC_Property_struct *hHDC_Property, const uint8_t* RequestMessage, const uint8_t RequestMessageSize) {
	return HDC_Reply_StringValue(hHDC_Feature->FeatureTags, RequestMessage);
}

void HDC_Property_AvailableCommands_get(const HDC_Feature_Descriptor_t *hHDC_Feature, const struct HDC_Property_struct *hHDC_Property, const uint8_t* RequestMessage, const uint8_t RequestMessageSize) {
	uint8_t availableCommands[256] = {0}; // There can't be more than 256 per feature
	uint8_t n=0;
	for (uint8_t i=0; i < hHDC_Feature->NumCommands;i++)
		availableCommands[n++] = hHDC_Feature->Commands[i]->CommandID;

	for (uint8_t i=0; i < NUM_MANDATORY_COMMANDS;i++)
		availableCommands[n++] = HDC_MandatoryCommands[i]->CommandID;

	HDC_Reply_BlobValue(availableCommands, n, RequestMessage, HDC_ReplyErrorCode_NO_ERROR);
}

void HDC_Property_AvailableEvents_get(const HDC_Feature_Descriptor_t *hHDC_Feature, const struct HDC_Property_struct *hHDC_Property, const uint8_t* RequestMessage, const uint8_t RequestMessageSize) {
	uint8_t availableEvents[256] = {0}; // There can't be more than 256 per feature
	uint8_t n=0;
	for (uint8_t i=0; i< hHDC_Feature->NumEvents;i++)
		availableEvents[n++] = hHDC_Feature->Events[i]->EventID;
	for (uint8_t i=0; i < NUM_MANDATORY_EVENTS;i++)
		availableEvents[n++] = HDC_MandatoryEvents[i]->EventID;

	HDC_Reply_BlobValue(availableEvents, n, RequestMessage, HDC_ReplyErrorCode_NO_ERROR);
}

void HDC_Property_AvailableProperties_get(const HDC_Feature_Descriptor_t *hHDC_Feature, const struct HDC_Property_struct *hHDC_Property, const uint8_t* RequestMessage, const uint8_t RequestMessageSize) {
	uint8_t availableProperties[256] = {0}; // There can't be more than 256 per feature
	uint8_t n=0;
	for (uint8_t i=0; i< hHDC_Feature->NumProperties;i++)
		availableProperties[n++] = hHDC_Feature->Properties[i]->PropertyID;
	for (uint8_t i=0; i < NUM_MANDATORY_PROPERTIES;i++)
		availableProperties[n++] = HDC_MandatoryProperties[i]->PropertyID;
	if (hHDC_Feature->FeatureID == HDC_FEATUREID_CORE) {
		for (uint8_t i=0; i < NUM_MANDATORY_PROPERTIES_OF_CORE_FEATURE;i++)
			availableProperties[n++] = HDC_MandatoryPropertiesOfCoreFeature[i]->PropertyID;
	}

	HDC_Reply_BlobValue(availableProperties, n, RequestMessage, HDC_ReplyErrorCode_NO_ERROR);
}

void HDC_Property_FeatureState_get(const HDC_Feature_Descriptor_t *hHDC_Feature, const struct HDC_Property_struct *hHDC_Property, const uint8_t* RequestMessage, const uint8_t RequestMessageSize) {
	HDC_Reply_UInt8Value(hHDC_Feature->FeatureState, RequestMessage);
}

void HDC_Property_LogEventThreshold_get(const HDC_Feature_Descriptor_t *hHDC_Feature, const struct HDC_Property_struct *hHDC_Property, const uint8_t* RequestMessage, const uint8_t RequestMessageSize) {
	HDC_Reply_UInt8Value(hHDC_Feature->LogEventThreshold, RequestMessage);
}

void HDC_Property_LogEventThreshold_set(HDC_Feature_Descriptor_t *hHDC_Feature, const struct HDC_Property_struct *hHDC_Property, const uint8_t* RequestMessage, const uint8_t RequestMessageSize) {
	uint8_t newValue = *((const uint8_t *)(RequestMessage + 4));

	newValue = CONSTRAIN(newValue, HDC_EventLogLevel_DEBUG, HDC_EventLogLevel_CRITICAL);

	hHDC_Feature->LogEventThreshold = newValue;
	HDC_Reply_UInt8Value(hHDC_Feature->LogEventThreshold, RequestMessage);
}

const HDC_Property_Descriptor_t *HDC_MandatoryProperties[NUM_MANDATORY_PROPERTIES] = {
		&(HDC_Property_Descriptor_t ) {
			.PropertyID = 0xF0,
			.PropertyName = "FeatureName",
			.PropertyDataType = HDC_DataType_UTF8,
			.PropertyIsReadonly = true,
			.GetPropertyValue = HDC_Property_FeatureName_get,
			.PropertyDescription = "Unique label of this feature-instance."
		},

		&(HDC_Property_Descriptor_t ) {
			.PropertyID = 0xF1,
			.PropertyName = "FeatureTypeName",
			.PropertyDataType = HDC_DataType_UTF8,
			.PropertyIsReadonly = true,
			.GetPropertyValue = HDC_Property_FeatureTypeName_get,
			.PropertyDescription = "Unique label of this feature's class."
		},

		&(HDC_Property_Descriptor_t ) {
			.PropertyID = 0xF2,
			.PropertyName = "FeatureTypeRevision",
			.PropertyDataType = HDC_DataType_UINT8,
			.PropertyIsReadonly = true,
			.GetPropertyValue = HDC_Property_FeatureTypeRevision_get,
			.PropertyDescription = "Revision number of this feature's class-implementation."
		},

		&(HDC_Property_Descriptor_t ) {
			.PropertyID = 0xF3,
			.PropertyName = "FeatureDescription",
			.PropertyDataType = HDC_DataType_UTF8,
			.PropertyIsReadonly = true,
			.GetPropertyValue = HDC_Property_FeatureDescription_get,
			.PropertyDescription = "Human readable documentation about this feature."
		},

		&(HDC_Property_Descriptor_t ) {
			.PropertyID = 0xF4,
			.PropertyName = "FeatureTags",
			.PropertyDataType = HDC_DataType_UTF8,
			.PropertyIsReadonly = true,
			.GetPropertyValue = HDC_Property_FeatureTags_get,
			.PropertyDescription = "Semicolon-delimited list of tags and categories associated with this feature."
		},

		&(HDC_Property_Descriptor_t ) {
			.PropertyID = 0xF5,
			.PropertyName = "AvailableCommands",
			.PropertyDataType = HDC_DataType_BLOB,
			.PropertyIsReadonly = true,
			.GetPropertyValue = HDC_Property_AvailableCommands_get,
			.PropertyDescription = "List of IDs of commands available on this feature."
		},

		&(HDC_Property_Descriptor_t ) {
			.PropertyID = 0xF6,
			.PropertyName = "AvailableEvents",
			.PropertyDataType = HDC_DataType_BLOB,
			.PropertyIsReadonly = true,
			.GetPropertyValue = HDC_Property_AvailableEvents_get,
			.PropertyDescription = "List of IDs of events available on this feature."
		},

		&(HDC_Property_Descriptor_t ) {
			.PropertyID = 0xF7,
			.PropertyName = "AvailableProperties",
			.PropertyDataType = HDC_DataType_BLOB,
			.PropertyIsReadonly = true,
			.GetPropertyValue = HDC_Property_AvailableProperties_get,
			.PropertyDescription = "List of IDs of properties available on this feature."
		},

		&(HDC_Property_Descriptor_t ) {
			.PropertyID = 0xF8,
			.PropertyName = "FeatureState",
			.PropertyDataType = HDC_DataType_UINT8,
			.PropertyIsReadonly = true,
			.GetPropertyValue = HDC_Property_FeatureState_get,
			// Description of FeatureStates is usually provided by the FeatureStatesDescription property.
			// The following is only a fall-back for Features that do not implement any state-machine.
			.PropertyDescription = "{0:'Stateless'}"
		},

		&(HDC_Property_Descriptor_t ) {
			.PropertyID = 0xF9,
			.PropertyName = "LogEventThreshold",
			.PropertyDataType = HDC_DataType_UINT8,
			.PropertyIsReadonly = false,
			.GetPropertyValue = HDC_Property_LogEventThreshold_get,
			.SetPropertyValue = HDC_Property_LogEventThreshold_set,
			.PropertyDescription = "Suppresses LogEvents with lower log-levels."
		}
};


////////////////////////////////////////////////////////////
// Properties that are only mandatory for the Core feature

void HDC_Property_AvailableFeatures_get(
		const HDC_Feature_Descriptor_t *hHDC_Feature,
		const struct HDC_Property_struct *hHDC_Property,
		const uint8_t* RequestMessage,
		const uint8_t RequestMessageSize) {

	// ToDo: Is it worth it to rewrite the following into a more RAM-efficient direct message composition in the TX buffer?

	uint8_t availableFeatures[256] = {0}; // There can't be more than 256 features.
	for (uint8_t i=0; i< hHDC.NumFeatures;i++)
		availableFeatures[i] = hHDC.Features[i]->FeatureID;
	return HDC_Reply_BlobValue(availableFeatures, hHDC.NumFeatures, RequestMessage, HDC_ReplyErrorCode_NO_ERROR);
}

const HDC_Property_Descriptor_t *HDC_MandatoryPropertiesOfCoreFeature[NUM_MANDATORY_PROPERTIES_OF_CORE_FEATURE] = {
	&(HDC_Property_Descriptor_t ) {
		.PropertyID = 0xFA,
		.PropertyName = "AvailableFeatures",
		.PropertyDataType = HDC_DataType_BLOB,
		.PropertyIsReadonly = true,
		.GetPropertyValue = HDC_Property_AvailableFeatures_get,
		.PropertyDescription = "List of IDs of features available on this device."
	},

	&(HDC_Property_Descriptor_t ) {
		.PropertyID = 0xFB,
		.PropertyName = "MaxReqMsgSize",
		.PropertyDataType = HDC_DataType_UINT16,
		.PropertyIsReadonly = true,
		.pValue = &(uint16_t){HDC_MAX_REQ_MESSAGE_SIZE},  // Pointer to a literal integer value. https://stackoverflow.com/a/3443883
		.PropertyDescription = "Maximum number of bytes of a request message that this device can cope with."
	},
};


////////////////////////////////////////////
// Request broker
void HDC_ProcessRxPacket(const uint8_t *packet) {
	// Packet has already been validated to be well formed by caller.
	const uint8_t MessageSize = packet[0];

	if (MessageSize==0)  // Ignore empty messages. They are legal, but currently without purpose.
		return;

	const uint8_t *RequestMessage = packet+1;
	const uint8_t MessageType = RequestMessage[0];

	if (MessageType == HDC_MessageType_COMMAND_ECHO)
		return HDC_MandatoryCmd_Echo(NULL, RequestMessage, MessageSize);

	if (MessageType != HDC_MessageType_COMMAND_FEATURE)
		// Note how we can't reply with a ReplyErrorCode, because we don't
		// even know if this is a proper Command request.
		return HDC_Reply_Event_Log(NULL, HDC_EventLogLevel_ERROR, "Unknown message type");

	uint8_t FeatureID = RequestMessage[1];
	uint8_t CommandID = RequestMessage[2];

	const HDC_Feature_Descriptor_t* feature = HDC_GetFeature(FeatureID);

	if (feature == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_FEATURE, RequestMessage);

	const HDC_Command_Descriptor_t* command = HDC_GetCommand(feature, CommandID);

	if (command == NULL)
		return HDC_Reply_Error(HDC_ReplyErrorCode_UNKNOWN_COMMAND, RequestMessage);


	command->HandleRequest(feature, RequestMessage, MessageSize);
}


