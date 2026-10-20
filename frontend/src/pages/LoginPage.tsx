import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { Lock, User, UserPlus, LogIn, Sparkles, CheckCircle2 } from 'lucide-react';

export const LoginPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'login' | 'register'>('login');

  // Login form state
  const [loginUsername, setLoginUsername] = useState('');
  const [loginPassword, setLoginPassword] = useState('');

  // Register form state
  const [regName, setRegName] = useState('');
  const [regUsername, setRegUsername] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regConfirmPassword, setRegConfirmPassword] = useState('');

  const [loading, setLoading] = useState(false);
  const { login, register } = useAuth();
  const { showToast } = useToast();
  const navigate = useNavigate();

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!loginUsername || !loginPassword) {
      showToast('Iltimos barcha maydonlarni toʻldiring', 'error');
      return;
    }

    try {
      setLoading(true);
      const profile = await login(loginUsername, loginPassword);
      showToast('Muvaffaqiyatli kirdingiz!', 'success');
      if (profile.role === 'admin') {
        navigate('/admin-panel');
      } else {
        navigate('/app');
      }
    } catch (err: any) {
      if (err.response?.status === 429) {
        showToast('Juda koʻp urinishlar qilindi. 1 daqiqadan soʻng qayta urining.', 'error');
      } else {
        showToast(err.response?.data?.detail || 'Login yoki parol notoʻgʻri!', 'error');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!regName.trim() || !regUsername.trim() || !regPassword) {
      showToast('Iltimos, barcha maydonlarni toʻldiring', 'error');
      return;
    }

    if (regPassword.length < 8) {
      showToast('Parol kamida 8 ta belgidan iborat boʻlishi kerak', 'error');
      return;
    }

    if (regPassword !== regConfirmPassword) {
      showToast('Kiritilgan parollar bir-biriga mos kelmadi', 'error');
      return;
    }

    try {
      setLoading(true);
      await register({
        name: regName.trim(),
        username: regUsername.trim(),
        password: regPassword,
      });
      showToast("Muvaffaqiyatli ro'yxatdan o'tdingiz! Endi Instagram hisobingizni ulang.", 'success');
      // Ro'yxatdan o'tgach darhol video va Instagram ulash sahifasiga yo'naltirish
      navigate('/app/video');
    } catch (err: any) {
      const data = err.response?.data;
      if (data?.username) {
        showToast(Array.isArray(data.username) ? data.username[0] : data.username, 'error');
      } else if (data?.password) {
        showToast(Array.isArray(data.password) ? data.password[0] : data.password, 'error');
      } else if (data?.name) {
        showToast(Array.isArray(data.name) ? data.name[0] : data.name, 'error');
      } else {
        showToast(data?.error || "Ro'yxatdan o'tishda xatolik yuz berdi", 'error');
      }
    } finally {
      setLoading(false);
    }
  };

  const fillQuickDemo = (user: string, pass: string) => {
    setLoginUsername(user);
    setLoginPassword(pass);
    showToast(`Demo hisob kiritildi: ${user}`, 'info');
  };

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-slate-800 rounded-3xl shadow-2xl p-6 sm:p-8 border border-slate-700/80 transition-all">
        {/* Header with Instagram Gradient Badge */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-tr from-amber-500 via-rose-500 to-purple-600 text-white shadow-lg shadow-rose-500/20 mb-3 text-2xl font-bold">
            📸
          </div>
          <h1 className="text-2xl font-black text-white tracking-tight">InstaChecker</h1>
          <p className="text-slate-400 text-xs mt-1">
            Instagram Reels kuzatuvi va ko'rishlar uchun sovg'alar platformasi
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="flex bg-slate-900/80 p-1 rounded-xl mb-6 border border-slate-700/50">
          <button
            type="button"
            onClick={() => setActiveTab('login')}
            className={`flex-1 py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-all ${
              activeTab === 'login'
                ? 'bg-indigo-600 text-white shadow-md'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <LogIn size={15} />
            <span>Kirish</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('register')}
            className={`flex-1 py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-all ${
              activeTab === 'register'
                ? 'bg-gradient-to-r from-rose-500 to-indigo-600 text-white shadow-md'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <UserPlus size={15} />
            <span>Ro'yxatdan o'tish</span>
          </button>
        </div>

        {/* LOGIN FORM */}
        {activeTab === 'login' && (
          <form onSubmit={handleLoginSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                Foydalanuvchi nomi
              </label>
              <div className="relative">
                <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400">
                  <User size={17} />
                </span>
                <input
                  type="text"
                  value={loginUsername}
                  onChange={(e) => setLoginUsername(e.target.value)}
                  placeholder="admin yoki bekzod"
                  className="w-full bg-slate-900/60 border border-slate-700 rounded-xl pl-10 pr-4 py-2.5 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm transition"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                Parol
              </label>
              <div className="relative">
                <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400">
                  <Lock size={17} />
                </span>
                <input
                  type="password"
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-slate-900/60 border border-slate-700 rounded-xl pl-10 pr-4 py-2.5 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm transition"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-2 bg-indigo-600 hover:bg-indigo-500 active:scale-[0.99] text-white font-semibold py-2.5 rounded-xl shadow-lg shadow-indigo-600/30 transition disabled:opacity-50 text-sm"
            >
              {loading ? 'Kirilmoqda...' : 'Tizimga kirish'}
            </button>

            {/* Quick Demo Fill Buttons */}
            <div className="pt-3 border-t border-slate-700/60">
              <span className="text-[11px] text-slate-400 block mb-2 font-medium">
                Tezkor sinov hisoblari (1-bosish bilan):
              </span>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => fillQuickDemo('admin', 'admin123')}
                  className="px-2.5 py-1.5 rounded-lg bg-slate-700/60 hover:bg-slate-700 text-slate-200 border border-slate-600/50 flex items-center justify-center gap-1 transition"
                >
                  <Sparkles size={13} className="text-amber-400" />
                  <span>Admin</span>
                </button>
                <button
                  type="button"
                  onClick={() => fillQuickDemo('bekzod', 'user123')}
                  className="px-2.5 py-1.5 rounded-lg bg-slate-700/60 hover:bg-slate-700 text-slate-200 border border-slate-600/50 flex items-center justify-center gap-1 transition"
                >
                  <User size={13} className="text-emerald-400" />
                  <span>Foydalanuvchi</span>
                </button>
              </div>
            </div>
          </form>
        )}

        {/* REGISTER FORM */}
        {activeTab === 'register' && (
          <form onSubmit={handleRegisterSubmit} className="space-y-3.5">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                Ism va Familiya
              </label>
              <input
                type="text"
                value={regName}
                onChange={(e) => setRegName(e.target.value)}
                placeholder="Masalan: Sardor Rahimov"
                className="w-full bg-slate-900/60 border border-slate-700 rounded-xl px-3.5 py-2 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-rose-500 text-sm transition"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                Foydalanuvchi nomi (Login)
              </label>
              <input
                type="text"
                value={regUsername}
                onChange={(e) => setRegUsername(e.target.value)}
                placeholder="masalan: sardor_r"
                className="w-full bg-slate-900/60 border border-slate-700 rounded-xl px-3.5 py-2 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-rose-500 text-sm transition"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                Parol (kamida 8 ta belgi)
              </label>
              <input
                type="password"
                value={regPassword}
                onChange={(e) => setRegPassword(e.target.value)}
                placeholder="Parol kiriting"
                className="w-full bg-slate-900/60 border border-slate-700 rounded-xl px-3.5 py-2 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-rose-500 text-sm transition"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                Parolni tasdiqlash
              </label>
              <input
                type="password"
                value={regConfirmPassword}
                onChange={(e) => setRegConfirmPassword(e.target.value)}
                placeholder="Parolni qayta kiriting"
                className="w-full bg-slate-900/60 border border-slate-700 rounded-xl px-3.5 py-2 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-rose-500 text-sm transition"
              />
            </div>

            <div className="p-3 bg-gradient-to-r from-purple-900/30 to-rose-900/30 rounded-xl border border-rose-500/20 text-[11px] text-slate-300 flex items-start gap-2">
              <CheckCircle2 size={16} className="text-emerald-400 shrink-0 mt-0.5" />
              <span>
                Ro'yxatdan o'tgach, hisobingizga <strong>Instagram</strong> akkauntingizni ulab, videoni Reels qilib joylashingiz mumkin bo'ladi.
              </span>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-2 bg-gradient-to-r from-rose-500 via-purple-600 to-indigo-600 hover:opacity-90 active:scale-[0.99] text-white font-semibold py-2.5 rounded-xl shadow-lg shadow-rose-500/20 transition disabled:opacity-50 text-sm"
            >
              {loading ? "Ro'yxatdan o'tkazilmoqda..." : "Ro'yxatdan o'tish"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
};
