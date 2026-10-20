import React, { useEffect, useState, useCallback } from 'react';
import { apiClient } from '../api/client';
import type { InstagramUser, PaginatedResponse } from '../types';
import { Pagination } from '../components/Pagination';
import { useToast } from '../context/ToastContext';
import { Search, UserPlus, RefreshCw, KeyRound } from 'lucide-react';

export const UsersPage: React.FC = () => {
  const [users, setUsers] = useState<InstagramUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  // Add User Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newUserName, setNewUserName] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Refresh token button state
  const [refreshingId, setRefreshingId] = useState<number | null>(null);

  const { showToast } = useToast();

  const fetchUsers = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      params.append('page', page.toString());
      if (search) params.append('search', search);
      if (statusFilter) params.append('status', statusFilter);

      const response = await apiClient.get<PaginatedResponse<InstagramUser>>(`/api/users/?${params.toString()}`);
      setUsers(response.data.results);
      setTotalCount(response.data.count);
    } catch {
      showToast('Foydalanuvchilarni yuklashda xatolik yuz berdi', 'error');
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter, showToast]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleAddUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUserName.trim()) return;

    try {
      setSubmitting(true);
      await apiClient.post('/api/users/', { name: newUserName.trim() });
      showToast('Foydalanuvchi muvaffaqiyatli yaratildi', 'success');
      setNewUserName('');
      setIsModalOpen(false);
      fetchUsers();
    } catch {
      showToast('Foydalanuvchi yaratishda xatolik', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRefreshToken = async (userId: number) => {
    try {
      setRefreshingId(userId);
      const response = await apiClient.post(`/api/users/${userId}/refresh-token/`);
      showToast(response.data.message || 'Token yangilandi', 'success');
      fetchUsers();
    } catch (err: any) {
      const msg = err.detail || 'Tokenni yangilab boʻlmadi';
      showToast(msg, 'error');
    } finally {
      setRefreshingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Foydalanuvchilar</h1>
          <p className="text-sm text-slate-500 mt-1">Instagram hisobiga bogʻlangan barcha foydalanuvchilar</p>
        </div>
        <button
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium shadow-sm transition-colors"
        >
          <UserPlus size={16} />
          <span>Foydalanuvchi qoʻshish</span>
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400">
            <Search size={18} />
          </span>
          <input
            type="text"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Ism yoki IG User ID boʻyicha qidiruv..."
            className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div className="w-full sm:w-48">
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
          >
            <option value="">Barcha statuslar</option>
            <option value="connected">Ulangan (Connected)</option>
            <option value="needs_reauth">Qayta ruxsat kerak</option>
            <option value="pending">Kutilmoqda (Pending)</option>
          </select>
        </div>
      </div>

      {/* Users Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm text-left">
            <thead className="bg-slate-50 text-slate-600 font-semibold uppercase text-xs tracking-wider">
              <tr>
                <th className="px-6 py-3">ID</th>
                <th className="px-6 py-3">Ism</th>
                <th className="px-6 py-3">Instagram ID</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3">Token Holati</th>
                <th className="px-6 py-3">Token muddati</th>
                <th className="px-6 py-3 text-right">Amallar</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-6 py-8 text-center text-slate-400">
                    Yuklanmoqda...
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-8 text-center text-slate-500">
                    Foydalanuvchilar topilmadi
                  </td>
                </tr>
              ) : (
                users.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-4 font-mono text-xs text-slate-500">{u.id}</td>
                    <td className="px-6 py-4 font-medium text-slate-900">{u.name}</td>
                    <td className="px-6 py-4 font-mono text-xs text-slate-600">
                      {u.ig_user_id || '—'}
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          u.status === 'connected'
                            ? 'bg-emerald-100 text-emerald-800'
                            : u.status === 'needs_reauth'
                            ? 'bg-amber-100 text-amber-800'
                            : 'bg-slate-100 text-slate-800'
                        }`}
                      >
                        {u.status}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className="flex items-center gap-1.5 text-xs text-slate-600">
                        <KeyRound size={14} className={u.has_token ? 'text-emerald-500' : 'text-slate-300'} />
                        {u.has_token ? 'Mavjud' : 'Yoʻq'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                      {u.token_expires_at
                        ? new Date(u.token_expires_at).toLocaleDateString()
                        : '—'}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => handleRefreshToken(u.id)}
                        disabled={refreshingId === u.id || !u.has_token}
                        className="inline-flex items-center gap-1.5 px-3 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        <RefreshCw size={12} className={refreshingId === u.id ? 'animate-spin' : ''} />
                        <span>Yangilash</span>
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <Pagination
          currentPage={page}
          totalCount={totalCount}
          pageSize={50}
          onPageChange={(newPage) => setPage(newPage)}
        />
      </div>

      {/* Add User Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-xl max-w-md w-full p-6 shadow-xl space-y-4">
            <h2 className="text-lg font-bold text-slate-900">Yangi Foydalanuvchi</h2>
            <form onSubmit={handleAddUser} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Foydalanuvchi nomi
                </label>
                <input
                  type="text"
                  required
                  value={newUserName}
                  onChange={(e) => setNewUserName(e.target.value)}
                  placeholder="Masalan: Sardor Rahimxon"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Bekor qilish
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium disabled:opacity-50"
                >
                  {submitting ? 'Saqlanmoqda...' : 'Saqlash'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
