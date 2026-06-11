import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export default function NotFound() {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4">
      <div className="text-center space-y-6">
        {/* Large 404 number */}
        <h1 className="text-8xl font-bold text-muted-foreground/30">404</h1>

        {/* Message */}
        <div className="space-y-2">
          <h2 className="text-2xl font-semibold text-foreground">
            {t("notFound.title", "Page not found")}
          </h2>
          <p className="text-muted-foreground max-w-md mx-auto">
            {t(
              "notFound.description",
              "The page you're looking for doesn't exist or has been moved."
            )}
          </p>
        </div>

        {/* Action buttons */}
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            to="/"
            className="inline-flex items-center justify-center px-6 py-3 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium"
          >
            {t("notFound.goHome", "Go to homepage")}
          </Link>
          <Link
            to="/search"
            className="inline-flex items-center justify-center px-6 py-3 bg-secondary text-secondary-foreground rounded-lg hover:bg-secondary/80 transition-colors font-medium"
          >
            {t("notFound.search", "Search")}
          </Link>
        </div>
      </div>
    </div>
  );
}
