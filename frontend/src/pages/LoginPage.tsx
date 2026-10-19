import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { Lock, User } from 'lucide-react';

export const LoginPage: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const { showToast } = useToast();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username || !password) {
      showToast('Iltimos barcha maydonlarni toʻldiring', 'error');
      return;
    }

    try {
      setLoading(true);
      // await login(username, password);
      // navigate('/');
      const profile = await login(username, password);
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
        showToast('Login yoki parol notoʻgʻri!', 'error');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-slate-800 rounded-2xl shadow-xl p-8 border border-slate-700">
        <div className="text-center mb-8">
          <div className="text-4xl mb-2">📸</div>
          {/* <h1 className="text-2xl font-bold text-white tracking-tight">InstaChecker Admin</h1> */}
          {/* <p className="text-slate-400 text-sm mt-1">Boshqaruv paneliga kirish</p> */}
          <h1 className="text-2xl font-bold text-white tracking-tight">InstaChecker</h1>
          <p className="text-slate-400 text-sm mt-1">Tizimga kirish (Admin va Foydalanuvchi)</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-2">
              Foydalanuvchi nomi
            </label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400">
                <User size={18} />
              </span>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="admin"
                className="w-full bg-slate-700/50 border border-slate-600 rounded-lg pl-10 pr-4 py-2.5 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-2">
              Parol
            </label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400">
                <Lock size={18} />
              </span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full bg-slate-700/50 border border-slate-600 rounded-lg pl-10 pr-4 py-2.5 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-medium py-2.5 rounded-lg shadow-md transition-colors disabled:opacity-50 text-sm"
          >
            {loading ? 'Kirilmoqda...' : 'Kirish'}
          </button>
        </form>
      </div>
    </div>
  );
};
