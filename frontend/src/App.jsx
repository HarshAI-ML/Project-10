import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Navbar from "./components/Navbar";
import ChatWidget from "./components/ChatWidget";
import ProtectedRoute from "./routes/ProtectedRoute";
import Home from "./pages/Home";
import Login from "./pages/Login";
import Register from "./pages/Register";
import TelegramRegister from "./pages/TelegramRegister";
import TelegramForgotPassword from "./pages/TelegramForgotPassword";
import Portfolio from "./pages/Portfolio";
import PortfolioClusters from "./pages/PortfolioClusters";
import Stocks from "./pages/Stocks";
import StockDetail from "./pages/StockDetail";
import LiveStockDetail from "./pages/LiveStockDetail";
import CompareStocks from "./pages/CompareStocks";
import PricePrediction from "./pages/PricePrediction";
import AutoSignal from "./pages/AutoSignal";
import AutoSignalCompany from "./pages/AutoSignalCompany";

export default function App() {
  const location = useLocation();
  const isHome = location.pathname === "/";

  return (
    <div
      className={
        isHome
          ? "min-h-screen"
          : "relative min-h-screen overflow-x-hidden bg-gradient-to-br from-slate-100 via-indigo-100 to-cyan-100"
      }
    >
      {!isHome && (
        <>
          <div className="pointer-events-none absolute -left-24 top-20 h-80 w-80 rounded-full bg-cyan-300/35 blur-3xl" />
          <div className="pointer-events-none absolute right-[-5rem] top-32 h-96 w-96 rounded-full bg-indigo-300/30 blur-3xl" />
          <div className="pointer-events-none absolute bottom-[-8rem] left-1/3 h-96 w-96 rounded-full bg-fuchsia-300/20 blur-3xl" />
          <div className="pointer-events-none absolute inset-0 opacity-[0.28] [background-image:radial-gradient(rgba(99,102,241,0.16)_1px,transparent_1px)] [background-size:22px_22px]" />
        </>
      )}
      {!isHome && <Navbar />}
      <main
        className={
          isHome
            ? ""
            : "relative mx-auto mt-4 w-full max-w-7xl rounded-3xl border border-white/70 bg-white/76 px-4 py-6 shadow-[0_20px_60px_-25px_rgba(30,41,59,0.35)] backdrop-blur-xl sm:px-6 lg:px-8"
        }
      >
        {!isHome && <div className="pointer-events-none absolute inset-0 rounded-3xl bg-gradient-to-br from-white/35 via-transparent to-indigo-100/30" />}
        <div key={location.pathname} className="page-enter relative">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Navigate to="/telegram-register" replace />} />
            <Route path="/telegram-register" element={<TelegramRegister />} />
            <Route path="/telegram-forgot-password" element={<TelegramForgotPassword />} />
            <Route
              path="/portfolio"
              element={
                <ProtectedRoute>
                  <Portfolio />
                </ProtectedRoute>
              }
            />
            <Route
              path="/portfolio/:id/clusters"
              element={
                <ProtectedRoute>
                  <PortfolioClusters />
                </ProtectedRoute>
              }
            />
            <Route
              path="/clusters"
              element={
                <ProtectedRoute>
                  <PortfolioClusters />
                </ProtectedRoute>
              }
            />
            <Route
              path="/stocks"
              element={
                <ProtectedRoute>
                  <Stocks />
                </ProtectedRoute>
              }
            />
            <Route
              path="/compare"
              element={
                <ProtectedRoute>
                  <CompareStocks />
                </ProtectedRoute>
              }
            />
            <Route
              path="/prediction"
              element={
                <ProtectedRoute>
                  <PricePrediction />
                </ProtectedRoute>
              }
            />
            <Route
              path="/stocks/:id"
              element={
                <ProtectedRoute>
                  <StockDetail />
                </ProtectedRoute>
              }
            />
            <Route
              path="/stocks/live/:symbol"
              element={
                <ProtectedRoute>
                  <LiveStockDetail />
                </ProtectedRoute>
              }
            />
            <Route
              path="/autosignal"
              element={
                <ProtectedRoute>
                  <AutoSignal />
                </ProtectedRoute>
              }
            />
            <Route
              path="/autosignal/:slug"
              element={
                <ProtectedRoute>
                  <AutoSignalCompany />
                </ProtectedRoute>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </main>
      <ChatWidget />
    </div>
  );
}
