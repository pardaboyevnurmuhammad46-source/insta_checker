import React, { useEffect, useState, useCallback } from 'react';
import { apiClient } from '../api/client';
import type { DataDeletionRequest, PaginatedResponse } from '../types';
import { Pagination } from '../components/Pagination';
import { useToast } from '../context/ToastContext';

export const DataDeletionsPage: React.FC = () => {
  const [requests, setRequests] = useState<DataDeletionRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  const { showToast } = useToast();

  const fetchRequests = useCallback(async () => {
    try {
      setLoading(true);
      const response = await apiClient.get<PaginatedResponse<DataDeletionRequest>>(`/api/data-deletions/?page=${page}`);
      setRequests(response.data.results);
      setTotalCount(response.data.count);
    } catch {
      showToast('Soʻrovlarni yuklashda xatolik', 'error');
    } finally {
      setLoading(false);
    }
  }, [page, showToast]);

  useEffect(() => {
    fetchRequests();
  }, [fetchRequests]);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">Completed</span>;
      case 'failed':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-100 text-rose-800">Failed</span>;
      default:
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800">Pending</span>;
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Maʼlumotlarni Oʻchirish Soʻrovlari</h1>
        <p className="text-sm text-slate-500 mt-1">Meta (Instagram) orqali kelib tushgan foydalanuvchi maʼlumotlarini oʻchirish soʻrovlari</p>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm text-left">
            <thead className="bg-slate-50 text-slate-600 font-semibold uppercase text-xs tracking-wider">
              <tr>
                <th className="px-6 py-3">Tasdiq kodi (Confirmation Code)</th>
                <th className="px-6 py-3">Meta User ID</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3">Soʻralgan Vaqt</th>
                <th className="px-6 py-3">Tafsilotlar</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-slate-400">
                    Yuklanmoqda...
                  </td>
                </tr>
              ) : requests.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-slate-500">
                    Soʻrovlar mavjud emas
                  </td>
                </tr>
              ) : (
                requests.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-4 font-mono text-xs text-indigo-600 font-medium">
                      {r.confirmation_code}
                    </td>
                    <td className="px-6 py-4 font-mono text-xs text-slate-700">{r.user_id}</td>
                    <td className="px-6 py-4">{getStatusBadge(r.status)}</td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                      {new Date(r.requested_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500 max-w-xs truncate">
                      {r.details || '—'}
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
    </div>
  );
};
