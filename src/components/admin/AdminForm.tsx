/**
 * 通用管理表单组件
 * 支持验证、提交加载态、错误显示
 */

import { useState, useCallback, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

/** 表单字段定义 */
export interface AdminFormField {
  /** 字段名 */
  name: string;
  /** 标签 */
  label: string;
  /** 输入类型 */
  type: 'text' | 'email' | 'password' | 'select' | 'textarea' | 'number' | 'switch';
  /** 是否必填 */
  required?: boolean;
  /** 选项（select 类型） */
  options?: Array<{ value: string; label: string }>;
  /** 验证函数 */
  validate?: (value: unknown) => string | undefined;
  /** 占位符 */
  placeholder?: string;
}

interface AdminFormProps {
  /** 字段定义 */
  fields: AdminFormField[];
  /** 初始值 */
  initialValues?: Record<string, unknown>;
  /** 提交回调 */
  onSubmit: (values: Record<string, unknown>) => Promise<void> | void;
  /** 提交加载态 */
  loading?: boolean;
  /** 表单标题 */
  title?: string;
  /** 额外类名 */
  className?: string;
}

export function AdminForm({
  fields,
  initialValues = {},
  onSubmit,
  loading = false,
  title,
  className = '',
}: AdminFormProps) {
  const { t } = useTranslation();
  const [values, setValues] = useState<Record<string, unknown>>(() => {
    const init: Record<string, unknown> = {};
    for (const field of fields) {
      init[field.name] = initialValues[field.name] ?? (field.type === 'switch' ? false : '');
    }
    return init;
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleChange = useCallback((name: string, value: unknown) => {
    setValues((prev) => ({ ...prev, [name]: value }));
    setErrors((prev) => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
  }, []);

  const handleSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      setSubmitError(null);

      // 验证
      const newErrors: Record<string, string> = {};
      for (const field of fields) {
        const val = values[field.name];
        if (field.required && (val === '' || val === undefined || val === null)) {
          newErrors[field.name] = t('admin.form.required', '此字段为必填项');
        } else if (field.validate) {
          const err = field.validate(val);
          if (err) newErrors[field.name] = err;
        }
      }

      if (Object.keys(newErrors).length > 0) {
        setErrors(newErrors);
        return;
      }

      try {
        await onSubmit(values);
      } catch (err) {
        setSubmitError(
          err instanceof Error ? err.message : t('admin.form.submit_error', '提交失败'),
        );
      }
    },
    [fields, values, onSubmit, t],
  );

  return (
    <form onSubmit={handleSubmit} className={`space-y-4 ${className}`}>
      {title && (
        <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">{title}</h3>
      )}

      {fields.map((field) => (
        <div key={field.name}>
          <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">
            {field.label}
            {field.required && <span className="text-red-400 ml-0.5">*</span>}
          </label>

          {field.type === 'select' ? (
            <select
              value={String(values[field.name] ?? '')}
              onChange={(e) => handleChange(field.name, e.target.value)}
              className="w-full px-3 py-2 rounded-md border border-[var(--border)] bg-[var(--bg-tertiary)] text-[var(--text-primary)] text-sm focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] outline-none transition-colors"
            >
              <option value="">{field.placeholder ?? t('admin.form.select_placeholder', '请选择...')}</option>
              {field.options?.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          ) : field.type === 'textarea' ? (
            <textarea
              value={String(values[field.name] ?? '')}
              onChange={(e) => handleChange(field.name, e.target.value)}
              placeholder={field.placeholder}
              rows={3}
              className="w-full px-3 py-2 rounded-md border border-[var(--border)] bg-[var(--bg-tertiary)] text-[var(--text-primary)] text-sm focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] outline-none transition-colors resize-y"
            />
          ) : field.type === 'switch' ? (
            <button
              type="button"
              role="switch"
              aria-checked={Boolean(values[field.name])}
              onClick={() => handleChange(field.name, !values[field.name])}
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                values[field.name] ? 'bg-[var(--accent)]' : 'bg-[var(--bg-tertiary)] border border-[var(--border)]'
              }`}
            >
              <span
                className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
                  values[field.name] ? 'translate-x-4' : 'translate-x-0.5'
                }`}
              />
            </button>
          ) : (
            <input
              type={field.type}
              value={String(values[field.name] ?? '')}
              onChange={(e) =>
                handleChange(field.name, field.type === 'number' ? Number(e.target.value) : e.target.value)
              }
              placeholder={field.placeholder}
              className="w-full px-3 py-2 rounded-md border border-[var(--border)] bg-[var(--bg-tertiary)] text-[var(--text-primary)] text-sm focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] outline-none transition-colors"
            />
          )}

          {errors[field.name] && (
            <p className="mt-1 text-xs text-red-400">{errors[field.name]}</p>
          )}
        </div>
      ))}

      {submitError && (
        <div className="px-3 py-2 rounded-md bg-red-500/10 border border-red-500/20 text-xs text-red-400">
          {submitError}
        </div>
      )}

      <div className="flex justify-end pt-2">
        <button
          type="submit"
          disabled={loading}
          className="glow-btn px-4 py-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? t('admin.loading') : t('admin.form.submit', '提交')}
        </button>
      </div>
    </form>
  );
}
