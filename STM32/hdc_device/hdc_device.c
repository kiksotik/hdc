
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

#define NUM_MANDATORY_COMMANDS 2
#define NUM_MANDATORY_EVENTS 2
#define NUM_MANDATORY_PROPERTIES 2

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
const HDC_Descriptor_Command_t *HDC_MandatoryCommands[];
const HDC_Descriptor_Event_t *HDC_MandatoryEvents[];
const HDC_Descriptor_Property_t *HDC_MandatoryProperties[];

/////////////////////////////////
// Handle of the HDC singleton
struct HDC_struct {

  // Configuration
  UART_HandleTypeDef* huart;
  HDC_Descriptor_Feature_t** Features;
  uint8_t NumFeatures;
  HDC_MessageHandler_t CustomMsgRouter;

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


  // State
  bool isInitialized;
  volatile bool isDmaRxComplete;
  volatile bool isDmaTxComplete;
  uint8_t currentDmaBufferTx;

} hHDC = { 0 };

// Interrupt handler that must be called from HAL_UARTEx_RxEventCallback()
// Typically triggered by the UART-IDLE event, thus allowing us to process data as soon as the burst is over!
void HDC_RxEventCallback(UART_HandleTypeDef *huart, uint16_t Size) {
  if (huart != hHDC.huart)
    return;

  // Note how unruly hosts sending too large requests will be scrambling their own
  // packets, because of the DMA-circular mode. The parser will interpret those as
  // reading-frame-errors and restart reception, so that any subsequent packets will
  // be received correctly.

  // Note how the DMA-circular mode will cause Size=0 whenever packet is as big as the RX buffer is.
  hHDC.NumBytesInBufferRx = (Size==0) ? HDC_BUFFER_SIZE_RX : Size;
  hHDC.isDmaRxComplete = true;
}

// Interrupt handler that must be called from HAL_UART_TxCpltCallback
void HDC_TxCpltCallback(UART_HandleTypeDef *huart) {
  if (huart != hHDC.huart)
    return;

  hHDC.isDmaTxComplete = true;
}


////////////////////////////////////////////
// Utility methods
HDC_Descriptor_Feature_t* HDC_GetFeature(const uint8_t featureID) {
  for (uint8_t i=0 ; i < hHDC.NumFeatures; i++) {
    if (hHDC.Features[i]->FeatureID == featureID)
      return hHDC.Features[i];
  }
  return NULL;
}

const HDC_Descriptor_Command_t* HDC_GetCommand(const HDC_Descriptor_Feature_t *feature, const uint8_t commandID) {
  for (uint8_t i=0; i< feature->NumCommands;i++)
    if (feature->Commands[i]->CommandID == commandID)
      return feature->Commands[i];

  for (uint8_t i=0; i<NUM_MANDATORY_COMMANDS;i++)
      if (HDC_MandatoryCommands[i]->CommandID == commandID)
        return HDC_MandatoryCommands[i];
  return NULL;
}

const HDC_Descriptor_Event_t* HDC_GetEvent(const HDC_Descriptor_Feature_t *feature, const uint8_t eventID) {
  for (uint8_t i = 0; i < feature->NumEvents; i++)
    if (feature->Events[i]->EventID == eventID)
      return feature->Events[i];

  for (uint8_t i=0; i<NUM_MANDATORY_EVENTS ; i++)
      if (HDC_MandatoryEvents[i]->EventID == eventID)
        return HDC_MandatoryEvents[i];
  return NULL;
}

const HDC_Descriptor_Property_t* HDC_GetProperty(const HDC_Descriptor_Feature_t *hHDC_Feature, const uint8_t propertyID) {

  for (uint8_t i=0 ; i < hHDC_Feature->NumProperties ; i++)
    if (hHDC_Feature->Properties[i]->PropertyID == propertyID)
      return hHDC_Feature->Properties[i];

  for (uint8_t i=0; i<NUM_MANDATORY_PROPERTIES ; i++)
    if (HDC_MandatoryProperties[i]->PropertyID == propertyID)
      return HDC_MandatoryProperties[i];

  return NULL;
}

const char* HDC_GetDataTypeName(const HDC_DataTypeID_t data_type_id){
  switch (data_type_id){
    case HDC_DataTypeID_UINT8: return "UINT8";
    case HDC_DataTypeID_UINT16: return "UINT16";
    case HDC_DataTypeID_UINT32: return "UINT32";
    case HDC_DataTypeID_INT8: return "INT8";
    case HDC_DataTypeID_INT16: return "INT16";
    case HDC_DataTypeID_INT32: return "INT32";
    case HDC_DataTypeID_FLOAT: return "FLOAT";
    case HDC_DataTypeID_DOUBLE: return "DOUBLE";
    case HDC_DataTypeID_BOOL: return "BOOL";
    case HDC_DataTypeID_BLOB: return "BLOB";
    case HDC_DataTypeID_UTF8: return "UTF8";
    case HDC_DataTypeID_DTYPE: return "DTYPE";
    default:
      Error_Handler();
      return "UNKNOWN!";  // Usually unreachable
  }
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
  if (HAL_UART_Transmit_DMA(hHDC.huart, hHDC.BufferTx[hHDC.currentDmaBufferTx], hHDC.NumBytesInBufferTx[hHDC.currentDmaBufferTx]) != HAL_OK)
    Error_Handler();

  // Use the other buffer for composing further reply messages
  indexOfBufferBeingComposed = hHDC.currentDmaBufferTx == 0 ? 1 : 0;

  *pBuffer = hHDC.BufferTx[indexOfBufferBeingComposed];
  *pNumBytesInBuffer = &hHDC.NumBytesInBufferTx[indexOfBufferBeingComposed];
}

void HDC_StartTransmittingAnyPendingPackets() {
  // Note how requesting a composition buffer as big as the buffer's maximum capacity will:
  //   - If the current composition buffer is empty: --> Do nothing! :-)
  //   - If the current composition buffer is not empty, it won't have the requested capacity, thus switch buffers and start sending it

  uint8_t *pBuffer = 0;
  uint16_t *pNumBytesInBuffer = 0;
  HDC_GetTxBufferWithCapacityForAtLeast(HDC_BUFFER_SIZE_TX, &pBuffer, &pNumBytesInBuffer);
}



/////////////////////////////////////
// HDC-packets are composed directly
// into one of the TX buffers

void HDC_Compose_EmptyPacket() {
  const uint8_t PacketPayloadSize = 0;

  uint8_t *pBuffer = 0;
  uint16_t *pNumBytesInBuffer = 0;
  HDC_GetTxBufferWithCapacityForAtLeast(PacketPayloadSize + HDC_PACKET_OVERHEAD, &pBuffer, &pNumBytesInBuffer);

  pBuffer[(*pNumBytesInBuffer)++] = PacketPayloadSize;
  pBuffer[(*pNumBytesInBuffer)++] = 0x00;  // Checksum of zero payload is also zero.
  pBuffer[(*pNumBytesInBuffer)++] = HDC_PACKET_TERMINATOR;
}


/*
 * Packetizes payloads whose size is not known ahead of time, i.e. dynamic JSON string generation for the Meta-reply.
 * This method is meant to be called multiple times:
 *    - First call must pass DataSize=-1 and no data, to initialize the composition.
 *
 *    - Subsequent calls can provide as much data as necessary in as many calls as necessary.
 *      Packets are composed directly into the TX buffers, and are being transmitted as necessary.
 *
 *    - Last call must pass DataSize=-2 and no data, to finalize the composition.
 *
 * Satisfies HDC-spec requirements:
 *    - Payloads larger than 255 bytes will be split into multiple packets.
 *    - Payloads that are an exact multiple of 255 will be terminated with an empty packet.
 *
 * ToDo: Fail more graciously whenever user provides less than 258 bytes for HDC_BUFFER_SIZE_TX but sends larger packets than that.
 */
