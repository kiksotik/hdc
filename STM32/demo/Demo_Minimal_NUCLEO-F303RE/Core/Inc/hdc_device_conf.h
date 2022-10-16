/*
 * Private configuration of hdc_device driver
 */

// Largest HDC-message that HDC-hosts are allowed to send to this HDC-device.
#define HDC_MAX_REQ_MESSAGE_SIZE 128

// Buffer sizes to be allocated for the transmission of data.
// Must be at least 3 bytes larger than the longest reply that this device will be sending to any host.
// It's recommended to allow for larger TX buffers, because the hdc_device driver is able to compose
// multiple replies in a single buffer transfer to improve data throughput.
// ToDo: Its confusing, because actually two buffers of this size are being allocated
#define HDC_BUFFER_SIZE_TX 258
