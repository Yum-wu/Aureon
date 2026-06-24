/** Dashboard shared types */

export interface AlertMessage {
  id: string;
  severity: 'critical' | 'warning' | 'info';
  message: string;
  timestamp: string;
}

export interface ServiceHealth {
  name: string;
  healthy: boolean;
  responseTime: number;
}
