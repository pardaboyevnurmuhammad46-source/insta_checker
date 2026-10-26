import React, { useState, useEffect } from 'react';
import { apiClient } from '../../api/client';
import type { Prize, PaginatedResponse } from '../../types';
import { formatDate } from '../../utils/format';
import { Award, Sparkles, CheckCircle, Calendar, Gift, Lock } from 'lucide-react';

export const UserPrizesPage: React.FC = () => {
  const [prizes, setPrizes] = useState<Prize[]>([]);
  const [loading, setLoading] = useState(true);

  const milestones = [500, 1000, 5000, 10000, 50000, 100000];

  useEffect(() => {
    const fetchPrizes = async () => {
      try {
        setLoading(true);
        const res = await apiClient.get<PaginatedResponse<Prize>>('/api/me/prizes/');
        setPrizes(res.data.results || []);
      } catch {
      } finally {
        setLoading(false);
      }
    };
    fetchPrizes();
  }, []);

  if (loading) {
    return <div className="animate-pulse space-y-6"><div className="h-8 bg-slate-900 rounded w-48" /><div className="h-44 bg-slate-900 rounded-2xl" /></div>;
  }

  // Calculate highest achieved for the roadmap
  const highestMilestone = prizes.length > 0 ? Math.max(...prizes.map(p => p.milestone)) : 0;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
          Mening Prizlarim
        </h1>
        <p className="text-slate-400 text-sm mt-1">
          Ko'rishlar marrasiga erishilganda beriladigan maxsus sovg'alar
        </p>
      </div>

      {/* Roadmap visualization */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 overflow-x-auto">
        <h3 className="text-white font-bold mb-6 flex items-center gap-2">
           <Gift className="text-pink-400" size={18} /> Sovrinlar Yo'l Xaritasi
        </h3>
        <div className="flex items-center min-w-max pb-4">
           {milestones.map((m, idx) => {
             const achieved = m <= highestMilestone;
             const isNext = !achieved && (idx === 0 || milestones[idx-1] <= highestMilestone);
             return (
               <React.Fragment key={m}>
                 <div className="flex flex-col items-center relative">
                   <div className={`w-12 h-12 rounded-full flex items-center justify-center border-4 z-10 ${achieved ? 'bg-amber-400 border-amber-900 text-slate-900' : isNext ? 'bg-slate-800 border-amber-500 text-amber-500 shadow-[0_0_15px_rgba(245,158,11,0.3)]' : 'bg-slate-900 border-slate-700 text-slate-600'}`}>
                     {achieved ? <CheckCircle size={20} /> : isNext ? <Sparkles size={20} /> : <Lock size={18} />}
                   </div>
                   <span className={`text-xs font-bold mt-2 ${achieved ? 'text-amber-400' : isNext ? 'text-white' : 'text-slate-500'}`}>
                     {m >= 1000 ? `${m/1000}k` : m}
                   </span>
                 </div>
                 {idx < milestones.length - 1 && (
                   <div className={`w-16 h-1 mx-2 rounded-full ${achieved ? 'bg-amber-400/50' : 'bg-slate-800'}`}></div>
                 )}
               </React.Fragment>
             );
           })}
        </div>
      </div>

      {prizes.length === 0 ? (
        <div className="bg-slate-950 p-12 rounded-2xl border border-slate-800 text-center space-y-3">
          <div className="w-16 h-16 bg-slate-900 rounded-full flex items-center justify-center mx-auto text-amber-500/50 border border-slate-800">
            <Award size={32} />
          </div>
          <h3 className="text-lg font-semibold text-white">Hozircha sovrinlar mavjud emas</h3>
          <p className="text-sm text-slate-400 max-w-md mx-auto">
            Birinchi marra — 500 ko'rish. Reels videongiz shu marraga yetganda avtomatik sovrin beriladi.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {prizes.map((prize) => (
            <div
              key={prize.id}
              className="bg-gradient-to-b from-slate-900 to-slate-950 rounded-2xl p-6 border border-amber-500/30 shadow-lg relative overflow-hidden flex flex-col justify-between group hover:border-amber-500/50 transition"
            >
              <div className="absolute -top-10 -right-10 w-32 h-32 bg-amber-500/10 rounded-full blur-2xl pointer-events-none group-hover:bg-amber-500/20 transition" />

              <div>
                <div className="flex items-center justify-between mb-4">
                  <span className="p-2.5 bg-amber-500/10 text-amber-400 rounded-xl border border-amber-500/20">
                    <Award size={24} />
                  </span>
                  <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    <CheckCircle size={14} /> Tasdiqlangan
                  </span>
                </div>

                <div className="space-y-1">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-amber-400 uppercase tracking-wider">
                    <Sparkles size={13} />
                    <span>Marra Bajarildi</span>
                  </div>
                  <h3 className="text-3xl font-black text-white tracking-tight">
                    {prize.milestone.toLocaleString()} <span className="text-sm font-normal text-slate-400">koʻrish</span>
                  </h3>
                </div>
              </div>

              <div className="mt-6 pt-4 border-t border-slate-800 flex items-center justify-between text-xs font-mono">
                <span className="text-slate-500 inline-flex items-center gap-1.5">
                  <Calendar size={14} /> {formatDate(prize.sent_at)}
                </span>
                <span className="text-indigo-400 bg-indigo-500/10 px-2 py-1 rounded border border-indigo-500/20">
                  KOD: {prize.post_code || 'Noma\'lum'}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
