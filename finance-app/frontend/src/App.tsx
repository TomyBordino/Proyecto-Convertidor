import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import StockDetail from "./pages/StockDetail";

// Se carga en un chunk separado porque trae recharts (la libreria mas pesada del bundle).
const Analysis = lazy(() => import("./pages/Analysis"));

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/us" replace />} />
      <Route element={<Layout />}>
        <Route path="/:market" element={<Dashboard />} />
        <Route path="/:market/:symbol" element={<StockDetail />} />
        <Route
          path="/:market/:symbol/analisis"
          element={
            <Suspense fallback={<p className="text-slate-500">Cargando analisis...</p>}>
              <Analysis />
            </Suspense>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/us" replace />} />
    </Routes>
  );
}
