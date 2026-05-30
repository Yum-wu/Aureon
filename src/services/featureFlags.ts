/**
 * Feature Flags Service
 * 管理 Feature Flags 的 API 调用
 */

export interface FeatureFlag {
  id: number;
  name: string;
  description: string | null;
  status: string;
  enabled: boolean;
  percentage: number;
  conditions: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface FeatureFlagCreate {
  name: string;
  description?: string;
  enabled?: boolean;
  percentage?: number;
  conditions?: Record<string, unknown>;
}

export interface FeatureFlagUpdate {
  description?: string;
  status?: string;
  enabled?: boolean;
  percentage?: number;
  conditions?: Record<string, unknown>;
}

const API_BASE = import.meta.env.VITE_API_URL || "/api";

export const featureFlagsApi = {
  /**
   * 获取所有 Feature Flags
   */
  async list(status?: string): Promise<FeatureFlag[]> {
    const url = status
      ? `${API_BASE}/feature-flags/?status=${status}`
      : `${API_BASE}/feature-flags/`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error("Failed to list feature flags");
    }
    return response.json();
  },

  /**
   * 获取单个 Feature Flag
   */
  async get(name: string): Promise<FeatureFlag> {
    const response = await fetch(`${API_BASE}/feature-flags/${name}`);
    if (!response.ok) {
      throw new Error("Feature flag not found");
    }
    return response.json();
  },

  /**
   * 创建 Feature Flag
   */
  async create(flag: FeatureFlagCreate): Promise<FeatureFlag> {
    const response = await fetch(`${API_BASE}/feature-flags/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(flag),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Failed to create feature flag");
    }
    return response.json();
  },

  /**
   * 更新 Feature Flag
   */
  async update(name: string, update: FeatureFlagUpdate): Promise<FeatureFlag> {
    const response = await fetch(`${API_BASE}/feature-flags/${name}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    });
    if (!response.ok) {
      throw new Error("Failed to update feature flag");
    }
    return response.json();
  },

  /**
   * 删除 Feature Flag
   */
  async delete(name: string): Promise<void> {
    const response = await fetch(`${API_BASE}/feature-flags/${name}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      throw new Error("Failed to delete feature flag");
    }
  },

  /**
   * 评估 Feature Flag
   */
  async evaluate(
    name: string,
    userId?: string,
    workspaceId?: string
  ): Promise<boolean> {
    const params = new URLSearchParams();
    if (userId) params.append("user_id", userId);
    if (workspaceId) params.append("workspace_id", workspaceId);

    const response = await fetch(
      `${API_BASE}/feature-flags/evaluate/${name}?${params.toString()}`
    );
    if (!response.ok) {
      throw new Error("Failed to evaluate feature flag");
    }
    const data = await response.json();
    return data.enabled;
  },
};
