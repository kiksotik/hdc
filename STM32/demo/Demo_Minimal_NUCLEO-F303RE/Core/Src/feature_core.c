/*
 * API and HDC-feature of the Demo_Minimal Core-feature
 */

#include "main.h"
#include "feature_core.h"

/////////////////////////
// Forward declarations

HDC_Feature_Descriptor_t Core_HDC_Feature;

////////////////////////////////////////
// HDC Stuff

///////////////
// HDC Commands

// Example of an HDC-command handler
void Core_HDC_Cmd_Reset(const HDC_Feature_Descriptor_t *hHDC_Feature,
                        const uint8_t* pRequestMessage,
                        const uint8_t Size) {
  if (Size != 3)  // MessageType ; FeatureID ; CommandID
    return HDC_Reply_Error(HDC_ReplyErrorCode_INCORRECT_COMMAND_ARGUMENTS, pRequestMessage);

  // Send a void reply before actually resetting the system.
  // Otherwise the HDC-host will timeout while awaiting it.
  HDC_Reply_Void(pRequestMessage);
  HDC_FeatureStateTransition(&Core_HDC_Feature, Core_State_Off);
  HDC_Flush();  // Ensure the command-reply and FeatureStateTransition event have been transmitted!

  NVIC_SystemReset();  // Reset microcontroller via software interrupt.
}

// Example of an HDC-command descriptor.
// Note how it is defined directly in the array initialization.
const HDC_Command_Descriptor_t *Core_HDC_Commands[] = {

  &(HDC_Command_Descriptor_t) {
    .CommandID = 0xC1,       // Arbitrary value, but unique within this feature. Values 0xF0 and above are reserved for HDC internals.
    .CommandName = "Reset",  // Name of the corresponding, automatically generated API-method in a proxy-class.
    .CommandHandler = &Core_HDC_Cmd_Reset,  // Function pointer to the handler defined above.
    .CommandDescription =
        "(void) -> void\n"                 // ToDo: Standardize argument and return value documentation.
        "Reinitializes the whole device."  // Human readable docstring
  },

  // Note how hdc_device driver takes care of all mandatory HDC-commands (GetPropertyName, GetPropertyValue, ...)
 };


/////////////
// HDC Events

// Example of an HDC-event descriptor
// Note how it's convenient to define it as a proper variable, so that
// the Core_HDC_Raise_Event_Button() method below can access the EventID it defines.
HDC_Event_Descriptor_t Core_HDC_Event_Button = {
      .EventID = 0x01,  // Arbitrary value, but unique within this feature. Values 0xF0 and above are reserved for HDC internals.
      .EventName = "ButtonEvent",  // Name of the corresponding, automatically generated event handler in a proxy-class.
      .EventDescription = "-> UINT8 ButtonID, UINT8 ButtonState\n"
                          "Showcases how HDC handles events: Notify host about the button being pressed on the device."
};

const HDC_Event_Descriptor_t *Core_HDC_Events[] = {
  &Core_HDC_Event_Button,
  // Note how hdc_device driver takes care of all mandatory HDC-events (Log, FeatureStateTransition, ...)
};

// Example of an API for raising a custom HDC-event.
void Core_HDC_Raise_Event_Button(uint8_t ButtonID, uint8_t ButtonState) {

  HDC_Raise_Event(
    &Core_HDC_Feature,
    Core_HDC_Event_Button.EventID,
    // Note how HDC_Raise_Event() allows to provide the payload in two separate chunks.
    // In this case we just sent one byte in the payload-prefix and another byte in the payload-suffix.
    &ButtonID, 1,
    &ButtonState, 1);
}


/////////////////
// HDC Properties

// Example of getters for HDC-properties
void Core_HDC_Property_uC_DEVID_get(const HDC_Feature_Descriptor_t *hHDC_Feature,
                                    const HDC_Property_Descriptor_t *hHDC_Property,
                                    const uint8_t* pRequestMessage,
                                    const uint8_t RequestMessageSize)
{
  const uint32_t devid = HAL_GetDEVID();
  HDC_Reply_UInt32Value(devid, pRequestMessage);
}

void Core_HDC_Property_uC_REVID_get(const HDC_Feature_Descriptor_t *hHDC_Feature,
                                    const HDC_Property_Descriptor_t *hHDC_Property,
                                    const uint8_t* pRequestMessage,
                                    const uint8_t RequestMessageSize)
{
  const uint32_t revid = HAL_GetREVID();
  HDC_Reply_UInt32Value(revid, pRequestMessage);
}

// Example of how HDC-properties can also be backed by a simple C variable
uint8_t led_blinking_rate = 5;