void HDC_Compose_Packets_From_Stream(
    const uint8_t *const pDataStart,  // Constant pointer to a constant uint8_t: Can't change pointer nor the values it points to.
    int32_t DataSize
   )
{
  assert_param(HDC_BUFFER_SIZE_TX >= 258); // Otherwise we cannot create full packets! ToDo: Is the complexity worth it to deal with smaller TX buffers? Make MsgType META optional for those cases!!

  static const uint8_t* pDataEnd = NULL;  // Non-constant pointer to a constant uint8_t: Pointer can move, but it can not change values it points to.
  static uint8_t* pPktStart = NULL;  // Points at TX buffer address where the packet begins that is currently being composed.
  static uint8_t* pPktEnd = NULL;    // Points at TX buffer address at which to continue appending to the packet that's being composed.
  static uint16_t* pNumBytesInBuffer = NULL;

  bool is_starting_composition = (DataSize == -1);
  if (is_starting_composition) {
    // Initialize new message composition
    assert_param(pDataStart == NULL);
    assert_param(is_composing == false);
    DataSize = 0;  // Do not confuse the remainder of the code-flow!
    // Allocation of TX buffer happens further below
  }

  bool is_finished_composing = (DataSize == -2);
  if (is_finished_composing) {
    assert_param(pDataStart == NULL);
    assert_param(is_composing == true);
    DataSize = 0;  // Do not confuse the remainder of the code-flow!
    // Flushing of current packet happens further below
  }

  pDataEnd = pDataStart; // Points at data item that's still pending to be packetized.

  size_t pending_data;
  do {
    size_t available_packet_payload = 255 - (pPktEnd - pPktStart) + 1;  // Plus one of the leading PS byte of the packet header, which does not count as payload.
    pending_data = DataSize - (pDataEnd - pDataStart);

    size_t num_bytes_to_copy = (pending_data > available_packet_payload) ? available_packet_payload : pending_data;
    memcpy(pPktEnd, pDataEnd, num_bytes_to_copy);

    *pNumBytesInBuffer += num_bytes_to_copy;
    pDataEnd += num_bytes_to_copy;
    pPktEnd += num_bytes_to_copy;
    pending_data -= num_bytes_to_copy;
    available_packet_payload -= num_bytes_to_copy;

    bool is_packet_full = (available_packet_payload==0) && !is_starting_composition;

    if (is_packet_full || is_finished_composing) {
      // First byte of the packet is the size of the payload
      uint8_t packet_size = pPktEnd - pPktStart - 1;
      *pPktStart = packet_size;
      // Penultimate byte of the packet is the two's complement checksum
      uint8_t checksum = 0;
      for (uint8_t *p=pPktStart+1 ; p<pPktEnd ; p++)
        checksum += *p;
      checksum = (uint8_t)0xFF - checksum + 1;
      *pPktEnd = checksum;  // pPktEnd is pointing to byte that follows the last payload byte
      // Last byte of the packet is the HDC terminator
      *(pPktEnd+1) = HDC_PACKET_TERMINATOR;

      *pNumBytesInBuffer += 3; // The one byte we prepended and the two bytes we just appended to the payload
    }

    if (is_starting_composition || is_packet_full) {
      HDC_GetTxBufferWithCapacityForAtLeast(255+HDC_PACKET_OVERHEAD, &pPktStart, &pNumBytesInBuffer);  // Assuming we are going to fill up one packet
      pPktEnd = pPktStart + 1;  // Skip leading PS byte of the packet header. Will be populated later, when packet is completed.
    }

  } while (pending_data);

  if (is_finished_composing) {
    // Reset static variables to initial values
    pDataEnd = NULL;
    pPktStart = NULL;
    pPktEnd = NULL;
    pNumBytesInBuffer = NULL;
  }
}


/*
 * Packetizes data provided as a single, contiguous block.
 * Packets are composed directly into the TX buffers, and are being transmitted as necessary.
 * Whether data contains one or more HDC-messages is up to the caller.
 *
 * For composition of HDC-messages emitted by the HDC-Feature-layer it might be more convenient
 * to use HDC_Compose_Message_From_Pieces(), instead, because it combines message- and
 * packet-composition in a single call.
 */
void HDC_Compose_Packets_From_Buffer(const uint8_t* pData, const uint16_t DataSize) {
  HDC_Compose_Packets_From_Stream(NULL, -1);        // Initialize packet composition
  HDC_Compose_Packets_From_Stream(pData, DataSize); // Packetize data
  HDC_Compose_Packets_From_Stream(NULL, -2);        // Finalize packet composition
}


/*
 * A more convenient way to packetize one Command- or Event-message in a single call.
 * Besides passing the four header bytes as individual values, the message payload can
 * be supplied as two chunks (prefix & suffix), which is convenient in many use-cases.
 * The ExcID argument will only be used to compose Command-messages.
 */
void HDC_Compose_Message_From_Pieces(
    const uint8_t MsgType,
    const uint8_t FeatureID,
    const uint8_t CmdOrEvtID,
    const uint8_t ExcID,
    const uint8_t* pMsgPayloadPrefix,
    const size_t MsgPayloadPrefixSize,
    const uint8_t* pMsgPayloadSuffix,
    const size_t MsgPayloadSuffixSize)
{
  HDC_Compose_Packets_From_Stream(NULL, -1);        // Initialize packet composition
  HDC_Compose_Packets_From_Stream(&MsgType, 1);     // Msg[0] = MessageTypeID
  HDC_Compose_Packets_From_Stream(&FeatureID, 1);   // Msg[1] = FeatureID
  HDC_Compose_Packets_From_Stream(&CmdOrEvtID, 1);  // Msg[2] = CommandID or EventID

  if (MsgType == HDC_MessageTypeID_Command)
      HDC_Compose_Packets_From_Stream(&ExcID, 1);   // Msg[3] = ExceptionID

  if (MsgPayloadPrefixSize > 0)
    HDC_Compose_Packets_From_Stream(pMsgPayloadPrefix, MsgPayloadPrefixSize);  // Append first chunk of the message payload

  if (MsgPayloadSuffixSize > 0)
    HDC_Compose_Packets_From_Stream(pMsgPayloadSuffix, MsgPayloadSuffixSize);  // Append second chunk of the message payload

  HDC_Compose_Packets_From_Stream(NULL, -2);  // Finalize packet composition
}


/////////////////////////////////////////
// HDC replies to Command requests

void HDC_CmdReply_From_Pieces(
    const uint8_t FeatureID,
    const uint8_t CmdID,
    const uint8_t ExcID,
    const uint8_t* pMsgPayloadPrefix,
    const size_t MsgPayloadPrefixSize,
    const uint8_t* pMsgPayloadSuffix,
    const size_t MsgPayloadSuffixSize)
{

  HDC_Compose_Message_From_Pieces(
    HDC_MessageTypeID_Command,
    FeatureID,
    CmdID,
    ExcID,
    pMsgPayloadPrefix, MsgPayloadPrefixSize,
    pMsgPayloadSuffix, MsgPayloadSuffixSize);

}

void HDC_CmdReply_Error_WithDescription(
    const uint8_t ExceptionID,
    const char* ErrorDescription,
    const uint8_t* pRequestMessage)
{
  // It is only legal to include a description in the reply when an error happened. When no error happened, we must reply as expected for the given command!
  assert_param(ExceptionID != 0x00 || ErrorDescription == NULL);

  // The error description is optional
  size_t ErrorDescriptionSize = (ErrorDescription == NULL) ? 0 : strlen(ErrorDescription);

  HDC_CmdReply_From_Pieces(
    pRequestMessage[1],  // Infer FeatureID from request-header
    pRequestMessage[2],  // Infer CommandID from request-header
    ExceptionID,
    (uint8_t *) ErrorDescription, ErrorDescriptionSize,
    NULL, 0);  // No payload-suffix
}

