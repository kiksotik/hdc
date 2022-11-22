/*
 * API and HDC-feature of the Demo_Minimal Core-feature
 */

#include "main.h"
#include "feature_core.h"

/////////////////////////
// Forward declarations

HDC_Descriptor_Feature_t Core_HDC_Feature;

////////////////////////////////////////
// HDC Stuff

/////////////////////////
// HDC Custom Exceptions
HDC_Descriptor_Exc_t Core_HDC_Exc_DivZero = {.id=0x01, .name="MyDivZero"};


///////////////
// HDC Commands

// Example of an HDC-command handler without any arguments nor any return value
void Core_HDC_Cmd_Reset(const HDC_Descriptor_Feature_t *hHDC_Feature,
                        const uint8_t* pRequestMessage,
                        const uint8_t Size) {
  if (Size != 3)  // MessageType ; FeatureID ; CommandID
    return HDC_CmdReply_Error(HDC_Descriptor_Exc_InvalidArgs.id, pRequestMessage);

  // Send a void reply before actually resetting the system.
  // Otherwise the HDC-host will timeout while awaiting it.
  HDC_CmdReply_Void(pRequestMessage);
  HDC_FeatureStateTransition(&Core_HDC_Feature, Core_State_Off);
  HDC_Flush();  // Ensure the command-reply and FeatureStateTransition event have been transmitted!

  NVIC_SystemReset();  // Reset microcontroller via software interrupt.
}

// Example of an HDC-command handler with two arguments and one return value
void Core_HDC_Cmd_Divide(const HDC_Descriptor_Feature_t *hHDC_Feature,
                         const uint8_t* pRequestMessage,
                         const uint8_t Size) {
  if (Size != 11)  // MessageType ; FeatureID ; CommandID ; FLOAT ; FLOAT
    return HDC_CmdReply_Error(HDC_Descriptor_Exc_InvalidArgs.id, pRequestMessage);

  // ToDo: HDC-library should provide more comfortable ways to parse arguments than this:
  float numerator   = *((float*)(pRequestMessage + 3));
  float denominator = *((float*)(pRequestMessage + 7));

  if (denominator == 0.0f)
    return HDC_CmdReply_Error(Core_HDC_Exc_DivZero.id, pRequestMessage);

  double result = numerator / denominator;

  return HDC_CmdReply_DoubleValue(result, pRequestMessage);
}

// Example of an HDC-command descriptor.
// Note how it is defined directly in the array initialization.
const HDC_Descriptor_Command_t *Core_HDC_Commands[] = {

  &(HDC_Descriptor_Command_t) {
    .CommandID = 0x01,       // Arbitrary value, but unique within this feature. Values 0xF0 and above are reserved for HDC internals.
    .CommandName = "reset",  // Name of the corresponding, automatically generated API-method in a proxy-class.
    .CommandHandler = &Core_HDC_Cmd_Reset,  // Function pointer to the handler defined above.
    .CommandDescription = "Reinitializes the whole device."   // Human readable docstring
  },


  &(HDC_Descriptor_Command_t) {
    .CommandID = 0x02,        // Arbitrary value, but unique within this feature. Values 0xF0 and above are reserved for HDC internals.
    .CommandName = "division",  // Name of the corresponding, automatically generated API-method in a proxy-class.
    .CommandHandler = &Core_HDC_Cmd_Divide,  // Function pointer to the handler defined above.
    .arg1 = &(HDC_Descriptor_Arg_t) {.dtype=HDC_DataTypeID_FLOAT, .name="numerator"},
    .arg2 = &(HDC_Descriptor_Arg_t) {.dtype=HDC_DataTypeID_FLOAT, .name="denominator", .doc="Beware of the zero!"},
    .ret1 = &(HDC_Descriptor_Ret_t) {.dtype=HDC_DataTypeID_DOUBLE, .doc="Quotient of numerator/denominator"}, // Name of return values can be omitted
    .raises = &(const HDC_Descriptor_Exc_t*) { &Core_HDC_Exc_DivZero },
    .numraises = 1,
    .CommandDescription = "Divides numerator by denominator."    // Human readable docstring
  },

  // Note how hdc_device driver takes care of all mandatory HDC-commands (GetPropertyValue, SetPropertyValue, ...)
 };


/////////////
// HDC Events

// Example of an HDC-event descriptor
// Note how it's convenient to define it as a proper variable, so that
// the Core_HDC_Raise_Event_Button() method below can access the EventID it defines.
HDC_Descriptor_Event_t Core_HDC_Event_Button = {
      .EventID = 0x01,  // Arbitrary value, but unique within this feature. Values 0xF0 and above are reserved for HDC internals.
      .EventName = "button",  // Name of the corresponding, automatically generated event handler in a proxy-class.
      .EventDescription = "Notify host about the button being pressed on the device.",
      .arg1 = &(HDC_Descriptor_Arg_t) {.dtype=HDC_DataTypeID_UINT8, .name="ButtonID"},
      .arg2 = &(HDC_Descriptor_Arg_t) {.dtype=HDC_DataTypeID_UINT8, .name="ButtonState"},
};

