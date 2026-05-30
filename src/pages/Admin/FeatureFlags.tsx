import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  featureFlagsApi,
  type FeatureFlag,
  type FeatureFlagCreate,
} from "../../services/featureFlags";

export default function FeatureFlags() {
  const { t } = useTranslation();
  const [flags, setFlags] = useState<FeatureFlag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newFlag, setNewFlag] = useState<FeatureFlagCreate>({
    name: "",
    description: "",
    enabled: false,
    percentage: 0,
  });

  const loadFlags = useCallback(async () => {
    try {
      setLoading(true);
      const data = await featureFlagsApi.list();
      setFlags(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load flags");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadFlags();
  }, [loadFlags]);

  const handleCreate = async () => {
    try {
      await featureFlagsApi.create(newFlag);
      setShowCreateModal(false);
      setNewFlag({ name: "", description: "", enabled: false, percentage: 0 });
      loadFlags();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create flag");
    }
  };

  const handleToggle = async (flag: FeatureFlag) => {
    try {
      await featureFlagsApi.update(flag.name, { enabled: !flag.enabled });
      loadFlags();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to toggle flag");
    }
  };

  const handleStatusChange = async (
    flag: FeatureFlag,
    status: string
  ) => {
    try {
      await featureFlagsApi.update(flag.name, { status });
      loadFlags();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to update status"
      );
    }
  };

  const handleDelete = async (name: string) => {
    if (!confirm(t("admin.featureFlags.confirmDelete"))) return;
    try {
      await featureFlagsApi.delete(name);
      loadFlags();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete flag");
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "active":
        return "bg-green-100 text-green-800";
      case "draft":
        return "bg-yellow-100 text-yellow-800";
      case "deprecated":
        return "bg-orange-100 text-orange-800";
      case "archived":
        return "bg-gray-100 text-gray-800";
      default:
        return "bg-gray-100 text-gray-800";
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">{t("common.loading")}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {t("admin.featureFlags.title")}
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            {t("admin.featureFlags.description")}
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          {t("admin.featureFlags.create")}
        </button>
      </div>

      {/* Error Message */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-red-800">{error}</p>
          <button
            onClick={() => setError(null)}
            className="mt-2 text-sm text-red-600 hover:text-red-800"
          >
            {t("common.dismiss")}
          </button>
        </div>
      )}

      {/* Flags Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                {t("admin.featureFlags.name")}
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                {t("admin.featureFlags.status")}
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                {t("admin.featureFlags.enabled")}
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                {t("admin.featureFlags.percentage")}
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                {t("admin.featureFlags.actions")}
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {flags.map((flag) => (
              <tr key={flag.id} className="hover:bg-gray-50">
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="text-sm font-medium text-gray-900">
                    {flag.name}
                  </div>
                  {flag.description && (
                    <div className="text-sm text-gray-500">
                      {flag.description}
                    </div>
                  )}
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <select
                    value={flag.status}
                    onChange={(e) =>
                      handleStatusChange(flag, e.target.value)
                    }
                    className={`px-2 py-1 text-xs rounded-full ${getStatusColor(flag.status)}`}
                  >
                    <option value="draft">Draft</option>
                    <option value="active">Active</option>
                    <option value="deprecated">Deprecated</option>
                    <option value="archived">Archived</option>
                  </select>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <button
                    onClick={() => handleToggle(flag)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      flag.enabled ? "bg-blue-600" : "bg-gray-200"
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        flag.enabled ? "translate-x-6" : "translate-x-1"
                      }`}
                    />
                  </button>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {flag.percentage}%
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                  <button
                    onClick={() => handleDelete(flag.name)}
                    className="text-red-600 hover:text-red-900"
                  >
                    {t("common.delete")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {flags.length === 0 && (
          <div className="text-center py-12">
            <p className="text-gray-500">
              {t("admin.featureFlags.noFlags")}
            </p>
          </div>
        )}
      </div>

      {/* Create Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h2 className="text-lg font-semibold mb-4">
              {t("admin.featureFlags.createNew")}
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {t("admin.featureFlags.name")}
                </label>
                <input
                  type="text"
                  value={newFlag.name}
                  onChange={(e) =>
                    setNewFlag({ ...newFlag, name: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="e.g., new-feature"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {t("admin.featureFlags.description")}
                </label>
                <textarea
                  value={newFlag.description || ""}
                  onChange={(e) =>
                    setNewFlag({ ...newFlag, description: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  rows={3}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {t("admin.featureFlags.rolloutPercentage")}
                </label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={newFlag.percentage}
                  onChange={(e) =>
                    setNewFlag({
                      ...newFlag,
                      percentage: parseInt(e.target.value) || 0,
                    })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
            </div>
            <div className="flex justify-end space-x-3 mt-6">
              <button
                onClick={() => setShowCreateModal(false)}
                className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200"
              >
                {t("common.cancel")}
              </button>
              <button
                onClick={handleCreate}
                disabled={!newFlag.name}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {t("common.create")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