void HDC_CmdReply_Error(
    const uint8_t ExceptionID,
    const uint8_t* pRequestMessage)
{
  HDC_CmdReply_Error_WithDescription(ExceptionID, NULL, pRequestMessage);
}

// Reply of Commands that return no values. (a.k.a. a "void" command reply)
void HDC_CmdReply_Void(const uint8_t* pRequestMessage)
{
  HDC_CmdReply_Error(0x00, pRequestMessage);  // ExceptionID=0x00 means "NO ERROR"
}


//////////////////////////////////////////
// HDC replies to PropertyGet/Set requests

void HDC_CmdReply_BlobValue(
    const uint8_t* pBlob,
    const size_t BlobSize,
    const uint8_t* pRequestMessage)
{

  HDC_CmdReply_From_Pieces(
    pRequestMessage[1],  // Infer FeatureID from request-header
    pRequestMessage[2],  // Infer CommandID from request-header
    0x00,                // ExceptionID=0x00 means "NO ERROR"
    pBlob, BlobSize,
    NULL, 0);  // No payload-suffix

}

void HDC_CmdReply_BoolValue(const bool value, const uint8_t* pRequestMessage) {
  HDC_CmdReply_BlobValue((uint8_t*)&value, 1, pRequestMessage);
}

void HDC_CmdReply_UInt8Value(const uint8_t value, const uint8_t* pRequestMessage) {
  HDC_CmdReply_BlobValue(&value, 1, pRequestMessage);
}

void HDC_CmdReply_UInt16Value(const uint16_t value, const uint8_t* pRequestMessage) {
  // Note that STM32 is little-endian
  HDC_CmdReply_BlobValue((uint8_t*)&value, 2, pRequestMessage);
}

void HDC_CmdReply_UInt32Value(const uint32_t value, const uint8_t* pRequestMessage) {
  // Note that STM32 is little-endian
  HDC_CmdReply_BlobValue((uint8_t*)&value, 4, pRequestMessage);
}

void HDC_CmdReply_Int8Value(const int8_t value, const uint8_t* pRequestMessage) {
  HDC_CmdReply_BlobValue((uint8_t*)&value, 1, pRequestMessage);
}

void HDC_CmdReply_Int16Value(const int16_t value, const uint8_t* pRequestMessage) {
  // Note that STM32 is little-endian
  HDC_CmdReply_BlobValue((uint8_t*)&value, 2, pRequestMessage);
}

void HDC_CmdReply_Int32Value(const int32_t value, const uint8_t* pRequestMessage) {
  // Note that STM32 is little-endian
  HDC_CmdReply_BlobValue((uint8_t*)&value, 4, pRequestMessage);
}

void HDC_CmdReply_FloatValue(const float value, const uint8_t* pRequestMessage) {
  // Note that STM32 is little-endian
  HDC_CmdReply_BlobValue((uint8_t*)&value, 4, pRequestMessage);
}

void HDC_CmdReply_DoubleValue(const double value, const uint8_t* pRequestMessage) {
  // Note that STM32 is little-endian
  HDC_CmdReply_BlobValue((uint8_t*)&value, 8, pRequestMessage);
}

void HDC_CmdReply_StringValue(const char* value, const uint8_t* pRequestMessage) {
  if (value == NULL)
    // Treat null-pointer in the same way as an "empty string"
    return HDC_CmdReply_BlobValue(NULL, 0, pRequestMessage);

  // Omit string's zero-termination byte! Note how the string's length is determined by the HDC-message size.
  HDC_CmdReply_BlobValue((uint8_t*)value, strlen(value), pRequestMessage);
}

void HDC_CmdReply_DTypeValue(const HDC_DataTypeID_t value, const uint8_t* pRequestMessage) {
  HDC_CmdReply_BlobValue((uint8_t*)&value, 1, pRequestMessage);
}


/////////////////////////////////////////////////
// Request Handlers for mandatory Commands

void HDC_Cmd_GetPropertyValue(
    const HDC_Descriptor_Feature_t *hHDC_Feature,
    const uint8_t* pRequestMessage,
    const uint8_t Size)
{
  uint8_t CommandID = pRequestMessage[2];
  if (CommandID==HDC_CommandID_GetPropertyValue && Size != 4)  // Skip validation whenever called from HDC_Cmd_SetPropertyValue()
    return HDC_CmdReply_Error(HDC_Descriptor_Exc_InvalidArgs.id, pRequestMessage);

  assert_param(pRequestMessage[0] == HDC_MessageTypeID_Command);
  assert_param(CommandID == HDC_CommandID_GetPropertyValue || CommandID == HDC_CommandID_SetPropertyValue);  // This may have been called via HDC_Cmd_SetPropertyValue()

  uint8_t FeatureID = pRequestMessage[1];
  uint8_t PropertyID = pRequestMessage[3];

  const HDC_Descriptor_Feature_t* feature = HDC_GetFeature(FeatureID);

  if (feature == NULL)
    return HDC_CmdReply_Error(HDC_Descriptor_Exc_UnknownFeature.id, pRequestMessage);

  const HDC_Descriptor_Property_t* property = HDC_GetProperty(feature, PropertyID);

  if (property == NULL)
    return HDC_CmdReply_Error(HDC_Descriptor_Exc_UnknownProperty.id, pRequestMessage);

  if (property->GetPropertyValue != NULL)
    return property->GetPropertyValue(feature, property, pRequestMessage, Size);

  if (property->pValue == NULL)
    Error_Handler();  // ToDo: Complain about incorrect descriptor.

  switch (property->PropertyDataType) {

  case HDC_DataTypeID_BOOL:
    return HDC_CmdReply_BoolValue(*(bool*)property->pValue, pRequestMessage);

  case HDC_DataTypeID_UINT8:
    return HDC_CmdReply_UInt8Value(*(uint8_t*)property->pValue, pRequestMessage);

  case HDC_DataTypeID_UINT16:
    return HDC_CmdReply_UInt16Value(*(uint16_t*)property->pValue, pRequestMessage);

  case HDC_DataTypeID_UINT32:
    return HDC_CmdReply_UInt32Value(*(uint32_t*)property->pValue, pRequestMessage);

  case HDC_DataTypeID_INT8:
    return HDC_CmdReply_Int8Value(*(int8_t*)property->pValue, pRequestMessage);

  case HDC_DataTypeID_INT16:
    return HDC_CmdReply_Int16Value(*(int16_t*)property->pValue, pRequestMessage);

  case HDC_DataTypeID_INT32:
    return HDC_CmdReply_Int32Value(*(int32_t*)property->pValue, pRequestMessage);

  case HDC_DataTypeID_FLOAT:
    return HDC_CmdReply_FloatValue(*(float*)property->pValue, pRequestMessage);

  case HDC_DataTypeID_DOUBLE:
    return HDC_CmdReply_DoubleValue(*(double*)property->pValue, pRequestMessage);

  case HDC_DataTypeID_UTF8:
    return HDC_CmdReply_StringValue((char *)property->pValue, pRequestMessage);

  case HDC_DataTypeID_BLOB:
    if (property->ValueSize == 0)
      Error_Handler();  // ToDo: Complain about incorrect descriptor.
    return HDC_CmdReply_BlobValue(
        (uint8_t *)property->pValue,
        property->ValueSize,
        pRequestMessage);

  case HDC_DataTypeID_DTYPE:
    return HDC_CmdReply_DTypeValue(*(HDC_DataTypeID_t*)property->pValue, pRequestMessage);

  default:
    Error_Handler();  // ToDo: Complain about unknown property-data-type
  }
}

