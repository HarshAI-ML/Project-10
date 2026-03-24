import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Navbar from "./components/Navbar";
import ProtectedRoute from "./routes/ProtectedRoute";
import Login from "./pages/Login";
import Register from "./pages/Register";
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

  return (
    <div className="min-h-screen">
      <Navbar />
      <main className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <div key={location.pathname} className="page-enter">
          <Routes>
            <Route path="/" element={<Navigate to="/portfolio" replace />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
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
            <Route path="*" element={<Navigate to="/portfolio" replace />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
