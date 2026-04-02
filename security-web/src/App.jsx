import './App.css';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import ForgotPassword from './pages/ForgetPassword';

function App() {
  // Токен байгаа эсэхийг шалгах
  const isAuthenticated = !!localStorage.getItem('token');

  return (
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

        {/* 2. НУУЦ ҮГ СЭРГЭЭХ ЗАМЫГ ЭНД НЭМЭВ */}
        <Route 
          path="/forgot-password" 
          element={isAuthenticated ? <Navigate to="/dashboard" /> : <ForgotPassword />} 
        />

        <Route 
          path="/dashboard" 
          element={isAuthenticated ? <Dashboard /> : <Navigate to="/login" />} 
        />

        {/* Бүртгэлгүй хаяг орвол Landing руу буцна */}
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Router>
  );
}

export default App;