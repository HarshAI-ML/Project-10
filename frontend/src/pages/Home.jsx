import LandingNavbar from "../components/landing/LandingNavbar";
import LandingMarketTape from "../components/landing/LandingMarketTape";
import HeroSection from "../components/landing/HeroSection";
import FeatureHighlights from "../components/landing/FeatureHighlights";
import ChatbotShowcase from "../components/landing/ChatbotShowcase";
import WorkflowStrip from "../components/landing/WorkflowStrip";
import LandingFooter from "../components/landing/LandingFooter";

export default function Home() {
  return (
    <div className="landing-shell min-h-screen text-slate-100">
      <LandingNavbar />
      <LandingMarketTape />
      <div className="landing-bg">
        <main className="mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
          <HeroSection />
          <FeatureHighlights />
          <ChatbotShowcase />
          <WorkflowStrip />
        </main>
      </div>
      <LandingFooter />
    </div>
  );
}
