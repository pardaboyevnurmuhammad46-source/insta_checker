import React, { useState, useEffect } from 'react';
import { apiClient } from '../../api/client';
import type { Prize, PaginatedResponse } from '../../types';
import { formatDate } from '../../utils/format';
import { Award, Sparkles, CheckCircle, Calendar } from 'lucide-react';

export const UserPrizesPage: React.FC = () => {
  const [prizes, setPrizes] = useState<Prize[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchPrizes = async () => {
      try {
        setLoading(true);
        const res = await apiClient.get<PaginatedResponse<Prize>>('/api/me/prizes/');
        setPrizes(res.data.results || []);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    };

    fetchPrizes();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 bg-slate-800 rounded w-48" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-44 bg-slate-800 rounded-2xl" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
          Mening Prizlarim
        </h1>
        <p className="text-slate-400 text-sm mt-1">
          Instagram koʻrishlar soni marralariga erishganingiz uchun taqdim etilgan sovrinlar
        </p>
      </div>

      {prizes.length === 0 ? (
        <div className="bg-slate-950 p-12 rounded-2xl border border-slate-800 text-center space-y-3">
          <div className="w-16 h-16 bg-slate-900 rounded-full flex items-center justify-center mx-auto text-amber-500/50 border border-slate-800">
            <Award size={32} />
          </div>
          <h3 className="text-lg font-semibold text-white">Hozircha sovrinlar mavjud emas</h3>
          <p className="text-sm text-slate-400 max-w-md mx-auto">
            Reels videongiz 500, 1000 yoki 5000 koʻrishlar soniga yetganda avtomatik ravishda sovrin beriladi.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {prizes.map((prize) => (
            <div
              key={prize.id}
              className="bg-gradient-to-b from-slate-950 to-slate-900/90 rounded-2xl p-6 border border-amber-500/20 shadow-lg relative overflow-hidden flex flex-col justify-between"
            >
              <div className="absolute top-0 right-0 w-32 h-32 bg-amber-500/5 rounded-full blur-2xl pointer-events-none" />

              <div>
                <div className="flex items-center justify-between mb-4">
                  <span className="p-3 bg-amber-500/10 text-amber-400 rounded-xl border border-amber-500/30">
                    <Award size={24} />
                  </span>
                  <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800">
                    <CheckCircle size={12} /> Taqdim etilgan
                  </span>
                </div>

                <div className="space-y-1">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-amber-400 uppercase tracking-wider">
                    <Sparkles size={13} />
                    <span>Marra Bajarildi</span>
                  </div>
                  <h3 className="text-2xl font-bold text-white tracking-tight">
                    {prize.milestone.toLocaleString()} koʻrish
                  </h3>
                  <p className="text-xs text-slate-400 pt-1">
                    Post #{prize.post} uchun marra muvaffaqiyatli zabt etildi!
                  </p>
                </div>
              </div>

              <div className="mt-6 pt-4 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-500">
                <span className="inline-flex items-center gap-1">
                  <Calendar size={13} />
                  <span>{formatDate(prize.sent_at)}</span>
                </span>
                <span className="font-mono text-slate-400">ID #{prize.id}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
