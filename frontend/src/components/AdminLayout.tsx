import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  LayoutDashboard,
  Users,
  Film,
  Video as VideoIcon,
  Link2,
  Award,
  ShieldAlert,
  LogOut,
  Menu,
  X,
  User as UserIcon,
} from 'lucide-react';

export const AdminLayout: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const navItems = [
    { name: 'Dashboard', path: '/admin-panel', icon: LayoutDashboard },
    { name: 'Foydalanuvchilar', path: '/admin-panel/users', icon: Users },
    { name: 'Videolar', path: '/admin-panel/videos', icon: Film },
    { name: 'Postlar (Reels)', path: '/admin-panel/posts', icon: VideoIcon },
    { name: 'Unikal Linklar', path: '/admin-panel/links', icon: Link2 },
    { name: 'Sovrinlar', path: '/admin-panel/prizes', icon: Award },
    { name: 'Maʼlumot oʻchirish', path: '/admin-panel/deletions', icon: ShieldAlert },
  ];

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col md:flex-row">
      {/* Mobile Header */}
      <div className="md:hidden bg-slate-950 text-white flex items-center justify-between p-4 sticky top-0 z-40 border-b border-slate-800">
        <div className="font-bold text-lg tracking-wide flex items-center gap-2">
          <span className="text-pink-500">📸</span> InstaChecker <span className="text-xs px-2 py-0.5 rounded bg-indigo-900/60 text-indigo-300 border border-indigo-700">Admin</span>
        </div>
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="p-1 rounded-md hover:bg-slate-800 text-slate-300"
        >
          {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {/* Sidebar for Desktop & Mobile drawer */}
      <div
        className={`${
          mobileMenuOpen ? 'block' : 'hidden'
        } md:block md:w-64 bg-slate-950 text-slate-300 flex-shrink-0 flex flex-col justify-between fixed md:static inset-0 z-30 md:z-auto top-14 md:top-0 border-r border-slate-800`}
      >
        <div className="p-4">
          <div className="hidden md:flex items-center justify-between mb-8 px-2">
            <div className="font-bold text-xl text-white tracking-wide flex items-center gap-2">
              <span className="text-pink-500">📸</span> InstaChecker
            </div>
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-indigo-950 text-indigo-400 border border-indigo-800">
              Admin
            </span>
          </div>

          <nav className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  end={item.path === '/admin-panel'}
                  onClick={() => setMobileMenuOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                      isActive
                        ? 'bg-indigo-600 text-white shadow-sm'
                        : 'text-slate-400 hover:text-white hover:bg-slate-900'
                    }`
                  }
                >
                  <Icon size={18} />
                  <span>{item.name}</span>
                </NavLink>
              );
            })}
          </nav>
        </div>

        <div className="p-4 border-t border-slate-800 space-y-3">
          <div className="flex items-center gap-3 px-2 py-1 text-xs text-slate-400">
            <UserIcon size={16} className="text-slate-500" />
            <span className="truncate">{user?.username || 'Administrator'}</span>
          </div>
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-rose-400 hover:text-rose-300 hover:bg-slate-900 transition-colors"
          >
            <LogOut size={18} />
            <span>Chiqish</span>
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto bg-slate-900">
        <main className="flex-1 p-4 md:p-8 max-w-7xl w-full mx-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
