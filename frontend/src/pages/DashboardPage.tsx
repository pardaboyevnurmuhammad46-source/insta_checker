import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import type { DashboardStats } from '../types';
import { useToast } from '../context/ToastContext';
import {
  Users,
  Link2,
  Video,
  Award,
  Eye,
  Heart,
  MessageCircle,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';

export const DashboardPage: React.FC = () => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const { showToast } = useToast();

  const fetchStats = async () => {
    try {
      const response = await apiClient.get<DashboardStats>('/api/dashboard/');
      setStats(response.data);
    } catch {
      showToast('Dashboard maʼlumotlarini yuklab boʻlmadi', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  if (!stats) {
    return <div className="text-center py-12 text-slate-500">Maʼlumot mavjud emas</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Umumiy Koʻrsatkichlar</h1>
          <p className="text-sm text-slate-500 mt-1">Har 30 soniyada avtomatik yangilanadi</p>
        </div>
        <button
          onClick={fetchStats}
          className="flex items-center gap-2 px-3 py-1.5 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 shadow-sm transition-colors"
        >
          <RefreshCw size={16} />
          <span>Yangilash</span>
        </button>
      </div>

      {/* Expiring tokens warning banner */}
      {stats.expiring_tokens_count > 0 && (
        <div className="bg-amber-50 border-l-4 border-amber-400 p-4 rounded-r-lg flex items-center gap-3">
          <AlertTriangle className="text-amber-500 flex-shrink-0" size={24} />
          <div>
            <h3 className="text-sm font-semibold text-amber-800">
              Diqqat: Token muddati tugayotgan foydalanuvchilar bor!
            </h3>
            <p className="text-xs text-amber-700 mt-0.5">
              {stats.expiring_tokens_count} ta foydalanuvchining tokeni 7 kundan kam muddatda eskiradi.
            </p>
          </div>
        </div>
      )}

      {/* Top Total Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase text-slate-500">Jami Koʻrishlar</p>
            <p className="text-2xl font-bold text-slate-900 mt-1">
              {(stats.total_metrics.total_views || 0).toLocaleString()}
            </p>
          </div>
          <div className="w-12 h-12 bg-blue-50 text-blue-600 rounded-xl flex items-center justify-center">
            <Eye size={24} />
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase text-slate-500">Jami Layklar</p>
            <p className="text-2xl font-bold text-slate-900 mt-1">
              {(stats.total_metrics.total_likes || 0).toLocaleString()}
            </p>
          </div>
          <div className="w-12 h-12 bg-rose-50 text-rose-600 rounded-xl flex items-center justify-center">
            <Heart size={24} />
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase text-slate-500">Kommentlar</p>
            <p className="text-2xl font-bold text-slate-900 mt-1">
              {(stats.total_metrics.total_comments || 0).toLocaleString()}
            </p>
          </div>
          <div className="w-12 h-12 bg-emerald-50 text-emerald-600 rounded-xl flex items-center justify-center">
            <MessageCircle size={24} />
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase text-slate-500">Berilgan Sovrinlar</p>
            <p className="text-2xl font-bold text-slate-900 mt-1">
              {stats.total_prizes.toLocaleString()}
            </p>
          </div>
          <div className="w-12 h-12 bg-amber-50 text-amber-600 rounded-xl flex items-center justify-center">
            <Award size={24} />
          </div>
        </div>
      </div>

      {/* Status Breakdown Section */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Users Card */}
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <Users className="text-indigo-600" size={20} />
            <h2 className="text-base font-bold text-slate-900">Foydalanuvchilar</h2>
          </div>
          <div className="space-y-3">
            <div className="flex justify-between items-center text-sm py-1.5 border-b border-slate-100">
              <span className="text-slate-600">Ulangan (Connected)</span>
              <span className="font-semibold text-emerald-600">
                {stats.users_by_status.connected || 0}
              </span>
            </div>
            <div className="flex justify-between items-center text-sm py-1.5 border-b border-slate-100">
              <span className="text-slate-600">Qayta ruxsat kerak (Needs Reauth)</span>
              <span className="font-semibold text-amber-600">
                {stats.users_by_status.needs_reauth || 0}
              </span>
            </div>
            <div className="flex justify-between items-center text-sm py-1.5">
              <span className="text-slate-600">Kutilmoqda (Pending)</span>
              <span className="font-semibold text-slate-500">
                {stats.users_by_status.pending || 0}
              </span>
            </div>
          </div>
        </div>

        {/* Links Card */}
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <Link2 className="text-indigo-600" size={20} />
            <h2 className="text-base font-bold text-slate-900">Unikal Linklar</h2>
          </div>
          <div className="space-y-3">
            <div className="flex justify-between items-center text-sm py-1.5 border-b border-slate-100">
              <span className="text-slate-600">Yaratilgan (Pending)</span>
              <span className="font-semibold text-amber-600">
                {stats.links_by_status.pending || 0}
              </span>
            </div>
            <div className="flex justify-between items-center text-sm py-1.5 border-b border-slate-100">
              <span className="text-slate-600">Ochilgan (Opened)</span>
              <span className="font-semibold text-blue-600">
                {stats.links_by_status.opened || 0}
              </span>
            </div>
            <div className="flex justify-between items-center text-sm py-1.5 border-b border-slate-100">
              <span className="text-slate-600">Joylandi (Posted)</span>
              <span className="font-semibold text-emerald-600">
                {stats.links_by_status.posted || 0}
              </span>
            </div>
            <div className="flex justify-between items-center text-sm py-1.5">
              <span className="text-slate-600">Xatolik (Failed)</span>
              <span className="font-semibold text-rose-600">
                {stats.links_by_status.failed || 0}
              </span>
            </div>
          </div>
        </div>

        {/* Posts Card */}
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <Video className="text-indigo-600" size={20} />
            <h2 className="text-base font-bold text-slate-900">Postlar (Reels)</h2>
          </div>
          <div className="space-y-3">
            <div className="flex justify-between items-center text-sm py-1.5 border-b border-slate-100">
              <span className="text-slate-600">Nashr etilgan (Published)</span>
              <span className="font-semibold text-emerald-600">
                {stats.posts_by_status.published || 0}
              </span>
            </div>
            <div className="flex justify-between items-center text-sm py-1.5 border-b border-slate-100">
              <span className="text-slate-600">Yuklanmoqda (Publishing)</span>
              <span className="font-semibold text-blue-600">
                {stats.posts_by_status.publishing || 0}
              </span>
            </div>
            <div className="flex justify-between items-center text-sm py-1.5 border-b border-slate-100">
              <span className="text-slate-600">Navbatda (Queued)</span>
              <span className="font-semibold text-amber-600">
                {stats.posts_by_status.queued || 0}
              </span>
            </div>
            <div className="flex justify-between items-center text-sm py-1.5">
              <span className="text-slate-600">Xatolik (Failed)</span>
              <span className="font-semibold text-rose-600">
                {stats.posts_by_status.failed || 0}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
