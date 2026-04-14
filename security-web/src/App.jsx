import './App.css';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import ErrorBoundary from './components/ErrorBoundary';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import DashboardAdmin from './pages/DashboardAdmin';
import Settings from './pages/Settings';
import MyCameras from './pages/MyCameras';
import ForgotPassword from './pages/ForgetPassword';

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

        {/* 3. SUPER ADMIN CONTROL PANEL (Хамгаалалттай) */}
        <Route 
          path="/admin/control" 
          element={
            isAuthenticated && isSuperAdmin 
              ? <DashboardAdmin /> 
              : <Navigate to="/dashboard" /> 
          } 
        />

        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Router>
    </ErrorBoundary>
  );
}

export default App;