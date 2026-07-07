/**
 * WebSocket 客户端
 * 支持指数退避重连、心跳检测、连接状态追踪
 * 支持 Page Visibility API、回调 setter、jitter、fatal close codes
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
  /** 最大重连次数，默认 10 */
  maxReconnectAttempts?: number;
  /** 重连延迟添加随机抖动（0-1000ms），默认 false */
  reconnectJitter?: boolean;
  /** 不重连的关闭码，默认 [4001, 1013] */
  fatalCloseCodes?: number[];
}

/** 心跳消息（后端期望 type: "heartbeat"） */
const HEARTBEAT_MESSAGE = '{"type":"heartbeat"}';

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
  onMessage?: (data: unknown) => void;
  onOpen?: () => void;
  onClose?: () => void;
} {
  const {
    heartbeatInterval = 30_000,
    initialReconnectDelay = 1_000,
    maxReconnectDelay = 30_000,
    maxReconnectAttempts = 10,
    reconnectJitter = false,
    fatalCloseCodes = [4001, 1013],
  } = config;

  let ws: WebSocket | null = null;
  let state: WSConnectionState = 'disconnected';
  let reconnectAttempts = 0;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  let intentionalClose = false;
  let onStateChange: ((state: WSConnectionState) => void) | undefined;
  let onMessageHandler: ((data: unknown) => void) | undefined;
  let onOpenHandler: (() => void) | undefined;
  let onCloseHandler: (() => void) | undefined;
  let visibilityHandler: (() => void) | null = null;

  /** 获取 WebSocket 完整 URL（携带 JWT token 作为查询参数）
   *
   * 行业最佳实践: 在 handshake 阶段用 query param 传递 token，
   * 服务端可在 accept() 前拒绝无效连接，避免资源浪费。
   * 参见: https://websocket.org/guides/authentication
   *       https://fastapi.tiangolo.com/advanced/websockets/
   */
  function getWSUrl(): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const token = getAuthToken();
    const hasToken = /[?&]token=/.test(path);
    const separator = path.includes('?') ? '&' : '?';
    const queryToken = token && !hasToken ? `${separator}token=${encodeURIComponent(token)}` : '';
    return `${protocol}//${host}${path}${queryToken}`;
  }

  /** 获取认证 token */
  function getAuthToken(): string {
    try {
      const jwt = sessionStorage.getItem('aureon_jwt_token') || '';
      const apiKey = sessionStorage.getItem('aureon_api_key') || '';
      return jwt || apiKey;
    } catch {
      return '';
    }
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
        ws.send(HEARTBEAT_MESSAGE);
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

  /** 计算重连延迟（指数退避 + 可选 jitter） */
  function getReconnectDelay(): number {
    const base = initialReconnectDelay * Math.pow(2, reconnectAttempts);
    const jitter = reconnectJitter ? Math.random() * 1000 : 0;
    return Math.min(base + jitter, maxReconnectDelay);
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

    // Page Visibility API — pause/resume reconnect on tab visibility
    visibilityHandler = () => {
      if (document.hidden) {
        if (reconnectTimer) {
          clearTimeout(reconnectTimer);
          reconnectTimer = null;
        }
      } else if (!intentionalClose && ws?.readyState !== WebSocket.OPEN) {
        if (reconnectAttempts < maxReconnectAttempts) {
          connect();
        }
      }
    };
    document.addEventListener('visibilitychange', visibilityHandler);

    try {
      ws = new WebSocket(getWSUrl());

      ws.onopen = () => {
        reconnectAttempts = 0;
        setState('connected');
        startHeartbeat();
        onOpenHandler?.();
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          // 后端心跳响应类型：pong (chat) / heartbeat_ack (dashboard)
          if (data.type === 'pong' || data.type === 'heartbeat_ack') return;
          onMessageHandler?.(data);
        } catch {
          onMessageHandler?.(event.data);
        }
      };

      ws.onclose = (event: CloseEvent) => {
        stopHeartbeat();
        onCloseHandler?.();
        if (!intentionalClose && !fatalCloseCodes.includes(event.code)) {
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
    if (visibilityHandler) {
      document.removeEventListener('visibilitychange', visibilityHandler);
      visibilityHandler = null;
    }
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
    get onMessage() {
      return onMessageHandler;
    },
    set onMessage(handler: ((data: unknown) => void) | undefined) {
      onMessageHandler = handler;
    },
    get onOpen() {
      return onOpenHandler;
    },
    set onOpen(handler: (() => void) | undefined) {
      onOpenHandler = handler;
    },
    get onClose() {
      return onCloseHandler;
    },
    set onClose(handler: (() => void) | undefined) {
      onCloseHandler = handler;
    },
  };
}
