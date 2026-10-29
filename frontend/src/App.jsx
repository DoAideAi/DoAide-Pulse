import { Suspense, useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ErrorFallback, PAGE_MESSAGE, RouteErrorBoundary } from "./components/ErrorBoundary";
import FeedbackWidget from "./components/FeedbackWidget";
import InstallPrompt from "./components/InstallPrompt";
import Shell from "./components/Shell";
import { useAuth } from "./hooks/useAuth";
import { trackPageView } from "./lib/activity";
import LandingPage from "./pages/LandingPage";
import lazyPage from "./lib/lazyPage";

// The landing page is the cold entry for nearly every visit and the place a
// signed-out redirect lands, so it ships in the entry chunk. Everything else
// is fetched when its route is first matched.
const AdminFeedback = lazyPage(() => import("./pages/AdminFeedback"));
const Analytics = lazyPage(() => import("./pages/Analytics"));
const Blog = lazyPage(() => import("./pages/Blog"));
const BlogPost = lazyPage(() => import("./pages/BlogPost"));
const Calendar = lazyPage(() => import("./pages/Calendar"));
const ContentEditor = lazyPage(() => import("./pages/ContentEditor"));
const ContentList = lazyPage(() => import("./pages/ContentList"));
const Dashboard = lazyPage(() => import("./pages/Dashboard"));
const Embed = lazyPage(() => import("./pages/Embed"));
const Login = lazyPage(() => import("./pages/Login"));
const NewsletterGallery = lazyPage(() => import("./pages/NewsletterGallery"));
const PreviewPage = lazyPage(() => import("./pages/PreviewPage"));
const ProductActivity = lazyPage(() => import("./pages/ProductActivity"));
const Seo = lazyPage(() => import("./pages/Seo"));
const Projects = lazyPage(() => import("./pages/Projects"));
const Publish = lazyPage(() => import("./pages/Publish"));
const Settings = lazyPage(() => import("./pages/Settings"));
const Templates = lazyPage(() => import("./pages/Templates"));
const TemplatesGallery = lazyPage(() => import("./pages/TemplatesGallery"));
const Triggers = lazyPage(() => import("./pages/Triggers"));
const Unsubscribe = lazyPage(() => import("./pages/Unsubscribe"));
const ResetPassword = lazyPage(() => import("./pages/ResetPassword"));
const PublicArticle = lazyPage(() => import("./pages/PublicArticle"));
const NotFound = lazyPage(() => import("./pages/NotFound"));
const SubjectLineTester = lazyPage(() => import("./pages/tools/SubjectLineTester"));
const SendTimeOptimizer = lazyPage(() => import("./pages/tools/SendTimeOptimizer"));
const NewsletterRoiCalculator = lazyPage(() => import("./pages/tools/NewsletterRoiCalculator"));
const ContentIdeaGenerator = lazyPage(() => import("./pages/tools/ContentIdeaGenerator"));

function Loading() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <span className="eyebrow animate-pulse">Loading</span>
    </div>
  );
}

/** A page chunk loading inside the Shell: the chrome stays, only the body waits. */
function PageLoading() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center" role="status">
      <span className="eyebrow animate-pulse">Loading</span>
    </div>
  );
}

/**
 * Sign-in gate, chrome, and the boundary between the two.
 *
 * The boundary sits *inside* `Shell`, so a page that throws leaves the
 * navigation, the account menu and the queue badges standing — the user can
 * click their way out of the broken screen instead of reloading a blank tab.
 * It resets on navigation, so clicking away is all it takes.
 */
function Protected({ children }) {
  const { user, loading } = useAuth();
  const { pathname } = useLocation();
  // Signed-in pages only: the tracker files events under the account, so this
  // is the one wrapper every page it can record passes through.
  useEffect(() => {
    if (user) trackPageView(pathname);
  }, [user, pathname]);
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/" replace />;
  return (
    <Shell>
      <RouteErrorBoundary title="This page stopped working" message={PAGE_MESSAGE} section="page">
        <Suspense fallback={<PageLoading />}>{children}</Suspense>
      </RouteErrorBoundary>
    </Shell>
  );
}

/**
 * The boundary for a route that renders without the Shell.
 *
 * Same containment, different framing: with no chrome around it, the default
 * panel would sit alone against the top of an otherwise empty page, so these
 * two centre it the way their own content is centred.
 */
