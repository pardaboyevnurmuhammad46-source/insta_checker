import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import type { AdminUserItem, PaginatedResponse } from '../../types';
import { formatNumber, formatDate } from '../../utils/format';
import { Pagination } from '../../components/Pagination';
import {
  Search,
  UserPlus,
  KeyRound,
  Eye,
  CheckCircle,
  AlertCircle,
  X,
  Loader2,
} from 'lucide-react';

export const AdminUsersPage: React.FC = () => {
  const { showToast } = useToast();

  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [ordering, setOrdering] = useState('-id');
  const [loading, setLoading] = useState(true);

  // Create User Modal
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [createUsername, setCreateUsername] = useState('');
  const [createPassword, setCreatePassword] = useState('');
  const [createName, setCreateName] = useState('');
  const [createIsStaff, setCreateIsStaff] = useState(false);
  const [creating, setCreating] = useState(false);

  // Reset Password Modal
  const [resetModalOpen, setResetModalOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<AdminUserItem | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [resetting, setResetting] = useState(false);

  const fetchUsers = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        page: page.toString(),
        ordering: ordering,
      });
      if (search) params.append('search', search);
      if (statusFilter) params.append('status', statusFilter);

      const res = await apiClient.get<PaginatedResponse<AdminUserItem>>(`/api/admin/users/?${params.toString()}`);
      setUsers(res.data.results || []);
      setTotalCount(res.data.count || 0);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, [page, statusFilter, ordering]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchUsers();
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createUsername || !createPassword || !createName) {
      showToast('Barcha maydonlarni toʻldiring', 'error');
      return;
    }

    try {
      setCreating(true);
      await apiClient.post('/api/admin/create-user/', {
        username: createUsername,
        password: createPassword,
        name: createName,
        is_staff: createIsStaff,
      });
      showToast('Foydalanuvchi muvaffaqiyatli yaratildi', 'success');
      setCreateModalOpen(false);
      setCreateUsername('');
      setCreatePassword('');
      setCreateName('');
      setCreateIsStaff(false);
      fetchUsers();
    } catch (err: any) {
      showToast(err.response?.data?.username?.[0] || 'Foydalanuvchi yaratishda xatolik', 'error');
    } finally {
      setCreating(false);
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUser || !newPassword) return;

    try {
      setResetting(true);
      await apiClient.post(`/api/users/${selectedUser.id}/reset-password/`, {
        new_password: newPassword,
      });
      showToast(`${selectedUser.name} paroli muvaffaqiyatli yangilandi`, 'success');
      setResetModalOpen(false);
      setNewPassword('');
    } catch (err: any) {
      showToast(err.response?.data?.error || 'Parolni tiklashda xatolik', 'error');
    } finally {
      setResetting(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'connected':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
            <CheckCircle size={11} /> Ulangan
          </span>
        );
      case 'needs_reauth':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-950 text-rose-300 border border-rose-900">
            <AlertCircle size={11} /> Qayta ulanish kerak
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-800 text-slate-400">
            Kutilmoqda
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            Foydalanuvchilar
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Barcha tizim foydalanuvchilari va ularning ko'rsatkichlari
          </p>
        </div>

        <button
          onClick={() => setCreateModalOpen(true)}
          className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2.5 rounded-xl text-sm font-semibold transition shadow-md self-start sm:self-auto"
        >
          <UserPlus size={16} />
          <span>Yangi user yaratish</span>
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-slate-950 p-4 rounded-2xl border border-slate-800 flex flex-col md:flex-row items-center justify-between gap-4">
        <form onSubmit={handleSearchSubmit} className="relative w-full md:w-80">
          <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-500">
            <Search size={16} />
          </span>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Ism yoki username bo'yicha qidirish..."
            className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </form>

        <div className="flex flex-wrap items-center gap-3 w-full md:w-auto">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">Barcha holatlar</option>
            <option value="connected">Ulangan</option>
            <option value="needs_reauth">Qayta ulanish kerak</option>
            <option value="pending">Kutilmoqda</option>
          </select>

          <select
            value={ordering}
            onChange={(e) => setOrdering(e.target.value)}
            className="bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="-id">Eng yangi</option>
            <option value="-total_views">Ko'rishlar (ko'pdan kamga)</option>
            <option value="total_views">Ko'rishlar (kamdan ko'pga)</option>
            <option value="-posts_count">Postlar soni</option>
          </select>
        </div>
      </div>

      {/* Users Table */}
      <div className="bg-slate-950 rounded-2xl border border-slate-800 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-900/80 text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-3.5 px-4">ID</th>
                <th className="py-3.5 px-4">Ism / Username</th>
                <th className="py-3.5 px-4">Holati</th>
                <th className="py-3.5 px-4">Postlar</th>
                <th className="py-3.5 px-4">Jami Ko'rishlar</th>
                <th className="py-3.5 px-4">Oxirgi Post</th>
                <th className="py-3.5 px-4 text-right">Amallar</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {loading && (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-500 text-sm">
                    Yuklanmoqda...
                  </td>
                </tr>
              )}
              {!loading && users.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-500 text-sm">
                    Foydalanuvchilar topilmadi.
                  </td>
                </tr>
              )}
              {!loading &&
                users.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-900/40 transition">
                    <td className="py-3.5 px-4 font-mono text-xs text-slate-500">#{u.id}</td>
                    <td className="py-3.5 px-4">
                      <Link
                        to={`/admin-panel/users/${u.id}`}
                        className="font-medium text-white hover:text-indigo-400 transition block"
                      >
                        {u.name}
                      </Link>
                      <span className="text-xs text-slate-500">@{u.username || 'user'}</span>
                    </td>
                    <td className="py-3.5 px-4">{getStatusBadge(u.status)}</td>
                    <td className="py-3.5 px-4 font-semibold text-white">{u.posts_count}</td>
                    <td className="py-3.5 px-4 font-semibold text-sky-400">
                      <span className="inline-flex items-center gap-1.5">
                        <Eye size={14} />
                        {formatNumber(u.total_views)}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-xs text-slate-400">
                      {formatDate(u.last_posted_at)}
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Link
                          to={`/admin-panel/users/${u.id}`}
                          className="px-2.5 py-1 rounded-lg bg-indigo-950/60 text-indigo-400 border border-indigo-800 hover:bg-indigo-900 text-xs transition"
                          title="Tafsilotlar"
                        >
                          Ko'rish
                        </Link>
                        <button
                          onClick={() => {
                            setSelectedUser(u);
                            setResetModalOpen(true);
                          }}
                          className="px-2.5 py-1 rounded-lg bg-slate-900 text-slate-300 border border-slate-800 hover:text-white hover:bg-slate-800 text-xs transition inline-flex items-center gap-1"
                          title="Parolni tiklash"
                        >
                          <KeyRound size={12} />
                          <span>Parol</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>

        <Pagination
          currentPage={page}
          totalCount={totalCount}
          onPageChange={(p) => setPage(p)}
        />
      </div>

      {/* Create User Modal */}
      {createModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md overflow-hidden shadow-2xl">
            <div className="p-5 border-b border-slate-800 flex items-center justify-between">
              <h3 className="font-semibold text-white text-base">Yangi Foydalanuvchi Yaratish</h3>
              <button
                onClick={() => setCreateModalOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleCreateUser} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                  Foydalanuvchi nomi (Username)
                </label>
                <input
                  type="text"
                  value={createUsername}
                  onChange={(e) => setCreateUsername(e.target.value)}
                  placeholder="masalan: user123"
                  required
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                  Parol
                </label>
                <input
                  type="password"
                  value={createPassword}
                  onChange={(e) => setCreatePassword(e.target.value)}
                  placeholder="Kamida 6 belgi"
                  required
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                  Ism (Instagram Profile Name)
                </label>
                <input
                  type="text"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  placeholder="masalan: Anvar Karimov"
                  required
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="is_staff"
                  checked={createIsStaff}
                  onChange={(e) => setCreateIsStaff(e.target.checked)}
                  className="rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500"
                />
                <label htmlFor="is_staff" className="text-xs text-slate-300">
                  Administrator huquqini berish (Staff / Superuser)
                </label>
              </div>

              <div className="pt-3 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setCreateModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-slate-400 hover:text-white text-sm"
                >
                  Bekor qilish
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-sm font-semibold transition disabled:opacity-50 inline-flex items-center gap-1.5"
                >
                  {creating && <Loader2 size={15} className="animate-spin" />}
                  <span>Yaratish</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Reset Password Modal */}
      {resetModalOpen && selectedUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md overflow-hidden shadow-2xl">
            <div className="p-5 border-b border-slate-800 flex items-center justify-between">
              <h3 className="font-semibold text-white text-base">
                {selectedUser.name} parolini tiklash
              </h3>
              <button
                onClick={() => setResetModalOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleResetPassword} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                  Yangi parol
                </label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Kamida 6 belgi"
                  required
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="pt-3 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setResetModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-slate-400 hover:text-white text-sm"
                >
                  Bekor qilish
                </button>
                <button
                  type="submit"
                  disabled={resetting}
                  className="px-5 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-xl text-sm font-semibold transition disabled:opacity-50 inline-flex items-center gap-1.5"
                >
                  {resetting && <Loader2 size={15} className="animate-spin" />}
                  <span>Parolni yangilash</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