void HDC_Cmd_SetPropertyValue(
    const HDC_Descriptor_Feature_t *hHDC_Feature,
    const uint8_t* pRequestMessage,
    const uint8_t Size)
{
  assert_param(pRequestMessage[0] == HDC_MessageTypeID_Command);
  assert_param(pRequestMessage[2] == HDC_CommandID_SetPropertyValue);

  uint8_t FeatureID = pRequestMessage[1];
  uint8_t PropertyID = pRequestMessage[3];

  HDC_Descriptor_Feature_t* feature = HDC_GetFeature(FeatureID);

  if (feature == NULL)
    return HDC_CmdReply_Error(HDC_Descriptor_Exc_UnknownFeature.id, pRequestMessage);

  const HDC_Descriptor_Property_t *property = HDC_GetProperty(feature, PropertyID);

  if (property == NULL)
    return HDC_CmdReply_Error(HDC_Descriptor_Exc_UnknownProperty.id, pRequestMessage);

  if (property->PropertyIsReadonly)
    return HDC_CmdReply_Error(HDC_Descriptor_Exc_ReadOnlyProperty.id, pRequestMessage);

  // Validate size of received value
  uint8_t receivedValueSize = Size - 4;
  const uint8_t *pNewValueAsRawBytes = pRequestMessage + 4;

  // Lower nibble of a DataType's ID provides a hint about the size.
  const uint8_t lowerNibble = property->PropertyDataType & 0x0F;

  if (lowerNibble == 0x0F) {  // Exception is 0x_F, which means it's a variable size data-type
    if (property->ValueSize == 0)
      Error_Handler();  // ToDo: Complain about incorrect descriptor!

    // Check for buffer overflow
    if (receivedValueSize >= property->ValueSize)  // Comparing with greater-or-equal to reserve one byte for the zero-terminator!
      return HDC_CmdReply_Error(HDC_Descriptor_Exc_InvalidArgs.id, pRequestMessage);

    // Otherwise it's legal to receive a shorter value :-)
    // Note how empty values are legal, too.

  } else {
    const size_t expectedValueSize =
        (lowerNibble == 0)  // Special case for BOOL, whose DataTypeID is 0x00
        ? 1
        : lowerNibble;

    if (receivedValueSize != expectedValueSize)
      return HDC_CmdReply_Error(HDC_Descriptor_Exc_InvalidArgs.id, pRequestMessage);
  }

  if (property->SetPropertyValue != NULL)
    return property->SetPropertyValue(feature, property, pRequestMessage, Size);

  if (property->pValue == NULL)
    Error_Handler();  // ToDo: Complain about incorrect descriptor.

  memcpy(property->pValue, pNewValueAsRawBytes, receivedValueSize);

  if (property->PropertyDataType == HDC_DataTypeID_UTF8)
    *(((uint8_t*)property->pValue)+receivedValueSize) = 0;  // Zero-terminator for the string!

  // Note how the reply of a SetPropertyValue request is essentially
  // the same as for the GetPropertyValue request, except for the CommandID.
  return HDC_Cmd_GetPropertyValue(hHDC_Feature, pRequestMessage, Size);

}

///////////////////////////////////////////
// Descriptors of predefined exceptions
const HDC_Descriptor_Exc_t HDC_Descriptor_Exc_CommandFailed = {.id=0xF0, .name="CommandFailed"};
const HDC_Descriptor_Exc_t HDC_Descriptor_Exc_UnknownFeature = {.id=0xF1, .name="UnknownFeature"};
const HDC_Descriptor_Exc_t HDC_Descriptor_Exc_UnknownCommand = {.id=0xF2, .name="UnknownCommand"};
const HDC_Descriptor_Exc_t HDC_Descriptor_Exc_InvalidArgs = {.id=0xF3, .name="InvalidArgs"};
const HDC_Descriptor_Exc_t HDC_Descriptor_Exc_NotNow = {.id=0xF4, .name="NotNow", .doc="Command can't be executed at this moment."};
const HDC_Descriptor_Exc_t HDC_Descriptor_Exc_UnknownProperty = {.id=0xF5, .name="UnknownProperty"};
const HDC_Descriptor_Exc_t HDC_Descriptor_Exc_ReadOnlyProperty = {.id=0xF6, .name="ReadOnlyProperty"};


///////////////////////////////////////////
// Descriptors of mandatory Commands

const HDC_Descriptor_Command_t *HDC_MandatoryCommands[NUM_MANDATORY_COMMANDS] = {

  &(HDC_Descriptor_Command_t){
    .CommandID = HDC_CommandID_GetPropertyValue,
    .CommandName = "GetPropertyValue",
    .CommandHandler = &HDC_Cmd_GetPropertyValue,
    .arg1 = &(HDC_Descriptor_Arg_t) {.dtype=HDC_DataTypeID_UINT8, .name="PropertyID"},
    .ret1 = &(HDC_Descriptor_Ret_t) {.dtype=HDC_DataTypeID_BLOB, .doc="Actual data-type depends on property"},
    .raises = (const HDC_Descriptor_Exc_t*[1]) {&HDC_Descriptor_Exc_UnknownProperty},
    .numraises = 1
  },

  &(HDC_Descriptor_Command_t){
    .CommandID = HDC_CommandID_SetPropertyValue,
    .CommandName = "SetPropertyValue",
    .CommandHandler = &HDC_Cmd_SetPropertyValue,
    .arg1 = &(HDC_Descriptor_Arg_t) {.dtype=HDC_DataTypeID_UINT8, .name="PropertyID"},
    .arg2 = &(HDC_Descriptor_Arg_t) {.dtype=HDC_DataTypeID_BLOB, .name="NewValue", .doc="Actual data-type depends on property"},
    .ret1 = &(HDC_Descriptor_Ret_t) {.dtype=HDC_DataTypeID_BLOB, .name="ActualNewValue", .doc="May differ from NewValue!"},
    .raises = (const HDC_Descriptor_Exc_t*[2]) {&HDC_Descriptor_Exc_UnknownProperty, &HDC_Descriptor_Exc_ReadOnlyProperty},
    .numraises = 2
  },
};

/////////////////////
// Event descriptors

const HDC_Descriptor_Event_t HDC_Event_Log = {
  .EventID = HDC_EventID_Log,
  .EventName = "Log",
  .EventDescription = "Forwards software event log to the host.",
  .arg1 = &(HDC_Descriptor_Arg_t) {.dtype=HDC_DataTypeID_UINT8, .name="LogLevel", .doc="Same as in Python"},
  .arg2 = &(HDC_Descriptor_Arg_t) {.dtype=HDC_DataTypeID_UTF8, .name="LogMsg"},
};

const HDC_Descriptor_Event_t HDC_Event_FeatureStateTransition = {
  .EventID = HDC_EventID_FeatureStateTransition,
  .EventName = "FeatureStateTransition",
  .EventDescription = "Notifies host about transitions of this feature's state-machine.",
  .arg1 = &(HDC_Descriptor_Arg_t) {.dtype=HDC_DataTypeID_UINT8, .name="PreviousStateID"},
  .arg2 = &(HDC_Descriptor_Arg_t) {.dtype=HDC_DataTypeID_UINT8, .name="CurrentStateID"},
};

const HDC_Descriptor_Event_t *HDC_MandatoryEvents[NUM_MANDATORY_EVENTS] = {
    &HDC_Event_Log,
    &HDC_Event_FeatureStateTransition
};


//////////////////////////////
// Event API

