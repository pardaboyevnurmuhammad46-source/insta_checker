import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { apiClient } from '../../api/client';
import { Lock, KeyRound, Shield, CheckCircle2, Loader2 } from 'lucide-react';

export const UserProfilePage: React.FC = () => {
  const { user } = useAuth();
  const { showToast } = useToast();

  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!oldPassword || !newPassword) {
      showToast('Barcha maydonlarni toʻldiring', 'error');
      return;
    }

    if (newPassword.length < 6) {
      showToast('Yangi parol kamida 6 belgidan iborat boʻlishi kerak', 'error');
      return;
    }

    if (newPassword !== confirmPassword) {
      showToast('Yangi parollar bir-biriga mos kelmadi', 'error');
      return;
    }

    try {
      setSubmitting(true);
      const res = await apiClient.post('/api/change-password/', {
        old_password: oldPassword,
        new_password: newPassword,
      });
      showToast(res.data.message || 'Parol muvaffaqiyatli almashtirildi!', 'success');
      setOldPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: any) {
      showToast(err.detail || 'Parolni oʻzgartirishda xatolik yuz berdi', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-8 max-w-2xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
          Mening Profilim
        </h1>
        <p className="text-slate-400 text-sm mt-1">
          Shaxsiy hisob ma'lumotlari va xavfsizlik sozlamalari
        </p>
      </div>

      {/* Account Info Card */}
      <div className="bg-slate-950 p-6 rounded-2xl border border-slate-800 shadow-sm space-y-4">
        <div className="flex items-center gap-3 pb-4 border-b border-slate-800">
          <div className="w-12 h-12 rounded-full bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 flex items-center justify-center font-bold text-lg">
            {user?.username?.charAt(0).toUpperCase()}
          </div>
          <div>
            <h3 className="text-base font-semibold text-white">{user?.username}</h3>
            <span className="text-xs text-slate-400 capitalize inline-flex items-center gap-1">
              <Shield size={12} className="text-emerald-400" />
              <span>Rol: {user?.role === 'admin' ? 'Administrator' : 'Foydalanuvchi'}</span>
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
          <div className="p-3 rounded-xl bg-slate-900 border border-slate-800/80">
            <span className="text-slate-500 block mb-1">Instagram Ismi</span>
            <span className="text-slate-200 font-medium">
              {user?.instagram_user?.name || 'Biriktirilmagan'}
            </span>
          </div>
          <div className="p-3 rounded-xl bg-slate-900 border border-slate-800/80">
            <span className="text-slate-500 block mb-1">Instagram Holati</span>
            <span className="text-emerald-400 font-medium">
              {user?.instagram_user?.status === 'connected' ? 'Ulangan' : 'Ulanmagan'}
            </span>
          </div>
        </div>
      </div>

      {/* Change Password Form */}
      <div className="bg-slate-950 p-6 rounded-2xl border border-slate-800 shadow-sm">
        <div className="flex items-center gap-2 mb-6">
          <KeyRound size={20} className="text-indigo-400" />
          <h2 className="text-base font-semibold text-white">Parolni Almashtirish</h2>
        </div>

        <form onSubmit={handleChangePassword} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
              Hozirgi parol
            </label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-500">
                <Lock size={16} />
              </span>
              <input
                type="password"
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
                placeholder="••••••••"
                required
                className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
              Yangi parol
            </label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-500">
                <Lock size={16} />
              </span>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Kamida 6 belgi"
                required
                className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
              Yangi parolni tasdiqlash
            </label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-500">
                <Lock size={16} />
              </span>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••"
                required
                className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
              />
            </div>
          </div>

          <div className="pt-2">
            <button
              type="submit"
              disabled={submitting}
              className="inline-flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white font-medium py-2.5 px-6 rounded-xl transition text-sm shadow-md disabled:opacity-50"
            >
              {submitting ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  <span>Saqlanmoqda...</span>
                </>
              ) : (
                <>
                  <CheckCircle2 size={16} />
                  <span>Parolni yangilash</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
