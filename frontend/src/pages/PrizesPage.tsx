import React, { useEffect, useState, useCallback } from 'react';
import { apiClient } from '../api/client';
import type { Prize, PaginatedResponse } from '../types';
import { Pagination } from '../components/Pagination';
import { useToast } from '../context/ToastContext';
import { Award } from 'lucide-react';

export const PrizesPage: React.FC = () => {
  const [prizes, setPrizes] = useState<Prize[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  const { showToast } = useToast();

  const fetchPrizes = useCallback(async () => {
    try {
      setLoading(true);
      const response = await apiClient.get<PaginatedResponse<Prize>>(`/api/prizes/?page=${page}`);
      setPrizes(response.data.results);
      setTotalCount(response.data.count);
    } catch {
      showToast('Sovrinlarni yuklashda xatolik', 'error');
    } finally {
      setLoading(false);
    }
  }, [page, showToast]);

  useEffect(() => {
    fetchPrizes();
  }, [fetchPrizes]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Sovrinlar Tarixi</h1>
        <p className="text-sm text-slate-500 mt-1">Koʻrishlar soni marrasiga yetganda berilgan sovrinlar</p>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm text-left">
            <thead className="bg-slate-50 text-slate-600 font-semibold uppercase text-xs tracking-wider">
              <tr>
                <th className="px-6 py-3">ID</th>
                <th className="px-6 py-3">Foydalanuvchi</th>
                <th className="px-6 py-3">Post ID</th>
                <th className="px-6 py-3">Sovrin Marrasi (Milestone)</th>
                <th className="px-6 py-3">Yuborilgan Vaqt</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-slate-400">
                    Yuklanmoqda...
                  </td>
                </tr>
              ) : prizes.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-slate-500">
                    Sovrinlar hali berilmagan
                  </td>
                </tr>
              ) : (
                prizes.map((p) => (
                  <tr key={p.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-4 font-mono text-xs text-slate-500">{p.id}</td>
                    <td className="px-6 py-4 font-medium text-slate-900">{p.user_name}</td>
                    <td className="px-6 py-4 font-mono text-xs text-slate-600">#{p.post}</td>
                    <td className="px-6 py-4">
                      <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-amber-50 text-amber-800 text-xs font-semibold rounded-full border border-amber-200">
                        <Award size={14} className="text-amber-500" />
                        {p.milestone.toLocaleString()} koʻrish
                      </span>
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                      {new Date(p.sent_at).toLocaleString()}
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