function Unshelled({ children, section }) {
  return (
    <RouteErrorBoundary
      section={section}
      fallback={({ error, reset }) => (
        <div className="flex min-h-screen items-center justify-center px-5">
          <div className="w-full max-w-md">
            {/* The whole page, so the page wording — the section default
                promised a "rest of the page" that was not there. */}
            <ErrorFallback
              error={error}
              reset={reset}
              title="This page could not load"
              message={PAGE_MESSAGE}
            />
          </div>
        </div>
      )}
    >
      <Suspense fallback={<Loading />}>{children}</Suspense>
    </RouteErrorBoundary>
  );
}

export default function App() {
  return (
    <>
    <Routes>
      <Route
        path="/"
        element={
          <Unshelled section="landing">
            <LandingPage />
          </Unshelled>
        }
      />
      <Route
        path="/login"
        element={
          <Unshelled section="login">
            <Login />
          </Unshelled>
        }
      />
      {/* Unauthenticated on purpose — see app.services.preview_links. */}
      <Route
        path="/preview/:token"
        element={
          <Unshelled section="preview">
            <PreviewPage />
          </Unshelled>
        }
      />

      <Route path="/tools/subject-line-tester" element={<Unshelled section="tool"><SubjectLineTester /></Unshelled>} />
      <Route path="/tools/send-time-optimizer" element={<Unshelled section="tool"><SendTimeOptimizer /></Unshelled>} />
      <Route path="/tools/newsletter-roi-calculator" element={<Unshelled section="tool"><NewsletterRoiCalculator /></Unshelled>} />
      <Route path="/tools/content-idea-generator" element={<Unshelled section="tool"><ContentIdeaGenerator /></Unshelled>} />
      <Route path="/article/:slug" element={<Unshelled section="article"><PublicArticle /></Unshelled>} />
      <Route path="/blog" element={<Unshelled section="blog"><Blog /></Unshelled>} />
      <Route path="/blog/:slug" element={<Unshelled section="blog"><BlogPost /></Unshelled>} />
      <Route path="/templates" element={<Unshelled section="templates"><TemplatesGallery /></Unshelled>} />
      <Route path="/gallery" element={<Unshelled section="gallery"><NewsletterGallery /></Unshelled>} />
      <Route path="/embed" element={<Unshelled section="embed"><Embed /></Unshelled>} />
      <Route path="/unsubscribe" element={<Unshelled section="unsubscribe"><Unsubscribe /></Unshelled>} />
      {/* Where the reset email links to — see app.services.password_reset. */}
      <Route path="/reset-password" element={<Unshelled section="reset-password"><ResetPassword /></Unshelled>} />

      <Route
        path="/dashboard"
        element={
          <Protected>
            <Dashboard />
          </Protected>
        }
      />
      <Route
        path="/projects"
        element={
          <Protected>
            <Projects />
          </Protected>
        }
      />
      <Route
        path="/content"
        element={
          <Protected>
            <ContentList />
          </Protected>
        }
      />
      {/* The editor is entered from a piece, not from the nav. */}
      <Route
        path="/content/:contentId"
        element={
          <Protected>
            <ContentEditor />
          </Protected>
        }
      />
      <Route
        path="/products"
        element={
          <Protected>
            <ProductActivity />
          </Protected>
        }
      />
      <Route
        path="/seo"
        element={
          <Protected>
            <Seo />
          </Protected>
        }
      />
      <Route
        path="/triggers"
        element={
          <Protected>
            <Triggers />
          </Protected>
        }
      />
      <Route
        path="/my-templates"
        element={
          <Protected>
            <Templates />
          </Protected>
        }
      />
      <Route
        path="/calendar"
        element={
          <Protected>
            <Calendar />
          </Protected>
        }
      />
      <Route
        path="/publish"
        element={
          <Protected>
            <Publish />
          </Protected>
        }
      />
      <Route
        path="/analytics"
        element={
          <Protected>
            <Analytics />
          </Protected>
        }
      />
      <Route
        path="/settings"
        element={
          <Protected>
            <Settings />
          </Protected>
        }
      />
      <Route
        path="/admin/feedback"
        element={
          <Protected>
            <AdminFeedback />
          </Protected>
        }
      />

      {/* A page that says it is not there, rather than a redirect that made a
          dead link look like it had worked. See pages/NotFound. */}
      <Route
        path="*"
        element={
          <Unshelled section="not-found">
            <NotFound />
          </Unshelled>
        }
      />
    </Routes>
    {/* On every page, signed in or not — see FeedbackWidget for the two
        pages it stays off. */}
    <FeedbackWidget />
    <InstallPrompt />
    </>
  );
}