void HDC_EvtMsg(const HDC_Descriptor_Feature_t *hHDC_Feature,
                     const uint8_t EventID,
                     const uint8_t* pEvtPayloadPrefix,
                     const size_t EvtPayloadPrefixSize,
                     const uint8_t* pEvtPayloadSuffix,
                     const size_t EvtPayloadSuffixSize) {

  if (hHDC_Feature == NULL)
    // Default to Core-Feature, which by convention is the first array item.
    hHDC_Feature = hHDC.Features[0];

  HDC_Compose_Message_From_Pieces(
    HDC_MessageTypeID_Event,
    hHDC_Feature->FeatureID,
    EventID,
    0x00,  // ExceptionID will be ignored by packetizer method, due to MessageType being Event
    pEvtPayloadPrefix,
    EvtPayloadPrefixSize,
    pEvtPayloadSuffix,
    EvtPayloadSuffixSize);

}

void HDC_EvtMsg_Log(
    const HDC_Descriptor_Feature_t *hHDC_Feature,
    HDC_EventLogLevel_t logLevel,
    char* logText) {

  if (hHDC_Feature == NULL)
    // Default to Core-Feature, which by convention is the first array item.
    hHDC_Feature = hHDC.Features[0];

  if (logLevel < hHDC_Feature->LogEventThreshold)
    return;

  HDC_EvtMsg(
    hHDC_Feature,
    HDC_Event_Log.EventID,
    &logLevel,
    1,
    (uint8_t*) logText,
    strlen(logText));
}


/////////////////////////////
// FeatureState API


/*
 * Updates the FeatureState property value and raises a FeatureStateTransition-event
 */
void HDC_FeatureStateTransition(HDC_Descriptor_Feature_t *hHDC_Feature, uint8_t newState) {
  if (hHDC_Feature == NULL)
    // Default to Core-Feature, which by convention is the first array item.
    hHDC_Feature = hHDC.Features[0];

  if (newState == hHDC_Feature->FeatureState)
    return;  // Avoid transition into the same state we already are.

  // ToDo: State descriptors are optional, but when provided: Validate newState value!

  uint8_t oldState = hHDC_Feature->FeatureState;
  hHDC_Feature->FeatureState = newState;

  HDC_EvtMsg(
    hHDC_Feature,
    HDC_Event_FeatureStateTransition.EventID,
    &oldState,
    1,
    &newState,
    1);

}


///////////////////////////////////////////////
// Getters and setters for mandatory Properties

void HDC_Property_LogEventThreshold_get(
    const HDC_Descriptor_Feature_t *hHDC_Feature,
    const HDC_Descriptor_Property_t *hHDC_Property,
    const uint8_t* pRequestMessage,
    const uint8_t RequestMessageSize)
{
  HDC_CmdReply_UInt8Value(hHDC_Feature->LogEventThreshold, pRequestMessage);
}

void HDC_Property_LogEventThreshold_set(
    HDC_Descriptor_Feature_t *hHDC_Feature,
    const HDC_Descriptor_Property_t *hHDC_Property,
    const uint8_t* pRequestMessage,
    const uint8_t RequestMessageSize)
{
  uint8_t newValue = *((const uint8_t *)(pRequestMessage + 4));

  newValue = CONSTRAIN(newValue, HDC_EventLogLevel_DEBUG, HDC_EventLogLevel_CRITICAL);

  // Disallowing custom levels because of the same rationale as explained here:
  //     https://docs.python.org/3.10/howto/logging.html#custom-levels
  // Therefore rounding to the nearest multiple of 10. https://stackoverflow.com/a/2422723/20337562
  newValue = ((newValue + 5) / 10) * 10;

  hHDC_Feature->LogEventThreshold = newValue;
  HDC_CmdReply_UInt8Value(hHDC_Feature->LogEventThreshold, pRequestMessage);
}

void HDC_Property_FeatureState_get(
    const HDC_Descriptor_Feature_t *hHDC_Feature,
    const HDC_Descriptor_Property_t *hHDC_Property,
    const uint8_t* pRequestMessage,
    const uint8_t RequestMessageSize)
{
  HDC_CmdReply_UInt8Value(hHDC_Feature->FeatureState, pRequestMessage);
}


//////////////////////////////////////
// Descriptors of mandatory Properties

const HDC_Descriptor_Property_t *HDC_MandatoryProperties[NUM_MANDATORY_PROPERTIES] = {

  &(HDC_Descriptor_Property_t ) {
    .PropertyID = HDC_PropertyID_LogEventThreshold,
    .PropertyName = "LogEventThreshold",
    .PropertyDataType = HDC_DataTypeID_UINT8,
    .PropertyIsReadonly = false,
    .GetPropertyValue = HDC_Property_LogEventThreshold_get,
    .SetPropertyValue = HDC_Property_LogEventThreshold_set,
    .PropertyDescription = "Suppresses LogEvents with lower log-levels."
  },

  &(HDC_Descriptor_Property_t ) {
    .PropertyID = HDC_PropertyID_FeatureState,
    .PropertyName = "FeatureState",
    .PropertyDataType = HDC_DataTypeID_UINT8,
    .PropertyIsReadonly = true,
    .GetPropertyValue = HDC_Property_FeatureState_get,
    .PropertyDescription = "Current feature-state"
  },

};


/////////////////////////////////////////////////
// Request Handlers for mandatory Messages

/*
 * Reply to a received echo-message.
 */
void HDC_MsgReply_Echo(
    const uint8_t* pRequestMessage,
    const uint8_t Size)
{
  // Sanity check whether caller did its job correctly
  assert_param(pRequestMessage[0] == HDC_MessageTypeID_Echo);

  // Reply message must be exactly equal to the full request message.
  HDC_Compose_Packets_From_Buffer(pRequestMessage, Size);
}


/*
 * Routing of received command-message to a command-handler which will reply to it.
 *
 * Returns true whenever the message could be forwarded successfully to a command handler
 */
void HDC_MsgReply_Command(
    const uint8_t* pRequestMessage,
    const uint8_t Size)
{
  // Sanity check whether caller did its job correctly
  assert_param(pRequestMessage[0] == HDC_MessageTypeID_Command);
  assert_param(Size >= 3);

  uint8_t FeatureID = pRequestMessage[1];
  uint8_t CommandID = pRequestMessage[2];

  const HDC_Descriptor_Feature_t* feature = HDC_GetFeature(FeatureID);

  if (feature == NULL)
    return HDC_CmdReply_Error(HDC_Descriptor_Exc_UnknownFeature.id, pRequestMessage);

  const HDC_Descriptor_Command_t* command = HDC_GetCommand(feature, CommandID);

  if (command == NULL)
    return HDC_CmdReply_Error(HDC_Descriptor_Exc_UnknownCommand.id, pRequestMessage);

  command->CommandHandler(feature, pRequestMessage, Size);
}

void HDC_JSON_Colon() {
  HDC_Compose_Packets_From_Stream((uint8_t*)":", 1);
}

void HDC_JSON_Comma() {
  HDC_Compose_Packets_From_Stream((uint8_t*)",", 1);
}

void HDC_JSON_Quoted(const char* value) {
  HDC_Compose_Packets_From_Stream((uint8_t*)"\"", 1);
  HDC_Compose_Packets_From_Stream((uint8_t*)value, strlen(value));
  HDC_Compose_Packets_From_Stream((uint8_t*)"\"", 1);
}

void HDC_JSON_Integer(const uint16_t integer) {
  char str[6]; // 65535 + zero terminator!
  sprintf(str, "%d", integer);
  HDC_Compose_Packets_From_Stream((uint8_t*)str, strlen(str));
}

void HDC_JSON_Key(const char* key) {
  HDC_JSON_Quoted(key);
  HDC_JSON_Colon();
}

void HDC_JSON_Object_start(bool* prepend_comma) {
  if (*prepend_comma) HDC_JSON_Comma();
  HDC_Compose_Packets_From_Stream((uint8_t*)"{", 1);
  *prepend_comma = false;  // First child-item should suppress its leading comma
}

void HDC_JSON_Object_end(bool* prepend_comma) {
  HDC_Compose_Packets_From_Stream((uint8_t*)"}", 1);
  *prepend_comma = true;  // Next sibling-item will need to prepend a comma
}

