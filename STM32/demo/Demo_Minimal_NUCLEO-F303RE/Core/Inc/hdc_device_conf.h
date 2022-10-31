/*
 * Private configuration of hdc_device driver
 */

// Largest HDC-message that HDC-hosts are allowed to send to this HDC-device.
// This device will communicate this limitation to its host, and any HDC compliant host will stick to it.
// WARNING: Current implementation of hdc_device driver can only cope with request-messages of up to 254 bytes!
#define HDC_MAX_REQ_MESSAGE_SIZE 128

// Buffer sizes to be allocated for the transmission of data.
// Must be at least 3 bytes larger than the longest reply-message that this device will be sending to any host.
// It's recommended to allow for larger TX buffers, because the hdc_device driver is able to compose
// multiple replies in a single buffer transfer to improve data throughput.
// WARNING: Two buffers of this size will be used!
//          While one is being transmitted via DMA, the other
//          allows for concurrent composition of further HDC-messages.
#define HDC_BUFFER_SIZE_TX 258
