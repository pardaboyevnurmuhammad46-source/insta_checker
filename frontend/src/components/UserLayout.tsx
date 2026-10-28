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
  Bell,
  CheckCheck,
} from 'lucide-react';

export const UserLayout: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
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
    { name: 'Sovrinlarim', path: '/app/prizes', icon: Award },
    { name: 'Profil', path: '/app/profile', icon: UserIcon },
  ];

  return (
    <div className="min-h-[100dvh] bg-slate-950 text-slate-100 flex flex-col md:flex-row pb-16 md:pb-0 font-sans selection:bg-indigo-500/30">
      {/* Mobile Top Header (Fixed) */}
      <div className="md:hidden bg-slate-900/90 backdrop-blur-md text-white flex items-center justify-between px-4 py-3 sticky top-0 z-40 border-b border-slate-800 shadow-sm">
        <div className="font-black text-lg tracking-tight flex items-center gap-1.5">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-rose-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-rose-500/20 text-xs">
            📸
          </div>
          InstaChecker
        </div>
        <div className="relative">
          <button
            onClick={() => setNotifOpen(!notifOpen)}
            className="p-2 rounded-xl bg-slate-800 text-slate-300 relative transition-transform active:scale-95"
          >
            <Bell size={18} />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 bg-rose-500 text-white text-[9px] font-bold rounded-full w-4 h-4 flex items-center justify-center border-2 border-slate-900">
                {unreadCount}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Desktop Sidebar */}
      <div className="hidden md:flex w-64 bg-slate-900 flex-shrink-0 flex-col justify-between fixed inset-y-0 z-30 border-r border-slate-800/80 shadow-2xl">
        <div className="p-5">
          <div className="flex items-center justify-between mb-8 px-2">
            <div className="font-black text-xl text-white tracking-tight flex items-center gap-2">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-rose-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-rose-500/20 text-sm">
                📸
              </div>
              InstaChecker
            </div>
          </div>

          <nav className="space-y-1.5">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  end={item.path === '/app'}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3.5 py-3 rounded-xl text-sm font-semibold transition-all duration-200 ${
                      isActive
                        ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/20'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                    }`
                  }
                >
                  <Icon size={18} className="shrink-0" />
                  <span>{item.name}</span>
                </NavLink>
              );
            })}
          </nav>
        </div>

        <div className="p-5 border-t border-slate-800/80 space-y-3">
          <div className="flex items-center gap-3 px-3 py-2 bg-slate-950 rounded-xl border border-slate-800/50">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center font-bold text-xs">
              {user?.username?.charAt(0).toUpperCase()}
            </div>
            <div className="overflow-hidden">
              <p className="text-sm font-semibold text-slate-200 truncate">{user?.username}</p>
              <p className="text-[10px] text-emerald-400 font-medium capitalize">{user?.role || 'User'}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
          >
            <LogOut size={18} />
            <span>Tizimdan chiqish</span>
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 md:ml-64 relative bg-slate-950">
        {/* Desktop Top Navbar */}
        <header className="hidden md:flex items-center justify-between px-8 py-4 bg-slate-900/60 backdrop-blur-xl border-b border-slate-800/80 sticky top-0 z-20">
          <div>
            <h2 className="text-sm font-medium text-slate-400">
              Xush kelibsiz, <span className="text-white font-bold">{user?.username}</span> 👋
            </h2>
          </div>

          <div className="relative">
            <button
              onClick={() => setNotifOpen(!notifOpen)}
              className="p-2.5 rounded-xl bg-slate-800/80 border border-slate-700/50 text-slate-300 hover:text-white hover:bg-slate-700 transition relative"
            >
              <Bell size={18} />
              {unreadCount > 0 && (
                <span className="absolute -top-1.5 -right-1.5 bg-rose-500 text-white text-[10px] font-bold rounded-full w-5 h-5 flex items-center justify-center border-2 border-slate-900 shadow-sm">
                  {unreadCount}
                </span>
              )}
            </button>
          </div>
        </header>

        {/* Global Notifications Dropdown (Desktop & Mobile share this if built right, but easiest is absolute here) */}
        {notifOpen && (
          <div className="fixed md:absolute top-16 right-4 md:right-8 w-[calc(100vw-2rem)] md:w-80 bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl z-50 overflow-hidden animate-in fade-in slide-in-from-top-4 duration-200">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/50">
              <span className="text-sm font-bold text-white">Bildirishnomalar</span>
              {unreadCount > 0 && (
                <button
                  onClick={handleMarkAllRead}
                  className="text-[11px] font-semibold text-indigo-400 hover:text-indigo-300 flex items-center gap-1 bg-indigo-500/10 px-2 py-1 rounded-lg"
                >
                  <CheckCheck size={14} /> O'qildi
                </button>
              )}
            </div>
            <div className="max-h-[60vh] overflow-y-auto divide-y divide-slate-800/50">
              {loadingNotifs && (
                <div className="p-8 text-center text-xs text-slate-500 flex justify-center">
                  <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
                </div>
              )}
              {!loadingNotifs && notifications.length === 0 && (
                <div className="p-8 text-center text-xs text-slate-500">Yangi xabarlar yo'q</div>
              )}
              {notifications.map((n) => (
                <div
                  key={n.id}
                  className={`p-4 text-xs transition ${
                    n.is_read ? 'bg-slate-950/30 text-slate-400' : 'bg-slate-900 text-slate-200 font-medium'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1.5">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        n.kind === 'prize' ? 'bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.6)]' : 'bg-indigo-400'
                      }`}
                    />
                    <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                      {n.kind === 'prize' ? 'Sovrin' : 'Tizim'}
                    </span>
                    <span className="text-[10px] text-slate-500 ml-auto font-mono">
                      {formatDate(n.created_at)}
                    </span>
                  </div>
                  <p className="leading-relaxed">{n.message}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        <main className="flex-1 p-4 md:p-8 max-w-7xl w-full mx-auto pb-6">
          <Outlet />
        </main>
      </div>

      {/* Mobile Bottom Navigation (Fixed) */}
      <div className="md:hidden fixed bottom-0 left-0 right-0 bg-slate-900/95 backdrop-blur-xl border-t border-slate-800/80 z-40 pb-safe">
        <nav className="flex justify-around items-center h-16 px-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === '/app'}
                className={({ isActive }) =>
                  `flex flex-col items-center justify-center w-full h-full space-y-1 transition-colors ${
                    isActive ? 'text-indigo-400' : 'text-slate-500 hover:text-slate-300'
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <div className={`p-1.5 rounded-xl transition-all ${isActive ? 'bg-indigo-500/15' : ''}`}>
                      <Icon size={20} strokeWidth={isActive ? 2.5 : 2} />
                    </div>
                    <span className={`text-[10px] font-medium ${isActive ? 'font-bold' : ''}`}>
                      {item.name}
                    </span>
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>
      </div>
    </div>
  );
};
