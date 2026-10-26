import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../../api/client';
import type { UserSummary, Post } from '../../types';
import { formatNumber, formatDate } from '../../utils/format';
import { Eye, Heart, MessageCircle, Video as VideoIcon, Award, ArrowRight, TrendingUp, Sparkles, AlertTriangle } from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Area, AreaChart } from 'recharts';

export const UserDashboardPage: React.FC = () => {
  const [summary, setSummary] = useState<UserSummary | null>(null);
  const [recentPosts, setRecentPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState<'7' | '30'>('7');

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [sumRes, postsRes] = await Promise.all([
          apiClient.get<UserSummary>('/api/me/summary/'),
          apiClient.get(`/api/me/posts/?page_size=15&days=${timeRange}`),
        ]);
        setSummary(sumRes.data);
        // Only take active posts for chart logic to avoid 0 dips
        const activePosts = (postsRes.data.results || []).filter((p: any) => p.status !== 'deleted');
        setRecentPosts(activePosts);
      } catch (err) {
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [timeRange]);

  if (loading && !summary) {
    return <div className="animate-pulse space-y-6"><div className="h-32 bg-slate-900 rounded-2xl" /><div className="h-64 bg-slate-900 rounded-2xl" /></div>;
  }
  if (!summary) return <div className="text-center py-10 text-slate-400">Xatolik.</div>;

  const chartData = [...recentPosts].reverse().map(p => ({
    name: p.posted_at ? new Date(p.posted_at).toLocaleDateString('uz-UZ', { month: 'short', day: 'numeric' }) : '',
    views: p.views,
  }));

  const bestPost = [...recentPosts].sort((a, b) => b.views - a.views)[0];

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-black tracking-tight text-white">Xulosa</h1>
          <p className="text-slate-400 text-sm mt-1">Umumiy statistika va o'sish dinamikasi</p>
        </div>
        <Link to="/app/video" className="inline-flex items-center gap-2 bg-white text-slate-900 px-5 py-2.5 rounded-xl text-sm font-bold shadow-md hover:bg-slate-200 transition active:scale-95 w-fit">
          Videoni joylash <ArrowRight size={16} />
        </Link>
      </div>

      {/* Hero Stats Card */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-2 bg-gradient-to-br from-indigo-900/80 to-slate-900 p-6 rounded-2xl border border-indigo-500/30 flex flex-col justify-between relative overflow-hidden shadow-xl">
          <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl -z-10"></div>
          <div>
            <h3 className="text-indigo-200 text-sm font-semibold uppercase tracking-wider mb-1">Jami Ko'rishlar</h3>
            <div className="text-4xl md:text-5xl font-black text-white">{formatNumber(summary.total_views)}</div>
          </div>
          <div className="mt-6 flex gap-4 text-sm">
             <div className="flex items-center gap-1.5 text-rose-300 bg-rose-500/10 px-3 py-1.5 rounded-lg border border-rose-500/20">
               <Heart size={16} /> <span className="font-bold">{formatNumber(summary.total_likes)}</span>
             </div>
             <div className="flex items-center gap-1.5 text-emerald-300 bg-emerald-500/10 px-3 py-1.5 rounded-lg border border-emerald-500/20">
               <MessageCircle size={16} /> <span className="font-bold">{formatNumber(summary.total_comments)}</span>
             </div>
          </div>
        </div>

        {/* Milestone Card */}
        <div className="bg-slate-900 p-6 rounded-2xl border border-slate-800 flex flex-col justify-between space-y-4">
           <div>
             <div className="w-10 h-10 bg-amber-500/20 text-amber-400 rounded-xl flex items-center justify-center mb-3">
               <Award size={20} />
             </div>
             <h3 className="text-sm text-slate-400 font-medium">Keyingi sovrin marrasi</h3>
             <div className="text-2xl font-bold text-white mt-1">{formatNumber(summary.next_milestone)} <span className="text-sm font-normal text-slate-500">ko'rish</span></div>
           </div>
           
           <div>
             <div className="flex justify-between text-[10px] text-slate-400 mb-1.5 font-bold">
               <span>PROGRES</span>
               <span className="text-amber-400">{summary.progress_percent}%</span>
             </div>
             <div className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-slate-800">
                <div className="bg-gradient-to-r from-amber-600 to-amber-400 h-full rounded-full" style={{width: `${Math.max(2, summary.progress_percent || 0)}%`}}></div>
             </div>
             <p className="text-[10px] text-slate-500 mt-2">Yana {formatNumber(summary.views_remaining)} ko'rish qoldi</p>
           </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Chart */}
        <div className="lg:col-span-2 bg-slate-900 p-6 rounded-2xl border border-slate-800">
           <div className="flex items-center justify-between mb-6">
              <h3 className="font-bold text-white flex items-center gap-2">
                <TrendingUp size={18} className="text-indigo-400" /> Ko'rishlar O'sishi
              </h3>
              <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800">
                <button onClick={() => setTimeRange('7')} className={`px-3 py-1 rounded text-xs font-semibold ${timeRange === '7' ? 'bg-slate-800 text-white' : 'text-slate-400'}`}>7 kun</button>
                <button onClick={() => setTimeRange('30')} className={`px-3 py-1 rounded text-xs font-semibold ${timeRange === '30' ? 'bg-slate-800 text-white' : 'text-slate-400'}`}>30 kun</button>
              </div>
           </div>
           
           {chartData.length > 0 ? (
             <div className="h-64 w-full">
               <ResponsiveContainer width="100%" height="100%">
                 <AreaChart data={chartData} margin={{top:10, right:10, left:-20, bottom:0}}>
                   <defs>
                     <linearGradient id="colorViews" x1="0" y1="0" x2="0" y2="1">
                       <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3}/>
                       <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
                     </linearGradient>
                   </defs>
                   <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1e293b" />
                   <XAxis dataKey="name" stroke="#64748b" fontSize={10} axisLine={false} tickLine={false} />
                   <YAxis stroke="#64748b" fontSize={10} axisLine={false} tickLine={false} tickFormatter={val => formatNumber(val)} />
                   <Tooltip contentStyle={{backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px', color: '#fff'}} />
                   <Area type="monotone" dataKey="views" stroke="#818cf8" strokeWidth={3} fillOpacity={1} fill="url(#colorViews)" />
                 </AreaChart>
               </ResponsiveContainer>
             </div>
           ) : (
             <div className="h-64 flex flex-col items-center justify-center text-slate-500 text-sm gap-2">
               <AlertTriangle size={24} className="text-slate-600" />
               <p>Tanlangan davr uchun faol postlar yo'q</p>
             </div>
           )}
        </div>

        {/* Best Post */}
        <div className="bg-slate-900 p-6 rounded-2xl border border-slate-800 flex flex-col">
          <h3 className="font-bold text-white flex items-center gap-2 mb-4">
            <Sparkles size={18} className="text-amber-400" /> Eng zo'r natija
          </h3>
          
          {bestPost ? (
            <div className="flex-1 flex flex-col items-center text-center justify-center space-y-4">
               {bestPost.thumbnail_url ? (
                  <img src={bestPost.thumbnail_url} alt="Best" className="w-24 h-36 object-cover rounded-xl shadow-lg border border-slate-700" />
               ) : (
                  <div className="w-24 h-36 bg-slate-800 rounded-xl flex items-center justify-center text-slate-600 border border-slate-700">
                    <VideoIcon size={32} />
                  </div>
               )}
               <div>
                 <p className="text-[10px] uppercase font-bold text-slate-500 mb-1">Kod: <span className="text-amber-400">{bestPost.code || 'Yo\'q'}</span></p>
                 <h4 className="text-2xl font-black text-white">{formatNumber(bestPost.views)} <span className="text-sm font-normal text-slate-400">ko'rish</span></h4>
               </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-xs text-slate-500 text-center">Hali post joylanmagan.</div>
          )}
        </div>
      </div>
    </div>
  );
};
