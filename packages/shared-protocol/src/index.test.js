import { describe, it, expect } from "vitest";
import { MessageTypes, createMessage, isProtocolMessage } from "./index.js";

// ---------------------------------------------------------------------------
// MessageTypes
// ---------------------------------------------------------------------------

describe("MessageTypes", () => {
  it("exposes all required message type constants", () => {
    expect(MessageTypes.CHILD_READY).toBe("CHILD_READY");
    expect(MessageTypes.AUTH_TOKEN).toBe("AUTH_TOKEN");
    expect(MessageTypes.ROUTE_CHANGED).toBe("ROUTE_CHANGED");
    expect(MessageTypes.HOST_NAVIGATE).toBe("HOST_NAVIGATE");
    expect(MessageTypes.ERROR).toBe("ERROR");
    expect(MessageTypes.EXECUTE_START).toBe("EXECUTE_START");
    expect(MessageTypes.EXECUTE_COMPLETE).toBe("EXECUTE_COMPLETE");
    expect(MessageTypes.DISPLAY_UPDATE).toBe("DISPLAY_UPDATE");
    expect(MessageTypes.SWITCH_TAB).toBe("SWITCH_TAB");
    expect(MessageTypes.OPEN_PREVIEW).toBe("OPEN_PREVIEW");
    expect(MessageTypes.OPEN_TOOL).toBe("OPEN_TOOL");
  });

  it("is frozen and cannot be mutated", () => {
    expect(() => {
      MessageTypes.NEW_TYPE = "NEW_TYPE";
    }).toThrow();
  });
});

// ---------------------------------------------------------------------------
// createMessage
// ---------------------------------------------------------------------------

describe("createMessage", () => {
  it("sets source to cim-platform", () => {
    const msg = createMessage(MessageTypes.CHILD_READY);
    expect(msg.source).toBe("cim-platform");
  });

  it("sets the provided type", () => {
    const msg = createMessage(MessageTypes.AUTH_TOKEN);
    expect(msg.type).toBe(MessageTypes.AUTH_TOKEN);
  });

  it("includes an ISO timestamp", () => {
    const msg = createMessage(MessageTypes.CHILD_READY);
    expect(typeof msg.timestamp).toBe("string");
    expect(() => new Date(msg.timestamp)).not.toThrow();
    expect(new Date(msg.timestamp).getTime()).toBeGreaterThan(0);
  });

  it("defaults payload to empty object when omitted", () => {
    const msg = createMessage(MessageTypes.CHILD_READY);
    expect(msg.payload).toEqual({});
  });

  it("includes the provided payload", () => {
    const payload = { token: "abc.def.ghi" };
    const msg = createMessage(MessageTypes.AUTH_TOKEN, payload);
    expect(msg.payload).toEqual(payload);
  });

  it("does not mutate the provided payload", () => {
    const payload = { path: "/home" };
    createMessage(MessageTypes.ROUTE_CHANGED, payload);
    expect(payload).toEqual({ path: "/home" });
  });
});

// ---------------------------------------------------------------------------
// isProtocolMessage
// ---------------------------------------------------------------------------

describe("isProtocolMessage", () => {
  it("returns true for a valid message created by createMessage", () => {
    const msg = createMessage(MessageTypes.CHILD_READY);
    expect(isProtocolMessage(msg)).toBe(true);
  });

  it("returns true for all known message types", () => {
    for (const type of Object.values(MessageTypes)) {
      expect(isProtocolMessage(createMessage(type))).toBe(true);
    }
  });

  it("returns false for null", () => {
    expect(isProtocolMessage(null)).toBe(false);
  });

  it("returns false for undefined", () => {
    expect(isProtocolMessage(undefined)).toBe(false);
  });

  it("returns false for a plain object without source", () => {
    expect(isProtocolMessage({ type: "CHILD_READY", payload: {} })).toBe(false);
  });

  it("returns false when source is not cim-platform", () => {
    const msg = { source: "other-app", type: "CHILD_READY", payload: {} };
    expect(isProtocolMessage(msg)).toBe(false);
  });

  it("returns false when type is not a known MessageType", () => {
    const msg = { source: "cim-platform", type: "UNKNOWN_TYPE", payload: {} };
    expect(isProtocolMessage(msg)).toBe(false);
  });

  it("returns false when type is missing", () => {
    const msg = { source: "cim-platform", payload: {} };
    expect(isProtocolMessage(msg)).toBe(false);
  });

  it("returns false for a primitive value", () => {
    expect(isProtocolMessage("CHILD_READY")).toBe(false);
    expect(isProtocolMessage(42)).toBe(false);
  });
});
