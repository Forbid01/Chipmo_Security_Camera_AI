import './App.css';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import ErrorBoundary from './components/ErrorBoundary';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Register from './pages/Register';
import SignupPage from './pages/Onboarding/SignupPage';
import VerifyPage from './pages/Onboarding/VerifyPage';
import PlanPage from './pages/Onboarding/PlanPage';
import ReadyPage from './pages/Onboarding/ReadyPage';
import ConnectCamerasPage from './pages/Onboarding/ConnectCamerasPage';
import DownloadInstallerPage from './pages/Onboarding/DownloadInstallerPage';
import Dashboard from './pages/Dashboard';
import DashboardAdmin from './pages/DashboardAdmin';
import Settings from './pages/Settings';
import MyCameras from './pages/MyCameras';
import MyStores from './pages/MyStores';
import ForgotPassword from './pages/ForgetPassword';
import NotFound from './pages/NotFound';

function App() {
  const token = localStorage.getItem('token');
  const isAuthenticated = !!token;

  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const isSuperAdmin = user.role === 'super_admin';

  return (
    <ErrorBoundary>
    <Router>
      <Routes>
        <Route path="/" element={<Landing />} />
        
        <Route 
          path="/login" 
          element={isAuthenticated ? <Navigate to="/dashboard" /> : <Login />} 
        />
        
        <Route
          path="/register"
          element={isAuthenticated ? <Navigate to="/dashboard" /> : <Register />}
        />

        {/* Self-service onboarding wizard (T2-01..T2-06) */}
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/verify" element={<VerifyPage />} />
        <Route path="/plan" element={<PlanPage />} />
        <Route path="/ready" element={<ReadyPage />} />
        <Route path="/connect-cameras" element={<ConnectCamerasPage />} />
        <Route
          path="/install-agent"
          element={isAuthenticated ? <DownloadInstallerPage /> : <Navigate to="/login" />}
        />

        <Route 
          path="/forgot-password" 
          element={isAuthenticated ? <Navigate to="/dashboard" /> : <ForgotPassword />} 
        />

        {/* Энгийн хэрэглэгчийн Dashboard */}
        <Route
          path="/dashboard"
          element={isAuthenticated ? <Dashboard /> : <Navigate to="/login" />}
        />

        {/* Тохиргоо хуудас */}
        <Route
          path="/settings"
          element={isAuthenticated ? <Settings /> : <Navigate to="/login" />}
        />

        {/* Камерууд хуудас */}
        <Route
          path="/cameras"
          element={isAuthenticated ? <MyCameras /> : <Navigate to="/login" />}
        />

        {/* Дэлгүүрүүд хуудас */}
        <Route
          path="/stores"
          element={isAuthenticated ? <MyStores /> : <Navigate to="/login" />}
        />

        {/* 3. SUPER ADMIN CONTROL PANEL (Хамгаалалттай) */}
        <Route 
          path="/admin/control" 
          element={
            isAuthenticated && isSuperAdmin 
              ? <DashboardAdmin /> 
              : <Navigate to="/dashboard" /> 
          } 
        />

        <Route path="*" element={<NotFound />} />
      </Routes>
    </Router>
    </ErrorBoundary>
  );
}

export default App;
