import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ToastProvider } from './context/ToastContext';
import { AdminLayout } from './components/AdminLayout';
import { UserLayout } from './components/UserLayout';
import { LoginPage } from './pages/LoginPage';

// User Pages
import { UserDashboardPage } from './pages/user/UserDashboardPage';
import { UserVideoPage } from './pages/user/UserVideoPage';
import { UserPostsPage } from './pages/user/UserPostsPage';
import { UserPrizesPage } from './pages/user/UserPrizesPage';
import { UserProfilePage } from './pages/user/UserProfilePage';

// Admin Pages
import { AdminDashboardPage } from './pages/admin/AdminDashboardPage';
import { AdminUsersPage } from './pages/admin/AdminUsersPage';
import { AdminUserDetailPage } from './pages/admin/AdminUserDetailPage';
import { AdminVideosPage } from './pages/admin/AdminVideosPage';
import { AdminPostsPage } from './pages/admin/AdminPostsPage';
import { LinksPage } from './pages/LinksPage';
import { PrizesPage } from './pages/PrizesPage';
import { DataDeletionsPage } from './pages/DataDeletionsPage';

const RootRedirect: React.FC = () => {
  const { isAuthenticated, role, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900 text-slate-300 text-sm">
        Yuklanmoqda...
      </div>
    );
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  if (role === 'admin') {
    return <Navigate to="/admin-panel" replace />;
  }
  return <Navigate to="/app" replace />;
};

const UserProtectedLayout: React.FC = () => {
  const { isAuthenticated, role, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900 text-slate-300 text-sm">
        Yuklanmoqda...
      </div>
    );
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  if (role === 'admin') {
    return <Navigate to="/admin-panel" replace />;
  }
  return <UserLayout />;
};

const AdminProtectedLayout: React.FC = () => {
  const { isAuthenticated, role, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900 text-slate-300 text-sm">
        Yuklanmoqda...
      </div>
    );
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  if (role !== 'admin') {
    return <Navigate to="/app" replace />;
  }
  return <AdminLayout />;
};

export const App: React.FC = () => {
  return (
    <ToastProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<RootRedirect />} />

            {/* User panel routes (/app/...) */}
            <Route element={<UserProtectedLayout />}>
              <Route path="/app" element={<UserDashboardPage />} />
              <Route path="/app/video" element={<UserVideoPage />} />
              <Route path="/app/posts" element={<UserPostsPage />} />
              <Route path="/app/prizes" element={<UserPrizesPage />} />
              <Route path="/app/profile" element={<UserProfilePage />} />
            </Route>

            {/* Admin panel routes (/admin-panel/...) */}
            <Route element={<AdminProtectedLayout />}>
              <Route path="/admin-panel" element={<AdminDashboardPage />} />
              <Route path="/admin-panel/users" element={<AdminUsersPage />} />
              <Route path="/admin-panel/users/:id" element={<AdminUserDetailPage />} />
              <Route path="/admin-panel/videos" element={<AdminVideosPage />} />
              <Route path="/admin-panel/posts" element={<AdminPostsPage />} />
              <Route path="/admin-panel/links" element={<LinksPage />} />
              <Route path="/admin-panel/prizes" element={<PrizesPage />} />
              <Route path="/admin-panel/deletions" element={<DataDeletionsPage />} />
            </Route>

            {/* Fallback */}
            <Route path="*" element={<RootRedirect />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ToastProvider>
  );
};

export default App;
