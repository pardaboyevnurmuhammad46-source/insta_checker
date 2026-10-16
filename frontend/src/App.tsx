import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ToastProvider } from './context/ToastContext';
import { Layout } from './components/Layout';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { UsersPage } from './pages/UsersPage';
import { LinksPage } from './pages/LinksPage';
import { PostsPage } from './pages/PostsPage';
import { PrizesPage } from './pages/PrizesPage';
import { DataDeletionsPage } from './pages/DataDeletionsPage';

const ProtectedLayout: React.FC = () => {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <Layout />;
};

export const App: React.FC = () => {
  return (
    <ToastProvider>
      <AuthProvider>
        <BrowserRouter basename="/panel">
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<ProtectedLayout />}>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/users" element={<UsersPage />} />
              <Route path="/links" element={<LinksPage />} />
              <Route path="/posts" element={<PostsPage />} />
              <Route path="/prizes" element={<PrizesPage />} />
              <Route path="/deletions" element={<DataDeletionsPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ToastProvider>
  );
};

export default App;