void HDC_JSON_Attr_array_start(const char* key, bool* prepend_comma) {
  if (*prepend_comma) HDC_JSON_Comma();

  HDC_JSON_Quoted(key);
  HDC_JSON_Colon();
  HDC_Compose_Packets_From_Stream((uint8_t*)"[", 1);
  *prepend_comma = false;  // First child-item should suppress its leading comma
}

void HDC_JSON_Array_end(bool* prepend_comma) {
  HDC_Compose_Packets_From_Stream((uint8_t*)"]", 1);
  *prepend_comma = true;  // Next sibling-item will need to prepend a comma
}

void HDC_JSON_Attr_str(const char* key, const char* value, bool* prepend_comma) {
  if (value == NULL)
    // Simply omit the whole attribute.
    // Do *not* use JSON "null" values!
    return;

  if (*prepend_comma) HDC_JSON_Comma();

  HDC_JSON_Quoted(key);
  HDC_JSON_Colon();

  // ToDo: Escape illicit characters contained in string values.
  // But replacing a single character like '\n' with a two character
  // string like "\\n" is not worth the trouble!!
  // We should expect developers to take care of that themselves when
  // populating the descriptors. Can be validated easier than fixed here!
  HDC_JSON_Quoted(value);

  *prepend_comma = true; // Next sibling-item will need to prepend a comma
}

void HDC_JSON_Attr_int(const char* key, const uint16_t value, bool* prepend_comma) {
  if (*prepend_comma) HDC_JSON_Comma();
  HDC_JSON_Quoted(key);
  HDC_JSON_Colon();
  HDC_JSON_Integer(value);
  *prepend_comma = true; // Next sibling-item will need to prepend a comma
}

void HDC_JSON_Attr_bool(const char* key, const bool value, bool* prepend_comma) {
  if (*prepend_comma) HDC_JSON_Comma();
  HDC_JSON_Quoted(key);
  HDC_JSON_Colon();
  if (value)
    HDC_Compose_Packets_From_Stream((uint8_t*)"true", 4);
  else
    HDC_Compose_Packets_From_Stream((uint8_t*)"false", 5);

  *prepend_comma = true; // Next sibling-item will need to prepend a comma
}

void HDC_JSON_State(const HDC_Descriptor_State_t *d, bool* prepend_comma) {
  HDC_JSON_Object_start(prepend_comma);
  HDC_JSON_Attr_int("id", d->id, prepend_comma);
  HDC_JSON_Attr_str("name", d->name, prepend_comma);
  HDC_JSON_Attr_str("doc", d->doc, prepend_comma);
  HDC_JSON_Object_end(prepend_comma);
}

void HDC_JSON_Arg(const HDC_Descriptor_Arg_t *d, bool* prepend_comma) {
  if (d == NULL)
    return;  // Omit the whole object

  HDC_JSON_Object_start(prepend_comma);
  HDC_JSON_Attr_str("dtype", HDC_GetDataTypeName(d->dtype), prepend_comma);
  HDC_JSON_Attr_str("name", d->name, prepend_comma);
  HDC_JSON_Attr_str("doc", d->doc, prepend_comma);
  HDC_JSON_Object_end(prepend_comma);
}

void HDC_JSON_Ret(const HDC_Descriptor_Ret_t *d, bool* prepend_comma) {
  if (d == NULL)
    return;  // Omit the whole object
  
  HDC_JSON_Object_start(prepend_comma);
  HDC_JSON_Attr_str("dtype", HDC_GetDataTypeName(d->dtype), prepend_comma);
  HDC_JSON_Attr_str("name", d->name, prepend_comma);
  HDC_JSON_Attr_str("doc", d->doc, prepend_comma);
  HDC_JSON_Object_end(prepend_comma);
}

void HDC_JSON_Exc(const HDC_Descriptor_Exc_t *d, bool* prepend_comma) {
  if (d == NULL)
    return;  // Omit the whole object

  HDC_JSON_Object_start(prepend_comma);
  HDC_JSON_Attr_int("id", d->id, prepend_comma);
  HDC_JSON_Attr_str("name", d->name, prepend_comma);
  HDC_JSON_Attr_str("doc", d->doc, prepend_comma);
  HDC_JSON_Object_end(prepend_comma);
}

void HDC_JSON_Command(const HDC_Descriptor_Command_t *d, bool* prepend_comma) {
  HDC_JSON_Object_start(prepend_comma);
  HDC_JSON_Attr_int("id", d->CommandID, prepend_comma);
  HDC_JSON_Attr_str("name", d->CommandName, prepend_comma);
  HDC_JSON_Attr_str("doc", d->CommandDescription, prepend_comma);

  HDC_JSON_Attr_array_start("args", prepend_comma);
  HDC_JSON_Arg(d->arg1, prepend_comma);
  HDC_JSON_Arg(d->arg2, prepend_comma);
  HDC_JSON_Arg(d->arg3, prepend_comma);
  HDC_JSON_Arg(d->arg4, prepend_comma);
  HDC_JSON_Array_end(prepend_comma);

  HDC_JSON_Attr_array_start("returns", prepend_comma);
  HDC_JSON_Ret(d->ret1, prepend_comma);
  HDC_JSON_Ret(d->ret2, prepend_comma);
  HDC_JSON_Ret(d->ret3, prepend_comma);
  HDC_JSON_Ret(d->ret4, prepend_comma);
  HDC_JSON_Array_end(prepend_comma);

  HDC_JSON_Attr_array_start("raises", prepend_comma);
  for (int i = 0; i < d->numraises; ++i)
    HDC_JSON_Exc(d->raises[i], prepend_comma);
  HDC_JSON_Array_end(prepend_comma);

  HDC_JSON_Object_end(prepend_comma);
}

void HDC_JSON_Event(const HDC_Descriptor_Event_t *d, bool* prepend_comma) {
  HDC_JSON_Object_start(prepend_comma);

  HDC_JSON_Attr_int("id", d->EventID, prepend_comma);
  HDC_JSON_Attr_str("name", d->EventName, prepend_comma);
  HDC_JSON_Attr_str("doc", d->EventDescription, prepend_comma);

  HDC_JSON_Attr_array_start("args", prepend_comma);
  HDC_JSON_Arg(d->arg1, prepend_comma);
  HDC_JSON_Arg(d->arg2, prepend_comma);
  HDC_JSON_Arg(d->arg3, prepend_comma);
  HDC_JSON_Arg(d->arg4, prepend_comma);
  HDC_JSON_Array_end(prepend_comma);

  HDC_JSON_Object_end(prepend_comma);
}

void HDC_JSON_Property(const HDC_Descriptor_Property_t *d, bool* prepend_comma) {
  HDC_JSON_Object_start(prepend_comma);
  HDC_JSON_Attr_int("id", d->PropertyID, prepend_comma);
  HDC_JSON_Attr_str("name", d->PropertyName, prepend_comma);
  HDC_JSON_Attr_str("dtype", HDC_GetDataTypeName(d->PropertyDataType), prepend_comma);
  if (d->ValueSize > 0 && (d->PropertyDataType == HDC_DataTypeID_BLOB || d->PropertyDataType == HDC_DataTypeID_UTF8))
    HDC_JSON_Attr_int("size", d->ValueSize, prepend_comma);
  HDC_JSON_Attr_bool("ro", d->PropertyIsReadonly, prepend_comma);
  HDC_JSON_Attr_str("doc", d->PropertyDescription, prepend_comma);
  HDC_JSON_Object_end(prepend_comma);
}

