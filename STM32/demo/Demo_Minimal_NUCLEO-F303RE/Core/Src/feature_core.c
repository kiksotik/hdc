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

void Core_HDC_Cmd_Reset(const struct HDC_Feature_struct *hHDC_Feature,
                        const uint8_t* RequestMessage,
                        const uint8_t Size) {
  if (Size != 3)  // MessageType ; FeatureID ; CommandID
    return HDC_Reply_Error(HDC_ReplyErrorCode_INCORRECT_COMMAND_ARGUMENTS, RequestMessage);

  // Send a reply before actually resetting the system.
  HDC_Reply_Error(HDC_ReplyErrorCode_NO_ERROR, RequestMessage);
  HDC_FeatureStateTransition(&Core_HDC_Feature, Core_State_Off);
  HDC_Flush();  // Ensure the command-reply and FeatureStateTransition event have been transmitted!

  NVIC_SystemReset();  // Reset microcontroller via software interrupt.
}

const HDC_Command_Descriptor_t *Core_HDC_Commands[] = {

  &(HDC_Command_Descriptor_t) {
    .CommandID = 0xC1,
    .CommandName = "Reset",
    .HandleRequest = &Core_HDC_Cmd_Reset,
    .CommandDescription =
        "(void) -> void\n"
        "Reinitializes the whole device."
  },

  // Note how hdc_device driver takes care of all mandatory HDC-commands (GetPropertyName, GetPropertyValue, ...)
 };

/////////////
// HDC Events

#define EVENTID_BUTTON 0x01
const HDC_Event_Descriptor_t *Core_HDC_Events[] = {

  &(HDC_Event_Descriptor_t) {
    .EventID = EVENTID_BUTTON,
    .EventName = "ButtonEvent",
    .EventDescription = "-> UINT8 ButtonID, UINT8 ButtonState\n"
                        "Showcases how HDC handles events: Notify host about the button being pressed on the device."

  },

  // Note how hdc_device driver takes care of all mandatory HDC-events (Log, FeatureStateTransition, ...)
};

/////////////////
// HDC Properties

void Core_HDC_Property_uC_DEVID_get(const HDC_Feature_Descriptor_t *hHDC_Feature,
                                    const HDC_Property_Descriptor_t *hHDC_Property,
                                    const uint8_t* RequestMessage,
                                    const uint8_t RequestMessageSize) {
  const uint32_t devid = HAL_GetDEVID();
  HDC_Reply_UInt32Value(devid, RequestMessage);
}

void Core_HDC_Property_uC_REVID_get(const HDC_Feature_Descriptor_t *hHDC_Feature,
                                    const HDC_Property_Descriptor_t *hHDC_Property,
                                    const uint8_t* RequestMessage,
                                    const uint8_t RequestMessageSize) {
  const uint32_t revid = HAL_GetREVID();
  HDC_Reply_UInt32Value(revid, RequestMessage);
}

uint8_t led_blinking_rate = 5;

const HDC_Property_Descriptor_t *Core_HDC_Properties[] = {

  &(HDC_Property_Descriptor_t ) {
    .PropertyID = 0x10,
    .PropertyName = "uC_DEVID",
    .PropertyDataType = HDC_DataType_UINT32,
    .PropertyIsReadonly = true,
    .GetPropertyValue = Core_HDC_Property_uC_DEVID_get,  // HDC driver will use this getter to obtain the value.
    .PropertyDescription = "32bit Device-ID of STM32 microcontroller."
  },

  &(HDC_Property_Descriptor_t ) {
    .PropertyID = 0x11,
    .PropertyName = "uC_REVID",
    .PropertyDataType = HDC_DataType_UINT32,
    .PropertyIsReadonly = true,
    .GetPropertyValue = Core_HDC_Property_uC_REVID_get,  // HDC driver will use this getter to obtain the value.
    .PropertyDescription = "32bit Revision-ID of STM32 microcontroller."
  },

  &(HDC_Property_Descriptor_t ) {
    .PropertyID = 0x12,
    .PropertyName = "uC_UID",
    .PropertyDataType = HDC_DataType_BLOB,
    .PropertyIsReadonly = true,
    .pValue = (void*) UID_BASE,  // HDC driver will use this pointer/address to obtain the value.
    .ValueSize = 12,
    .PropertyDescription = "96bit unique-ID of STM32 microcontroller."
  },

  &(HDC_Property_Descriptor_t ) {
    .PropertyID = 0x13,
    .PropertyName = "LedBlinkingRate",
    .PropertyDataType = HDC_DataType_UINT8,
    .PropertyIsReadonly = false,
    .pValue = &led_blinking_rate,  // HDC driver will use this pointer/address to obtain the value.
    .PropertyDescription = "Blinking frequency of the LED given in Herz."
  },

  // Note how hdc_device driver takes care of all mandatory HDC properties (FeatureName, FeatureDescription, ...)
};



