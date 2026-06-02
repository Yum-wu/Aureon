// Aureon — Enterprise AI Knowledge Base Platform
import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { LanguageSwitcher } from "./i18n/LanguageSwitcher";

// Route-level code splitting — each page is a separate chunk
const Landing = lazy(() => import("./pages/Landing").then(m => ({ default: m.Landing })));
const Dashboard = lazy(() => import("./pages/Dashboard").then(m => ({ default: m.Dashboard })));
const Search = lazy(() => import("./pages/Search").then(m => ({ default: m.Search })));
const Documents = lazy(() => import("./pages/Documents").then(m => ({ default: m.Documents })));
const CrewGenerator = lazy(() => import("./components/CrewGenerator").then(m => ({ default: m.CrewGenerator })));
const Login = lazy(() => import("./pages/Login"));
const Analytics = lazy(() => import("./pages/Analytics"));
const Benchmark = lazy(() => import("./pages/Benchmark"));
const Admin = lazy(() => import("./pages/Admin"));
const Architecture = lazy(() => import("./pages/Architecture").then(m => ({ default: m.Architecture })));

function PageFallback() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
    </div>
  );
}

/* ── App Layout ── */
function AppLayout() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();

  const navItems = [
    { path: "/dashboard", key: "app.nav.dashboard" },
    { path: "/search", key: "app.nav.search" },
    { path: "/documents", key: "app.nav.documents" },
    { path: "/analytics", key: "app.nav.analytics" },
    { path: "/benchmark", key: "app.nav.benchmark" },
    { path: "/admin", key: "app.nav.admin" },
    { path: "/architecture", key: "app.nav.architecture" },
    // { path: "/crew", key: "app.nav.crew" },  // hidden: CrewAI not production-ready
  ];

  const isLanding = location.pathname === "/";
  const isLogin = location.pathname === "/login";

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {!isLanding && !isLogin && (
        <nav className="flex items-center bg-white border-b border-gray-200 px-6 py-0" role="navigation">
          {/* Logo */}
          <button
            onClick={() => navigate("/")}
            className="mr-8 py-3 shrink-0 group"
          >
            <span className="text-base font-extrabold bg-gradient-to-r from-blue-600 to-amber-500 bg-clip-text text-transparent group-hover:from-blue-700 group-hover:to-amber-600 transition-all">
              Aureon
            </span>
          </button>

          {/* Nav links */}
          <div className="flex items-center gap-1">
            {navItems.map((item) => (
              <button
                key={item.path}
                onClick={() => navigate(item.path)}
                className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                  location.pathname.startsWith(item.path)
                    ? "border-blue-600 text-blue-600"
                    : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                }`}
              >
                {t(item.key)}
              </button>
            ))}
          </div>

          {/* Right side */}
          <div className="ml-auto flex items-center gap-3">
            <LanguageSwitcher />
            <button
              onClick={() => navigate("/login")}
              className="px-3 py-1.5 text-sm font-medium text-gray-600 hover:text-gray-900 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              {t("app.nav.admin")}
            </button>
          </div>
        </nav>
      )}

      <div className="flex-1 overflow-auto">
        <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/search" element={<Search />} />
            <Route path="/documents" element={<Documents />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/benchmark" element={<Benchmark />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="/architecture" element={<Architecture />} />
            <Route path="/crew" element={<CrewGenerator />} />
          </Routes>
        </Suspense>
      </div>
    </div>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AppLayout />
      </BrowserRouter>
    </ErrorBoundary>
  );
}

export default App;
