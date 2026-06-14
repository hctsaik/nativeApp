export const MessageTypes = Object.freeze({
  CHILD_READY: "CHILD_READY",
  AUTH_TOKEN: "AUTH_TOKEN",
  ROUTE_CHANGED: "ROUTE_CHANGED",
  HOST_NAVIGATE: "HOST_NAVIGATE",
  ERROR: "ERROR",
  EXECUTE_START: "EXECUTE_START",
  EXECUTE_COMPLETE: "EXECUTE_COMPLETE",
  DISPLAY_UPDATE: "DISPLAY_UPDATE",
  SWITCH_TAB: "SWITCH_TAB",
  OPEN_PREVIEW: "OPEN_PREVIEW",
  // A tool iframe asks the host to switch the active tool to payload.toolId
  // (e.g. VisualLatent hands a batch to Labeling and wants module_026 opened).
  OPEN_TOOL: "OPEN_TOOL",
});

export function createMessage(type, payload = {}) {
  return {
    source: "cim-platform",
    type,
    payload,
    timestamp: new Date().toISOString()
  };
}

export function isProtocolMessage(value) {
  return Boolean(
    value &&
      value.source === "cim-platform" &&
      typeof value.type === "string" &&
      Object.prototype.hasOwnProperty.call(MessageTypes, value.type)
  );
}