void HDC_JSON_Feature(const HDC_Descriptor_Feature_t *d, bool* prepend_comma) {
  HDC_JSON_Object_start(prepend_comma);
  HDC_JSON_Attr_int("id", d->FeatureID, prepend_comma);
  HDC_JSON_Attr_str("name", d->FeatureName, prepend_comma);
  HDC_JSON_Attr_str("cls", d->FeatureClassName, prepend_comma);
  HDC_JSON_Attr_str("version", d->FeatureClassVersion, prepend_comma);
  HDC_JSON_Attr_str("doc", d->FeatureDescription, prepend_comma);

  HDC_JSON_Attr_array_start("states", prepend_comma);
  for (uint8_t idxState=0; idxState < d->NumStates; idxState++)
    HDC_JSON_State(d->States[idxState], prepend_comma);
  HDC_JSON_Array_end(prepend_comma);

  HDC_JSON_Attr_array_start("commands", prepend_comma);
  for (uint8_t idxCmd=0; idxCmd < d->NumCommands; idxCmd++)
    HDC_JSON_Command(d->Commands[idxCmd], prepend_comma);
  for (uint8_t idxCmd=0; idxCmd < NUM_MANDATORY_COMMANDS; idxCmd++)
    HDC_JSON_Command(HDC_MandatoryCommands[idxCmd], prepend_comma);
  HDC_JSON_Array_end(prepend_comma);

  HDC_JSON_Attr_array_start("events", prepend_comma);
  for (uint8_t idxEvt=0; idxEvt < d->NumEvents; idxEvt++)
    HDC_JSON_Event(d->Events[idxEvt], prepend_comma);
  for (uint8_t idxEvt=0; idxEvt < NUM_MANDATORY_EVENTS; idxEvt++)
    HDC_JSON_Event(HDC_MandatoryEvents[idxEvt], prepend_comma);
  HDC_JSON_Array_end(prepend_comma);

  HDC_JSON_Attr_array_start("properties", prepend_comma);
  for (uint8_t idxProp=0; idxProp < d->NumProperties; idxProp++)
    HDC_JSON_Property(d->Properties[idxProp], prepend_comma);
  for (uint8_t idxProp=0; idxProp < NUM_MANDATORY_PROPERTIES; idxProp++)
    HDC_JSON_Property(HDC_MandatoryProperties[idxProp], prepend_comma);
  HDC_JSON_Array_end(prepend_comma);

  HDC_JSON_Object_end(prepend_comma);
}


void HDC_JSON_Device() {
  bool prepend_comma = false;
  HDC_JSON_Object_start(&prepend_comma);
  HDC_JSON_Attr_str("version", HDC_VERSION_STRING, &prepend_comma);
  HDC_JSON_Attr_int("max_req", HDC_MAX_REQ_MESSAGE_SIZE, &prepend_comma);

  HDC_JSON_Attr_array_start("features", &prepend_comma);
  for (uint8_t idxFeature=0; idxFeature < hHDC.NumFeatures; idxFeature++)
    HDC_JSON_Feature(hHDC.Features[idxFeature], &prepend_comma);
  HDC_JSON_Array_end(&prepend_comma);
  HDC_JSON_Object_end(&prepend_comma);
}

void HDC_MsgReply_Meta_IdlJson(
    const uint8_t* pRequestMessage,
    const uint8_t Size)
{
  // Sanity check whether caller did its job correctly
  assert_param(pRequestMessage[0] == HDC_MessageTypeID_Meta);
  assert_param(pRequestMessage[1] == HDC_MetaID_IdlJson);

  // HDC-spec requires to echo the request whenever it contains unexpected arguments.
  if (Size > 2) {
    HDC_EvtMsg_Log(NULL, HDC_EventLogLevel_ERROR, "Unknown Meta-IdlJson request");
    return HDC_Compose_Packets_From_Buffer((uint8_t*)pRequestMessage, Size);
  }

  // ToDo: Return empty reply if request contains any payload.
  //       In future a request may contain arguments and an empty reply means it's an unsupported kind of request.

  HDC_Compose_Packets_From_Stream(NULL, -1);  // Initialize packet composition
  uint8_t msg_header[] = {HDC_MessageTypeID_Meta, HDC_MetaID_IdlJson};
  HDC_Compose_Packets_From_Stream(msg_header, sizeof(msg_header));
  HDC_JSON_Device();
  HDC_Compose_Packets_From_Stream(NULL, -2);  // Finalize packet composition
}


void HDC_MsgReply_Meta_MaxReq(
    const uint8_t* pRequestMessage,
    const uint8_t Size)
{
  // Sanity check whether caller did its job correctly
  assert_param(pRequestMessage[0] == HDC_MessageTypeID_Meta);
  assert_param(pRequestMessage[1] == HDC_MetaID_MaxReq);

  // HDC-spec requires to echo the request whenever it contains unexpected arguments.
  if (Size > 2) {
    HDC_EvtMsg_Log(NULL, HDC_EventLogLevel_ERROR, "Unknown Meta-MaxReq request");
    return HDC_Compose_Packets_From_Buffer((uint8_t*)pRequestMessage, Size);
  }

  uint8_t reply[6] = {0};
  reply[0] = HDC_MessageTypeID_Meta;
  reply[1] = HDC_MetaID_MaxReq;
  *(uint32_t*)(reply+2) = HDC_MAX_REQ_MESSAGE_SIZE;

  HDC_Compose_Packets_From_Buffer(reply, sizeof(reply));
}


void HDC_MsgReply_Meta_HdcVersion(
    const uint8_t* pRequestMessage,
    const uint8_t Size)
{
  // Sanity check whether caller did its job correctly
  assert_param(pRequestMessage[0] == HDC_MessageTypeID_Meta);
  assert_param(pRequestMessage[1] == HDC_MetaID_HdcVersion);

  // HDC-spec requires to echo the request whenever it contains unexpected arguments.
  if (Size > 2) {
    HDC_EvtMsg_Log(NULL, HDC_EventLogLevel_ERROR, "Unknown Meta-HdcVersion request");
    return HDC_Compose_Packets_From_Buffer((uint8_t*)pRequestMessage, Size);
  }

  char pReplyMessage[] = "__" HDC_VERSION_STRING;  // Leading underscores are just a placeholder for the MessageTypeID + MetaID.
  uint8_t ReplySize = strlen(pReplyMessage);

  // Inject MessageTypeID + MetaID header for this to be a valid reply message.
  pReplyMessage[0] = HDC_MessageTypeID_Meta;
  pReplyMessage[1] = HDC_MetaID_HdcVersion;

  HDC_Compose_Packets_From_Buffer((uint8_t*)pReplyMessage, ReplySize);
}

void HDC_MsgReply_Meta(
    const uint8_t* pRequestMessage,
    const uint8_t Size)
{

  // Sanity check whether caller did its job correctly
  assert_param(pRequestMessage[0] == HDC_MessageTypeID_Command);
  assert_param(Size >= 2);

  uint8_t MetaID = pRequestMessage[1];

  switch (MetaID) {
    case HDC_MetaID_HdcVersion:
      return HDC_MsgReply_Meta_HdcVersion(pRequestMessage, Size);
    case HDC_MetaID_MaxReq:
      return HDC_MsgReply_Meta_MaxReq(pRequestMessage, Size);
    case HDC_MetaID_IdlJson:
      return HDC_MsgReply_Meta_IdlJson(pRequestMessage, Size);
    default:
      // HDC-spec requires to echo the request whenever it contains unexpected arguments.
      HDC_EvtMsg_Log(NULL, HDC_EventLogLevel_ERROR, "Unknown Meta request");
      return HDC_Compose_Packets_From_Buffer((uint8_t*)pRequestMessage, Size);
  }


}


/*
 * Routing of received messages (aka requests)
 *
 * Returns true whenever the message could be routed successfully
 */
