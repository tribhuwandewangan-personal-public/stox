/**
 * WebSocket service for real-time updates.
 * Features:
 *  - Automatic reconnection with exponential backoff
 *  - Fallback to polling when WebSocket is unavailable
 *  - Ping/pong keep-alive
 *  - Event listeners for different message types
 */

type WSHandler = (data: any) => void;
type StateListener = (state: 'connected' | 'connecting' | 'disconnected') => void;

interface WebSocketMessage {
  type: string;
  payload?: any;
  data?: any;
  timestamp?: string;
}

export class WebSocketService {
  private ws: WebSocket | null = null;
  private url: string;
  private handlers: Map<string, Set<WSHandler>> = new Map();
  private stateListeners: Set<StateListener> = new Set();
  private maxReconnectAttempts = 10; // Stop trying after 10 failed attempts
  private reconnectTimer: number | null = null;
  private reconnectAttempts = 0;
  private reconnectDelay = 3000; // Start at 3s (was 1s — too aggressive)
  private maxReconnectDelay = 60000; // Cap at 60s (was 30s)
  private pollTimer: number | null = null;
  private state: 'connected' | 'connecting' | 'disconnected' = 'disconnected';
  private pollInterval = 30000; // 30s fallback polling (was 20s)

  constructor() {
    // Determine WebSocket URL (http → ws, https → wss)
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    this.url = `${protocol}//${window.location.host}/ws`;
  }

  /**
   * Connect to WebSocket.
   */
  connect(): void {
    if (this.state !== 'disconnected') return;

    this.setState('connecting');

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log('[WS] Connected');
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        this.setState('connected');
        this.clearPollTimer();
      };

      this.ws.onmessage = (event) => {
        try {
          const msg: WebSocketMessage = JSON.parse(event.data);
          this.handleMessage(msg);
        } catch (e) {
          console.error('[WS] Failed to parse message:', e);
        }
      };

      this.ws.onerror = (error) => {
        console.error('[WS] Error:', error);
      };

      this.ws.onclose = () => {
        console.log('[WS] Disconnected');
        this.ws = null;
        this.setState('disconnected');
        this.scheduleReconnect();
        this.startPolling();
      };
    } catch (error) {
      console.error('[WS] Failed to create WebSocket:', error);
      this.setState('disconnected');
      this.scheduleReconnect();
      this.startPolling();
    }
  }

  /**
   * Disconnect from WebSocket.
   */
  disconnect(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.clearPollTimer();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.setState('disconnected');
  }

  /**
   * Send a message to the server.
   */
  send(msg: WebSocketMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  /**
   * Subscribe to a message type.
   */
  on(type: string, handler: WSHandler): void {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, new Set());
    }
    this.handlers.get(type)!.add(handler);
  }

  /**
   * Unsubscribe from a message type.
   */
  off(type: string, handler: WSHandler): void {
    const handlers = this.handlers.get(type);
    if (handlers) {
      handlers.delete(handler);
    }
  }

  /**
   * Listen to connection state changes.
   */
  onStateChange(listener: StateListener): void {
    this.stateListeners.add(listener);
  }

  /**
   * Unlisten from connection state changes.
   */
  offStateChange(listener: StateListener): void {
    this.stateListeners.delete(listener);
  }

  /**
   * Get current connection state.
   */
  getState(): string {
    return this.state;
  }

  /**
   * Check if connected.
   */
  isConnected(): boolean {
    return this.state === 'connected';
  }

  // ---- private ----

  private handleMessage(msg: WebSocketMessage): void {
    const type = msg.type;
    const handlers = this.handlers.get(type);

    if (handlers) {
      for (const handler of handlers) {
        try {
          handler(msg.payload || msg.data || msg);
        } catch (error) {
          console.error(`[WS] Handler for ${type} failed:`, error);
        }
      }
    }

    // Respond to ping
    if (type === 'ping') {
      this.send({ type: 'pong' });
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null) {
      return; // Already scheduled
    }

    // Stop reconnecting after too many failures to avoid flooding proxy
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.warn('[WS] Max reconnect attempts reached. Polling only.');
      return;
    }

    this.reconnectAttempts++;
    const delay = Math.min(
      this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
      this.maxReconnectDelay
    );

    console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private startPolling(): void {
    if (this.pollTimer !== null) return;

    console.log('[WS] Starting fallback polling');
    this.pollTimer = window.setInterval(async () => {
      if (this.state === 'connected') {
        this.clearPollTimer();
        return;
      }

      try {
        // Poll for fresh stock data
        const resp = await fetch('/api/stocks');
        if (resp.ok) {
          const stocks = await resp.json();
          this.handleMessage({ type: 'stocks', payload: stocks });
        }
      } catch (error) {
        // Polling failure is silent
      }
    }, this.pollInterval);
  }

  private clearPollTimer(): void {
    if (this.pollTimer !== null) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  private setState(newState: 'connected' | 'connecting' | 'disconnected'): void {
    if (this.state !== newState) {
      this.state = newState;
      for (const listener of this.stateListeners) {
        listener(newState);
      }
    }
  }
}

// Export singleton
export const ws = new WebSocketService();