const HDC_Descriptor_Event_t *Core_HDC_Events[] = {
  &Core_HDC_Event_Button,
  // Note how hdc_device driver takes care of all mandatory HDC-events (Log, FeatureStateTransition, ...)
};

// Example of an API for raising a custom HDC-event.
void Core_HDC_Raise_Event_Button(uint8_t ButtonID, uint8_t ButtonState) {

  HDC_EvtMsg(
    &Core_HDC_Feature,
    Core_HDC_Event_Button.EventID,
    // Note how HDC_EvtMsg() allows to provide the payload in two separate chunks.
    // In this case we just sent one byte in the payload-prefix and another byte in the payload-suffix.
    &ButtonID, 1,
    &ButtonState, 1);
}


/////////////////
// HDC Properties

// Example of getters for HDC-properties
void Core_HDC_Property_uC_DEVID_get(const HDC_Descriptor_Feature_t *hHDC_Feature,
                                    const HDC_Descriptor_Property_t *hHDC_Property,
                                    const uint8_t* pRequestMessage,
                                    const uint8_t RequestMessageSize)
{
  const uint32_t devid = HAL_GetDEVID();
  HDC_CmdReply_UInt32Value(devid, pRequestMessage);
}


// Example of how HDC-properties can also be backed by a simple C variable
uint8_t led_blinking_rate = 5;

// Example of HDC-property descriptors.
// Note how some descriptor attributes can simply be omitted.
const HDC_Descriptor_Property_t *Core_HDC_Properties[] = {

  &(HDC_Descriptor_Property_t ) {
    .PropertyID = 0x10,          // Arbitrary value, but unique within this feature. Values 0xF0 and above are reserved for HDC internals.
    .PropertyName = "uc_devid",  // Name of the corresponding, automatically generated API-property in a proxy-class.
    .PropertyDataType = HDC_DataTypeID_UINT32,
    .PropertyIsReadonly = true,
    .GetPropertyValue = Core_HDC_Property_uC_DEVID_get,  // hdc_driver will use this getter to obtain the value.
    .PropertyDescription = "32bit Device-ID of STM32 microcontroller."
  },

  &(HDC_Descriptor_Property_t ) {
    .PropertyID = 0x11,        // Arbitrary value, but unique within this feature. Values 0xF0 and above are reserved for HDC internals.
    .PropertyName = "uc_uid",  // Name of the corresponding, automatically generated API-property in a proxy-class.
    .PropertyDataType = HDC_DataTypeID_BLOB,
    .PropertyIsReadonly = true,
    .pValue = (void*) UID_BASE,  // hdc_driver will use this pointer/address to obtain the value.
    .ValueSize = 12,             //
    .PropertyDescription = "96bit unique-ID of STM32 microcontroller."
  },

  &(HDC_Descriptor_Property_t ) {
    .PropertyID = 0x12,  // Arbitrary value, but unique within this feature. Values 0xF0 and above are reserved for HDC internals.
    .PropertyName = "led_blinking_rate",  // Name of the corresponding, automatically generated API-property in a proxy-class.
    .PropertyDataType = HDC_DataTypeID_UINT8,
    .PropertyIsReadonly = false,
    .pValue = &led_blinking_rate,  // hdc_driver will read/write value directly from/to this memory address.
                                   // No need to specify any ValueSize, because hdc_driver infers it from the data type.
    .PropertyDescription = "Blinking frequency of the LED given in Herz."
  },

  // Note how hdc_device driver takes care of all mandatory HDC properties (LogEventThreshold, FeatureState, ...)
};


// Example of state descriptors.
// Note how some descriptor attributes can simply be omitted.
const HDC_Descriptor_State_t *Core_HDC_States[] = {
  &(HDC_Descriptor_State_t ) {
    .id = Core_State_Off,
    .name = "OFF"
  },
  &(HDC_Descriptor_State_t ) {
    .id = Core_State_Initializing,
    .name = "INIT"
  },
  &(HDC_Descriptor_State_t ) {
    .id = Core_State_Ready,
    .name = "READY"
  },
  &(HDC_Descriptor_State_t ) {
    .id = Core_State_Error,
    .name = "ERROR"
  },
};


//////////////
// HDC Feature