// Example of HDC-property descriptors.
// Note how some descriptor attributes can simply be omitted.
const HDC_Property_Descriptor_t *Core_HDC_Properties[] = {

  &(HDC_Property_Descriptor_t ) {
    .PropertyID = 0x10,          // Arbitrary value, but unique within this feature. Values 0xF0 and above are reserved for HDC internals.
    .PropertyName = "uC_DEVID",  // Name of the corresponding, automatically generated API-property in a proxy-class.
    .PropertyDataType = HDC_DataTypeID_UINT32,
    .PropertyIsReadonly = true,
    .GetPropertyValue = Core_HDC_Property_uC_DEVID_get,  // hdc_driver will use this getter to obtain the value.
    .PropertyDescription = "32bit Device-ID of STM32 microcontroller."
  },

  &(HDC_Property_Descriptor_t ) {
    .PropertyID = 0x11,          // Arbitrary value, but unique within this feature. Values 0xF0 and above are reserved for HDC internals.
    .PropertyName = "uC_REVID",  // Name of the corresponding, automatically generated API-property in a proxy-class.
    .PropertyDataType = HDC_DataTypeID_UINT32,
    .PropertyIsReadonly = true,
    .GetPropertyValue = Core_HDC_Property_uC_REVID_get,  // hdc_driver will use this getter to obtain the value.
    .PropertyDescription = "32bit Revision-ID of STM32 microcontroller."
  },

  &(HDC_Property_Descriptor_t ) {
    .PropertyID = 0x12,        // Arbitrary value, but unique within this feature. Values 0xF0 and above are reserved for HDC internals.
    .PropertyName = "uC_UID",  // Name of the corresponding, automatically generated API-property in a proxy-class.
    .PropertyDataType = HDC_DataTypeID_BLOB,
    .PropertyIsReadonly = true,
    .pValue = (void*) UID_BASE,  // hdc_driver will use this pointer/address to obtain the value.
    .ValueSize = 12,             //
    .PropertyDescription = "96bit unique-ID of STM32 microcontroller."
  },

  &(HDC_Property_Descriptor_t ) {
    .PropertyID = 0x13,  // Arbitrary value, but unique within this feature. Values 0xF0 and above are reserved for HDC internals.
    .PropertyName = "LedBlinkingRate",  // Name of the corresponding, automatically generated API-property in a proxy-class.
    .PropertyDataType = HDC_DataTypeID_UINT8,
    .PropertyIsReadonly = false,
    .pValue = &led_blinking_rate,  // hdc_driver will read/write value directly from/to this memory address.
                                   // No need to specify any ValueSize, because hdc_driver infers it from the data type.
    .PropertyDescription = "Blinking frequency of the LED given in Herz."
  },

  // Note how hdc_device driver takes care of all mandatory HDC properties (FeatureName, FeatureDescription, ...)
};



//////////////
// HDC Feature

// Example of an HDC-feature descriptor.
// In this case for the mandatory core-feature of this device.
HDC_Feature_Descriptor_t Core_HDC_Feature = {
  .FeatureID = HDC_FeatureID_Core,      // A FeatureID of 0x00 is what makes this the mandatory Core-Feature of this device.
  .FeatureName = "Core",                // Name of this feature instance --> name of the proxy instance
  .FeatureTypeName = "MinimalCore",     // Name of this feature's implementation --> name of the proxy class
  .FeatureTypeRevision = 1,             // Revision number of this feature's implementation
  .FeatureDescription = "Core feature of the minimal demo.",  // Docstring about this feature
  .FeatureTags = "Demo;NUCLEO-F303RE",  // ToDo: Standardize tag delimiter and explain potential use-cases.
  // Documentation of this feature's states and their human readable names. Syntax as for python dictionary initialization
  .FeatureStatesDescription = "{0:'Off', 1:'Initializing', 2:'Ready', 0xFF:'Error'}",
  .Commands = Core_HDC_Commands,
  .NumCommands = sizeof(Core_HDC_Commands) / sizeof(HDC_Command_Descriptor_t*),
  .Properties = Core_HDC_Properties,
  .NumProperties = sizeof(Core_HDC_Properties) / sizeof(HDC_Property_Descriptor_t*),
  .Events = Core_HDC_Events,
  .NumEvents = sizeof(Core_HDC_Events) / sizeof(HDC_Event_Descriptor_t*),
  .hAPI = NULL,  // Optional pointer to whatever handle might be useful to access in contexts
                 // where only this descriptor is available, e.g within HDC-command handlers.
  // The following are variables for the mandatory FeatureState and Logging capabilities.
  // Note how the hdc_driver takes care of exposing those as HDC-properties.
  .FeatureState = Core_State_Off,
  .LogEventThreshold = HDC_EventLogLevel_INFO
};

HDC_Feature_Descriptor_t *Core_HDC_Features[] = {
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
           sizeof(Core_HDC_Features) / sizeof(HDC_Feature_Descriptor_t*));

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
    HDC_Raise_Event_Log(NULL, HDC_EventLogLevel_DEBUG, "This is just to showcase how to use the logging capabilities of HDC.");
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
  HDC_Raise_Event_Log(&Core_HDC_Feature, logLevel, errorMessage);
}