//////////////
// HDC Feature

HDC_Feature_Descriptor_t Core_HDC_Feature = {
  .FeatureID = HDC_FEATUREID_CORE,
  .FeatureName = "Core",
  .FeatureTypeName = "MinimalCore",
  .FeatureTypeRevision = 1,
  .FeatureDescription = "Core feature of the minimal demo.",
  .FeatureTags = "Demo",
  .FeatureStatesDescription = "{0:'Off', 1:'Initializing', 2:'Ready', 0xFF:'Error'}",
  .Commands = Core_HDC_Commands,
  .NumCommands = sizeof(Core_HDC_Commands) / sizeof(HDC_Command_Descriptor_t*),
  .Properties = Core_HDC_Properties,
  .NumProperties = sizeof(Core_HDC_Properties) / sizeof(HDC_Property_Descriptor_t*),
  .Events = Core_HDC_Events,
  .NumEvents = sizeof(Core_HDC_Events) / sizeof(HDC_Event_Descriptor_t*),
  .hAPI = NULL,
  .FeatureState = Core_State_Off,
  .LogEventThreshold = HDC_EventLogLevel_INFO
};

HDC_Feature_Descriptor_t *Core_HDC_Features[] = {

  // The Core feature
  &Core_HDC_Feature,

  // Demo_Minimal demo does not implement any other features, because
  // it implements all demonstrated aspects directly in the mandatory Core-feature.
};


//////////////////////////////////
// API of Core Feature

void Core_Init(UART_HandleTypeDef *huart) {

  HDC_Init(huart,
           Core_HDC_Features,
           sizeof(Core_HDC_Features) / sizeof(HDC_Feature_Descriptor_t*));

  HDC_FeatureStateTransition(&Core_HDC_Feature, Core_State_Initializing);  // Shouldn't transition before configuring HDC-feature!

  // This is were typically other features and components should be
  // initialized, but in Demo_Minimal there's nothing to be done here.

  HDC_FeatureStateTransition(&Core_HDC_Feature, Core_State_Ready);
}

void Core_UpdateState(void) {
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
    // ToDo: Implement proper method in hdc_device driver to send custom event messages. The following is just an ugly workaround!
    const int eventMessageSize = 5;
    uint8_t eventMessage[eventMessageSize];
    eventMessage[0] = HDC_MessageType_EVENT_FEATURE;
    eventMessage[1] = HDC_FEATUREID_CORE;
    eventMessage[2] = EVENTID_BUTTON;
    eventMessage[3] = 0x42;
    eventMessage[4] = newButtonState;
    HDC_Reply_Raw(eventMessage, eventMessageSize);
  }
  previousButtonState = newButtonState;

  // Demonstrate HDC-logging capabilities
  static uint32_t ticksNextDummyTransfer = 1000;
  if (ticksNow > ticksNextDummyTransfer) {
    HDC_Reply_Event_Log(NULL, HDC_EventLogLevel_DEBUG, "This is just to showcase how to use the logging capabilities of HDC.");
    ticksNextDummyTransfer = ticksNow + 1000;
  }

  // The following call handles the actual transmission and reception of HDC-messages
  HDC_UpdateState();
}

void Core_ErrorHandler(HDC_EventLogLevel_t logLevel, char* errorMessage) {
  assert_param(logLevel >= HDC_EventLogLevel_ERROR);

  // ToDo: Ensure device is reset into a safe state!

  HDC_FeatureStateTransition(&Core_HDC_Feature, Core_State_Error);
  // Log error message after entering the error state.
  HDC_Reply_Event_Log(&Core_HDC_Feature, logLevel, errorMessage);
}