// Example of an HDC-feature descriptor.
// In this case for the mandatory core-feature of this device.
HDC_Descriptor_Feature_t Core_HDC_Feature = {
  .FeatureID = HDC_FeatureID_Core,       // A FeatureID of 0x00 is what makes this the mandatory Core-Feature of this device.
  .FeatureName = "core",                 // Name of this feature instance --> name of the proxy instance
  .FeatureClassName = "MinimalCore",     // Name of this feature's implementation
  .FeatureClassVersion = "0.0.1",        // SemVer of this feature's implementation
  .FeatureDescription = "STM32 C implementation of the 'Minimal' HDC-device demonstration",  // Docstring about this feature/device
  // Documentation of this feature's states and their human readable names. Syntax as for python dictionary initialization
  .States = Core_HDC_States,
  .NumStates = sizeof(Core_HDC_States) / sizeof(HDC_Descriptor_State_t*),
  .Commands = Core_HDC_Commands,
  .NumCommands = sizeof(Core_HDC_Commands) / sizeof(HDC_Descriptor_Command_t*),
  .Properties = Core_HDC_Properties,
  .NumProperties = sizeof(Core_HDC_Properties) / sizeof(HDC_Descriptor_Property_t*),
  .Events = Core_HDC_Events,
  .NumEvents = sizeof(Core_HDC_Events) / sizeof(HDC_Descriptor_Event_t*),
  .hAPI = NULL,  // Optional pointer to whatever handle might be useful to access in contexts
                 // where only this descriptor is available, e.g within HDC-command handlers.
  // The following are variables for the mandatory FeatureState and Logging capabilities.
  // Note how the hdc_driver takes care of exposing those as HDC-properties.
  .FeatureState = Core_State_Off,
  .LogEventThreshold = HDC_EventLogLevel_INFO
};

HDC_Descriptor_Feature_t *Core_HDC_Features[] = {
  &Core_HDC_Feature,

  // Demo_Minimal demo does not implement any other features, because
  // it implements all demonstrated aspects directly in the mandatory Core-feature.
};


//////////////////////////////////
// API of Core Feature

void Core_Init(UART_HandleTypeDef *huart) {

  // This example encapsulates all HDC stuff within the feature_core, thus
  // this where the hdc_device driver is being initialized.
  // Note how the huart instance has been initialized by the auto-generated main.c code.
  HDC_Init(huart,
           Core_HDC_Features,
           sizeof(Core_HDC_Features) / sizeof(HDC_Descriptor_Feature_t*));

  // Note that HDC should obviously not be used before it's initialized! ;-)

  // Example of how an HDC-feature updates its state.
  // This updates the FeatureState property and raises a FeatureStateTransition event.
  HDC_FeatureStateTransition(&Core_HDC_Feature, Core_State_Initializing);

  // This is were typically other features and components should be
  // initialized, but in Demo_Minimal there's nothing to be done here.

  HDC_FeatureStateTransition(&Core_HDC_Feature, Core_State_Ready);
}

void Core_Work(void) {
  uint32_t ticksNow = HAL_GetTick();

  // LED blinking, whose rate is controlled via a read-writable HDC-property
  static uint32_t ticksNextLedToggle = 0;
  if (ticksNow > ticksNextLedToggle) {
    HAL_GPIO_TogglePin(LD2_GPIO_Port, LD2_Pin);
    ticksNextLedToggle = ticksNow + (1000 / led_blinking_rate);
  }

  // Demonstrate custom HDC-event, which notifies HDC-host about a button being pressed on the HDC-device.
  static bool previousButtonState = 1;
  bool newButtonState = HAL_GPIO_ReadPin(B1_GPIO_Port, B1_Pin);
  if (newButtonState != previousButtonState) {
    Core_HDC_Raise_Event_Button(0x42, newButtonState);  // ButtonID=0x42 is just arbitrary
  }
  previousButtonState = newButtonState;

  // Demonstrate HDC-logging capabilities
  static uint32_t ticksNextDummyTransfer = 1000;
  if (ticksNow > ticksNextDummyTransfer) {
    HDC_EvtMsg_Log(NULL, HDC_EventLogLevel_DEBUG, "This is just to showcase how to use the logging capabilities of HDC.");
    ticksNextDummyTransfer = ticksNow + 1000;
  }

  // The following call handles the actual transmission and reception of HDC-messages
  HDC_Work();
}

void Core_ErrorHandler(HDC_EventLogLevel_t logLevel, char* errorMessage) {
  assert_param(logLevel >= HDC_EventLogLevel_ERROR);

  // ToDo: Ensure device is reset into a safe state!

  HDC_FeatureStateTransition(&Core_HDC_Feature, Core_State_Error);
  // Log error message after entering the error state.
  HDC_EvtMsg_Log(&Core_HDC_Feature, logLevel, errorMessage);
}
