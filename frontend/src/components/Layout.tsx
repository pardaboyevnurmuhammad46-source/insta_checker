import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  LayoutDashboard,
  Users,
  Link2,
  Video,
  Award,
  ShieldAlert,
  LogOut,
  Menu,
  X,
} from 'lucide-react';

export const Layout: React.FC = () => {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const navItems = [
    { name: 'Dashboard', path: '/', icon: LayoutDashboard },
    { name: 'Foydalanuvchilar', path: '/users', icon: Users },
    { name: 'Unikal Linklar', path: '/links', icon: Link2 },
    { name: 'Postlar (Reels)', path: '/posts', icon: Video },
    { name: 'Sovrinlar', path: '/prizes', icon: Award },
    { name: 'Maʼlumot oʻchirish', path: '/deletions', icon: ShieldAlert },
  ];

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col md:flex-row">
      {/* Mobile Header */}
      <div className="md:hidden bg-slate-900 text-white flex items-center justify-between p-4 sticky top-0 z-40">
        <div className="font-bold text-lg tracking-wide flex items-center gap-2">
          <span className="text-pink-500">📸</span> InstaChecker
        </div>
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="p-1 rounded-md hover:bg-slate-800"
        >
          {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {/* Sidebar for Desktop & Mobile drawer */}
      <div
        className={`${
          mobileMenuOpen ? 'block' : 'hidden'
        } md:block md:w-64 bg-slate-900 text-slate-300 flex-shrink-0 flex flex-col justify-between fixed md:static inset-0 z-30 md:z-auto top-14 md:top-0`}
      >
        <div className="p-4">
          <div className="hidden md:flex items-center gap-2 font-bold text-xl text-white mb-8 px-2 tracking-wide">
            <span className="text-pink-500">📸</span> InstaChecker
          </div>

          <nav className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  end={item.path === '/'}
                  onClick={() => setMobileMenuOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                      isActive
                        ? 'bg-indigo-600 text-white'
                        : 'text-slate-400 hover:text-white hover:bg-slate-800'
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

        <div className="p-4 border-t border-slate-800">
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-rose-400 hover:text-rose-300 hover:bg-slate-800 transition-colors"
          >
            <LogOut size={18} />
            <span>Chiqish</span>
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        <main className="flex-1 p-4 md:p-8 max-w-7xl w-full mx-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
