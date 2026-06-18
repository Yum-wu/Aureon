/**
 * WebSocket 客户端
 * 支持指数退避重连、心跳检测、连接状态追踪
 */

/** 连接状态 */
export type WSConnectionState = 'connecting' | 'connected' | 'disconnected' | 'reconnecting';

/** WebSocket 配置 */
interface WSConfig {
  /** 心跳间隔（毫秒），默认 30000 */
  heartbeatInterval?: number;
  /** 初始重连延迟（毫秒），默认 1000 */
  initialReconnectDelay?: number;
  /** 最大重连延迟（毫秒），默认 30000 */
  maxReconnectDelay?: number;
  /** 最大重连次数，默认 Infinity */
  maxReconnectAttempts?: number;
}

/** 心跳消息 */
const PING_MESSAGE = '{"type":"ping"}';

/**
 * 创建带重连和心跳的 WebSocket 连接
 * @param path - WebSocket 路径（如 /ws/dashboard）
 * @param config - 配置选项
 * @returns WebSocket 实例和控制方法
 */
export function createWebSocket(
  path: string,
  config: WSConfig = {},
): {
  ws: WebSocket | null;
  getState: () => WSConnectionState;
  connect: () => void;
  disconnect: () => void;
  send: (data: string | object) => void;
  onStateChange?: (state: WSConnectionState) => void;
} {
  const {
    heartbeatInterval = 30_000,
    initialReconnectDelay = 1_000,
    maxReconnectDelay = 30_000,
    maxReconnectAttempts = Infinity,
  } = config;

  let ws: WebSocket | null = null;
  let state: WSConnectionState = 'disconnected';
  let reconnectAttempts = 0;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  let intentionalClose = false;
  let onStateChange: ((state: WSConnectionState) => void) | undefined;

  /** 获取 WebSocket 完整 URL */
  function getWSUrl(): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    return `${protocol}//${host}${path}`;
  }

  /** 更新连接状态 */
  function setState(newState: WSConnectionState): void {
    state = newState;
    onStateChange?.(newState);
  }

  /** 启动心跳 */
  function startHeartbeat(): void {
    stopHeartbeat();
    heartbeatTimer = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(PING_MESSAGE);
      }
    }, heartbeatInterval);
  }

  /** 停止心跳 */
  function stopHeartbeat(): void {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
  }

  /** 计算重连延迟（指数退避） */
  function getReconnectDelay(): number {
    const delay = initialReconnectDelay * Math.pow(2, reconnectAttempts);
    return Math.min(delay, maxReconnectDelay);
  }

  /** 尝试重连 */
  function tryReconnect(): void {
    if (intentionalClose) return;
    if (reconnectAttempts >= maxReconnectAttempts) return;

    reconnectAttempts++;
    setState('reconnecting');

    const delay = getReconnectDelay();
    reconnectTimer = setTimeout(() => {
      connect();
    }, delay);
  }

  /** 建立连接 */
  function connect(): void {
    if (ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) return;

    intentionalClose = false;
    setState('connecting');

    try {
      ws = new WebSocket(getWSUrl());

      ws.onopen = () => {
        reconnectAttempts = 0;
        setState('connected');
        startHeartbeat();
      };

      ws.onclose = () => {
        stopHeartbeat();
        if (!intentionalClose) {
          setState('disconnected');
          tryReconnect();
        } else {
          setState('disconnected');
        }
      };

      ws.onerror = () => {
        // onclose 会在 onerror 之后触发，重连逻辑在 onclose 中处理
      };
    } catch {
      setState('disconnected');
      tryReconnect();
    }
  }

  /** 断开连接 */
  function disconnect(): void {
    intentionalClose = true;
    stopHeartbeat();
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (ws) {
      ws.close();
      ws = null;
    }
    setState('disconnected');
  }

  /** 发送消息 */
  function send(data: string | object): void {
    if (ws?.readyState !== WebSocket.OPEN) return;
    const payload = typeof data === 'string' ? data : JSON.stringify(data);
    ws.send(payload);
  }

  return {
    get ws() {
      return ws;
    },
    getState: () => state,
    connect,
    disconnect,
    send,
    get onStateChange() {
      return onStateChange;
    },
    set onStateChange(handler: ((state: WSConnectionState) => void) | undefined) {
      onStateChange = handler;
    },
  };
}
