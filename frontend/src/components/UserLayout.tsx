import React, { useState, useEffect } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { apiClient } from '../api/client';
import type { Notification } from '../types';
import { formatDate } from '../utils/format';
import {
  LayoutDashboard,
  Film,
  Video as VideoIcon,
  Award,
  User as UserIcon,
  LogOut,
  Menu,
  X,
  Bell,
  CheckCheck,
} from 'lucide-react';

export const UserLayout: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [loadingNotifs, setLoadingNotifs] = useState(false);

  const fetchNotifications = async () => {
    try {
      setLoadingNotifs(true);
      const res = await apiClient.get('/api/me/notifications/');
      setNotifications(res.data.results || []);
      setUnreadCount(res.data.unread_count || 0);
    } catch {
      // ignore
    } finally {
      setLoadingNotifs(false);
    }
  };

  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleMarkAllRead = async () => {
    try {
      await apiClient.post('/api/me/notifications/read/');
      setUnreadCount(0);
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    } catch {
      // ignore
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const navItems = [
    { name: 'Bosh sahifa', path: '/app', icon: LayoutDashboard },
    { name: 'Mening videom', path: '/app/video', icon: Film },
    { name: 'Postlarim', path: '/app/posts', icon: VideoIcon },
    { name: 'Prizlarim', path: '/app/prizes', icon: Award },
    { name: 'Profil', path: '/app/profile', icon: UserIcon },
  ];

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col md:flex-row">
      {/* Mobile Top Header */}
      <div className="md:hidden bg-slate-950 text-white flex items-center justify-between p-4 sticky top-0 z-40 border-b border-slate-800">
        <div className="font-bold text-lg tracking-wide flex items-center gap-2">
          <span className="text-pink-500">📸</span> InstaChecker
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setNotifOpen(!notifOpen)}
            className="p-2 rounded-lg bg-slate-800 text-slate-300 relative"
          >
            <Bell size={20} />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 bg-rose-600 text-white text-[10px] font-bold rounded-full w-5 h-5 flex items-center justify-center">
                {unreadCount}
              </span>
            )}
          </button>
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-2 rounded-lg bg-slate-800 text-slate-300"
          >
            {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
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
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
              User
            </span>
          </div>

          <nav className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  end={item.path === '/app'}
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
            <span className="truncate">{user?.username || 'Foydalanuvchi'}</span>
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
        {/* Desktop Top Navbar */}
        <header className="hidden md:flex items-center justify-between px-8 py-4 bg-slate-950/80 backdrop-blur border-b border-slate-800 sticky top-0 z-20">
          <div>
            <h2 className="text-sm font-medium text-slate-400">
              Xush kelibsiz, <span className="text-white font-semibold">{user?.username}</span>
            </h2>
          </div>

          <div className="relative">
            <button
              onClick={() => setNotifOpen(!notifOpen)}
              className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-300 hover:text-white hover:bg-slate-800 transition relative"
              title="Bildirishnomalar"
            >
              <Bell size={18} />
              {unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 bg-rose-600 text-white text-[10px] font-bold rounded-full w-5 h-5 flex items-center justify-center animate-pulse">
                  {unreadCount}
                </span>
              )}
            </button>

            {/* Notification Dropdown */}
            {notifOpen && (
              <div className="absolute right-0 mt-2 w-80 bg-slate-950 border border-slate-800 rounded-xl shadow-2xl z-50 overflow-hidden">
                <div className="p-3 border-b border-slate-800 flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-200">Bildirishnomalar</span>
                  {unreadCount > 0 && (
                    <button
                      onClick={handleMarkAllRead}
                      className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1"
                    >
                      <CheckCheck size={14} /> Barchasi o'qildi
                    </button>
                  )}
                </div>

                <div className="max-h-80 overflow-y-auto divide-y divide-slate-800/50">
                  {loadingNotifs && (
                    <div className="p-4 text-center text-xs text-slate-500">Yuklanmoqda...</div>
                  )}
                  {!loadingNotifs && notifications.length === 0 && (
                    <div className="p-4 text-center text-xs text-slate-500">Bildirishnomalar yo'q</div>
                  )}
                  {notifications.map((n) => (
                    <div
                      key={n.id}
                      className={`p-3 text-xs transition ${
                        n.is_read ? 'bg-slate-950 text-slate-400' : 'bg-slate-900/80 text-slate-200 font-medium'
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span
                          className={`w-2 h-2 rounded-full ${
                            n.kind === 'prize' ? 'bg-amber-400' : 'bg-indigo-400'
                          }`}
                        />
                        <span className="text-[10px] uppercase font-bold text-slate-400">
                          {n.kind === 'prize' ? 'Sovrin' : 'Tizim'}
                        </span>
                        <span className="text-[10px] text-slate-500 ml-auto">
                          {formatDate(n.created_at)}
                        </span>
                      </div>
                      <p>{n.message}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </header>

        <main className="flex-1 p-4 md:p-8 max-w-7xl w-full mx-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
