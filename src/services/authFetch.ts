/**
 * Auth-aware fetch wrapper.
 *
 * Automatically injects auth headers when the user is logged in.
 * Supports two auth modes:
 * 1. JWT Bearer token (Authorization: Bearer <jwt>) — SSO login
 * 2. API Key (X-API-Key header) — legacy mode
 *
 * JWT token takes priority over API key when both are present.
 *
 * 全局 401 拦截:
 * 当任何请求返回 401(凭证缺失/失效),自动清除失效凭证并跳转登录页,
 * 避免用户面对空数据或通用错误却无引导。
 */

const API_KEY_STORAGE = "aureon_api_key";
const JWT_TOKEN_STORAGE = "aureon_jwt_token";

/**
 * 白名单:这些路径的 401 不触发跳转(避免登录页/健康检查自身请求循环)
 * - /login          登录页探测请求
 * - /api/health     公开端点
 * - /api/crew/health
 * - /metrics
 */
const AUTH_BYPASS_PATTERNS = [
  "/login",
  "/api/health",
  "/api/crew/health",
  "/metrics",
  "/api/security/sso/login",
  "/api/security/demo-token",
  "/api/v1/security/demo-token",
];

function isAuthBypass(url: string): boolean {
  return AUTH_BYPASS_PATTERNS.some((p) => url.includes(p));
}

/** 标记位:防止多个并发请求同时触发跳转 */
let isRedirecting = false;

/**
 * 处理 401:跳转登录页。
 * 幂等:多次调用安全(靠 isRedirecting 标志位去重)。
 *
 * 关键:不在这里清除 sessionStorage/authStore!
 * 原因:清除凭证是同步的,但跳转是异步的(setTimeout),
 * 中间窗口内其他 in-flight 请求会丢失凭证导致连锁 401。
 * 让登录页在成功登录时自然覆盖旧凭证即可。
 */
function handleAuthExpired(): void {
  if (isRedirecting) return;

  // 派发自定义事件,供 App 层做额外处理(toast 等)
  try {
    window.dispatchEvent(new CustomEvent("aureon:auth-expired"));
  } catch {
    /* SSR */
  }

  // 异步跳转登录页(不阻塞当前响应链,也避免 jsdom 环境报错)
  isRedirecting = true;
  setTimeout(() => {
    try {
      const currentPath = window.location.pathname + window.location.search;
      const redirect = encodeURIComponent(currentPath);
      window.location.href = `/login?redirect=${redirect}`;
    } catch {
      /* jsdom 或 SSR 环境跳过 */
    }
    // 5s 后重置标志位(若跳转失败容错)
    setTimeout(() => {
      isRedirecting = false;
    }, 5000);
  }, 0);
}

function getApiKey(): string {
  try {
    return sessionStorage.getItem(API_KEY_STORAGE) || "";
  } catch {
    return "";
  }
}

function getJwtToken(): string {
  try {
    return sessionStorage.getItem(JWT_TOKEN_STORAGE) || "";
  } catch {
    return "";
  }
}

/**
 * Drop-in replacement for `fetch` that adds auth headers.
 * JWT Bearer token takes priority; falls back to X-API-Key.
 */
export function authFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const jwt = getJwtToken();
  const apiKey = getApiKey();

  const headers = new Headers(init?.headers);
  if (jwt) {
    headers.set("Authorization", `Bearer ${jwt}`);
  }
  if (apiKey) {
    headers.set("X-API-Key", apiKey);
  }

  const finalInit = (jwt || apiKey) ? { ...init, headers } : init;

  return fetch(input, finalInit).then((res) => {
    // 全局 401 拦截:凭证失效时统一处理,白名单路径除外
    // (已通过 signal abort 的请求不会走到这里,fetch 会直接 reject)
    if (res.status === 401 && !isAuthBypass(String(input))) {
      handleAuthExpired();
    }
    return res;
  });
}
