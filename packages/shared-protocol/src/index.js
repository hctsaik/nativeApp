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

