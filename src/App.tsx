// Aureon — Enterprise AI Knowledge Base Platform
import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ToastProvider } from "./hooks/useToast";
import { AuthProvider } from "./hooks/AuthProvider";
import { ThemeProvider } from "./hooks/ThemeProvider";
import { OnboardingProvider } from "./components/onboarding/OnboardingProvider";
import { RealtimeMetricsProvider } from "./providers/RealtimeMetricsProvider";
import { useAuth } from "./hooks/AuthContext";
import { AdminGate } from "./components/AdminGate";
import { useUIStore } from "./stores/useUIStore";
import { AppSidebar } from "./components/AppSidebar";

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

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <ToastProvider>
          <BrowserRouter useTransitions={false}>
            <AuthProvider>
              <RealtimeMetricsProvider>
                <OnboardingProvider>
                  <AppLayout />
                </OnboardingProvider>
              </RealtimeMetricsProvider>
            </AuthProvider>
          </BrowserRouter>
        </ToastProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

/* ── App Layout — Sidebar + Content (flex-row) ── */
function AppLayout() {
  const location = useLocation();
  const sidebarCollapsed = useUIStore(s => s.sidebarCollapsed);
  const toggleSidebarCollapsed = useUIStore(s => s.toggleSidebarCollapsed);
  const mobileSidebarOpen = useUIStore(s => s.mobileSidebarOpen);
  const setMobileSidebarOpen = useUIStore(s => s.setMobileSidebarOpen);

  // 路由变化时关闭移动端侧边栏
  useEffect(() => { setMobileSidebarOpen(false); }, [location.pathname, setMobileSidebarOpen]);

  // Body scroll lock when mobile drawer is open
  useEffect(() => {
    if (mobileSidebarOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [mobileSidebarOpen]);

  const isLanding = location.pathname === "/";
  const isLogin = location.pathname === "/login";
  // Landing 和 Login 页面不显示侧边栏
  const showSidebar = !isLanding && !isLogin;

  return (
    <div className="h-screen flex flex-row" style={{background:'var(--bg-primary)'}}>
      {/* Desktop Sidebar */}
      {showSidebar && (
        <div className="hidden md:block">
          <AppSidebar collapsed={sidebarCollapsed} onToggleCollapse={toggleSidebarCollapsed} />
        </div>
      )}

      {/* Mobile Sidebar Drawer */}
      {showSidebar && (
        <>
          {/* Overlay with fade */}
          <div
            className="md:hidden fixed inset-0 z-40 transition-opacity duration-200"
            style={{
              background: 'rgba(0,0,0,0.4)',
              opacity: mobileSidebarOpen ? 1 : 0,
              pointerEvents: mobileSidebarOpen ? 'auto' : 'none',
            }}
            onClick={() => setMobileSidebarOpen(false)}
          />
          {/* Drawer with slide */}
          <div
            className="md:hidden fixed left-0 top-0 bottom-0 z-50 transition-transform duration-200 ease-out"
            style={{
              transform: mobileSidebarOpen ? 'translateX(0)' : 'translateX(-100%)',
              maxWidth: '80vw',
            }}
          >
            <AppSidebar collapsed={false} onToggleCollapse={() => setMobileSidebarOpen(false)} />
          </div>
        </>
      )}

      {/* Mobile top bar — hamburger only */}
      {showSidebar && (
        <div className="md:hidden fixed top-0 left-0 right-0 z-30 flex items-center px-4 py-2 glass" style={{ borderBottom: '1px solid var(--border)' }}>
          <button
            onClick={() => setMobileSidebarOpen(true)}
            className="p-2 rounded-md"
            style={{ color: 'var(--text-secondary)' }}
            aria-label="Open menu"
            aria-expanded={mobileSidebarOpen}
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <span className="ml-3 text-base font-extrabold tracking-tight" style={{color:'var(--seed-primary)', fontFamily:'var(--font-display)'}}>Aureon</span>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 min-w-0 overflow-auto">
        {/* Add top padding on mobile when sidebar is shown (for the fixed hamburger bar) */}
        <div className={showSidebar ? 'md:pt-0 pt-12' : ''}>
          <Suspense fallback={<PageFallback />}>
            <Routes key={location.pathname}>
              <Route path="/" element={<Landing />} />
              <Route path="/login" element={<Login />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/search" element={<Search />} />
              <Route path="/documents" element={<Documents />} />
              <Route path="/crew" element={<CrewGenerator />} />
              {/* Protected routes — require auth */}
              <Route path="/analytics" element={<ProtectedRoute><Analytics /></ProtectedRoute>} />
              {/* Admin routes — require auth + admin gate */}
              <Route path="/architecture" element={<AdminGate><Architecture /></AdminGate>} />
              <Route path="/portfolio" element={<Navigate to="/architecture" replace />} />
              <Route path="/admin" element={<AdminGate><Admin /></AdminGate>} />
              <Route path="/cost" element={<AdminGate><CostGovernance /></AdminGate>} />
              {/* Catch-all 404 route */}
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </div>
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

export default App;
