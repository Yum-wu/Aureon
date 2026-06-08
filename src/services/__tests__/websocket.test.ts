import { AureonWebSocket } from '../websocket';

describe('AureonWebSocket', () => {
  let ws: AureonWebSocket;

  beforeEach(() => {
    ws = new AureonWebSocket('test-client');
  });

  afterEach(() => {
    ws.disconnect();
  });

  test('initializes with client ID', () => {
    expect(ws).toBeDefined();
    expect(ws.getConversationId()).toBeNull();
  });

  test('isConnected returns false initially', () => {
    expect(ws.isConnected()).toBe(false);
  });

  test('registers message handlers', () => {
    const handler = jest.fn();
    ws.onMessage('text', handler);

    // Handler should be registered (can't test without actual connection)
    expect(handler).not.toHaveBeenCalled();
  });

  test('registers connection handlers', () => {
    const handler = jest.fn();
    ws.onConnection(handler);

    // Handler should be registered
    expect(handler).not.toHaveBeenCalled();
  });

  test('disconnect does not throw', () => {
    expect(() => ws.disconnect()).not.toThrow();
  });

  test('send does not throw when disconnected', () => {
    expect(() => ws.send({ type: 'test' })).not.toThrow();
  });

  test('getWebSocket returns singleton instance', () => {
    const { getWebSocket } = require('../websocket');
    const ws1 = getWebSocket('client-1');
    const ws2 = getWebSocket('client-2');
    expect(ws1).toBe(ws2);
  });

  test('disconnectWebSocket clears instance', () => {
    const { getWebSocket, disconnectWebSocket } = require('../websocket');
    const ws1 = getWebSocket('client-1');
    disconnectWebSocket();
    const ws2 = getWebSocket('client-2');
    expect(ws1).not.toBe(ws2);
  });
});
