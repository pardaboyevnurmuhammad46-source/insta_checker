import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { Lock, User, UserPlus, LogIn, Camera as Instagram, Eye, EyeOff, AlertTriangle } from 'lucide-react';

export const LoginPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'login' | 'register'>('login');
  const [loginUsername, setLoginUsername] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const [regName, setRegName] = useState('');
  const [regUsername, setRegUsername] = useState('');
  const [regPassword, setRegPassword] = useState('');
  
  const [loading, setLoading] = useState(false);
  const { login, register } = useAuth();
  const { showToast } = useToast();
  const navigate = useNavigate();

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('access_token');
    if (token) {
      localStorage.setItem('access_token', token);
      navigate('/app/video');
    }
  }, [navigate]);

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!loginUsername || !loginPassword) return;
    try {
      setLoading(true);
      const profile = await login(loginUsername, loginPassword);
      if (profile.role === 'admin') navigate('/admin-panel');
      else navigate('/app');
    } catch (err: any) {
      const data = err.response?.data;
      let msg = 'Tizimga kirishda xatolik yuz berdi';
      if (data) {
        if (typeof data === 'string') msg = data;
        else if (data.detail) msg = data.detail;
        else if (data.error) msg = data.error;
        else if (data.non_field_errors) msg = Array.isArray(data.non_field_errors) ? data.non_field_errors.join(' ') : String(data.non_field_errors);
      }
      showToast(msg, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!regName || !regUsername || !regPassword) return;
    try {
      setLoading(true);
      await register({ name: regName, username: regUsername, password: regPassword });
      navigate('/app/video');
    } catch (err: any) {
      const data = err.response?.data;
      let msg = "Ro'yxatdan o'tishda xatolik yuz berdi";
      if (data) {
        if (typeof data === 'string') msg = data;
        else if (data.error) msg = data.error;
        else if (data.detail) msg = data.detail;
        else if (data.password) msg = Array.isArray(data.password) ? data.password.join(' ') : String(data.password);
        else if (data.username) msg = Array.isArray(data.username) ? data.username.join(' ') : String(data.username);
        else if (data.name) msg = Array.isArray(data.name) ? data.name.join(' ') : String(data.name);
      }
      showToast(msg, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleInstagramLogin = async () => {
    try {
      setLoading(true);
      const res = await apiClient.get('/api/auth/instagram/url/');
      if (res.data?.auth_url) {
        window.location.href = res.data.auth_url;
      } else {
        showToast("Instagram avtorizatsiya havolasini olib bo'lmadi", 'error');
      }
    } catch {
      showToast('Instagram havolasini olishda xatolik yuz berdi', 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-4 selection:bg-indigo-500/30 font-sans">
      <div className="w-full max-w-sm relative z-10">
        
        {/* Brand */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-tr from-pink-500 to-indigo-600 shadow-xl shadow-pink-500/20 text-white text-3xl mb-4 transform -rotate-6">
            📸
          </div>
          <h1 className="text-3xl font-black text-white tracking-tight">InstaChecker</h1>
          <p className="text-slate-400 text-sm mt-2">Professional reels monitoring tizimi</p>
        </div>

        {/* Card */}
        <div className="bg-slate-900 border border-slate-800 rounded-3xl shadow-2xl p-6 sm:p-8 backdrop-blur-xl">
          <div className="flex bg-slate-950 p-1.5 rounded-xl mb-6 border border-slate-800">
            <button
              type="button"
              onClick={() => setActiveTab('login')}
              className={`flex-1 py-2 rounded-lg text-sm font-bold flex justify-center items-center gap-2 transition ${activeTab === 'login' ? 'bg-indigo-600 text-white shadow' : 'text-slate-500 hover:text-slate-300'}`}
            >
              <LogIn size={16} /> Kirish
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('register')}
              className={`flex-1 py-2 rounded-lg text-sm font-bold flex justify-center items-center gap-2 transition ${activeTab === 'register' ? 'bg-slate-800 text-white shadow' : 'text-slate-500 hover:text-slate-300'}`}
            >
              <UserPlus size={16} /> Ro'yxatdan o'tish
            </button>
          </div>

          <button
            type="button"
            onClick={handleInstagramLogin}
            disabled={loading}
            className="w-full mb-6 bg-slate-800 hover:bg-slate-700 text-white flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-bold transition border border-slate-700 disabled:opacity-50"
          >
             <Instagram size={18} className="text-pink-400" />
             <span>Instagram orqali davom etish</span>
          </button>

          <div className="relative mb-6">
            <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-slate-800"></div></div>
            <div className="relative flex justify-center text-[10px] uppercase tracking-wider font-bold"><span className="bg-slate-900 px-3 text-slate-500">yoki login orqali</span></div>
          </div>

          {activeTab === 'login' ? (
            <form onSubmit={handleLoginSubmit} className="space-y-4">
              <div>
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider ml-1">Login</label>
                <div className="mt-1 relative">
                  <User size={18} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input type="text" value={loginUsername} onChange={e => setLoginUsername(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-10 pr-4 py-3 text-sm text-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none transition" />
                </div>
              </div>
              <div>
                <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider ml-1">Parol</label>
                <div className="mt-1 relative">
                  <Lock size={18} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input type={showPassword ? 'text' : 'password'} value={loginPassword} onChange={e => setLoginPassword(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-10 pr-10 py-3 text-sm text-white focus:border-indigo-500 outline-none transition" />
                  <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>
              <button type="submit" disabled={loading} className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-3 rounded-xl mt-2 transition">
                {loading ? 'Kirilmoqda...' : 'Tizimga kirish'}
              </button>
            </form>
          ) : (
            <form onSubmit={handleRegisterSubmit} className="space-y-4">
              <div>
                <input type="text" placeholder="Ism va Familiya" value={regName} onChange={e => setRegName(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm text-white outline-none focus:border-indigo-500" />
              </div>
              <div>
                <input type="text" placeholder="Login (foydalanuvchi nomi)" value={regUsername} onChange={e => setRegUsername(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm text-white outline-none focus:border-indigo-500" />
              </div>
              <div>
                <input type="password" placeholder="Parol (min 8 ta belgi)" value={regPassword} onChange={e => setRegPassword(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm text-white outline-none focus:border-indigo-500" />
              </div>
              <button type="submit" disabled={loading} className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-3 rounded-xl mt-2 transition">
                {loading ? "Ro'yxatdan o'tilmoqda..." : "Ro'yxatdan o'tish"}
              </button>
            </form>
          )}

          {/* Dev Notice */}
          <div className="mt-8 p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-[10px] text-amber-200/70 flex items-start gap-2">
             <AlertTriangle size={14} className="shrink-0 text-amber-500/50 mt-0.5" />
             <p>Test rejimi uchun: <strong>bekzod</strong> (user123) yoki <strong>admin</strong> (admin123).<br/>Haqiqiy foydalanish uchun Instagram orqali kiring.</p>
          </div>
        </div>
      </div>
    </div>
  );
};
