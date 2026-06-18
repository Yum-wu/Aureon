// Aureon — Enterprise AI Knowledge Base Platform
import { lazy, Suspense, useState, useEffect, type ReactNode } from "react";
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Toaster } from "sonner";
import { LanguageSwitcher } from "./i18n/LanguageSwitcher";
import { AuthProvider } from "./hooks/AuthProvider";
import { useAuth } from "./hooks/AuthContext";

// Route-level code splitting — each page is a separate chunk
const Landing = lazy(() => import("./pages/Landing").then(m => ({ default: m.Landing })));
const Dashboard = lazy(() => import("./pages/Dashboard").then(m => ({ default: m.Dashboard })));
const Search = lazy(() => import("./pages/Search").then(m => ({ default: m.Search })));
const Documents = lazy(() => import("./pages/Documents").then(m => ({ default: m.Documents })));
const CrewGenerator = lazy(() => import("./components/CrewGenerator").then(m => ({ default: m.CrewGenerator })));
const Login = lazy(() => import("./pages/Login"));
const Analytics = lazy(() => import("./pages/Analytics"));
const Admin = lazy(() => import("./pages/Admin"));
const CostGovernance = lazy(() => import("./pages/CostGovernance").then(m => ({ default: m.CostGovernance })));
const Architecture = lazy(() => import("./pages/Architecture").then(m => ({ default: m.Architecture })));
const Portfolio = lazy(() => import("./pages/Portfolio").then(m => ({ default: m.Portfolio })));
const NotFound = lazy(() => import("./pages/NotFound"));
const SupportWidget = lazy(() => import("./components/SupportWidget").then(m => ({ default: m.SupportWidget })));

function PageFallback() {
  return (
    <div className="flex items-center justify-center h-64" style={{background:'var(--bg-primary)'}}>
      <div className="animate-spin rounded-full h-8 w-8" style={{borderColor:'var(--bg-tertiary)',borderTopColor:'var(--accent)'}} />
    </div>
  );
}

/* -- Route Guard -- */
function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

/* ── App Layout ── */
function AppLayout() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // 路由变化时关闭移动端菜单
  useEffect(() => { setMobileMenuOpen(false); }, [location.pathname]);

  const navItems = [
    { path: "/dashboard", key: "app.nav.dashboard" },
    { path: "/search", key: "app.nav.search" },
    { path: "/documents", key: "app.nav.documents" },
    { path: "/analytics", key: "app.nav.analytics" },
    { path: "/architecture", key: "app.nav.architecture" },
    { path: "/portfolio", key: "app.nav.portfolio" },
    { path: "/admin", key: "app.nav.admin" },
    { path: "/cost", key: "app.nav.cost" },
  ];

  const isLanding = location.pathname === "/";
  const isLogin = location.pathname === "/login";

  return (
    <div className="h-screen flex flex-col" style={{background:'var(--bg-primary)'}}>
      {!isLanding && !isLogin && (
        <>
        <nav className="flex items-center border-b px-6 py-0 glass sticky top-0 z-40" style={{borderColor:'var(--border)'}} role="navigation" aria-label={t('app.nav.menu')}>
          {/* Logo */}
          <button
            onClick={() => navigate("/")}
            className="mr-8 py-3 shrink-0 group"
          >
            <span className="text-base font-extrabold tracking-tight" style={{color:'var(--accent)'}}>Aureon</span>
          </button>

          {/* Desktop Nav links */}
          <div className="hidden md:flex items-center gap-1">
            {navItems.map((item) => {
              const isActive = location.pathname.startsWith(item.path);
              return (
                <button
                  key={item.path}
                  onClick={() => navigate(item.path)}
                  className="relative px-4 py-3 text-sm font-medium transition-colors rounded-md"
                  style={{
                    color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                    background: isActive ? 'var(--accent-soft)' : 'transparent',
                  }}
                  aria-current={isActive ? 'page' : undefined}
                >
                  {t(item.key)}
                </button>
              );
            })}
          </div>

          {/* Mobile hamburger button */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden p-2 rounded-md"
            style={{ color: 'var(--text-secondary)' }}
            aria-label={t('app.nav.menu')}
            aria-expanded={mobileMenuOpen}
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {mobileMenuOpen ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </button>

          {/* Right side */}
          <div className="ml-auto flex items-center gap-3">
            <LanguageSwitcher />
            <button
              onClick={() => navigate("/login")}
              className="glow-btn-outline !py-1.5 !px-3 !text-xs"
            >
              {t("app.nav.admin")}
            </button>
          </div>
        </nav>

        {/* Mobile dropdown menu */}
        {mobileMenuOpen && (
          <div className="md:hidden absolute top-full left-0 right-0 border-b z-50" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
            {navItems.map((item) => {
              const isActive = location.pathname.startsWith(item.path);
              return (
                <button
                  key={item.path}
                  onClick={() => { navigate(item.path); setMobileMenuOpen(false); }}
                  className="block w-full text-left px-6 py-3 text-sm font-medium transition-colors"
                  style={{
                    color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                    background: isActive ? 'var(--accent-soft)' : 'transparent',
                  }}
                  aria-current={isActive ? 'page' : undefined}
                >
                  {t(item.key)}
                </button>
              );
            })}
          </div>
        )}
        </>
      )}

      <div className="flex-1 overflow-auto">
        <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/search" element={<Search />} />
            <Route path="/documents" element={<Documents />} />
            <Route path="/architecture" element={<Architecture />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/crew" element={<CrewGenerator />} />
            {/* Protected routes — require auth */}
            <Route path="/analytics" element={<ProtectedRoute><Analytics /></ProtectedRoute>} />
            <Route path="/admin" element={<ProtectedRoute><Admin /></ProtectedRoute>} />
            <Route path="/cost" element={<ProtectedRoute><CostGovernance /></ProtectedRoute>} />
            {/* Catch-all 404 route */}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </div>

      {/* Global Support Widget — hidden on login page */}
      {!isLogin && (
        <Suspense fallback={null}>
          <SupportWidget />
        </Suspense>
      )}
    </div>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <Toaster theme="dark" position="top-center" richColors closeButton />
      <BrowserRouter>
        <AuthProvider>
          <AppLayout />
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
}

export default App;
