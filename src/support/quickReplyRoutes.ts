export function getRouteQuickReplies(t: (key: string) => string): string[] {
  const ROUTE_QUESTIONS: Record<string, string[]> = {
    '/search': ['support.qr_search_tips', 'support.qr_search_filters'],
    '/documents': ['support.qr_upload_doc', 'support.qr_file_formats'],
    '/dashboard': ['support.qr_dashboard_metrics'],
    '/analytics': ['support.qr_analytics_frequency'],
    '/admin': ['support.qr_admin_permissions'],
    '/cost': ['support.qr_cost_calculation'],
  };

  const path = window.location.pathname;
  const keys = Object.entries(ROUTE_QUESTIONS).find(([route]) =>
    path === route || path.startsWith(route + '/')
  )?.[1] ?? [];
  return keys.map(k => t(k));
}