void HDC_ProcessRxMessage(const uint8_t *pRequestMessage, const uint8_t Size) {

  if (Size==0)
    // Ignore empty messages.
    // They are legal, but currently without purpose.
    return;

  const uint8_t MessageTypeID = pRequestMessage[0];


  switch (MessageTypeID) {
    case HDC_MessageTypeID_Meta:
      return HDC_MsgReply_Meta(pRequestMessage, Size);

    case HDC_MessageTypeID_Echo:
      return HDC_MsgReply_Echo(pRequestMessage, Size);

    case HDC_MessageTypeID_Command:
      if (Size < 3) {
        HDC_EvtMsg_Log(NULL, HDC_EventLogLevel_ERROR, "Malformed command request");
        return;
      }
      return HDC_MsgReply_Command(pRequestMessage, Size);
  }

  if ((hHDC.CustomMsgRouter != NULL)
      && (MessageTypeID < 0xF0)  // ToDo: Proper method to check whether ID is reserved by HDC
      && hHDC.CustomMsgRouter(pRequestMessage, Size))
    return;  // Meaning that the custom message router could route it successfully


  HDC_EvtMsg_Log(NULL, HDC_EventLogLevel_ERROR, "Unknown message type");
}


/*
 * Unpacketizing of received packet.
 * Only single-packet requests are currently supported! (In other words: Messages sent by the host can be at most 254 bytes long.)
 */
void HDC_ProcessRxPacket(const uint8_t *packet) {
  const uint8_t RequestMessageSize = packet[0];     // Payload-size of a packet is also size of the message.
  const uint8_t *pRequestMessage = packet+1; // Message starts at the second byte of the packet.

  HDC_ProcessRxMessage(pRequestMessage, RequestMessageSize);
}


const uint8_t* HDC_ParsePacket(const uint8_t *Buffer, const uint16_t BufferSize, uint16_t *pReadingFrameErrorCounter) {

  const uint8_t *packet_candidate = Buffer; // const means the content of the buffer is const, not the pointer to it
  uint16_t chunk_size = BufferSize;

  // Search for packet directly in the RX buffer
  while (chunk_size >= HDC_PACKET_OVERHEAD) {
    uint8_t payload_size = packet_candidate[0];

    if (payload_size > HDC_MAX_REQ_MESSAGE_SIZE) {
      // Might be a reading-frame error. Skip first byte and try again.
      packet_candidate += 1;
      chunk_size -= 1;
      *pReadingFrameErrorCounter += 1;
      continue; // Try to de-queue another message from the remainder of the chunk
    }

    if (payload_size + HDC_PACKET_OVERHEAD > chunk_size)
      return NULL; // Seems the chunk is not yet a full packet. Give further bytes a chance to arrive!

    uint16_t terminatorIndex = payload_size + 2;
    if (packet_candidate[terminatorIndex] == HDC_PACKET_TERMINATOR) {
      uint8_t checksum = 0;
      for (uint16_t i=1; i < terminatorIndex; i++)
        checksum += packet_candidate[i];
      if (checksum == 0) {

        // We found a full packet!

        // Do NOT try to de-queue any further packet from the remainder of the chunk!
        //   - Current implementation of this hdc_device driver disallows multi-packet requests.
        //   - HDC-spec disallows hosts to send another request before the previous has been replied to.
        //
        // Therefore, sanity check whether there's any unexpected bytes beyond this packet
        // and report any as being a reading-frame-error
        *pReadingFrameErrorCounter += chunk_size - (payload_size + HDC_PACKET_OVERHEAD);

        return packet_candidate;

      } else {
        // Most likely a reading-frame error. Skip first byte and try again.
        packet_candidate += 1;
        chunk_size -= 1;
        *pReadingFrameErrorCounter += 1;
        continue;
      }
    } else {
      // Most likely a reading-frame error. Skip first byte and try again.
      packet_candidate += 1;
      chunk_size -= 1;
      *pReadingFrameErrorCounter += 1;
      continue;
    }
  }

  // Chunk is too small to be any packet Give further bytes a chance to arrive!
  return NULL;
}


void HDC_ProcessRxBuffer() {
  uint16_t ReadingFrameErrorCounter = 0;

  // Attempt to get a single, full packet out of the chunk of data received

  const uint8_t *packet = HDC_ParsePacket(hHDC.BufferRx, hHDC.NumBytesInBufferRx, &ReadingFrameErrorCounter);

  bool restart_reception = false;
  restart_reception |= (packet != NULL);  // Because we received a proper packet.
  restart_reception |= ReadingFrameErrorCounter > 0;  // Because we received crap of some sort.

  if (restart_reception)
  {
    // Restart RX for next packet to arrive at the beginning of
    // the RX-buffer, because that's where the packet-parser expects it.

    // It's safe to do so here, because HDC-spec disallows hosts from sending any
    // further request before receiving the reply to the previous one,
    // and we haven't yet processed the request, thus no reply has been composed nor sent yet.

    // Stop any ongoing reception
    HAL_UART_AbortReceive(hHDC.huart);

    // Start receiving next request.
    hHDC.isDmaRxComplete = false;
    if (HAL_UARTEx_ReceiveToIdle_DMA(hHDC.huart, hHDC.BufferRx, HDC_BUFFER_SIZE_RX) != HAL_OK)
      Error_Handler();

  }

  if (packet != NULL)
    HDC_ProcessRxPacket(packet);

  if (ReadingFrameErrorCounter > 0) {
    HDC_EvtMsg_Log(NULL, HDC_EventLogLevel_WARNING, "Reading-frame-errors detected while parsing request message on device.");
  }

}


/////////////////////////////////
// API of the hdc_device driver


void HDC_Flush() {

  HDC_StartTransmittingAnyPendingPackets();

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

uint32_t HDC_Work() {

  if (hHDC.isDmaRxComplete) {  // Whenever an attempt to receive a burst of data completes...
    HDC_ProcessRxBuffer();     // ... we check whether a valid packet can be found in the RX buffer.
  }

  // If a request was received, its reply (and any events) have at this point been composed already.
  // If the TX buffer is not large enough some packets of said reply might have been transmitted already.
  // Regardless, now it's the moment we'll ensure to transmit whatever remains to be transmitted.

  if (hHDC.isDmaTxComplete) {  // Whenever transmission of one TX buffer completed ...
    HDC_StartTransmittingAnyPendingPackets();  // ... we start transmission of the other TX buffer, but only if it contains any packets.
  }

  return 0; // Update an every possible occasion
}

void HDC_Init_WithCustomMsgRouting(
    UART_HandleTypeDef *huart,
    HDC_Descriptor_Feature_t **HDC_Features,
    uint8_t NumFeatures,
    HDC_MessageHandler_t CustomMsgRouter) {

  // ToDo: Validation of descriptors:
  //       - No duplicate IDs nor names for features, commands and properties
  //       - No empty names for features, commands and properties

  hHDC.huart = huart;
  hHDC.Features = HDC_Features;
  hHDC.NumFeatures = NumFeatures;
  hHDC.CustomMsgRouter = CustomMsgRouter;

  hHDC.NumBytesInBufferRx = 0;
  hHDC.NumBytesInBufferTx[0] = 0;
  hHDC.NumBytesInBufferTx[1] = 0;

  hHDC.currentDmaBufferTx = 0;

  hHDC.isDmaRxComplete = false;
  hHDC.isDmaTxComplete = true;


  // Start reception of the first chunk
  if (HAL_UARTEx_ReceiveToIdle_DMA(hHDC.huart, hHDC.BufferRx, HDC_BUFFER_SIZE_RX) != HAL_OK)
    Error_Handler();

  hHDC.isInitialized = true;

}


void HDC_Init(
    UART_HandleTypeDef *huart,
    HDC_Descriptor_Feature_t **HDC_Features,
    uint8_t NumFeatures) {

 HDC_Init_WithCustomMsgRouting(
     huart,
     HDC_Features,
     NumFeatures,
     NULL);

}
